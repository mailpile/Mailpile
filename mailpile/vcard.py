import random
from gettext import gettext as _

import mailpile.util
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

    def set_attr(self, attr, value):
        try:
            for av in self._attrs:
                if av[0] == attr:
                    nav = (av[0], value)
                    av = nav
                    return
            self._attrs.append((attr, value))
        finally:
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
            count = len([l for l in self._lines if l and l.name == vcl.name])
            if not cardinality:
                raise ValueError('Not allowed on card: %s' % vcl.name)
            if cardinality in ('1', '*1'):
                if count:
                    raise ValueError('Already on card: %s' % vcl.name)
            self._lines.append(vcl)
            vcl.line_id = len(self._lines)

    def get_clientpidmap(self):
        """
        Return a dictionary representing the CLIENTPIDMAP, grouping VCard
        lines by data sources.

        >>> vc = SimpleVCard(VCardLine(name='fn', value='Bjarni', pid='1.2'),
        ...                  VCardLine(name='clientpidmap',
        ...                            value='1;thisisauid'))
        >>> vc.get_clientpidmap()['thisisauid']['pid']
        1
        >>> vc.get_clientpidmap()[1]['lines'][0][0]
        2
        >>> vc.get_clientpidmap()[1]['lines'][0][1].value
        u'Bjarni'
        """
        cpm = {}
        for pm in self.get_all('clientpidmap'):
            pid, guid = pm.value.split(';')
            cpm[guid] = cpm[int(pid)] = {
                'pid': int(pid),
                'lines': []
            }
        for vcl in self.as_lines():
            if 'pid' in vcl:
                pv = [v.split('.', 1) for v in vcl['pid'].split(',')]
                for pid, version in pv:
                    try:
                        cpm[int(pid)]['lines'].append((int(version), vcl))
                    except KeyError, e:
                        print ("KNOWN BUG IN VERSIONING CODE. "
                               "[%s] [pid: %s] [cpm: %s]") % (e, pid, cpm)
        return cpm

    def merge(self, src_id, lines):
        """
        Merge a set of VCard lines from a given source into this card.

        >>> vc = SimpleVCard(VCardLine(name='fn', value='Bjarni', pid='1.2'),
        ...                  VCardLine(name='clientpidmap',
        ...                            value='1;thisisauid'))
        >>> vc.merge('thisisauid', [VCardLine(name='fn', value='Bjarni'),
        ...                         VCardLine(name='x-a', value='b')])
        >>> vc.get('x-a')['pid']
        '1.3'
        >>> vc.get('fn')['pid']
        '1.2'

        >>> vc.merge('otheruid', [VCardLine(name='x-b', value='c')])
        >>> vc.get('x-b')['pid']
        '2.1'

        >>> vc.merge('thisisauid', [VCardLine(name='fn', value='Inrajb')])
        >>> vc.get('fn')['pid']
        '1.4'
        >>> vc.fn
        u'Inrajb'
        >>> vc.get('x-a')
        Traceback (most recent call last):
           ...
        IndexError: ...

        >>> print vc.as_vCard()
        BEGIN:VCARD
        VERSION:4.0
        CLIENTPIDMAP:2\\;otheruid
        CLIENTPIDMAP:1\\;thisisauid
        FN;PID=1.4:Inrajb
        X-B;PID=2.1:c
        END:VCARD
        """
        if not lines:
            return

        # First, we figure out which CLIENTPIDMAP applies, if any
        cpm = self.get_clientpidmap()
        pidmap = cpm.get(src_id)
        if pidmap:
            src_pid = pidmap['pid']
        else:
            pids = [p['pid'] for p in cpm.values()]
            src_pid = max([int(p) for p in pids] + [0]) + 1
            self.add(VCardLine(name='clientpidmap',
                               value='%s;%s' % (src_pid, src_id)))
            pidmap = cpm[src_pid] = cpm[src_id] = {'lines': []}

        # Deduplicate the lines, but give them a rank if they are repeated
        lines.sort(key=lambda k: (k.name, k.value))
        dedup = [lines[0]]
        rank = 0

        def rankit(rank):
            if rank:
                dedup[-1].set_attr('x-rank', rank)

        for line in lines[1:]:
            if dedup[-1].name == line.name and dedup[-1].value == line.value:
                rank += 1
            else:
                rankit(rank)
                rank = 0
                dedup.append(line)
        rankit(rank)
        lines = dedup

        # 1st, iterate through existing lines for this source, removing
        # all that differ from our input. Remove any input lines which are
        # identical to those already on this card.
        this_version = 0
        for ver, ol in cpm[src_pid]['lines'][:]:
            this_version = max(ver, this_version)
            match = [l for l in lines if (l
                                          and l.name == ol.name
                                          and l.value == ol.value)]
            for l in match:
                lines.remove(l)
            if not match:
                # FIXME: Actually, we should JUST remove our pid and if no
                #        pids are left, remove the line itself.
                self.remove(ol.line_id)

        # 2nd, iterate through provided lines and copy them.
        this_version += 1
        for vcl in lines:
            pids = [pid for pid in vcl.get('pid', '').split(',')
                    if pid and pid.split('.')[0] != src_pid]
            pids.append('%s.%s' % (src_pid, this_version))
            vcl.set_attr('pid', ','.join(pids))
            self.add(vcl)

        # FIXME: 3rd, collapse lines from multiple sources that have
        #        identical values?

    def get_all(self, key):
        return [l for l in self._lines if l and l.name == key.lower()]

    def get(self, key, n=0):
        lines = self.get_all(key)
        lines.sort(key=lambda l: 1 - (int(l.get('x-rank', 0)) or
                                      (('pref' in l or
                                        'pref' in l.get('type', '').lower()
                                        ) and 100 or 0)))
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
        mpCard, ln, lv = {}, None, None
        self._sort_lines()
        for vcl in self._lines:
            if not vcl or vcl.name in self.MPCARD_SUPPRESSED:
                continue
            if ln == vcl.name and lv == vcl.value:
                continue
            name = vcl.name.replace('x-mailpile-', '')
            if name not in mpCard:
                if vcl.name in self.MPCARD_SINGLETONS:
                    mpCard[name] = vcl.value
                else:
                    mpCard[name] = [self._mpcdict(vcl)]
            elif vcl.name not in self.MPCARD_SINGLETONS:
                mpCard[name].append(self._mpcdict(vcl))
            ln, lv = vcl.name, vcl.value
        return mpCard

    def _sort_lines(self):
        self._lines.sort(key=lambda k: ((k and k.name == 'version') and 1 or 2,
                                        k and k.name,
                                        k and len(k.value),
                                        k and k.value))

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

        # Make sure VERSION is first, order is stable.
        self._sort_lines()

        return '\n'.join(['BEGIN:VCARD'] +
                         [l.as_vcardline() for l in self._lines if l] +
                         ['END:VCARD'])

    def as_lines(self):
        self._sort_lines()
        return [vcl for vcl in self._lines if vcl]

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

    def load(self, filename=None, data=None, config=None):
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
                                    lambda l: lines.append(l.rstrip()),
                                    config)
            while lines and not lines[-1]:
                lines.pop(-1)
            lines = unwrap('\n'.join(lines)).splitlines()
        else:
            raise ValueError('Need data or a filename!')

        if (not len(lines) >= 2 or
                not lines.pop(0).upper() == 'BEGIN:VCARD' or
                not lines.pop(-1).upper() == 'END:VCARD'):
            raise ValueError('Not a valid VCard: %s' % '\n'.join(lines))

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


def AddressInfo(addr, fn, vcard=None, rank=0, proto='smtp', secure=False):
    info = {
        'fn': fn,
        'address': addr,
        'rank': rank,
        'protocol': proto,
        'flags': {}
    }
    if vcard:
        info['flags']['contact'] = True

        keys = []
        for k in vcard.get_all('KEY'):
            val = k.value.split("data:")[1]
            mime, fp = val.split(",")
            keys.append({'fingerprint': fp, 'type': 'openpgp', 'mime': mime})
        if keys:
            info['keys'] = [k for k in keys[:1]]
            info['flags']['secure'] = True

        photos = vcard.get_all('photo')
        if photos:
            info['photo'] = photos[0].value

        info['rank'] += 10.0 + 25 * len(keys) + 5 * len(photos)

    return info


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
        self.loaded = False

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
        if self.loaded:
            return
        try:
            self.loaded = True
            prefs = self.config.prefs
            for fn in os.listdir(self.vcard_dir):
                if mailpile.util.QUITTING:
                    return
                try:
                    c = SimpleVCard().load(os.path.join(self.vcard_dir, fn),
                                           config=(session and session.config))
                    c.gpg_recipient = lambda: prefs.get('gpg_recipient')
                    self.index_vcard(c)
                    if session:
                        session.ui.mark('Loaded %s' % c.email)
                except:
                    if session:
                        if 'vcard' in self.config.sys.debug:
                            import traceback
                            traceback.print_exc()
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


GUID_COUNTER = 0


class VCardPluginClass:
    REQUIRED_PARAMETERS = []
    OPTIONAL_PARAMETERS = []
    FORMAT_NAME = None
    FORMAT_DESCRIPTION = 'VCard Import/Export plugin'
    SHORT_NAME = None
    CONFIG_RULES = None

    def __init__(self, session, config, guid=None):
        self.session = session
        self.config = config
        if not self.config.guid:
            if not guid:
                global GUID_COUNTER
                guid = 'urn:uuid:mp-%s-%x-%x' % (self.SHORT_NAME, time.time(),
                                                 GUID_COUNTER)
                GUID_COUNTER += 1
            self.config.guid = guid
            self.session.config.save()


class VCardImporter(VCardPluginClass):

    def import_vcards(self, session, vcard_store):
        all_vcards = self.get_vcards()
        updated = []
        for vcard in all_vcards:
            existing = None
            for email in vcard.get_all('email'):
                existing = vcard_store.get_vcard(email.value)
                if existing:
                    existing.merge(self.config.guid, vcard.as_lines())
                    updated.append(existing)
                if session.config and session.config.index:
                    session.config.index.update_email(email.value,
                                                      name=vcard.fn)
            if existing is None:
                new_vcard = SimpleVCard()
                new_vcard.merge(self.config.guid, vcard.as_lines())
                vcard_store.add_vcards(new_vcard)
                updated.append(new_vcard)
                play_nice_with_threads()
        for vcard in set(updated):
            vcard.save()
            play_nice_with_threads()
        return len(updated)

    def get_vcards(self):
        raise Exception('Please override this function')


class VCardExporter(VCardPluginClass):

    def __init__(self):
        self.exporting = []

    def add_contact(self, contact):
        self.exporting.append(contact)

    def remove_contact(self, contact):
        self.exporting.remove(contact)

    def save(self):
        pass


class VCardContextProvider(VCardPluginClass):

    def __init__(self, contact):
        self.contact = contact

    def get_recent_context(self, max=10):
        pass

    def get_related_context(self, query, max=10):
        pass


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
