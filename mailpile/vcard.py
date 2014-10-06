import random
import threading
import time

import mailpile.util
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
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

    line_id = property(
        lambda self: self._line_id,
        set_line_id)

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
            for i, av in enumerate(self._attrs):
                if av[0] == attr:
                    nav = (av[0], value)
                    self.attrs[i] = nav
                    return
            self._attrs.append((attr, value))
        finally:
            self._update_dict()

    name = property(
        lambda self: self._name,
        lambda self, v: self.set_name(v))

    value = property(
        lambda self: self._value,
        lambda self, v: self.set_value(v))

    attrs = property(
        lambda self: self._attrs,
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
        self.filename = None
        self._lines = []
        self._lock = VCardRLock()
        if 'data' in kwargs and kwargs['data'] is not None:
            self.load(data=kwargs['data'])
        self.add(*lines)

    def _cardinality(self, vcl):
        if vcl.name.startswith('x-'):
            return '*'
        else:
            return self.VCARD4_KEYS.get(vcl.name.upper(), [''])[0]

    UNREMOVABLE = ('x-mailpile-rid', 'clientpidmap', 'version')

    def remove(self, *line_ids):
        """
        Remove one or more lines from the VCard.

        >>> vc = SimpleVCard(VCardLine(name='fn', value='Houdini'))
        >>> vc.remove(vc.get('fn').line_id)
        1
        >>> vc.get('fn')
        Traceback (most recent call last):
            ...
        IndexError: ...
        """
        removed = 0
        with self._lock:
            for index in range(0, len(self._lines)):
                vcl = self._lines[index]
                if vcl and vcl.line_id in line_ids:
                    if self._lines[index].name in self.UNREMOVABLE:
                        raise ValueError('Cannot remove %s from VCard'
                                         % self._lines[index].name)
                    self._lines[index] = None
                    removed += 1
        return removed

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
            with self._lock:
                if not vcl.name:
                    continue
                cardinality = self._cardinality(vcl)
                count = len([l for l in self._lines
                             if l and l.name == vcl.name])
                if not cardinality:
                    raise ValueError('Not allowed on card: %s' % vcl.name)
                if cardinality in ('1', '*1'):
                    if count:
                        raise ValueError('Already on card: %s' % vcl.name)
                self._lines.append(vcl)
                vcl.line_id = len(self._lines)

    def set_line(self, ln, vcl):
        """
        Modify one line of a VCard.

        >>> vc = SimpleVCard(VCardLine(name='fn', value='Bjarni'))
        >>> vc.get('fn').value
        u'Bjarni'

        >>> vc.set_line(vc.get('fn').line_id,
        ...             VCardLine(name='fn', value='Dude'))
        >>> vc.get('fn').value
        u'Dude'
        """
        if not (ln > 0 and ln <= len(self._lines)):
            raise ValueError(_('Line number %s is out of range') % ln)
        with self._lock:
            vcl.line_id = ln
            self._lines[ln-1] = vcl

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
        ...                  VCardLine(name='email', value='bre@foo', t='1'),
        ...                  VCardLine(name='email', value='bre@bar', t='2'),
        ...                  VCardLine(name='clientpidmap',
        ...                            value='1;thisisauid'))
        >>> vc.merge('thisisauid', [VCardLine(name='fn', value='Bjarni'),
        ...                         VCardLine(name='x-a', value='b')])
        >>> vc.get('x-a')['pid']
        '1.3'
        >>> vc.get('fn')['pid']
        '1.2'
        >>> vc.get('email', prefer={'t': '1'}).value
        u'bre@foo'
        >>> vc.get('email', prefer={'t': '2'}).value
        u'bre@bar'
        >>> vc.get('email', prefer={'t': 'unfindable'}).value
        u'bre@foo'

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
        CLIENTPIDMAP:1\\;thisisauid
        CLIENTPIDMAP:2\\;otheruid
        EMAIL;T=1:bre@foo
        EMAIL;T=2:bre@bar
        FN;PID=1.4:Inrajb
        X-B;PID=2.1:c
        END:VCARD
        """
        if not lines:
            return

        with self._lock:
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
                if line.name in self.UNREMOVABLE:
                    # Do not merge these
                    continue
                if (dedup[-1].name == line.name and
                        dedup[-1].value == line.value):
                    rank += 1
                else:
                    rankit(rank)
                    rank = 0
                    dedup.append(line)
            rankit(rank)
            lines = dedup

            # 1st, iterate through existing lines for this source, removing
            # all that differ from our input. Remove any input lines which
            # are identical to those already on this card.
            this_version = 0
            for ver, ol in cpm[src_pid]['lines'][:]:
                this_version = max(ver, this_version)
                match = [l for l in lines if (l
                                              and l.name == ol.name
                                              and l.value == ol.value)]
                for l in match:
                    lines.remove(l)
                if not match:
                    # FIXME: Actually, we should JUST remove our pid and if
                    #        no pids are left, remove the line itself.
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

    def get_all(self, key, sort=False):
        with self._lock:
            lines = [l for l in self._lines if l and l.name == key.lower()]
        if sort:
            self._sort_lines(lines)
        return lines

    def get(self, key, n=0, prefer=None):
        lines = self.get_all(key)
        if prefer:
            for k, v in prefer.iteritems():
                llines = [l for l in lines if l.get(k) == v]
                if llines:
                    lines = llines
        return self._sort_lines(lines)[n]

    def _sort_lines(self, lines=None):
        lines = self._lines if (lines is None) else lines

        def sortkey(l):
            if not l:
                return (3, 0, 0, 0)
            return ((l.name == 'version') and 1 or 2,
                    (l.name),
                    (1 - ((('pref' in l or
                            'pref' in l.get('type', '').lower()) and 100 or 0)
                          or (50 - (l.get('pid', 0) and 50))
                          or int(l.get('x-rank', 0)))),
                    (l.line_id))

        with self._lock:
            lines.sort(key=sortkey)
        return lines

    def as_jCard(self):
        with self._lock:
            card = [[key.lower(), {}, "text", self[key][0][0]]
                    for key in self.order]
        stream = ["vcardstream", ["vcard", card]]
        return stream

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
            with self._lock:
                if not self.get_all(key):
                    default = self.VCARD4_KEYS[key][2]
                    self._lines[:0] = [VCardLine(name=key, value=default)]

        # Make sure VERSION is first, order is stable.
        with self._lock:
            self._sort_lines()
            return '\n'.join(['BEGIN:VCARD'] +
                             [l.as_vcardline() for l in self._lines if l] +
                             ['END:VCARD'])

    def as_lines(self):
        with self._lock:
            self._sort_lines()
            return [vcl for vcl in self._lines if vcl]

    def _vcard_get(self, key, default=None):
        try:
            return self.get(key).value
        except IndexError:
            if default is None:
                default = self.VCARD4_KEYS.get(key.upper(), ['', '', None])[2]
            return default

    def _vcard_set(self, key, value):
        try:
            self.get(key).value = value
        except IndexError:
            self.add(VCardLine(name=key, value=value, pref=None))

    nickname = property(
        lambda self: unicode(self._vcard_get('nickname')),
        lambda self, e: self._vcard_set('nickname', e))

    email = property(
        lambda self: unicode(self._vcard_get('email')),
        lambda self, e: self._vcard_set('email', e))

    kind = property(
        lambda self: unicode(self._vcard_get('kind')),
        lambda self, e: self._vcard_set('kind', e))

    fn = property(
        lambda self: unicode(self._vcard_get('fn')),
        lambda self, e: self._vcard_set('fn', e))

    note = property(
        lambda self: unicode(self._vcard_get('note')),
        lambda self, e: self._vcard_set('note', e.replace('\n', ' ')))


class MailpileVCard(SimpleVCard):
    """
    This is adds some mailpile-specific extensions to the SimpleVCard.
    """
    HISTORY_MAX_AGE = 31 * 24 * 3600

    def __init__(self, *lines, **kwargs):
        SimpleVCard.__init__(self, *lines, **kwargs)
        self.configure_encryption(kwargs.get('config'))

    def configure_encryption(self, config):
        if config:
            dec = lambda: config.master_key
            enc = lambda: (config.prefs.encrypt_vcards and
                           config.master_key)
            self.config = config
        else:
            enc = dec = lambda: None
            self.config = None
        self.encryption_key_func = enc
        self.decryption_key_func = dec

    def _history_parse_expire(self, history_vcl, now):
        history = {
            'sent': [],
            'received': []
        }
        entries = []
        for entry in [e for e in history_vcl.value.split(',') if e]:
            try:
                what, when, mid = entry.split('-')
                when = int(when, 36)
                if when > now - self.HISTORY_MAX_AGE:
                    history['sent' if (what == 's') else 'received'].append(
                        (when, mid))
                    entries.append(entry)
            except (ValueError, IndexError, TypeError):
                pass
        history_vcl.value = ','.join(entries)
        return entries, history

    def recent_history(self, now=None):
        try:
            now = now if (now is not None) else time.time()
            history_vcl = self.get('x-mailpile-history')
            return self._history_parse_expire(history_vcl, now)[1]
        except IndexError:
            return {}

    def record_history(self, what, when, mid, now=None):
        assert(what[0] in ('s', 'r'))
        with self._lock:
            try:
                history_vcl = self.get('x-mailpile-history')
            except IndexError:
                history_vcl = VCardLine(name='x-mailpile-history', value='')
                self.add(history_vcl)
            now = now if (now is not None) else time.time()
            entries, history = self._history_parse_expire(history_vcl, now)
            entries.append('%s-%s-%s' % (what[0], b36(int(when)), mid))
            history_vcl.value = ','.join(entries)

    def prefer_sender(self, address, sender):
        address = address.lower()
        for vcl in self.get_all('x-mailpile-prefer-profile'):
            addr = vcl.get('address')
            if addr and addr == address:
                vcl.value = sender.random_uid
                return
        self.add(VCardLine(name='x-mailpile-prefer-profile',
                           value=sender.random_uid,
                           address=address))

    def sending_profile(self, address):
        default = None
        which_email = None
        for vcl in self.get_all('x-mailpile-prefer-profile'):
            addr = vcl.get('address')
            value = vcl.value
            if addr:
                if addr == address.lower():
                    if ',' in value:
                        value, which_email = value.split(',')
                    return (value, which_email)
            else:
                if ',' in value:
                    default, which_email = value.split(',')
                else:
                    default, which_email = value, None
        return (default, which_email)

    def sends_to(self, address):
        domain = address.rsplit('#')[0].rsplit('@', 1)[-1].lower()
        address = address.lower()
        my_email = self.email
        for vcl in self.get_all('x-mailpile-scope'):
            if vcl.value in (domain, address):
                return vcl.get('address') or my_email
        return False

    def same_domain(self, address):
        domain = address.rsplit('#')[0].rsplit('@')[-1].lower()
        for vcl in self.get_all('email'):
            if domain == vcl.value.rsplit('@', 1)[-1].lower():
                return vcl.value
        return False

    def _random_uid(self):
        with self._lock:
            try:
                rid = self.get('x-mailpile-rid').value
            except IndexError:
                crap = '%s %s' % (self.email, random.randint(0, 0x1fffffff))
                rid = b64w(sha1b64(crap)).lower()
                self.add(VCardLine(name='x-mailpile-rid', value=rid))
        return rid

    signature = property(
        lambda self: self._vcard_get('x-mailpile-profile-signature'),
        lambda self, v: self._vcard_set('x-mailpile-profile-signature', v))

    route = property(
        lambda self: self._vcard_get('x-mailpile-profile-route'),
        lambda self, v: self._vcard_set('x-mailpile-profile-route', v))

    gpgshared = property(
        lambda self: self._vcard_get('x-mailpile-last-gpg-key-share'),
        lambda self, v: self._vcard_set('x-mailpile-last-gpg-key-share', v))

    random_uid = property(_random_uid)

    def _mpcdict(self, vcl):
        d = {}
        for k in vcl.keys():
            if k not in ('line_id', ):
                if k.startswith('x-mailpile-'):
                    d[k.replace('x-mailpile-', '')] = vcl[k]
                else:
                    d[k] = vcl[k]
        return d

    MPCARD_SINGLETONS = ('fn', 'kind', 'note',
                         'x-mailpile-profile-signature',
                         'x-mailpile-profile-route',
                         'x-mailpile-last-gpg-key-share')
    MPCARD_SUPPRESSED = ('version', 'x-mailpile-rid')

    def as_mpCard(self):
        mpCard, added = {}, set()
        with self._lock:
            self._sort_lines()
            for vcl in self._lines:
                if not vcl or vcl.name in self.MPCARD_SUPPRESSED:
                    continue
                name = vcl.name
                if (name, vcl.value) in added:
                    continue
                if name not in mpCard:
                    if name in self.MPCARD_SINGLETONS:
                        mpCard[name] = vcl.value
                    else:
                        mpCard[name] = [self._mpcdict(vcl)]
                elif name not in self.MPCARD_SINGLETONS:
                    mpCard[name].append(self._mpcdict(vcl))
                added.add((name, vcl.value))
            return mpCard

    def load(self, filename=None, data=None, config=None):
        """
        Load VCard lines from a file on disk or data in memory.
        """
        if data:
            pass
        elif filename:
            from mailpile.crypto.streamer import DecryptingStreamer
            self.filename = filename or self.filename
            with open(self.filename, 'rb') as fd:
                with DecryptingStreamer(fd,
                                        mep_key=self.decryption_key_func(),
                                        name='VCard/load') as streamer:
                    data = streamer.read().decode('utf-8')
                    streamer.verify(_raise=IOError)
        else:
            raise ValueError('Need data or a filename!')

        def unwrap(text):
            # This undoes the VCard standard line wrapping
            return text.replace('\n ', '').replace('\n\t', '')

        lines = [l.strip() for l in unwrap(data.strip()).splitlines()]
        if (not len(lines) >= 2 or
                not lines.pop(0).upper() == 'BEGIN:VCARD' or
                not lines.pop(-1).upper() == 'END:VCARD'):
            raise ValueError('Not a valid VCard: %s' % '\n'.join(lines))

        with self._lock:
            for line in lines:
                self.add(VCardLine(line))

        return self

    def save(self, filename=None):
        filename = filename or self.filename
        if filename:
            encryption_key = self.encryption_key_func()
            if encryption_key:
                from mailpile.crypto.streamer import EncryptingStreamer
                subj = self.config.mailpile_path(filename)
                with EncryptingStreamer(encryption_key,
                                        delimited=False,
                                        dir=self.config.tempfile_dir(),
                                        header_data={'subject': subj},
                                        name='VCard/save') as es:
                    es.write(self.as_vCard())
                    es.save(filename)
            else:
                with open(filename, 'wb') as fd:
                    fd.write(self.as_vCard())
            return self
        else:
            raise ValueError('Save to what file?')


class AddressInfo(dict):

    fn = property(
        lambda self: unicode(self['fn']),
        lambda self, v: self.__setitem__('fn', v))

    address = property(
        lambda self: unicode(self['address']),
        lambda self, v: self.__setitem__('address', v))

    rank = property(
        lambda self: self['rank'],
        lambda self, v: self.__setitem__('rank', v))

    protocol = property(
        lambda self: self['protocol'],
        lambda self, v: self.__setitem__('protocol', v))

    flags = property(
        lambda self: self['flags'],
        lambda self, v: self.__setitem__('flags', v))

    keys = property(
        lambda self: self.get('keys'),
        lambda self, v: self.__setitem__('keys', v))

    def __init__(self, addr, fn, vcard=None, rank=0, proto='smtp', keys=None):
        info = {
            'fn': fn,
            'address': addr,
            'rank': rank,
            'protocol': proto,
            'flags': {}
        }
        if keys:
            info['keys'] = keys
            info['flags']['secure'] = True
        self.update(info)
        if vcard:
            self.merge_vcard(vcard)

    def merge_vcard(self, vcard):
        if vcard.kind == 'profile':
            base_rank = 5.0
            self['flags']['profile'] = True
        else:
            base_rank = 10.0
            self['flags']['contact'] = True

        keys = []
        for k in vcard.get_all('KEY'):
            val = k.value.split("data:")[1]
            mime, fp = val.split(",")
            keys.append({'fingerprint': fp, 'type': 'openpgp', 'mime': mime})
        if keys:
            self['keys'] = self.get('keys', []) + [k for k in keys[:1]]
            self['flags']['secure'] = True

        photos = vcard.get_all('photo')
        if photos:
            self['photo'] = photos[0].value

        self['x-mailpile-rid'] = vcard.random_uid
        self['rank'] += base_rank + 25 * len(keys) + 5 * len(photos)
        if vcard.email == self.address:
            self['rank'] *= 2


class VCardStore(dict):
    """
    This is a disk-backed in-memory collection of VCards.

    >>> vcs = VCardStore(cfg, '/tmp')

    # VCards are added to the collection using add_vcard. This will
    # create a file for the card on disk, using a random name.
    >>> vcs.add_vcards(MailpileVCard(VCardLine('FN:Dude'),
    ...                              VCardLine('EMAIL:d@evil.com')),
    ...                MailpileVCard(VCardLine('FN:Guy')))

    VCards can be looked up directly by e-mail.
    >>> vcs.get_vcard('d@evil.com').fn
    u'Dude'
    >>> vcs.get_vcard('nosuch@email.address') is None
    True

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
    KINDS_ALL = ('individual', 'group', 'profile', 'internal')
    KINDS_PEOPLE = ('individual', 'profile', 'internal')

    def __init__(self, config, vcard_dir):
        dict.__init__(self)
        self.config = config
        self.vcard_dir = vcard_dir
        self.loaded = False
        self._lock = VCardRLock()

    def index_vcard(self, card):
        attrs = (['email'] if (card.kind in self.KINDS_PEOPLE)
                 else ['nickname'])
        with self._lock:
            for attr in attrs:
                for n, vcl in enumerate(card.get_all(attr, sort=True)):
                    key = vcl.value.lower()
                    if n == 0 or key not in self:
                        self[key] = card
            self[card.random_uid] = card

    def deindex_vcard(self, card):
        attrs = (['email'] if (card.kind in self.KINDS_PEOPLE)
                 else ['nickname'])
        with self._lock:
            for attr in attrs:
                for vcl in card.get_all(attr):
                    key = vcl.value.lower()
                    indexed = self.get(key)
                    if indexed and indexed.random_uid == card.random_uid:
                        del self[key]
            if card.random_uid in self:
                del self[card.random_uid]

    def load_vcards(self, session=None):
        if self.loaded:
            return
        try:
            with self._lock:
                self.loaded = True
                prfs = self.config.prefs
                key_func = lambda: self.config.master_key
                for fn in sorted(os.listdir(self.vcard_dir)):
                    if mailpile.util.QUITTING:
                        return
                    try:
                        c = MailpileVCard(config=self.config)
                        c.load(os.path.join(self.vcard_dir, fn),
                               config=self.config)
                        self.index_vcard(c)
                        if session:
                            session.ui.mark('Loaded %s from %s'
                                            % (c.email, fn))
                    except KeyboardInterrupt:
                        raise
                    except ValueError:
                        if fn.startswith('tmp'):
                            safe_remove(os.path.join(self.vcard_dir, fn))
                    except:
                        if session:
                            if 'vcard' in self.config.sys.debug:
                                import traceback
                                traceback.print_exc()
                            session.ui.warning('Failed to load vcard %s' % fn)
        except (OSError, IOError):
            pass

    def get_vcard(self, email):
        return self.get(email.lower(), None)

    def find_vcards_with_line(vcards, name, value):
        # FIXME: This is pretty slow. Can we do better?
        vcards = [vc for vc in set(vcards.values())
                  if [vcl for vcl in vc.get_all(name) if vcl.value == value]]
        vcards.sort(key=lambda vc: (vc.fn, vc.email))
        return vcards

    def find_vcards(vcards, terms, kinds=None):
        kinds = kinds or vcards.KINDS_ALL
        results = []
        with vcards._lock:
            if not terms:
                results = [set([vcards[k].random_uid for k in vcards
                                if (vcards[k].kind in kinds) or not kinds])]
            for term in terms:
                term = term.lower()
                results.append(set([vcards[k].random_uid for k in vcards
                                    if (term in k or
                                        term in vcards[k].fn.lower())
                                    and ((vcards[k].kind in kinds) or
                                         not kinds)]))
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
            card.configure_encryption(self.config)
            card.save()
            self.index_vcard(card)

    def del_vcards(self, *cards):
        for card in cards:
            self.deindex_vcard(card)
            safe_remove(card.filename)

    def choose_from_address(vcards, *args, **kwargs):
        """
        This method will choose a from address from the available
        profiles, using the given config and lists of addresses as
        a guideline. An address is chosen by assigning each potential
        from address a cumulative score, where scores express roughly
        the following preferences.

        1. If one of the profiles' e-mail addresses is present in the
           headers, prefer that so replies come from the address they
           were sent to.
        2. Else, if we have a preferred profile for communicating
           with a given contact, use that.
        3. Else, if any of the profiles lists one of the addresses
           or their domains as being "in scope", use that.
        4. Else, try and match on domain names.
        5. Finally, use the global default or pick a profile at random.

        >>> vcs = VCardStore(cfg, '/tmp')
        >>> vcs.add_vcards(MailpileVCard(VCardLine('FN:Evil Dude'),
        ...                              VCardLine('EMAIL:d@evil.com'),
        ...                              VCardLine('KIND:profile')),
        ...                MailpileVCard(VCardLine('FN:Guy'),
        ...                              VCardLine('EMAIL;TYPE=PREF:g@f.com'),
        ...                              VCardLine('EMAIL:ok@foo.com'),
        ...                              VCardLine('X-MAILPILE-SCOPE;zzz'),
        ...                              VCardLine('X-MAILPILE-SCOPE;'
        ...                                        'address=ok@foo.com:x.y'),
        ...                              VCardLine('KIND:profile')),
        ...                MailpileVCard(VCardLine('FN:Icelander'),
        ...                              VCardLine('EMAIL:x@bla.is'),
        ...                              VCardLine('KIND:individual')))
        >>> c41 = AddressInfo(u'dude@evil.com', 'Dude')
        >>> c42 = AddressInfo(u'dude@f.com', 'Other dude')
        >>> c31 = AddressInfo(u'd@x.y', 'D at X dot Y')
        >>> c32 = AddressInfo(u'd@zzz', 'D at ZZZ')
        >>> c21 = AddressInfo(u'x@bla.is', 'Icelander')
        >>> c11 = AddressInfo(u'd@evil.com', 'Evil dude')

        # Case 5
        >>> '@' in vcs.choose_from_address(None, [c21]).address
        True

        # Case 4
        >>> vcs.choose_from_address(None, [c41]).address
        u'd@evil.com'
        >>> vcs.choose_from_address(None, [c42]).address
        u'g@f.com'

        # Case 3
        >>> vcs.choose_from_address(None, [c31], [c42, c41]).address
        u'ok@foo.com'
        >>> vcs.choose_from_address(None, [c32], [c42, c41]).address
        u'g@f.com'

        # Case 2
        >>> vcs.get_vcard(c21.address).add(
        ...    VCardLine(name='X-MAILPILE-PREFER-PROFILE',
        ...              value=vcs.get_vcard('g@f.com').random_uid))
        >>> vcs.choose_from_address(None, [c42, c41], [c31, c32],
        ...                               [c21]).address
        u'g@f.com'

        # Case 1
        >>> vcs.choose_from_address(None, [c42, c41], [c31, c32],
        ...                               [c21, c11]).address
        u'd@evil.com'

        """
        fa_list = vcards.choose_from_addresses(*args, **kwargs)
        return fa_list and fa_list[0] or None

    def choose_from_addresses(vcards, config, *address_lists):
        # Generate all the possible e-mail address / vcard pairs
        profile_cards = vcards.find_vcards([], kinds=['profile'])
        matches = []
        for pc in profile_cards:
            for vcl in pc.get_all('email'):
                ai = AddressInfo(vcl.value, pc.fn, vcard=pc)
                if config and config.prefs.default_email == vcl.value:
                    ai.rank *= 1.75
                matches.append((ai, pc))

        # Iterate through all the provided addresses, and update the match
        # scores based on how suitable each is for that address.  We assume
        # the most important addresses are first.
        order = 1.0
        for addrinfo in (ai for src in address_lists for ai in src):
            vcs = vcards.get_vcard(addrinfo.address)
            if vcs:
                sp_rid, sp_e = vcs.sending_profile(addrinfo.address)
            else:
                sp_rid = sp_e = None

            for pc_ai, pc in matches:
                pc_e = pc.sends_to(addrinfo.address)
                pc_d = pc.same_domain(addrinfo.address)

                # Is this address already in the headers?
                if pc_ai.address == addrinfo.address:
                    pc_ai.rank += (100000 * order)

                # Does the user's card have a preference for this profile?
                if sp_rid and sp_rid == pc.random_uid:
                    if sp_e and sp_e == pc_ai.address:
                        pc_ai.rank += (15000 * order)
                    else:
                        pc_ai.rank += (10000 * order)

                # Does the profile card have a prefernce for this user?
                if pc_e == pc_ai.address:
                    pc_ai.rank += (1000 * order)

                # Does the domain at least match??
                if pc_d == pc_ai.address:
                    pc_ai.rank += (100 * order)

            order *= 0.95

        if not matches:
            return None

        matches.sort(key=lambda m: -m[0].rank)
        return [m[0] for m in matches]


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
    MERGE_BY = ['email']
    UPDATE_INDEX = False

    def import_vcards(self, session, vcard_store):
        all_vcards = self.get_vcards()
        updated = []
        for vcard in all_vcards:
            # Some importers want to update the index's idea of what names go
            # with what e-mail addresses. Not all do, but some...
            if (self.UPDATE_INDEX and vcard.fn and
                    session.config and session.config.index):
                for email in vcard.get_all('email'):
                    session.config.index.update_email(email.value,
                                                      name=vcard.fn)

            # Update existing vcards if possible...
            existing = []
            for merge_by in self.MERGE_BY:
                for vcl in vcard.get_all(merge_by):
                    existing.extend(
                        vcard_store.find_vcards_with_line(merge_by, vcl.value))
            for card in existing:
                card.merge(self.config.guid, vcard.as_lines())
                updated.append(card)

            # Otherwise, create new ones.
            if not existing:
                new_vcard = MailpileVCard(config=self.config)
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
