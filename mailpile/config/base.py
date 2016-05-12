import io
import json
import os
import ConfigParser
from urllib import quote, unquote

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *

import mailpile.config.validators as validators


class ConfigValueError(ValueError):
    pass


def ConfigRule(*args):
    class _ConfigRule(list):
        def __init__(self):
            list.__init__(self, args)
            self._types = []
    return _ConfigRule()


def PublicConfigRule(*args):
    c = ConfigRule(*args)
    c._types.append('public')
    return c


def KeyConfigRule(*args):
    c = ConfigRule(*args)
    c._types.append('key')
    return c


# FIXME: This should be enforced somehow when variables are altered.
#        Run in a context?
def CriticalConfigRule(*args):
    c = ConfigRule(*args)
    c._types += ['critical']
    return c


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


class InvalidKeyError(ValueError):
    pass


class CommentedEscapedConfigParser(ConfigParser.RawConfigParser):
    """
    This is a ConfigParser that allows embedded comments and safely escapes
    and encodes/decodes values that include funky characters.

    >>> cfg = u'[config/sys: Stuff]\\ndebug = True ; Ignored comment'
    >>> cecp = CommentedEscapedConfigParser()
    >>> cecp.readfp(io.BytesIO(cfg.encode('utf-8')))
    >>> cecp.get('config/sys: Stuff', 'debug') == 'True'
    True

    >>> cecp.items('config/sys: Stuff')
    [(u'debug', u'True')]
    """
    NOT_UTF8 = '%C0'  # This byte is never valid at the start of an utf-8
                      # string, so we use it to mark binary data.
    SAFE = '!?: /#@<>[]()=-'

    def set(self, section, key, value, comment):
        key = unicode(key).encode('utf-8')
        section = unicode(section).encode('utf-8')

        if isinstance(value, unicode):
            value = quote(value.encode('utf-8'), safe=self.SAFE)
        elif isinstance(value, str):
            quoted = quote(value, safe=self.SAFE)
            if quoted != value:
                value = self.NOT_UTF8 + quoted
        else:
            value = quote(unicode(value).encode('utf-8'), safe=self.SAFE)

        if value.endswith(' '):
            value = value[:-1] + '%20'
        if comment:
            pad = ' ' * (25 - len(key) - len(value)) + ' ; '
            value = '%s%s%s' % (value, pad, comment)
        return ConfigParser.RawConfigParser.set(self, section, key, value)

    def _decode_value(self, value):
        if value.startswith(self.NOT_UTF8):
            return unquote(value[len(self.NOT_UTF8):])
        else:
            return unquote(value).decode('utf-8')

    def get(self, section, key):
        key = unicode(key).encode('utf-8')
        section = unicode(section).encode('utf-8')
        value = ConfigParser.RawConfigParser.get(self, section, key)
        return self._decode_value(value)

    def items(self, section):
        return [(k.decode('utf-8'), self._decode_value(i)) for k, i
                in ConfigParser.RawConfigParser.items(self, section)]


def _MakeCheck(pcls, name, comment, rules):
    class Checker(pcls):
        _NAME = name
        _RULES = rules
        _COMMENT = comment
    return Checker


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
            bool: validators.BoolCheck,
            'bin': validators.NotUnicode,
            'bool': validators.BoolCheck,
            'b36': validators.B36Check,
            'dir': validators.DirCheck,
            'directory': validators.DirCheck,
            'ignore': validators.IgnoreCheck,
            'email': validators.EmailCheck,
            'False': False, 'false': False,
            'file': validators.FileCheck,
            'float': float,
            'gpgkeyid': validators.GPGKeyCheck,
            'hostname': validators.HostNameCheck,
            'int': int,
            'long': long,
            'multiline': unicode,
            'new file': validators.NewPathCheck,
            'new dir': validators.NewPathCheck,
            'new directory': validators.NewPathCheck,
            'path': validators.PathCheck,
            str: unicode,
            'slashslug': validators.SlashSlugCheck,
            'slug': validators.SlugCheck,
            'str': unicode,
            'True': True, 'true': True,
            'timestamp': long,
            'unicode': unicode,
            'url': validators.UrlCheck, # FIXME: check more than the scheme?
            'webroot': validators.WebRootCheck
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

        def as_config_bytes(self, _type=None, _xtype=None):
            of = io.BytesIO()
            self.as_config(_type=_type, _xtype=_xtype).write(of)
            return of.getvalue()

        def key_types(self, key):
            if key not in self.rules:
                key = '_any'
            if key in self.rules and hasattr(self.rules[key], '_types'):
                return self.rules[key]._types
            else:
                return []

        def as_config(self, config=None, _type=None, _xtype=None):
            config = config or CommentedEscapedConfigParser()
            section = self._name
            if self._comment:
                section += ': %s' % self._comment
            added_section = False

            keys = self.rules.keys()
            if _type:
                keys = [k for k in keys if _type in self.key_types(k)]

            ignore = self.ignored_keys() | set(['_any'])
            if not _type:
                if not keys or '_any' in keys:
                    keys.extend(self.keys())

            keys = [k for k in sorted(set(keys)) if k not in ignore]
            set_keys = set(self.keys())

            for key in keys:
                if not hasattr(self[key], 'as_config'):
                    if key in self.rules:
                        comment = self.rules[key][self.RULE_COMMENT]
                    else:
                        comment = ''
                    value = self[key]
                    if value is not None and value != '':
                        if key not in set_keys:
                            key = ';' + key
                            comment = '(default) ' + comment
                        if not added_section:
                            config.add_section(str(section))
                            added_section = True
                        if _xtype not in self.key_types(key) or not _xtype:
                            config.set(section, key, value, comment)
            for key in keys:
                if hasattr(self[key], 'as_config'):
                    self[key].as_config(config=config, _type=_type, _xtype=_xtype)

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

            orule, rule = rule, ConfigRule(*rule[:])
            if hasattr(orule, '_types'):
                rule._types = orule._types

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
                    raise ConfigValueError(_('Subsections must be immutable '
                                             '(key %s).') % name)
                sub_rule = {'_any': [rule[self.RULE_COMMENT], check, None]}
                checker = _MakeCheck(ConfigDict, name, check, sub_rule)
                pcls.__setitem__(self, key, checker())
                rule[self.RULE_CHECKER] = checker

            elif isinstance(value, list):
                if value:
                    raise ConfigValueError(_('Lists cannot have default '
                                             'values (key %s).') % name)
                sub_rule = {'_any': [rule[self.RULE_COMMENT], check, None]}
                checker = _MakeCheck(ConfigList, name, comment, sub_rule)
                pcls.__setitem__(self, key, checker())
                rule[self.RULE_CHECKER] = checker

            elif not isinstance(value, (type(None), int, long, bool,
                                        float, str, unicode)):
                raise TypeError(_('Invalid type "%s" for key "%s" (value: %s)'
                                  ) % (type(value), name, repr(value)))

        def __fixkey__(self, key):
            return key.lower()

        def fmt_key(self, key):
            return key.lower()

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
                if self.rules[k][self.RULE_CHECKER] == validators.IgnoreCheck])

        def walk(self, path, parent=0, key_types=None):
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
                if key_types is not None:
                    if [t for t in cfg.key_types(part) if t not in key_types]:
                        raise AccessError(_('Access denied to %s') % part)
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
                    if isinstance(value, dict) and isinstance(self[key], dict):
                        for k, v in value.iteritems():
                            self[key][k] = v
                        return
                    raise ConfigValueError(_('Modifying %s/%s is not '
                                             'allowed') % (self._name, key))
                elif isinstance(checker, (list, set, tuple)):
                    if value not in checker:
                        raise ConfigValueError(_('Invalid value for %s/%s: %s'
                                                 ) % (self._name, key, value))
                elif isinstance(checker, (type, type(RuledContainer))):
                    try:
                        if value is None:
                            value = checker()
                        else:
                            value = checker(value)
                    except (ConfigValueError):
                        raise
                    except (validators.IgnoreValue):
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
            return b36(len(self) - 1).lower()
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

    def get(self, key, default=None):
        try:
            return list.__getitem__(self, self.__fixkey__(key))
        except IndexError:
            return default

    def __getitem__(self, key):
        return list.__getitem__(self, self.__fixkey__(key))

    def fmt_key(self, key):
        f = b36(self.__fixkey__(key)).lower()
        return ('0000' + f)[-4:] if (len(f) < 4) else f

    def iterkeys(self):
        return (self.fmt_key(i) for i in range(0, len(self)))

    def iteritems(self):
        for k in self.iterkeys():
            yield (k, self[k])

    def keys(self):
        return list(self.iterkeys())

    def all_keys(self):
        return list(self.iterkeys())

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
    ConfigValueError: Invalid value for config/colors/4: green

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


if __name__ == "__main__":
    import doctest
    import sys
    result = doctest.testmod(optionflags=doctest.ELLIPSIS)
    print '%s' % (result, )
    if result.failed:
        sys.exit(1)
