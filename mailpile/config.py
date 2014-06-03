import copy
import cPickle
import io
import json
import os
import random
import re
import threading
import traceback
import ConfigParser
from gettext import translation, gettext, NullTranslations
from gettext import gettext as _

from jinja2 import Environment, BaseLoader, TemplateNotFound

from urllib import quote, unquote
from mailpile.crypto.streamer import DecryptingStreamer

try:
    import ssl
except ImportError:
    ssl = None

try:
    import sockschain as socks
except ImportError:
    try:
        import socks
    except ImportError:
        socks = None

from mailpile.commands import Rescan
from mailpile.eventlog import EventLog
from mailpile.httpd import HttpWorker
from mailpile.mailboxes import MBX_ID_LEN, OpenMailbox, NoSuchMailboxError
from mailpile.mailboxes import wervd
from mailpile.search import MailIndex
from mailpile.util import *
from mailpile.ui import Session, BackgroundInteraction
from mailpile.vcard import SimpleVCard, VCardStore
from mailpile.workers import Worker, DumbWorker, Cron


def ConfigPrinter(cfg, indent=''):
    rv = []
    if isinstance(cfg, dict):
        pairer = cfg.iteritems()
    else:
        pairer = enumerate(cfg)
    for key, val in pairer:
        if hasattr(val, 'rules'):
            preamble = '[%s: %s] ' % (val._NAME, val._COMMENT)
        else:
            preamble = ''
        if isinstance(val, (dict, list, tuple)):
            if isinstance(val, dict):
                b, e = '{', '}'
            else:
                b, e = '[', ']'
            rv.append(('%s: %s%s\n%s\n%s'
                       '' % (key, preamble, b, ConfigPrinter(val, '  '), e)
                       ).replace('\n  \n', ''))
        elif isinstance(val, (str, unicode)):
            rv.append('%s: "%s"' % (key, val))
        else:
            rv.append('%s: %s' % (key, val))
    return indent + ',\n'.join(rv).replace('\n', '\n'+indent)


def getLocaleDirectory():
    """Get the gettext translation object, no matter where our CWD is"""
    # NOTE: MO files are loaded from the directory where the scripts reside in
    return os.path.join(os.path.dirname(__file__), "..", "locale")


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


def _MakeCheck(pcls, name, comment, rules):
    class Checker(pcls):
        _NAME = name
        _RULES = rules
        _COMMENT = comment
    return Checker


def _BoolCheck(value):
    """
    Convert common yes/no strings into booleal values.

    >>> _BoolCheck('yes')
    True
    >>> _BoolCheck('no')
    False

    >>> _BoolCheck('true')
    True
    >>> _BoolCheck('false')
    False

    >>> _BoolCheck('on')
    True
    >>> _BoolCheck('off')
    False

    >>> _BoolCheck('wiggle')
    Traceback (most recent call last):
        ...
    ValueError: Invalid boolean: wiggle
    """
    if value in (True, False):
        return value
    if value.lower() in ('1', 'true', 'yes', 'on',
                         _('true'), _('yes'), _('on')):
        return True
    if value.lower() in ('0', 'false', 'no', 'off',
                         _('false'), _('no'), _('off')):
        return False
    raise ValueError(_('Invalid boolean: %s') % value)


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
        raise ValueError(_('Invalid URL slug: %s') % slug)
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
    # FIXME: We do not want to check the network, but rules for DNS are
    #        still stricter than this so a static check could do more.
    if not unicode(host) == CleanText(unicode(host),
                                      banned=CleanText.NONDNS).clean:
        raise ValueError(_('Invalid hostname: %s') % host)
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
        raise ValueError(_('File/directory does not exist: %s') % path)
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
        raise ValueError(_('Not a file: %s') % path)
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
        raise ValueError(_('Not a directory: %s') % path)
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


class IgnoreValue(Exception):
    pass


def _IgnoreCheck(data):
    raise IgnoreValue()


def RuledContainer(pcls):
    """
    Factory for abstract 'container with rules' class. See ConfigDict for
    details, examples and tests.
    """

    class _RuledContainer(pcls):
        RULE_COMMENT = 0
        RULE_CHECKER = 1
        # Reserved ...
        RULE_DEFAULT = -1
        RULE_CHECK_MAP = {
            bool: _BoolCheck,
            'bool': _BoolCheck,
            'b36': _B36Check,
            'dir': _DirCheck,
            'directory': _DirCheck,
            'ignore': _IgnoreCheck,
            'email': unicode,  # FIXME: Make more strict
            'False': False, 'false': False,
            'file': _FileCheck,
            'float': float,
            'hostname': _HostNameCheck,
            'int': int,
            'long': long,
            'multiline': unicode,
            'new file': _NewPathCheck,
            'new dir': _NewPathCheck,
            'new directory': _NewPathCheck,
            'path': _PathCheck,
            str: unicode,
            'slashslug': _SlashSlugCheck,
            'slug': _SlugCheck,
            'str': unicode,
            'True': True, 'true': True,
            'timestamp': long,
            'unicode': unicode,
            'url': unicode,  # FIXME: Make more strict
        }
        _NAME = 'container'
        _RULES = None
        _COMMENT = None
        _MAGIC = True

        def __init__(self, *args, **kwargs):
            rules = kwargs.get('_rules', self._RULES or {})
            self._name = kwargs.get('_name', self._NAME)
            self._comment = kwargs.get('_comment', self._COMMENT)
            enable_magic = kwargs.get('_magic', self._MAGIC)
            for kw in ('_rules', '_comment', '_name', '_magic'):
                if kw in kwargs:
                    del kwargs[kw]

            pcls.__init__(self)
            self._key = self._name
            self._rules_source = rules
            self.rules = {}
            self.set_rules(rules)
            self.update(*args, **kwargs)

            self._magic = enable_magic  # Enable the getitem/getattr magic

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
            ignore = self.ignored_keys() | set(['_any'])
            if not keys or '_any' in keys:
                keys.extend(self.keys())
            keys = [k for k in sorted(set(keys)) if k not in ignore]
            set_keys = set(self.keys())

            for key in keys:
                if not hasattr(self[key], 'as_config'):
                    if key in self.rules:
                        comment = _(self.rules[key][self.RULE_COMMENT])
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
            raise Exception(_('Please override this method'))

        def set_rules(self, rules):
            assert(isinstance(rules, dict))
            self.reset()
            for key, rule in rules.iteritems():
                self.add_rule(key, rule)

        def add_rule(self, key, rule):
            if not ((isinstance(rule, (list, tuple))) and
                    (key == CleanText(key, banned=CleanText.NONVARS).clean) and
                    (not self.real_hasattr(key))):
                raise TypeError('add_rule(%s, %s): Bad key or rule.'
                                % (key, rule))

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

            if (isinstance(check, dict) and value is not None
                    and not isinstance(value, (dict, list))):
                raise TypeError(_('Only lists or dictionaries can contain '
                                  'dictionary values (key %s).') % name)

            if isinstance(value, dict) and check is False:
                pcls.__setitem__(self, key, ConfigDict(_name=name,
                                                       _comment=comment,
                                                       _rules=value))

            elif isinstance(value, dict):
                if value:
                    raise ValueError(_('Subsections must be immutable '
                                       '(key %s).') % name)
                sub_rule = {'_any': [rule[self.RULE_COMMENT], check, None]}
                checker = _MakeCheck(ConfigDict, name, check, sub_rule)
                pcls.__setitem__(self, key, checker())
                rule[self.RULE_CHECKER] = checker

            elif isinstance(value, list):
                if value:
                    raise ValueError(_('Lists cannot have default values '
                                       '(key %s).') % name)
                sub_rule = {'_any': [rule[self.RULE_COMMENT], check, None]}
                checker = _MakeCheck(ConfigList, name, comment, sub_rule)
                pcls.__setitem__(self, key, checker())
                rule[self.RULE_CHECKER] = checker

            elif not isinstance(value, (type(None), int, long, bool,
                                        float, str, unicode)):
                raise TypeError(_('Invalid type "%s" for key "%s" (value: %s)'
                                  ) % (type(value), name, repr(value)))

        def __fixkey__(self, key):
            return key

        def fmt_key(self, key):
            return key

        def get_rule(self, key):
            key = self.__fixkey__(key)
            rule = self.rules.get(key, None)
            if rule is None:
                if '_any' in self.rules:
                    rule = self.rules['_any']
                else:
                    raise InvalidKeyError(_('Invalid key for %s: %s'
                                            ) % (self._name, key))
            if isinstance(rule[self.RULE_CHECKER], dict):
                rule = rule[:]
                rule[self.RULE_CHECKER] = _MakeCheck(
                    ConfigDict,
                    '%s/%s' % (self._name, key),
                    rule[self.RULE_COMMENT],
                    rule[self.RULE_CHECKER])
            return rule

        def ignored_keys(self):
            return set([k for k in self.rules
                        if self.rules[k][self.RULE_CHECKER] == _IgnoreCheck])

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

        def real_getattr(self, attr):
            try:
                return pcls.__getattribute__(self, attr)
            except AttributeError:
                return False

        def real_hasattr(self, attr):
            try:
                pcls.__getattribute__(self, attr)
                return True
            except AttributeError:
                return False

        def real_setattr(self, attr, value):
            return pcls.__setattr__(self, attr, value)

        def __getattr__(self, attr, default=None):
            if self.real_hasattr(attr) or not self.real_getattr('_magic'):
                return pcls.__getattribute__(self, attr)
            return self[attr]

        def __setattr__(self, attr, value):
            if self.real_hasattr(attr) or not self.real_getattr('_magic'):
                return self.real_setattr(attr, value)
            self.__setitem__(attr, value)

        def __passkey__(self, key, value):
            if hasattr(value, '__passkey__'):
                value._key = key
                value._name = '%s/%s' % (self._name, key)

        def __passkey_recurse__(self, key, value):
            if hasattr(value, '__passkey__'):
                if isinstance(value, (list, tuple)):
                    for k in range(0, len(value)):
                        value.__passkey__(value.__fixkey__(k), value[k])
                elif isinstance(value, dict):
                    for k in value:
                        value.__passkey__(value.__fixkey__(k), value[k])

        def __createkey_and_setitem__(self, key, value):
            pcls.__setitem__(self, key, value)

        def __setitem__(self, key, value):
            key = self.__fixkey__(key)
            checker = self.get_rule(key)[self.RULE_CHECKER]
            if not checker is True:
                if checker is False:
                    raise ValueError(_('Modifying %s/%s is not allowed'
                                       ) % (self._name, key))
                if isinstance(checker, (list, set, tuple)):
                    if value not in checker:
                        raise ValueError(_('Invalid value for %s/%s: %s'
                                           ) % (self._name, key, value))
                elif isinstance(checker, (type, type(RuledContainer))):
                    try:
                        if value is None:
                            value = checker()
                        else:
                            value = checker(value)
                    except (IgnoreValue):
                        return
                    except (ValueError, TypeError):
                        raise ValueError(_('Invalid value for %s/%s: %s'
                                           ) % (self._name, key, value))
                else:
                    raise Exception(_('Unknown constraint for %s/%s: %s'
                                      ) % (self._name, key, checker))
            self.__passkey__(key, value)
            self.__createkey_and_setitem__(key, value)
            self.__passkey_recurse__(key, value)

        def extend(self, src):
            for val in src:
                self.append(val)

        def __iadd__(self, src):
            self.extend(src)
            return self

    return _RuledContainer


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
        while key > len(self):
            self.append(self.rules['_any'][self.RULE_DEFAULT])
        if key == len(self):
            self.append(value)
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
        if hasattr(value, '__passkey__'):
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

    def fmt_key(self, key):
        f = b36(self.__fixkey__(key)).lower()
        return ('0000' + f)[-4:] if (len(f) < 4) else f

    def keys(self):
        return [self.fmt_key(i) for i in range(0, len(self))]

    def iteritems(self):
        for k in self.keys():
            yield (k, self[k])

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
    (['colors', 'liquids', 'tags'], [[], [], {}])

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
        return list(set(self.keys()) | set(self.rules.keys())
                    - self.ignored_keys() - set(['_any']))

    def append(self, value):
        """Add to the dict using an autoselected key"""
        if '_any' in self.rules:
            k = b36(max([int(k, 36) for k in self.keys()] + [-1]) + 1).lower()
            self[k] = value
            return k
        else:
            raise UsageError(_('Cannot append to fixed dict'))

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


class MailpileJinjaLoader(BaseLoader):
    """
    A Jinja2 template loader which uses the Mailpile configuration
    and plugin system to find template files.
    """
    def __init__(self, config):
        self.config = config

    def get_source(self, environment, template):
        tpl = os.path.join('html', template)
        path, mt = self.config.data_file_and_mimetype('html_theme', tpl)
        if not path:
            raise TemplateNotFound(tpl)

        mtime = os.path.getmtime(path)
        unchanged = lambda: (
            path == self.config.data_file_and_mimetype('html_theme', tpl)[0]
            and mtime == os.path.getmtime(path))

        with file(path) as f:
            source = f.read().decode('utf-8')

        return source, path, unchanged


class ConfigManager(ConfigDict):
    """
    This class manages the live global mailpile configuration. This includes
    the settings themselves, as well as global objects like the index and
    references to any background worker threads.
    """
    DEFAULT_WORKDIR = os.environ.get('MAILPILE_HOME',
                                     os.path.expanduser('~/.mailpile'))

    def __init__(self, workdir=None, rules={}):
        ConfigDict.__init__(self, _rules=rules, _magic=False)

        self.workdir = workdir or self.DEFAULT_WORKDIR
        self.conffile = os.path.join(self.workdir, 'mailpile.cfg')

        self.plugins = None
        self.background = None
        self.cron_worker = None
        self.http_worker = None
        self.dumb_worker = self.slow_worker = DumbWorker('Dumb worker', None)
        self.other_workers = []
        self.mail_sources = {}

        self.jinja_env = None

        self.event_log = None
        self.index = None
        self.vcards = {}
        self._mbox_cache = {}
        self._running = {}
        self._lock = threading.RLock()

        self._magic = True  # Enable the getattr/getitem magic

    def _mkworkdir(self, session):
        if not os.path.exists(self.workdir):
            if session:
                session.ui.notify(_('Creating: %s') % self.workdir)
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
        'Invalid (internal): section config/bogus does not exist'

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

        def item_sorter(i):
            try:
                return (int(i[0], 36), i[1])
            except (ValueError, IndexError, KeyError, TypeError):
                return i

        all_okay = True
        for section in parser.sections():
            okay = True
            cfgpath = section.split(':')[0].split('/')[1:]
            cfg = self
            added_parts = []
            for part in cfgpath:
                if cfg.fmt_key(part) in cfg.keys():
                    cfg = cfg[part]
                elif '_any' in cfg.rules:
                    cfg[part] = {}
                    cfg = cfg[part]
                else:
                    if session:
                        msg = _('Invalid (%s): section %s does not '
                                'exist') % (source, section)
                        session.ui.warning(msg)
                    all_okay = okay = False
            items = parser.items(section) if okay else []
            items.sort(key=item_sorter)
            for var, val in items:
                try:
                    cfg[var] = val
                except (ValueError, KeyError, IndexError):
                    if session:
                        msg = _(u'Invalid (%s): section %s, variable %s=%s'
                                ) % (source, section, var, val)
                        session.ui.warning(msg)
                    all_okay = okay = False
        return all_okay

    def load(self, *args, **kwargs):
        self._lock.acquire()
        try:
            return self._unlocked_load(*args, **kwargs)
        finally:
            self._lock.release()

    def _unlocked_load(self, session, filename=None):
        self._mkworkdir(session)
        self.index = None
        self.reset(rules=False, data=True)

        filename = filename or self.conffile
        lines = []
        try:
            with open(filename, 'rb') as fd:
                decrypt_and_parse_lines(fd, lambda l: lines.append(l), None)
        except ValueError:
            pass
        except IOError:
            pass

        # Discover plugins and update the config rule to match
        from mailpile.plugins import PluginManager
        self.plugins = PluginManager(config=self, builtin=True).discover([
            os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         '..', 'plugins'),
            os.path.join(self.workdir, 'plugins')
        ])
        self.sys.plugins.rules['_any'][self.RULE_CHECKER
                                       ] = [None] + self.plugins.available()

        # Parse once (silently), to figure out which plugins to load...
        self.parse_config(None, '\n'.join(lines), source=filename)

        if len(self.sys.plugins) == 0:
            self.sys.plugins.extend(self.plugins.DEFAULT)
        self.load_plugins(session)

        # Now all the plugins are loaded, reset and parse again!
        self.reset_rules_from_source()
        self.parse_config(session, '\n'.join(lines), source=filename)

        # Open event log
        self.event_log = EventLog(self.data_directory('event_log',
                                                      mode='rw', mkdir=True),
                                  # FIXME: Disbled encryption for now
                                  lambda: False and self.prefs.obfuscate_index
                                  ).load()

        # Enable translations
        translation = self.get_i18n_translation(session)

        # Configure jinja2
        self.jinja_env = Environment(
            loader=MailpileJinjaLoader(self),
            autoescape=True,
            trim_blocks=True,
            extensions=['jinja2.ext.i18n', 'jinja2.ext.with_',
                        'jinja2.ext.do', 'jinja2.ext.autoescape',
                        'mailpile.jinjaextensions.MailpileCommand']
        )
        self.jinja_env.install_gettext_translations(translation,
                                                    newstyle=True)

        # Load VCards
        self.vcards = VCardStore(self, self.data_directory('vcards',
                                                           mode='rw',
                                                           mkdir=True))

    def reset_rules_from_source(self):
        self._lock.acquire()
        try:
            self.set_rules(self._rules_source)
            self.sys.plugins.rules['_any'][self.RULE_CHECKER
                                           ] = [None] + self.plugins.available()
        finally:
            self._lock.release()

    def load_plugins(self, session):
        self._lock.acquire()
        try:
            from mailpile.plugins import PluginManager
            plugin_list = set(PluginManager.REQUIRED + self.sys.plugins)
            for plugin in plugin_list:
                if plugin is not None:
                    session.ui.mark(_('Loading plugin: %s') % plugin)
                    self.plugins.load(plugin)
            session.ui.mark(_('Processing manifests'))
            self.plugins.process_manifests()
            self.prepare_workers(session)
        finally:
            self._lock.release()

    def save(self, *args, **kwargs):
        self._lock.acquire()
        try:
            self._unlocked_save(*args, **kwargs)
        finally:
            self._lock.release()

    def _unlocked_save(self):
        self._mkworkdir(None)
        newfile = '%s.new' % self.conffile
        fd = gpg_open(newfile, self.prefs.get('gpg_recipient'), 'wb')
        fd.write(self.as_config_bytes(private=True))
        fd.close()

        # Keep the last 5 config files around... just in case.
        backup_file(self.conffile, backups=5, min_age_delta=10)
        os.rename(newfile, self.conffile)

        self.get_i18n_translation()
        self.prepare_workers()

    def clear_mbox_cache(self):
        self._mbox_cache = {}

    def _find_mail_source(self, mbx_id):
        for src in self.sources.values():
            if mbx_id in src.mailbox:
                return src
        return None

    def get_mailboxes(self, standalone=True, mail_sources=False):
        def fmt_mbxid(k):
            k = b36(int(k, 36))
            if len(k) > MBX_ID_LEN:
                raise ValueError(_('Mailbox ID too large: %s') % k)
            return (('0' * MBX_ID_LEN) + k)[-MBX_ID_LEN:]
        mailboxes = [(fmt_mbxid(k),
                      self.sys.mailbox[k],
                      self._find_mail_source(fmt_mbxid(k)))
                     for k in self.sys.mailbox.keys()]

        if not standalone:
            mailboxes = [(i, p, s) for i, p, s in mailboxes if s]

        if mail_sources:
            for i in range(0, len(mailboxes)):
                mid, path, src = mailboxes[i]
                mailboxes[i] = (mid,
                                src and src.mailbox[mid].local or path,
                                src)
        else:
            mailboxes = [(i, p, s) for i, p, s in mailboxes if not s]

        mailboxes.sort()
        return mailboxes

    def is_editable_message(self, msg_info):
        for ptr in msg_info[MailIndex.MSG_PTRS].split(','):
            if not self.is_editable_mailbox(ptr[: MBX_ID_LEN]):
                return False
        editable = False
        for tid in msg_info[MailIndex.MSG_TAGS].split(','):
            try:
                if self.tags and self.tags[tid].flag_editable:
                    editable = True
            except (KeyError, AttributeError):
                pass
        return editable

    def is_editable_mailbox(self, mailbox_id):
        mailbox_id = ((mailbox_id is None and -1) or
                      (mailbox_id == '' and -1) or
                      int(mailbox_id, 36))
        local_mailbox_id = int(self.sys.get('local_mailbox_id', 'ZZZZZ'), 36)
        return (mailbox_id == local_mailbox_id)

    def load_pickle(self, pfn):
        with open(os.path.join(self.workdir, pfn), 'rb') as fd:
            if self.prefs.obfuscate_index:
                from mailpile.crypto.streamer import DecryptingStreamer
                with DecryptingStreamer(self.prefs.obfuscate_index,
                                        fd) as streamer:
                    return cPickle.loads(streamer.read())
            else:
                return cPickle.loads(fd.read())

    def save_pickle(self, obj, pfn):
        try:
            if self.prefs.obfuscate_index:
                from mailpile.crypto.streamer import EncryptingStreamer
                fd = EncryptingStreamer(self.prefs.obfuscate_index,
                                        dir=self.workdir)
                cPickle.dump(obj, fd, protocol=0)
                fd.save(os.path.join(self.workdir, pfn))
            else:
                fd = open(os.path.join(self.workdir, pfn), 'wb')
                cPickle.dump(obj, fd, protocol=0)
        finally:
            fd.close()

    def open_mailbox(self, session, mailbox_id, prefer_local=True):
        try:
            mbx_id = mailbox_id.lower()
            mfn = self.sys.mailbox[mbx_id]
            if prefer_local:
                src = self._find_mail_source(mbx_id)
                mfn = src and src.mailbox[mbx_id].local or mfn
            pfn = 'pickled-mailbox.%s' % mbx_id
        except KeyError:
            raise NoSuchMailboxError(_('No such mailbox: %s') % mbx_id)

        self._lock.acquire()
        try:
            if mbx_id not in self._mbox_cache:
                if session:
                    session.ui.mark(_('%s: Updating: %s') % (mbx_id, mfn))
                self._mbox_cache[mbx_id] = self.load_pickle(pfn)
            self._mbox_cache[mbx_id].update_toc()
        except KeyboardInterrupt:
            raise
        except:
            if self.sys.debug:
                import traceback
                traceback.print_exc()
            if session:
                session.ui.mark(_('%s: Opening: %s (may take a while)'
                                  ) % (mbx_id, mfn))
            editable = self.is_editable_mailbox(mbx_id)
            mbox = OpenMailbox(mfn, self, create=editable)
            mbox.editable = editable
            mbox.save(session,
                      to=pfn,
                      pickler=lambda o, f: self.save_pickle(o, f))
            self._mbox_cache[mbx_id] = mbox
        finally:
            self._lock.release()

        # Always set this, it can't be pickled
        self._mbox_cache[mbx_id]._encryption_key_func = \
            lambda: self.prefs.obfuscate_index

        return self._mbox_cache[mbx_id]

    def create_local_mailstore(self, session, name=None):
        self._lock.acquire()
        try:
            path = os.path.join(self.workdir, 'mail')
            if name is None:
                name = '%5.5x' % random.randint(0, 16**5)
                while os.path.exists(os.path.join(path, name)):
                    name = '%5.5x' % random.randint(0, 16**5)
            if name != '':
                path = os.path.join(path, name)

            mbx = wervd.MailpileMailbox(path)
            mbx._encryption_key_func = lambda: self.prefs.obfuscate_index
            return path, mbx
        finally:
            self._lock.release()

    def open_local_mailbox(self, session):
        self._lock.acquire()
        local_id = self.sys.get('local_mailbox_id', None)
        try:
            if not local_id:
                mailbox, mbx = self.create_local_mailstore(session, name='')
                local_id = self.sys.mailbox.append(mailbox)
                local_id = (('0' * MBX_ID_LEN) + local_id)[-MBX_ID_LEN:]
                self.sys.local_mailbox_id = local_id
            else:
                local_id = (('0' * MBX_ID_LEN) + local_id)[-MBX_ID_LEN:]
        finally:
            self._lock.release()
        return local_id, self.open_mailbox(session, local_id)

    def get_profile(self, email=None):
        find = email or self.prefs.get('default_email', None)
        default_profile = {
            'name': None,
            'email': find,
            'signature': None,
            'messageroute': self.prefs.default_messageroute
        }
        for profile in self.profiles:
            if profile.email == find or not find:
                if not email:
                    self.prefs.default_email = profile.email
                return dict_merge(default_profile, profile)
        return default_profile

    def get_sendmail(self, frm, rcpts=['-t']):
        if len(rcpts) == 1:
            if rcpts[0].lower().endswith('.onion'):
                return {"protocol": "smtorp",
                        "host": rcpts[0].split('@')[-1],
                        "port": 25,
                        "username": "",
                        "password": ""}
        routeid = self.get_profile(frm)['messageroute']
        if self.routes[routeid] is not None:
            return self.routes[routeid]
        else:
            print "Migration notice: Try running 'setup/migrate'."
            raise ValueError(_("Route %s does not exist.") % routeid)

    def data_directory(self, ftype, mode='rb', mkdir=False):
        """
        Return the path to a data directory for a particular type of file
        data, optionally creating the directory if it is missing.

        >>> p = cfg.data_directory('html_theme', mode='r', mkdir=False)
        >>> p == os.path.abspath('static/default')
        True
        """
        self._lock.acquire()
        try:
            # This should raise a KeyError if the ftype is unrecognized
            bpath = self.sys.path.get(ftype)
            if not bpath.startswith('/'):
                cpath = os.path.join(self.workdir, bpath)
                if os.path.exists(cpath) or 'w' in mode:
                    bpath = cpath
                    if mkdir and not os.path.exists(cpath):
                        os.mkdir(cpath)
                else:
                    bpath = os.path.join(os.path.dirname(__file__),
                                         '..', bpath)
            return os.path.abspath(bpath)
        finally:
            self._lock.release()

    def data_file_and_mimetype(self, ftype, fpath, *args, **kwargs):
        # The theme gets precedence
        core_path = self.data_directory(ftype, *args, **kwargs)
        path, mimetype = os.path.join(core_path, fpath), None

        # If there's nothing there, check our plugins
        if not os.path.exists(path):
            from mailpile.plugins import PluginManager
            path, mimetype = PluginManager().get_web_asset(fpath, path)

        if os.path.exists(path):
            return path, mimetype
        else:
            return None, None

    def history_file(self):
        return os.path.join(self.workdir, 'history')

    def mailindex_file(self):
        return os.path.join(self.workdir, 'mailpile.idx')

    def postinglist_dir(self, prefix):
        self._lock.acquire()
        try:
            d = os.path.join(self.workdir, 'search')
            if not os.path.exists(d):
                os.mkdir(d)
            d = os.path.join(d, prefix and prefix[0] or '_')
            if not os.path.exists(d):
                os.mkdir(d)
            return d
        finally:
            self._lock.release()

    def get_index(self, session):
        self._lock.acquire()
        try:
            if self.index:
                return self.index
            idx = MailIndex(self)
            idx.load(session)
            self.index = idx
            return idx
        finally:
            self._lock.release()

    def get_tor_socket(self):
        if socks:
            socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5,
                                  'localhost', 9050, True)
        return socks.socksocket

    def get_i18n_translation(self, session=None):
        self._lock.acquire()
        try:
            language = self.prefs.language
            trans = None
            if language != "":
                try:
                    trans = translation("mailpile", getLocaleDirectory(),
                                        [language], codeset="utf-8")
                except IOError:
                    if session:
                        session.ui.warning(('Failed to load language %s'
                                            ) % language)
            if not trans:
                trans = translation("mailpile", getLocaleDirectory(),
                                    codeset='utf-8', fallback=True)
                if session and isinstance(trans, NullTranslations):
                    session.ui.warning('Failed to configure i18n. '
                                       'Using fallback.')
            if trans:
                trans.set_output_charset("utf-8")
                trans.install(unicode=True)
            return trans
        finally:
            self._lock.release()

    def open_file(self, ftype, fpath, mode='rb', mkdir=False):
        if '..' in fpath:
            raise ValueError(_('Parent paths are not allowed'))
        fpath, mt = self.data_file_and_mimetype(ftype, fpath,
                                                mode=mode, mkdir=mkdir)
        if not fpath:
            raise IOError(2, 'Not Found')
        return fpath, open(fpath, mode), mt

    def prepare_workers(self, *args, **kwargs):
        self._lock.acquire()
        try:
            return self._unlocked_prepare_workers(*args, **kwargs)
        finally:
            self._lock.release()

    def _unlocked_prepare_workers(config, session=None, daemons=False):
        # Set globals from config first...
        import mailpile.util

        # Make sure we have a silent background session
        if not config.background:
            config.background = Session(config)
            config.background.ui = BackgroundInteraction(config)
            config.background.ui.block()

        # Start the workers
        if daemons:
            for src_id, src_config in config.sources.iteritems():
                if src_id not in config.mail_sources:
                    from mailpile.mail_source import MailSource
                    try:
                        config.mail_sources[src_id] = MailSource(
                            session or config.background, src_config)
                        config.mail_sources[src_id].start()
                    except ValueError:
                        traceback.print_exc()

            if config.slow_worker == config.dumb_worker:
                config.slow_worker = Worker('Slow worker', session)
                config.slow_worker.start()
            if not config.cron_worker:
                config.cron_worker = Cron('Cron worker', session)
                config.cron_worker.start()
            if not config.http_worker:
                # Start the HTTP worker if requested
                sspec = (config.sys.http_host, config.sys.http_port)
                if sspec[0].lower() != 'disabled' and sspec[1] >= 0:
                    config.http_worker = HttpWorker(session, sspec)
                    config.http_worker.start()
            if not config.other_workers:
                from mailpile.plugins import PluginManager
                for worker in PluginManager.WORKERS:
                    w = worker(session)
                    w.start()
                    config.other_workers.append(w)

        # Update the cron jobs, if necessary
        if config.cron_worker:
            session = session or config.background

            # Schedule periodic rescanning, if requested.
            rescan_interval = config.prefs.rescan_interval
            if rescan_interval:
                def rescan():
                    if 'rescan' not in config._running:
                        rsc = Rescan(session, 'rescan')
                        rsc.serialize = False
                        config.slow_worker.add_task(session, 'Rescan', rsc.run)
                config.cron_worker.add_task('rescan', rescan_interval, rescan)

            # Schedule plugin jobs
            from mailpile.plugins import PluginManager

            def interval(i):
                if isinstance(i, (str, unicode)):
                    i = config.walk(i)
                return int(i)

            def wrap_fast(func):
                def wrapped():
                    return func(session)
                return wrapped

            def wrap_slow(func):
                def wrapped():
                    config.slow_worker.add_task(session, job,
                                                lambda: func(session))
                return wrapped
            for job, (i, f) in PluginManager.FAST_PERIODIC_JOBS.iteritems():
                config.cron_worker.add_task(job, interval(i), wrap_fast(f))
            for job, (i, f) in PluginManager.SLOW_PERIODIC_JOBS.iteritems():
                config.cron_worker.add_task(job, interval(i), wrap_slow(f))

    def stop_workers(config):
        config._lock.acquire()
        try:
            for wait in (False, True):
                for w in ([config.http_worker,
                           config.slow_worker,
                           config.cron_worker] +
                          config.other_workers +
                          config.mail_sources.values()):
                    if w:
                        w.quit(join=wait)
            config.other_workers = []
            config.http_worker = config.cron_worker = None
            config.slow_worker = config.dumb_worker
        finally:
            config._lock.release()


##############################################################################

if __name__ == "__main__":
    import copy
    import doctest
    import sys
    import mailpile.config
    import mailpile.defaults
    import mailpile.plugins.tags
    import mailpile.ui

    rules = copy.deepcopy(mailpile.defaults.CONFIG_RULES)
    rules.update({
        'nest1': ['Nest1', {
            'nest2': ['Nest2', str, []],
            'nest3': ['Nest3', {
                'nest4': ['Nest4', str, []]
            }, []],
        }, {}]
    })
    cfg = mailpile.config.ConfigManager(rules=rules)
    session = mailpile.ui.Session(cfg)
    session.ui.block()

    for tries in (1, 2):
        # This tests that we can set (and reset) dicts of unnested objects
        cfg.tags = {}
        assert(cfg.tags.a is None)
        for tn in range(0, 11):
            cfg.tags.append({'name': 'Test Tag %s' % tn})
        assert(cfg.tags.a['name'] == 'Test Tag 10')

        # This tests the same thing for lists
        cfg.profiles = []
        assert(len(cfg.profiles) == 0)
        cfg.profiles.append({'name': 'Test Profile'})
        assert(len(cfg.profiles) == 1)
        assert(cfg.profiles[0].name == 'Test Profile')

        # This is the complicated one: multiple nesting layers
        cfg.nest1 = {}
        assert(cfg.nest1.a is None)
        cfg.nest1.a = {
            'nest2': ['hello', 'world'],
            'nest3': [{'nest4': ['Hooray']}]
        }
        cfg.nest1.b = {
            'nest2': ['hello', 'world'],
            'nest3': [{'nest4': ['Hooray', 'Bravo']}]
        }
        assert(cfg.nest1.a.nest3[0].nest4[0] == 'Hooray')
        assert(cfg.nest1.b.nest3[0].nest4[1] == 'Bravo')

    assert(cfg.sys.http_port ==
           mailpile.defaults.CONFIG_RULES['sys'][-1]['http_port'][-1])
    assert(cfg.sys.path.vcards == 'vcards')
    assert(cfg.walk('sys.path.vcards') == 'vcards')

    # Verify that the tricky nested stuff from above persists and
    # load/save doesn't change lists.
    for passes in (1, 2, 3):
        cfg2 = mailpile.config.ConfigManager(rules=rules)
        cfg2.parse_config(session, cfg.as_config_bytes())
        cfg.parse_config(session, cfg2.as_config_bytes())
        assert(cfg2.nest1.a.nest3[0].nest4[0] == 'Hooray')
        assert(cfg2.nest1.b.nest3[0].nest4[1] == 'Bravo')
        assert(len(cfg2.nest1) == 2)
        assert(len(cfg.nest1) == 2)
        assert(len(cfg.profiles) == 1)
        assert(len(cfg.tags) == 11)

    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={'cfg': cfg,
                                          'session': session})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
