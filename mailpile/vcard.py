import random
from mailpile.util import *
import httplib
import base64
from lxml import etree


class VCardLine(dict):
    """
    This class represents a single line in a VCard file. It knows how
    to parse the most common "structured" lines into attributes and
    values and also convert a name, attributes and value into a properly
    encoded/escaped VCard line.

    For specific values, the object can be initialized directly.
    >>> vcl = VCardLine(name='fn', value='The Dude')
    >>> vcl.as_vcardline()
    'FN:The Dude'

    Alternately, the name and value attributes can be set after the fact.
    >>> vcl.value = 'Lebowski'
    >>> vcl.as_vcardline()
    'FN:Lebowski'

    The object's str() and unicode() methods return the value.
    >>> print vcl
    Lebowski

    VCardLine objects can also be initialized by passing in a line of VCard
    data, which will then be parsed:
    >>> vcl = VCardLine('FN;TYPE=Nickname:Bjarni')
    >>> vcl.name
    u'fn'
    >>> vcl.value
    u'Bjarni'
    >>> vcl.get('type')
    u'Nickname'

    Note that the as_vcardline() method may return more than one actual line
    of text, as RFC6350 mandates that lines over 75 characters be wrapped:
    >>> print VCardLine(name='bogus', value=('B' * 100)+'C').as_vcardline()
    BOGUS:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
     BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBC
    """
    QUOTE_MAP = {
        "\\": "\\\\",
        ",": "\\,",
        ";": "\\;",
        "\n": "\\n",
    }
    QUOTE_RMAP = dict([(v, k) for k, v in QUOTE_MAP.iteritems()])

    def __init__(self, line=None, name=None, value=None):
        self.name = name
        self.value = value
        self.attr = []
        if line is not None:
            self.parse(line)

    def parse(self, line):
        self.name, self.attr, self.value = self.ParseLine(line)
        for key in self.keys():
            del self[key]
        self.update(dict(reversed(self.attr)))

    def __str__(self):
        return self.value

    def as_vcardline(self):
        key = self.Quote(self.name.upper())
        for k, v in self.attr:
            if v is None:
                key += ';%s' % (self.Quote(k))
            else:
                key += ';%s=%s' % (self.Quote(k), self.Quote(v))

        wrapped, line = '', '%s:%s' % (key, self.Quote(self.value))
        llen = 0
        for char in line:
            char = char.encode('utf-8')
            clen = len(char)
            if llen + clen >= 75:
                wrapped += '\n '
                llen = 0
            wrapped += char
            llen += clen

        return wrapped

    @classmethod
    def Quote(self, text):
        """
        Quote values so they can be safely represented in a VCard.

        >>> print VCardLine.Quote('Comma, semicolon; backslash\\ newline\\n')
        Comma\\, semicolon\\; backslash\\\\ newline\\n
        """
        return unicode(''.join([self.QUOTE_MAP.get(c, c) for c in text]))

    @classmethod
    def ParseLine(self, text):
        """
        Parse a single line, respecting to the VCard (RFC6350) quoting.

        >>> VCardLine.ParseLine('foo:val;ue')
        (u'foo', [], u'val;ue')
        >>> VCardLine.ParseLine('foo;BAR;\\\\baz:value')
        (u'foo', [(u'bar', True), (u'\\\\baz', True)], u'value')
        >>> VCardLine.ParseLine('FOO;bar=comma\\,semicolon\\;'
        ...                     'backslash\\\\\\\\:value')
        (u'foo', [(u'bar', u'comma,semicolon;backslash\\\\')], u'value')
        """
        # The parser is a state machine with two main states: quoted or
        # unquoted data. The unquoted data has three sub-states, to track
        # which part of the line is being parsed.

        def parse_quoted(char, state, parsed, name, attrs):
            pair = "\\" + char
            parsed = parsed[:-1] + self.QUOTE_RMAP.get(pair, pair)
            return parse_char, state, parsed, name, attrs

        def parse_char(char, state, parsed, name, attrs):
            if char == "\\":
                parsed += char
                return parse_quoted, state, parsed, name, attrs
            else:
                if state == 0 and char in (';', ':'):
                    name = parsed.lower()
                    parsed = ''
                    state += (char == ';') and 1 or 2
                elif state == 1 and char in (';', ':'):
                    if '=' in parsed:
                        k, v = parsed.split('=', 1)
                    else:
                        k = parsed
                        v = True
                    attrs.append((k.lower(), v))
                    parsed = ''
                    if char == ':':
                        state += 1
                else:
                    parsed += char
                return parse_char, state, parsed, name, attrs

        parser, state, parsed, name, attrs = parse_char, 0, '', None, []
        for char in unicode(text):
            parser, state, parsed, name, attrs = parser(
                char, state, parsed, name, attrs)

        return name, attrs, parsed


class SimpleVCard(dict):
    """
    This is a very simplistic implementation of VCard 4.0.
    """
    VCARD_OTHER_KEYS = {
        'AGENT': '',
        'CLASS': '',
        'EXPERTISE': '',
        'HOBBY': '',
        'INTEREST': '',
        'LABEL': '',
        'MAILER': '',
        'NAME': '',
        'ORG-DIRECTORY': '',
        'PROFILE': '',
        'SORT-STRING': '',
    }
    VCARD4_KEYS = {
        'ADR': '', 'ANNIVERSARY': '',
        'BDAY': '',
        'CALADRURI': '', 'CALURI': '', 'CATEGORIES': '', 'CLIENTPIDMAP': '',
        'EMAIL': '',
        'FBURL': '',
        'FN': '',
        'GENDER': '', 'GEO': '',
        'IMPP': '',
        'KEY': '', 'KIND': '',
        'LANG': '', 'LOGO': '',
        'MEMBER': '',
        'N': '', 'NICKNAME': '', 'NOTE': '',
        'ORG': '',
        'PHOTO': '', 'PRODID': '',
        'RELATED': '', 'REV': '', 'ROLE': '',
        'SOUND': '', 'SOURCE': '',
        'TEL': '', 'TITLE': '', 'TZ': '',
        'UID': '', 'URL': '',
        'XML': '',
    }

    def __init__(self):
        dict.__init__(self)
        self.filename = None
        self.gpg_recipient = lambda self: None
        self.version = '4.0'
        self.order = []

    def __getitem__(self, key):
        return dict.__getitem__(self, key.upper())

    def __setitem__(self, key, val):
        key = key.upper()
        if not (key.startswith('X-') or
                key in self.VCARD4_KEYS or
                key in self.VCARD_OTHER_KEYS):
            raise ValueError('Not a valid vCard key: %s' % key)
        if key not in self.order:
            self.order.append(key)
        if type(val) in (type(list()), type(set())):
            while key in self.order:
                self.order.remove(key)
            self.order.extend([key for v in val])
            dict.__setitem__(self, key, val)
        else:
            if key in self:
                dict.__getitem__(self, key)[0][0] = val
            else:
                dict.__setitem__(self, key, [[val, []]])

    def __str__(self):
        if self.kind == 'individual':
            return 'Contact: %s <%s>' % (self.fn, self.email)
        elif self.kind == 'group':
            return ('Group: %s (%s = %s)'
                    ) % (self.fn, self.nickname,
                         ','.join([e[0] for e in self.get('EMAIL', [])]))
        else:
            return '%s: %s (%s)' % (self.kind, self.fn, self.nickname)

    fn = property(lambda self: self.get('FN', [[None]])[0][0],
                  lambda self, v: self.__setitem__('FN', v))
    kind = property(lambda self: self.get('KIND',
                                          [[None]])[0][0] or 'individual',
                    lambda self, v: self.__setitem__('KIND', v))
    members = property(lambda self: [(m[0].startswith('mailto:')
                                      and m[0][7:] or m[0]).lower()
                                     for m in self.get('MEMBER', [])])
    nickname = property(lambda self: self.get('NICKNAME', [[None]])[0][0],
                         lambda self, v: self.__setitem__('KIND', v))

    def _getset_email(self, newemail=None):
        first = None
        for pair in self.get('EMAIL', []):
            first = first or pair
            for a in pair[1]:
                if 'PREF' in a.upper():
                    first = pair
        if newemail is not None:
            if first:
                first[0] = newemail
            else:
                self['EMAIL'] = newemail
                return self['EMAIL']
        return first or [None, []]

    email = property(lambda self: self._getset_email()[0],
                     lambda self, v: self._getset_email(v)[0])

    def _random_uid(self):
        if 'X-MAILPILE-RID' not in self:
            crap = '%s %s' % (self.email, random.randint(0, 0x1fffffff))
            self['X-MAILPILE-RID'] = b64w(sha1b64(crap)).lower()
        return self['X-MAILPILE-RID'][0][0]
    random_uid = property(_random_uid)

    def as_jCard(self):
        # FIXME: Needs type info and attributes.
        card = [[key.lower(), {}, "text", self[key][0][0]]
                for key in self.order]
        stream = ["vcardstream", ["vcard", card]]
        return stream

    def as_mpCard(self):
        return dict([(key, self[key][0][0]) for key in self.order])

    def as_xCard(self):
        # FIXME: Render as an xCard
        raise Exception('Unimplemented')

    def as_vCard(self):
        def _rotated_vcf(key):
            data = self[key].pop(0)
            self[key].append(data)
            return '%s:%s' % (';'.join([key] + data[1]), data[0])
        return '\r\n'.join([
            'BEGIN:VCARD',
            'VERSION:%s' % self.version,
        ] + [
            # The _rotated_vcf lets us rotate through the values in order
            # and we should end up with everything back in its original state.
            (_rotated_vcf(k)) for k in self.order
        ] + [
            'END:VCARD',
            ''
        ])

    def load(self, filename=None, data=None):
        def unwrap(text):
            return text.replace('\n ', '').replace('\n\t', '')
        if data:
            lines = [l.strip() for l in unwrap(data.strip()).splitlines()]
        else:
            self.filename = filename or self.filename
            lines = []
            decrypt_and_parse_lines(open(self.filename, 'rb'),
                                    lambda l: lines.append(l.strip()))
            while lines and not lines[-1]:
                lines.pop(-1)
            lines = unwrap('\n'.join(lines)).splitlines()

        if (not lines.pop(0).upper() == 'BEGIN:VCARD' or
                not lines.pop(-1).upper() == 'END:VCARD'):
            print '%s' % lines
            raise ValueError('Not a valid VCard')

        for line in lines:
            attrs, data = line.split(':', 1)
            attrs = attrs.split(';')
            key = attrs.pop(0)
            if key == 'VERSION':
                self.version = data
            elif key not in ('BEGIN:VCARD', 'VERSION', 'END:VCARD'):
                if not key in self:
                    self[key] = []
                self.order.append(key)
                self[key].append([data, attrs])

        return self

    def save(self, filename=None, gpg_recipient=None):
        filename = filename or self.filename
        if filename:
            gpg_recipient = gpg_recipient or self.gpg_recipient()
            fd = gpg_open(filename, gpg_recipient, 'wb')
            fd.write(self.as_vCard().encode('utf-8'))
            fd.close()
            return self
        else:
            raise ValueError('Save to what file?')


# FIXME: Move this into a contact importer plugin
class DAVClient:
    def __init__(self, host, port=None, username=None, password=None,
                             protocol='https'):
        if not port:
            if protocol == 'https':
                port = 443
            elif protocol == 'http':
                port = 80
            else:
                raise Exception("Can't determine port from protocol. "
                                "Please specifiy a port.")
        self.cwd = "/"
        self.baseurl = "%s://%s:%d" % (protocol, host, port)
        self.host = host
        self.port = port
        self.protocol = protocol
        self.username = username
        self.password = password
        if username and password:
            self.auth = base64.encodestring('%s:%s' % (username, password)
                                            ).replace('\n', '')
        else:
            self.auth = None

    def request(self, url, method, headers={}, body=""):
        if self.protocol == "https":
            req = httplib.HTTPSConnection(self.host, self.port)
            # FIXME: Verify HTTPS certificate
        else:
            req = httplib.HTTPConnection(self.host, self.port)

        req.putrequest(method, url)
        req.putheader("Host", self.host)
        req.putheader("User-Agent", "Mailpile")
        if self.auth:
            req.putheader("Authorization", "Basic %s" % self.auth)

        for key, value in headers.iteritems():
            req.putheader(key, value)

        req.endheaders()
        req.send(body)
        res = req.getresponse()

        self.last_status = res.status
        self.last_statusmessage = res.reason
        self.last_headers = dict(res.getheaders())
        self.last_body = res.read()

        if self.last_status >= 300:
            raise Exception(("HTTP %d: %s\n(%s %s)\n>>>%s<<<"
                             ) % (self.last_status, self.last_statusmessage,
                                  method, url, self.last_body))
        return (self.last_status, self.last_statusmessage,
                self.last_headers, self.last_body)

    def options(self, url):
        status, msg, header, resbody = self.request(url, "OPTIONS")
        return header["allow"].split(", ")


class CardDAV(DAVClient):
    def __init__(self, host, url, port=None, username=None,
                                  password=None, protocol='https'):
        DAVClient.__init__(self, host, port, username, password, protocol)
        self.url = url

        if not self._check_capability():
            raise Exception("No CardDAV support on server")

    def cd(self, url):
        self.url = url

    def _check_capability(self):
        result = self.options(self.url)
        return "addressbook" in self.last_headers["dav"].split(", ")

    def get_vcard(self, url):
        status, msg, header, resbody = self.request(url, "GET")
        card = SimpleVCard()
        card.load(data=resbody)
        return card

    def put_vcard(self, url, vcard):
        raise Exception('Unimplemented')

    def list_vcards(self):
        stat, msg, hdr, resbody = self.request(self.url, "PROPFIND", {}, {})
        tr = etree.fromstring(resbody)
        urls = [x.text for x in tr.xpath("/d:multistatus/d:response/d:href",
                                         namespaces={"d": "DAV:"})
                             if x.text not in ("", None) and
                                x.text[-3:] == "vcf"]
        return urls


if __name__ == "__main__":
    import doctest
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
