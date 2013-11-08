import base64
import httplib
import random

from lxml import etree

from mailpile.util import *


class VCardLine(dict):
    """
    This class represents a single line in a VCard file. It knows how
    to parse the most common "structured" lines into attributes and
    values and also convert a name, attributes and value into a properly
    encoded/escaped VCard line.

    For specific values, the object can be initialized directly.
    >>> vcl = VCardLine(name='name', value='The Dude', pref=None)
    >>> vcl.as_vcardline()
    'NAME;PREF:The Dude'

    Alternately, the name and value attributes can be set after the fact.
    >>> vcl.name = 'FN'
    >>> vcl.value = 'Lebowski'
    >>> vcl.attrs = []
    >>> vcl.as_vcardline()
    'FN:Lebowski'

    The object mostly behaves like a read-only dict.
    >>> print vcl
    {u'fn': u'Lebowski'}
    >>> print vcl.value
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

    def __init__(self, line=None, name=None, value=None, **attrs):
        self._name = name and unicode(name).lower() or None
        self._value = unicode(value)
        self._attrs = []
        self._line_id = 0
        for k in attrs:
            self._attrs.append((k.lower(), attrs[k]))
        if line is not None:
            self.parse(line)
        else:
            self._update_dict()

    def set_line_id(self, value):
        self._line_id = value
        self._update_dict()

    line_id = property(lambda self: self._line_id, set_line_id)

    def set_name(self, value):
        self._name = unicode(value).lower()
        self._update_dict()

    def set_value(self, value):
        self._value = unicode(value)
        self._update_dict()

    def set_attrs(self, value):
        self._attrs = value
        self._update_dict()

    name = property(lambda self: self._name,
                    lambda self, v: self.set_name(v))

    value = property(lambda self: self._value,
                     lambda self, v: self.set_value(v))

    attrs = property(lambda self: self._attrs,
                     lambda self, v: self.set_attrs(v))

    def parse(self, line):
        self._name, self._attrs, self._value = self.ParseLine(line)
        self._update_dict()

    def _update_dict(self):
        for key in self.keys():
            dict.__delitem__(self, key)
        dict.update(self, dict(reversed(self._attrs)))
        if self.name:
            dict.__setitem__(self, self._name, self._value)
        if self._line_id:
            dict.__setitem__(self, 'line_id', self._line_id)

    def __delitem__(self, *args, **kwargs):
        raise ValueError('This dict is read-only')

    def __setitem__(self, *args, **kwargs):
        raise ValueError('This dict is read-only')

    def update(self, *args, **kwargs):
        raise ValueError('This dict is read-only')

    def as_vcardline(self):
        key = self.Quote(self._name.upper())
        for k, v in self._attrs:
            k = k.upper()
            if v is None:
                key += ';%s' % (self.Quote(k))
            else:
                key += ';%s=%s' % (self.Quote(k), self.Quote(unicode(v)))

        wrapped, line = '', '%s:%s' % (key, self.Quote(self._value))
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
        (u'foo', [(u'bar', None), (u'\\\\baz', None)], u'value')
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
                        v = None
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


class SimpleVCard(object):
    """
    This is a very simplistic implementation of VCard 4.0.

    The card can be initialized with a series of VCardLine objects.
    >>> vcard = SimpleVCard(VCardLine(name='fn', value='Bjarni'),
    ...                     VCardLine(name='email', value='bre@example.com'),
    ...                     VCardLine(name='email', value='bre2@example.com'),
    ...                     VCardLine('EMAIL;TYPE=PREF:bre@evil.com'))

    The preferred (or Nth) line of any type can be retrieved using
    the get method. Lines are sorted by (preference, card order).
    >>> vcard.get('email').value
    u'bre@evil.com'
    >>> vcard.get('email', n=2).value
    u'bre2@example.com'
    >>> vcard.get('email', n=4).value
    Traceback (most recent call last):
        ...
    IndexError: ...

    There are shorthand methods for accessing or setting the values of
    the full name and e-mail lines:
    >>> vcard.email
    u'bre@evil.com'
    >>> vcard.fn = 'Bjarni R. E.'
    >>> vcard.get('fn').value
    u'Bjarni R. E.'

    To fetch all lines, use the get_all method. In this case no
    sorting is performed and lines are simply returned in card order.
    >>> [vcl.value for vcl in vcard.get_all('email')]
    [u'bre@example.com', u'bre2@example.com', u'bre@evil.com']

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
        # General properties
        # .. BEGIN
        # .. END
        'SOURCE': ['*', None, None],
        'KIND': ['*1', None, 'individual'],
        'XML': ['*', None, None],
        # Identification properties
        'FN': ['1*', None, 'Anonymous'],
        'N': ['*1', None, None],
        'NICKNAME': ['*', None, None],
        'PHOTO': ['*', None, None],
        'BDAY': ['*1', None, None],
        'ANNIVERSARY': ['*1', None, None],
        'GENDER': ['*1', None, None],
        # Delivery Addressing Properties
        'ADR': ['*', None, None],
        # Communications Properties
        'TEL': ['*', None, None],
        'EMAIL': ['*', None, None],
        'IMPP': ['*', None, None],
        'LANG': ['*', None, None],
        # Geographical Properties
        'TZ': ['*', None, None],
        'GEO': ['*', None, None],
        # Organizational Properties
        'TITLE': ['*', None, None],
        'ROLE': ['*', None, None],
        'LOGO': ['*', None, None],
        'ORG': ['*', None, None],
        'MEMBER': ['*', None, None],
        'RELATED': ['*', None, None],
        # Explanitory Properties
        'VERSION': ['1', None, '4.0'],
        'CATEGORIES': ['*', None, None],
        'NOTE': ['*', None, None],
        'PRODID': ['*', None, None],
        'REV': ['*1', None, None],
        'SOUND': ['*', None, None],
        'UID': ['*1', None, None],
        'CLIENTPIDMAP': ['*', None, None],
        'URL': ['*', None, None],
        # Security Properties
        'KEY': ['*', None, None],
        # Calendar Properties
        'FBURL': ['*', None, None],
        'CALADRURI': ['*', None, None],
        'CALURI': ['*', None, None],
    }
    VCARD4_REQUIRED = ('VERSION', 'FN')

    def __init__(self, *lines, **kwargs):
        self.gpg_recipient = lambda self: None
        self.filename = None
        self._lines = []
        if 'data' in kwargs and kwargs['data'] is not None:
            self.load(data=kwargs['data'])
        self.add(*lines)

    def _cardinality(self, vcl):
        if vcl.name.startswith('x-'):
            return '*'
        else:
            return self.VCARD4_KEYS.get(vcl.name.upper(), [''])[0]

    def remove(self, *line_ids):
        """
        Remove one or more lines from the VCard.

        >>> vc = SimpleVCard(VCardLine(name='fn', value='Houdini'))
        >>> vc.remove(vc.get('fn').line_id)
        >>> vc.get('fn')
        Traceback (most recent call last):
            ...
        IndexError: ...
        """
        for index in range(0, len(self._lines)):
            vcl = self._lines[index]
            if vcl and vcl.line_id in line_ids:
                 self._lines[index] = None

    def add(self, *vcls):
        """
        Add one or more lines to a VCard.

        >>> vc = SimpleVCard()
        >>> vc.add(VCardLine(name='fn', value='Bjarni'))
        >>> vc.get('fn').value
        u'Bjarni'

        Line types are checked against VCard 4.0 for validity.
        >>> vc.add(VCardLine(name='evil', value='Bjarni'))
        Traceback (most recent call last):
            ...
        ValueError: Not allowed on card: evil
        """
        for vcl in vcls:
            cardinality = self._cardinality(vcl)
            count = len([l for l in self._lines if l.name == vcl.name])
            if not cardinality:
                raise ValueError('Not allowed on card: %s' % vcl.name)
            if cardinality in ('1', '*1'):
                if count:
                    raise ValueError('Already on card: %s' % vcl.name)
            self._lines.append(vcl)
            vcl.line_id = len(self._lines)

    def get_all(self, key):
        return [l for l in self._lines if l and  l.name == key.lower()]

    def get(self, key, n=0):
        lines = self.get_all(key)
        lines.sort(key=lambda l: 1 - (('pref' in l or
                                       'pref' in l.get('type', '').lower()
                                      ) and 1 or 0))
        return lines[n]

    def as_jCard(self):
        card = [[key.lower(), {}, "text", self[key][0][0]]
                for key in self.order]
        stream = ["vcardstream", ["vcard", card]]
        return stream

    def _mpcdict(self, vcl):
        d = {}
        for k in vcl.keys():
            if k not in ('line_id', ):
                if k.startswith('x-mailpile-'):
                    d[k.replace('x-mailpile-', '')] = vcl[k]
                else:
                    d[k] = vcl[k]
        return d
 
    MPCARD_SINGLETONS = ('fn', 'kind')
    MPCARD_SUPPRESSED = ('version', 'x-mailpile-rid')

    def as_mpCard(self):
        mpCard = {}
        self._lines.sort(key=lambda c: 1-(c.get('pref', 0)))
        for vcl in self._lines:
            if vcl.name in self.MPCARD_SUPPRESSED:
                continue
            name = vcl.name.replace('x-mailpile-', '')
            if name not in mpCard:
                if vcl.name in self.MPCARD_SINGLETONS:
                    mpCard[name] = vcl.value
                else:
                    mpCard[name] = [self._mpcdict(vcl)]
            elif vcl.name not in self.MPCARD_SINGLETONS:
                mpCard[name].append(self._mpcdict(vcl))
        return mpCard

    def as_vCard(self):
        """
        This method returns the VCard data in its native format.
        Note: the output is a string of bytes, not unicode characters.

        >>> print SimpleVCard().as_vCard()
        BEGIN:VCARD
        VERSION:4.0
        FN:Anonymous
        END:VCARD
        """
        # Add any missing required keys...
        for key in self.VCARD4_REQUIRED:
            if not self.get_all(key):
                default = self.VCARD4_KEYS[key][2]
                self._lines[:0] = [VCardLine(name=key, value=default)]

        # Make sure VERSION is first.
        self._lines.sort(key=lambda k: (k.name == 'version') and 1 or 2)

        return '\n'.join(['BEGIN:VCARD'] +
                         [l.as_vcardline() for l in self._lines if l] +
                         ['END:VCARD'])

    def as_lines(self):
        return self._lines

    def _vcard_get(self, key):
        try:
            return self.get(key).value
        except IndexError:
            default = self.VCARD4_KEYS.get(key.upper(), ['', '', None])[2]
            return default

    def _vcard_set(self, key, value):
        try:
            self.get(key).value = value
        except IndexError:
            self.add(VCardLine(name=key, value=value, pref=None))

    nickname = property(lambda self: self._vcard_get('nickname'),
                        lambda self, e: self._vcard_set('nickname', e))

    email = property(lambda self: self._vcard_get('email'),
                     lambda self, e: self._vcard_set('email', e))

    kind = property(lambda self: self._vcard_get('kind'),
                    lambda self, e: self._vcard_set('kind', e))

    fn = property(lambda self: self._vcard_get('fn'),
                  lambda self, e: self._vcard_set('fn', e))

    def _random_uid(self):
        try:
            rid = self.get('x-mailpile-rid').value
        except IndexError:
            crap = '%s %s' % (self.email, random.randint(0, 0x1fffffff))
            rid = b64w(sha1b64(crap)).lower()
            self.add(VCardLine(name='x-mailpile-rid', value=rid))
        return rid

    random_uid = property(_random_uid)

    def load(self, filename=None, data=None):
        """
        Load VCard lines from a file on disk or data in memory.
        """
        def unwrap(text):
            return text.replace('\n ', '').replace('\n\t', '')

        if data:
            lines = [l.strip() for l in unwrap(data.strip()).splitlines()]
        elif filename:
            self.filename = filename or self.filename
            lines = []
            decrypt_and_parse_lines(open(self.filename, 'rb'),
                                    lambda l: lines.append(l.strip()))
            while lines and not lines[-1]:
                lines.pop(-1)
            lines = unwrap('\n'.join(lines)).splitlines()
        else:
            raise ValueError('Need data or a filename!')

        if (not lines.pop(0).upper() == 'BEGIN:VCARD' or
                not lines.pop(-1).upper() == 'END:VCARD'):
            print '%s' % lines
            raise ValueError('Not a valid VCard')

        for line in lines:
            self.add(VCardLine(line))

        return self

    def save(self, filename=None, gpg_recipient=None):
        filename = filename or self.filename
        if filename:
            gpg_recipient = gpg_recipient or self.gpg_recipient()
            fd = gpg_open(filename, gpg_recipient, 'wb')
            fd.write(self.as_vCard())
            fd.close()
            return self
        else:
            raise ValueError('Save to what file?')


class VCardStore(dict):
    """
    This is a disk-backed in-memory collection of VCards.

    >>> vcs = VCardStore(cfg, '/tmp')

    # VCards are added to the collection using add_vcard. This will
    # create a file for the card on disk, using a random name.
    >>> vcs.add_vcards(SimpleVCard(VCardLine('FN:Dude'),
    ...                            VCardLine('EMAIL:d@evil.com')),
    ...                SimpleVCard(VCardLine('FN:Guy')))

    VCards can be looked up directly by e-mail.
    >>> vcs.get_vcard('d@evil.com').fn
    u'Dude'

    Or they can be found using searches...
    >>> vcs.find_vcards(['guy'])[0].fn
    u'Guy'

    Cards can be removed using del_vcards
    >>> vcs.del_vcards(vcs.get_vcard('d@evil.com'))
    >>> vcs.get_vcard('d@evil.com') is None
    True
    >>> vcs.del_vcards(*vcs.find_vcards(['guy']))
    >>> vcs.find_vcards(['guy'])
    []
    """
    def __init__(self, config, vcard_dir):
        dict.__init__(self)
        self.config = config
        self.vcard_dir = vcard_dir

    def index_vcard(self, card):
        attr = (card.kind == 'individual') and 'email' or 'nickname'
        for vcl in card.get_all(attr):
            self[vcl.value.lower()] = card
        self[card.random_uid] = card

    def deindex_vcard(self, card):
        attr = (card.kind == 'individual') and 'email' or 'nickname'
        for vcl in card.get_all(attr):
            if vcl.value.lower() in self:
                del self[vcl.value.lower()]
        if card.random_uid in self:
            del self[card.random_uid]

    def load_vcards(self, session=None):
        try:
            prefs = self.config.prefs
            for fn in os.listdir(self.vcard_dir):
                try:
                    c = SimpleVCard().load(os.path.join(self.vcard_dir, fn))
                    c.gpg_recipient = lambda: prefs.get('gpg_recipient')
                    self.index_vcard(c)
                    if session:
                        session.ui.mark('Loaded %s' % c.email)
                except:
                    import traceback
                    traceback.print_exc()
                    if session:
                        session.ui.warning('Failed to load vcard %s' % fn)
        except OSError:
            pass

    def get_vcard(self, email):
        return self.get(email.lower(), None)

    def find_vcards(vcards, terms, kinds=['individual']):
        results = []
        if not terms:
            results = [set([vcards[k].random_uid for k in vcards
                            if (vcards[k].kind in kinds) or not kinds])]
        for term in terms:
            term = term.lower()
            results.append(set([vcards[k].random_uid for k in vcards
                                if (term in k or term in vcards[k].fn.lower())
                                and ((vcards[k].kind in kinds) or not kinds)]))
        while len(results) > 1:
            results[0] &= results.pop(-1)
        results = [vcards[rid] for rid in results[0]]
        results.sort(key=lambda card: card.fn)
        return results

    def add_vcards(self, *cards):
        prefs = self.config.prefs
        for card in cards:
            card.filename = os.path.join(self.vcard_dir,
                                         card.random_uid) + '.vcf'
            card.gpg_recipient = lambda: prefs.get('gpg_recipient')
            card.save()
            self.index_vcard(card)

    def del_vcards(self, *cards):
        for card in cards:
            self.deindex_vcard(card)
            try:
                os.remove(card.filename)
            except (OSError, IOError):
                pass


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
    import mailpile.config
    import mailpile.defaults
    cfg = mailpile.config.ConfigManager(rules=mailpile.defaults.CONFIG_RULES)
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={'cfg': cfg})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
