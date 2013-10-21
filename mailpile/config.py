import copy
import cPickle
import io
import json
import os
import re
import ConfigParser

from urllib import quote, unquote

import mailpile.util
from mailpile.httpd import HttpWorker
from mailpile.mailutils import MBX_ID_LEN, OpenMailbox, IncrementalMaildir
from mailpile.search import MailIndex
from mailpile.util import *
from mailpile.ui import Session, BackgroundInteraction
from mailpile.vcard import SimpleVCard
from mailpile.workers import Worker, DumbWorker, Cron


DEFAULT_SENDMAIL = '|/usr/sbin/sendmail -i %(rcpt)s'


class InvalidKeyError(ValueError):
    pass


class CommentedEscapedConfigParser(ConfigParser.RawConfigParser):
    """
    This is a ConfigParser that allows embedded comments and safely escapes
    and encodes/decodes values that include funky characters.

    >>> cfg.sys.debug = u'm\\xe1ny\\nlines\\nof\\nbelching  '
    >>> cecp = CommentedEscapedConfigParser()
    >>> cecp.readfp(io.BytesIO(cfg.as_config_bytes()))
    >>> cecp.get('config/sys: Technical system settings', 'debug'
    ...          ) == cfg.sys.debug
    True

    >>> cecp.items('config/sys: Technical system settings')
    [(u'debug', u'm\\xe1ny\\nlines\\nof\\nbelching  ')]
    """
    def set(self, section, key, value, comment):
        key = unicode(key).encode('utf-8')
        section = unicode(section).encode('utf-8')
        value = quote(unicode(value).encode('utf-8'), safe=' /')
        if value.endswith(' '):
            value = value[:-1] + '%20'
        if comment:
            pad = ' ' * (25 - len(key) - len(value)) + ' ; '
            value = '%s%s%s' % (value, pad, comment)
        return ConfigParser.RawConfigParser.set(self, section, key, value)

    def get(self, section, key):
        key = unicode(key).encode('utf-8')
        section = unicode(section).encode('utf-8')
        value = ConfigParser.RawConfigParser.get(self, section, key)
        return unquote(value).decode('utf-8')

    def items(self, section):
        return [(k.decode('utf-8'), unquote(i).decode('utf-8')) for k, i
                in ConfigParser.RawConfigParser.items(self, section)]


def _MakeCheck(pcls, rules):
    class CD(pcls):
        _RULES = rules
    return CD


def _SlugCheck(slug, allow=''):
    """
    Verify that a string is a valid URL slug.

    >>> _SlugCheck('_Foo-bar.5')
    '_foo-bar.5'

    >>> _SlugCheck('Bad Slug')
    Traceback (most recent call last):
        ...
    ValueError: Invalid URL slug: Bad Slug

    >>> _SlugCheck('Bad/Slug')
    Traceback (most recent call last):
        ...
    ValueError: Invalid URL slug: Bad/Slug
    """
    if not slug == CleanText(unicode(slug),
                             banned=(CleanText.NONDNS.replace(allow, ''))
                             ).clean:
        raise ValueError('Invalid URL slug: %s' % slug)
    return slug.lower()


def _SlashSlugCheck(slug):
    """
    Verify that a string is a valid URL slug (slashes allowed).

    >>> _SlashSlugCheck('Okay/Slug')
    'okay/slug'
    """
    return _SlugCheck(slug, allow='/')


def _HostNameCheck(host):
    """
    Verify that a string is a valid host-name, return it lowercased.

    >>> _HostNameCheck('foo.BAR.baz')
    'foo.bar.baz'

    >>> _HostNameCheck('127.0.0.1')
    '127.0.0.1'

    >>> _HostNameCheck('not/a/hostname')
    Traceback (most recent call last):
        ...
    ValueError: Invalid hostname: not/a/hostname
    """
    # FIXME: Check DNS?
    if not unicode(host) == CleanText(unicode(host),
                                      banned=CleanText.NONDNS).clean:
        raise ValueError('Invalid hostname: %s' % host)
    return str(host).lower()


def _B36Check(b36val):
    """
    Verify that a string is a valid path base-36 integer.

    >>> _B36Check('aa')
    'aa'

    >>> _B36Check('.')
    Traceback (most recent call last):
        ...
    ValueError: invalid ...
    """
    int(b36val, 36)
    return str(b36val).lower()


def _PathCheck(path):
    """
    Verify that a string is a valid path, make it absolute.

    >>> _PathCheck('/etc/../')
    '/'

    >>> _PathCheck('/no/such/path')
    Traceback (most recent call last):
        ...
    ValueError: File/directory does not exist: /no/such/path
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise ValueError('File/directory does not exist: %s' % path)
    return os.path.abspath(path)


def _FileCheck(path):
    """
    Verify that a string is a valid path to a file, make it absolute.

    >>> _FileCheck('/etc/../etc/passwd')
    '/etc/passwd'

    >>> _FileCheck('/')
    Traceback (most recent call last):
        ...
    ValueError: Not a file: /
    """
    path = _PathCheck(path)
    if not os.path.isfile(path):
        raise ValueError('Not a file: %s' % path)
    return path


def _DirCheck(path):
    """
    Verify that a string is a valid path to a directory, make it absolute.

    >>> _DirCheck('/etc/../')
    '/'

    >>> _DirCheck('/etc/passwd')
    Traceback (most recent call last):
        ...
    ValueError: Not a directory: /etc/passwd
    """
    path = _PathCheck(path)
    if not os.path.isdir(path):
        raise ValueError('Not a directory: %s' % path)
    return path


def _NewPathCheck(path):
    """
    Verify that a string is a valid path to a directory, make it absolute.

    >>> _NewPathCheck('/magic')
    '/magic'

    >>> _NewPathCheck('/no/such/path/magic')
    Traceback (most recent call last):
        ...
    ValueError: File/directory does not exist: /no/such/path
    """
    _PathCheck(os.path.dirname(path))
    return os.path.abspath(path)


def RuledContainer(pcls):
    """
    Factory for abstract 'container with rules' class. See ConfigDict for
    details, examples and tests.
    """

    class RC(pcls):
        RULE_COMMENT = 0
        RULE_CHECKER = 1
        # Reserved ...
        RULE_DEFAULT = -1
        RULE_CHECK_MAP = {
           'bool': bool,
           'b36': _B36Check,
           'dir': _DirCheck,
           'directory': _DirCheck,
           'email': unicode,  # FIXME: Make more strict
           'False': False, 'false': False,
           'file': _FileCheck,
           'float': float,
           'hostname': _HostNameCheck,
           'int': int,
           'long': long,
           'multiline': unicode,
           'mailroute': unicode,  # FIXME: Make more strict
           'new file': _NewPathCheck,
           'new dir': _NewPathCheck,
           'new directory': _NewPathCheck,
           'path': _PathCheck,
           str: unicode,
           'slashslug': _SlashSlugCheck,
           'slug': _SlugCheck,
           'str': unicode,
           'True': True, 'true': True,
           'unicode': unicode,
           # TODO: Create 'email' and 'url' and other high level checks
        }
        _NAME = 'container'
        _RULES = None

        def __init__(self, *args, **kwargs):
            rules = kwargs.get('_rules', self._RULES or {})
            self._name = kwargs.get('_name', self._NAME)
            self._comment = kwargs.get('_comment', None)
            for kw in ('_rules', '_comment', '_name'):
                if kw in kwargs:
                    del kwargs[kw]

            pcls.__init__(self)
            self._key = self._name
            self.set_rules(rules)
            self.update(*args, **kwargs)

        def __str__(self):
            return json.dumps(self, sort_keys=True, indent=2)

        def __unicode__(self):
            return json.dumps(self, sort_keys=True, indent=2)

        def as_config_bytes(self, private=True):
            of = io.BytesIO()
            self.as_config(private=private).write(of)
            return of.getvalue()

        def as_config(self, config=None, private=True):
            config = config or CommentedEscapedConfigParser()
            section = self._name
            if self._comment:
                section += ': %s' % self._comment
            added_section = False

            keys = self.rules.keys()
            if not keys or '_any' in keys:
                keys.extend(self.keys())
            keys = [k for k in sorted(set(keys)) if k != '_any']
            set_keys = set(self.keys())

            for key in keys:
                if not hasattr(self[key], 'as_config'):
                    if key in self.rules:
                        comment = self.rules[key][self.RULE_COMMENT]
                    else:
                        comment = ''
                    value = unicode(self[key])
                    if value is not None and value != '':
                        if key not in set_keys:
                            key = ';' + key
                            comment = '(default) ' + comment
                        if comment:
                            pad = ' ' * (30 - len(key) - len(value)) + ' ; '
                        else:
                            pad = ''
                        if not added_section:
                            config.add_section(str(section))
                            added_section = True
                        config.set(section, key, value, comment)
            for key in keys:
                if hasattr(self[key], 'as_config'):
                    self[key].as_config(config=config)

            return config

        def reset(self, rules=True, data=True):
            raise Exception('Override this')

        def set_rules(self, rules):
            assert(isinstance(rules, dict))
            self.reset()
            for key, rule in rules.iteritems():
                self.add_rule(key, rule)

        def add_rule(self, key, rule):
            assert(isinstance(rule, (list, tuple)))
            assert(key == CleanText(key, banned=CleanText.NONVARS).clean)
            assert(not hasattr(self, key))
            rule = list(rule[:])
            self.rules[key] = rule
            check = rule[self.RULE_CHECKER]
            try:
                check = self.RULE_CHECK_MAP.get(check, check)
                rule[self.RULE_CHECKER] = check
            except TypeError:
                pass

            name = '%s/%s' % (self._name, key)
            comment = rule[self.RULE_COMMENT]
            value = rule[self.RULE_DEFAULT]

            if type(check) == dict:
                check_rule = rule[:]
                check_rule[self.RULE_DEFAULT] = None
                check_rule[self.RULE_CHECKER] = _MakeCheck(ConfigDict, check)
                check_rule = {'_any': check_rule}
            else:
                check_rule = None

            if isinstance(value, dict):
                rule[self.RULE_CHECKER] = False
                if check_rule:
                    pcls.__setitem__(self, key, ConfigDict(_name=name,
                                                           _comment=comment,
                                                           _rules=check_rule))
                else:
                    pcls.__setitem__(self, key, ConfigDict(_name=name,
                                                           _comment=comment,
                                                           _rules=value))

            elif isinstance(value, list):
                rule[self.RULE_CHECKER] = False
                if check_rule:
                    pcls.__setitem__(self, key, ConfigList(_name=name,
                                                           _comment=comment,
                                                           _rules=check_rule))
                else:
                    pcls.__setitem__(self, key, ConfigList(_name=name,
                                                           _comment=comment,
                                                           _rules={
                        '_any': [rule[self.RULE_COMMENT], check, None]
                    }))

            elif not isinstance(value, (type(None), int, long, bool,
                                        float, str, unicode)):
                raise TypeError(('Invalid type for default %s = %s'
                                 ) % (name, value))

        def __fixkey__(self, key):
            return key

        def get_rule(self, key):
            key = self.__fixkey__(key)
            if key not in self.rules:
                if '_any' in self.rules:
                    return self.rules['_any']
                raise InvalidKeyError(('Invalid key for %s: %s'
                                       ) % (self._name, key))
            return self.rules[key]

        def walk(self, path, parent=0):
            if '.' in path:
                sep = '.'
            else:
                sep = '/'
            path_parts = path.split(sep)
            cfg = self
            if parent:
                vlist = path_parts[-parent:]
                path_parts[-parent:] = []
            else:
                vlist = []
            for part in path_parts:
                cfg = cfg[part]
            if parent:
                return tuple([cfg] + vlist)
            else:
                return cfg

        def get(self, key, default=None):
            key = self.__fixkey__(key)
            if key in self:
                return pcls.__getitem__(self, key)
            if default is None and key in self.rules:
                return self.rules[key][self.RULE_DEFAULT]
            return default

        def __getitem__(self, key):
            key = self.__fixkey__(key)
            if key in self.rules or '_any' in self.rules:
                return self.get(key)
            return pcls.__getitem__(self, key)

        def __getattr__(self, attr, default=None):
            try:
                rules = self.__getattribute__('rules')
            except AttributeError:
                rules = {}
            if self.__fixkey__(attr) in rules or '_any' in rules:
                return self[attr]
            else:
                return self.__getattribute__(attr)

        def __setattr__(self, attr, value):
            try:
                rules = self.__getattribute__('rules')
            except AttributeError:
                rules = {}
            if self.__fixkey__(attr) in rules:
                self.__setitem__(attr, value)
            else:
                pcls.__setattr__(self, attr, value)

        def __passkey__(self, key, value):
            if hasattr(value, '_key'):
                value._key = key
                value._name = '%s/%s' % (self._name, key)

        def __createkey_and_setitem__(self, key, value):
            pcls.__setitem__(self, key, value)

        def __setitem__(self, key, value):
            key = self.__fixkey__(key)
            checker = self.get_rule(key)[self.RULE_CHECKER]
            if not checker is True:
                if checker is False:
                    raise ValueError(('Modifying %s/%s is not allowed'
                                      ) % (self._name, key))
                if isinstance(checker, (list, set, tuple)):
                    if value not in checker:
                        raise ValueError(('Invalid value for %s/%s: %s'
                                          ) % (self._name, key, value))
                elif isinstance(checker, (type, type(RuledContainer))):
                    try:
                        value = checker(value)
                    except (ValueError, TypeError):
                        raise ValueError(('Invalid value for %s/%s: %s'
                                          ) % (self._name, key, value))
                else:
                    raise Exception(('Unknown constraint for %s/%s: %s'
                                     ) % (self._name, key, checker))
            self.__passkey__(key, value)
            self.__createkey_and_setitem__(key, value)

        def extend(self, src):
            for val in src:
                self.append(val)

        def __iadd__(self, src):
            self.extend(src)
            return self

    return RC


class ConfigList(RuledContainer(list)):
    """
    A sanity-checking, self-documenting list of program settings.

    Instances of this class are usually contained within a ConfigDict.

    >>> lst = ConfigList(_rules={'_any': ['We only like ints', int, 0]})
    >>> lst.append('1')
    '0'
    >>> lst.extend([2, '3'])
    >>> lst
    [1, 2, 3]

    >>> lst += ['1', '2']
    >>> lst
    [1, 2, 3, 1, 2]

    >>> lst.extend(range(0, 100))
    >>> lst['c'] == lst[int('c', 36)]
    True
    """
    def reset(self, rules=True, data=True):
        if rules:
            self.rules = {}
        if data:
            self[:] = []

    def __createkey_and_setitem__(self, key, value):
        if key == len(self):
            list.append(self, value)
        else:
            list.__setitem__(self, key, value)

    def append(self, value):
        list.append(self, None)
        try:
            self[len(self) - 1] = value
            return b36(len(self) - 1)
        except:
            self[len(self) - 1:] = []
            raise

    def __passkey__(self, key, value):
        if hasattr(value, '_key'):
            key = b36(key).lower()
            value._key = key
            value._name = '%s/%s' % (self._name, key)

    def __fixkey__(self, key):
        if isinstance(key, (str, unicode)):
            try:
                key = int(key, 36)
            except ValueError:
                pass
        return key

    def __getitem__(self, key):
        return list.__getitem__(self, self.__fixkey__(key))

    def keys(self):
        return [b36(i).lower() for i in range(0, len(self))]

    def values(self):
        return self[:]

    def update(self, *args):
        for l in args:
            l = list(l)
            for i in range(0, len(self)):
                self[i] = l[i]
            for i in range(len(self), len(l)):
                self.append(l[i])


class ConfigDict(RuledContainer(dict)):
    """
    A sanity-checking, self-documenting dictionary of program settings.

    The object must be initialized with a dictionary which describes in
    a structured way what variables exist, what their legal values are,
    and what their defaults are and what they are for.

    Each variable definition expects three values:
       1. A human readable description of what the variable is
       2. A data type / sanity check
       3. A default value

    If the sanity check is itself a dictionary of rules, values are expected
    to be dictionaries or lists of items that match the rules defined. This
    should be used with an empty list or dictionary as a default value.

    Configuration data can be nested by including a dictionary of further
    rules in place of the default value.

    If the default value is an empty list, it is assumed to be a list of
    values of the type specified.

    Examples:

    >>> pot = ConfigDict(_rules={'potatoes': ['How many potatoes?', 'int', 0],
    ...                          'carrots': ['How many carrots?', int, 99],
    ...                          'liquids': ['Fluids we like', False, {
    ...                                         'water': ['Liters', int, 0],
    ...                                         'vodka': ['Liters', int, 12]
    ...                                      }],
    ...                          'tags': ['Tags', {'c': ['C', int, 0],
    ...                                            'x': ['X', str, '']}, []],
    ...                          'colors': ['Colors', ('red', 'blue'), []]})
    >>> sorted(pot.keys()), sorted(pot.values())
    (['colors', 'liquids', 'tags'], [{...}, [], []])

    >>> pot['potatoes'] = pot['liquids']['vodka'] = "123"
    >>> pot['potatoes']
    123
    >>> pot['liquids']['vodka']
    123
    >>> pot['carrots']
    99

    >>> pot.walk('liquids.vodka')
    123
    >>> pot.walk('liquids/vodka', parent=True)
    ({...}, 'vodka')

    >>> pot['colors'].append('red')
    '0'
    >>> pot['colors'].extend(['blue', 'red', 'red'])
    >>> pot['colors']
    ['red', 'blue', 'red', 'red']

    >>> pot['tags'].append({'c': '123', 'x': 'woots'})
    '0'
    >>> pot['tags'][0]['c']
    123
    >>> pot['tags'].append({'z': 'invalid'})
    Traceback (most recent call last):
        ...
    ValueError: Invalid value for config/tags/1: ...

    >>> pot['evil'] = 123
    Traceback (most recent call last):
        ...
    InvalidKeyError: Invalid key for config: evil
    >>> pot['liquids']['evil'] = 123
    Traceback (most recent call last):
        ...
    InvalidKeyError: Invalid key for config/liquids: evil
    >>> pot['potatoes'] = "moo"
    Traceback (most recent call last):
        ...
    ValueError: Invalid value for config/potatoes: moo
    >>> pot['colors'].append('green')
    Traceback (most recent call last):
        ...
    ValueError: Invalid value for config/colors/4: green

    >>> pot.rules['potatoes']
    ['How many potatoes?', <type 'int'>, 0]

    >>> isinstance(pot['liquids'], ConfigDict)
    True
    """
    _NAME = 'config'

    def reset(self, rules=True, data=True):
        if rules:
            self.rules = {}
        if data:
            for key in self.keys():
                if hasattr(self[key], 'reset'):
                    self[key].reset(rules=rules, data=data)
                else:
                    dict.__delitem__(self, key)

    def all_keys(self):
        keys = set(self.keys()) | set(self.rules.keys()) - set(['_any'])
        return list(keys)

    def append(self, value):
        """Add to the dict using an autoselected key"""
        if '_any' in self.rules:
            k = b36(max([int(k, 36) for k in self.keys()] + [-1]) + 1).lower()
            self[k] = value
            return k
        else:
            raise UsageError('Cannot append to fixed dict')

    def update(self, *args, **kwargs):
        """Reimplement update, so it goes through our sanity checks."""
        for src in args:
            if hasattr(src, 'keys'):
                for key in src:
                    self[key] = src[key]
            else:
                for key, val in src:
                    self[key] = val
        for key in kwargs:
            self[key] = kwargs[key]


class PathDict(ConfigDict):
    _RULES = {
        '_any': ['Data directory', 'directory', '']
    }


class ConfigManager(ConfigDict):
    """
    This class manages the live global mailpile configuration. This includes
    the settings themselves, as well as global objects like the index and
    references to any background worker threads.
    """
    DEFAULT_WORKDIR = os.environ.get('MAILPILE_HOME',
                                     os.path.expanduser('~/.mailpile'))

    def __init__(self, workdir=None, rules={}):
        ConfigDict.__init__(self, _rules=rules)
        self.workdir = workdir or self.DEFAULT_WORKDIR
        self.conffile = os.path.join(self.workdir, 'mailpile.cfg')

        self.background = None
        self.cron_worker = None
        self.http_worker = None
        self.dumb_worker = self.slow_worker = DumbWorker('Dumb worker', None)

        self.index = None
        self._vcards = {}
        self._mbox_cache = {}
        self._running = {}

    def _mkworkdir(self, session):
        if not os.path.exists(self.workdir):
            if session:
                session.ui.notify('Creating: %s' % self.workdir)
            os.mkdir(self.workdir)

    def parse_config(self, session, data, source='internal'):
        """
        Parse a config file fragment. Invalid data will be ignored, but will
        generate warnings in the session UI. Returns True on a clean parse,
        False if any of the settings were bogus.

        >>> cfg.parse_config(session, '[config/sys]\\nfd_cache_size = 123\\n')
        True
        >>> cfg.sys.fd_cache_size
        123

        >>> cfg.parse_config(session, '[config/bogus]\\nblabla = bla\\n')
        False
        >>> [l[1] for l in session.ui.log_buffer if 'bogus' in l[1]][0]
        u'Invalid (internal): section config/bogus does not exist'

        >>> cfg.parse_config(session, '[config/sys]\\nhistory_length = 321\\n'
        ...                                          'bogus_variable = 456\\n')
        False
        >>> cfg.sys.history_length
        321
        >>> [l[1] for l in session.ui.log_buffer if 'bogus_var' in l[1]][0]
        u'Invalid (internal): section config/sys, ...

        >>> cfg.parse_config(session, '[config/tags/a]\\nname = TagName\\n')
        True
        >>> cfg.tags['a']._key
        'a'
        >>> cfg.tags['a'].name
        u'TagName'
        """
        parser = CommentedEscapedConfigParser()
        parser.readfp(io.BytesIO(str(data)))
        okay = True
        for section in parser.sections():
            cfgpath = section.split(':')[0].split('/')[1:]
            cfg = self
            for part in cfgpath:
                if part in cfg:
                    cfg = cfg[part]
                elif '_any' in cfg.rules:
                    if isinstance(cfg, list):
                        cfg.append({})
                    else:
                        cfg[part] = {}
                    cfg = cfg[part]
                else:
                    if session:
                        msg = (u'Invalid (%s): section %s does not exist'
                               ) % (source, section)
                        session.ui.warning(msg)
                    okay = False
            for var, val in okay and parser.items(section) or []:
                try:
                    cfg[var] = val
                except (ValueError, KeyError):
                    if session:
                        msg = (u'Invalid (%s): section %s, variable %s'
                               ) % (source, section, var)
                        session.ui.warning(msg)
                    okay = False
        return okay

    def load(self, session, filename=None):
        self._mkworkdir(session)
        self.index = None
        self.reset(rules=False, data=True)

        try:
            ocfg = os.path.join(self.workdir, 'config.rc')
            ocl = OldConfigLoader(filename=ocfg)
            if ocl.export(self) and session:
                session.ui.warning(('WARNING: Imported old config from %s'
                                    ) % ocfg)
            elif session:
                session.ui.warning(('WARNING: Failed to import config from %s'
                                    ) % ocfg)
        except:
            pass

        filename = filename or self.conffile
        lines = []
        try:
            fd = open(filename, 'rb')
            try:
                decrypt_and_parse_lines(fd, lambda l: lines.append(l))
            except ValueError:
                pass
            fd.close()
        except IOError:
            pass

        self.parse_config(session, '\n'.join(lines), source=filename)
        self.load_vcards(session)

    def save(self):
        self._mkworkdir(None)
        fd = gpg_open(self.conffile, self.prefs.get('gpg_recipient'), 'wb')
        fd.write(self.as_config_bytes(private=True))
        fd.close()

    def clear_mbox_cache(self):
        self._mbox_cache = {}

    def get_mailboxes(self):
        def fmt_mbxid(k):
            k = b36(int(k, 36))
            if len(k) > MBX_ID_LEN:
                raise ValueError('Mailbox ID too large: %s' % k)
            return (('0' * MBX_ID_LEN) + k)[-MBX_ID_LEN:]
        mailboxes = [fmt_mbxid(k) for k in self.sys.mailbox.keys()]
        mailboxes.sort()
        return [(k, self.sys.mailbox[k]) for k in mailboxes]

    def is_editable_message(self, msg_info):
        for ptr in msg_info[MailIndex.MSG_PTRS].split(', '):
            if not self.is_editable_mailbox(ptr[: MBX_ID_LEN]):
                return False
        editable = False
        for tid in msg_info[MailIndex.MSG_TAGS].split(', '):
            try:
                if tid in self.sys.writable_tags:
                    editable = True
            except KeyError:
                pass
        return editable

    def is_editable_mailbox(self, mailbox_id):
        mailbox_id = (mailbox_id is None and -1) or int(mailbox_id, 36)
        local_mailbox_id = int(self.sys.get('local_mailbox_id', 'ZZZZZ'), 36)
        return (mailbox_id == local_mailbox_id)

    def open_mailbox(self, session, mailbox_id):
        try:
            mbx_id = mailbox_id.lower()
            mfn = self.sys.mailbox[mbx_id]
            pfn = os.path.join(self.workdir, 'pickled-mailbox.%s' % mbx_id)
        except KeyError:
            raise NoSuchMailboxError('No such mailbox: %s' % mbx_id)

        try:
            if mbx_id in self._mbox_cache:
                self._mbox_cache[mbx_id].update_toc()
            else:
                if session:
                    session.ui.mark('%s: Updating: %s' % (mbx_id, mfn))
                self._mbox_cache[mbx_id] = cPickle.load(open(pfn, 'r'))
        except:
            if session.config.sys.debug:
                import traceback
                traceback.print_exc()
            if session:
                session.ui.mark(('%s: Opening: %s (may take a while)'
                                 ) % (mbx_id, mfn))
            mbox = OpenMailbox(mfn)
            mbox.editable = self.is_editable_mailbox(mbx_id)
            mbox.save(session, to=pfn)
            self._mbox_cache[mbx_id] = mbox

        return self._mbox_cache[mbx_id]

    def open_local_mailbox(self, session):
        local_id = self.sys.get('local_mailbox_id', None)
        if not local_id:
            mailbox = os.path.join(self.workdir, 'mail')
            mbx = IncrementalMaildir(mailbox)
            local_id = self.sys.mailbox.append(mailbox)
            local_id = (('0' * MBX_ID_LEN) + local_id)[-MBX_ID_LEN:]
            self.sys.local_mailbox_id = local_id
        else:
            local_id = (('0' * MBX_ID_LEN) + local_id)[-MBX_ID_LEN:]
        return local_id, self.open_mailbox(session, local_id)

    def get_profile(self, email=None):
        find = email or self.prefs.get('default_email', None)
        for profile in self.profiles:
            if profile.email == find or not find:
                if not email:
                    self.prefs.default_email = profile.email
                return profile
        return {
            'name': None,
            'email': find,
            'signature': None,
            'route': DEFAULT_SENDMAIL
        }

    def get_sendmail(self, frm, rcpts='-t'):
        return self.get_profile(frm)['route'] % {
            'rcpt': ', '.join(rcpts)
        }

    def data_directory(self, ftype, mode='rb', mkdir=False):
        """
        Return the path to a data directory for a particular type of file
        data, optionally creating the directory if it is missing.

        >>> p = cfg.data_directory('html_theme', mode='r', mkdir=False)
        >>> p == os.path.abspath('static/default')
        True
        """
        # This should raise a KeyError if the ftype is unrecognized
        bpath = self.sys.path.get(ftype)
        if not bpath.startswith('/'):
            cpath = os.path.join(self.workdir, bpath)
            if os.path.exists(cpath) or 'w' in mode:
                bpath = cpath
                if mkdir and not os.path.exists(cpath):
                    os.mkdir(cpath)
            else:
                bpath = os.path.join(os.path.dirname(__file__), '..', bpath)
        return os.path.abspath(bpath)

    def history_file(self):
        return os.path.join(self.workdir, 'history')

    def mailindex_file(self):
        return os.path.join(self.workdir, 'mailpile.idx')

    def postinglist_dir(self, prefix):
        d = os.path.join(self.workdir, 'search')
        if not os.path.exists(d):
            os.mkdir(d)
        d = os.path.join(d, prefix and prefix[0] or '_')
        if not os.path.exists(d):
            os.mkdir(d)
        return d

    def get_index(self, session):
        if self.index:
            return self.index
        idx = MailIndex(self)
        idx.load(session)
        self.index = idx
        return idx

    def open_file(self, ftype, fpath, mode='rb', mkdir=False):
        if '..' in fpath:
            raise ValueError('Parent paths are not allowed')
        bpath = self.data_directory(ftype, mode=mode, mkdir=mkdir)
        fpath = os.path.join(bpath, fpath)
        return fpath, open(fpath, mode)

    def load_vcards(self, session):
        try:
            vcard_dir = self.data_directory('vcards')
            for fn in os.listdir(vcard_dir):
                try:
                    c = SimpleVCard().load(os.path.join(vcard_dir, fn))
                    c.gpg_recipient = lambda: self.prefs.get('gpg_recipient')
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

    def index_vcard(self, c):
        if c.kind == 'individual':
            for email, attrs in c.get('EMAIL', []):
                self._vcards[email.lower()] = c
        else:
            for handle, attrs in c.get('NICKNAME', []):
                self._vcards[handle.lower()] = c
        self._vcards[c.random_uid] = c

    def deindex_vcard(self, c):
        for email, attrs in c.get('EMAIL', []):
            if email.lower() in self._vcards:
                if c.kind == 'individual':
                    del self._vcards[email.lower()]
        for handle, attrs in c.get('NICKNAME', []):
            if handle.lower() in self._vcards:
                if c.kind != 'individual':
                    del self._vcards[handle.lower()]
        if c.random_uid in self._vcards:
            del self._vcards[c.random_uid]

    def get_vcard(self, email):
        return self._vcards.get(email.lower(), None)

    def find_vcards(self, terms, kinds=['individual']):
        results, vcards = [], self._vcards
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
        results = [vcards[c] for c in results[0]]
        results.sort(key=lambda k: k.fn)
        return results

    def add_vcard(self, handle, name=None, kind=None):
        vcard_dir = self.data_directory('vcards', mode='w', mkdir=True)
        c = SimpleVCard()
        c.filename = os.path.join(vcard_dir, c.random_uid) + '.vcf'
        c.gpg_recipient = lambda: self.prefs.get('gpg_recipient')
        if kind == 'individual':
            c.email = handle
        else:
            c['NICKNAME'] = handle
        if name is not None:
            c.fn = name
        if kind is not None:
            c.kind = kind
        self.index_vcard(c)
        return c.save()

    def del_vcard(self, email):
        vcard = self.get_vcard(email)
        try:
            if vcard:
                self.deindex_vcard(vcard)
                os.remove(vcard.filename)
                return True
            else:
                return False
        except (OSError, IOError):
            return False

    def prepare_workers(config, session, daemons=False):
        # Set globals from config first...
        mailpile.util.APPEND_FD_CACHE_SIZE = config.get('fd_cache_size',
                                                        APPEND_FD_CACHE_SIZE)

        if not config.background:
            # Create a silent background session
            config.background = Session(config)
            config.background.ui = BackgroundInteraction(config)
            config.background.ui.block()

        # Start the workers
        if config.slow_worker == config.dumb_worker:
            config.slow_worker = Worker('Slow worker', session)
            config.slow_worker.start()
        if daemons and not config.cron_worker:
            config.cron_worker = Cron('Cron worker', session)
            config.cron_worker.start()

            # Schedule periodic rescanning, if requested.
            rescan_interval = config.prefs.rescan_interval
            if rescan_interval:
                def rescan():
                    if 'rescan' not in config._running:
                        rsc = Rescan(session, 'rescan')
                        rsc.serialize = False
                        config.slow_worker.add_task(None, 'Rescan', rsc.run)
                config.cron_worker.add_task('rescan', rescan_interval, rescan)

        if daemons and not config.http_worker:
            # Start the HTTP worker if requested
            sspec = (config.sys.http_host, config.sys.http_port)
            if sspec[0].lower() != 'disabled' and sspec[1] >= 0:
                config.http_worker = HttpWorker(session, sspec)
                config.http_worker.start()

    def stop_workers(config):
        for w in (config.http_worker, config.slow_worker, config.cron_worker):
            if w:
                w.quit()


# FIXME: Delete this when it is no longer needed.
class OldConfigLoader:
    """
    Load legacy config data into new config.

    >>> ocl = OldConfigLoader()
    >>> ocl.lines = ['obfuscate_index = 1234',
    ...              'tag:0 = Honk/Honk']
    >>> ocl.export(cfg)
    True
    >>> cfg.prefs.obfuscate_index
    u'1234'
    >>> cfg.tags['0'].slug
    'honk/honk'
    """
    def __init__(self, filename=None):
        self.lines = []
        if filename:
            try:
                fd = open(filename, 'rb')
                try:
                    decrypt_and_parse_lines(fd, lambda l: self.lines.append(l))
                except ValueError:
                    pass
                fd.close()
            except IOError:
                pass

    def parse(self, line):
        var, value = line.split(' = ', 1)
        if ':' in var:
            cat, var = var.split(':', 1)
        else:
            cat = None
        return cat, var, value

    def export(self, config):
        errors = 0
        for line in self.lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                cat, var, val = self.parse(line)
                if not cat:
                    for sect in (config.sys, config.prefs):
                        if var in sect.rules:
                            sect[var] = val
                elif cat == 'filter':
                    config.filters[var] = {'comment': val}
                elif cat == 'filter_tags':
                    config.filters[var]['tags'] = val
                elif cat == 'filter_terms':
                    config.filters[var]['terms'] = val
                elif cat == 'mailbox':
                    config.sys.mailbox[var] = val
                elif cat == 'my_from':
                    if not config.get_profile(email=var).get('name'):
                        config.profiles.append({
                            'email': var,
                            'name': val,
                        })
                elif cat == 'my_sendmail':
                    config.get_profile(email=var)['route'] = val
                elif cat == 'tag':
                    config.tags[var] = {'name': val, 'slug': val.lower()}

            except Exception, e:
                print 'Could not parse (%s): %s' % (e, line)
                errors += 1
        for writable in ('Blank', 'Drafts'):
            if writable not in config.sys.writable_tags:
                tid = config.get_tag_id(writable)
                if tid:
                    config.sys.writable_tags.append(tid)
        return (errors == 0)


##############################################################################

if __name__ == "__main__":
    import doctest
    import sys
    import mailpile.config
    import mailpile.defaults
    import mailpile.plugins.tags
    import mailpile.ui

    cfg = mailpile.config.ConfigManager(rules=mailpile.defaults.CONFIG_RULES)
    session = mailpile.ui.Session(cfg)
    session.ui.block()

    for tn in range(0, 11):
        cfg.tags.append({'name': 'Test Tag %s' % tn})

    assert(cfg.tags.a['name'] == 'Test Tag 10')
    assert(cfg.sys.http_port ==
           mailpile.defaults.CONFIG_RULES['sys'][-1]['http_port'][-1])
    assert(cfg.sys.path.vcards == 'vcards')
    assert(cfg.walk('sys.path.vcards') == 'vcards')

    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={'cfg': cfg,
                                          'session': session})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
