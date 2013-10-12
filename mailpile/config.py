import copy
import json
import os
import re

from mailpile.util import *


class InvalidKeyError(ValueError):
    pass


def _MakeCheck(pcls, rules):
    class CD(pcls):
        RULES = rules
    return CD


def _SlugCheck(slug):
    """
    Verify that a string is a valid URL slug.

    >>> _SlugCheck('Foobar')
    'Foobar'

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
                             banned=CleanText.WHITESPACE +
                                     CleanText.NONALNUM).clean:
        raise ValueError('Invalid URL slug: %s' % slug)
    return slug


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
           'False': False, 'false': False,
           'file': _FileCheck,
           'float': float,
           'hostname': _HostNameCheck,
           'int': int,
           'long': long,
           'new file': _NewPathCheck,
           'new dir': _NewPathCheck,
           'new directory': _NewPathCheck,
           'path': _PathCheck,
           str: unicode,
           'slug': _SlugCheck,
           'str': unicode,
           'True': True, 'true': True,
           'unicode': unicode,
           # TODO: Create 'email' and 'url' and other high level checks
        }
        NAME = 'container'
        RULES = None

        def __init__(self, *args, **kwargs):
            if '_rules' in kwargs:
                rules = kwargs['_rules']
                del kwargs['_rules']
            else:
                rules = self.RULES or {}

            if '_name' in kwargs:
                self.name = kwargs['_name']
                del kwargs['_name']
            else:
                self.name = self.NAME

            pcls.__init__(self)
            self.key = self.name
            self.set_rules(rules)
            self.update(*args, **kwargs)

        def __str__(self):
            return json.dumps(self, sort_keys=True, indent=2)

        def _reset(self):
            raise Exception('Override this')

        def set_rules(self, rules):
            assert(isinstance(rules, dict))
            self._reset()
            for key, rule in rules.iteritems():
                self.add_rule(key, rule)

        def add_rule(self, key, rule):
            assert(isinstance(rule, (list, tuple)))
            rule = list(rule[:])
            self.rules[key] = rule
            check = rule[self.RULE_CHECKER]
            try:
                check = self.RULE_CHECK_MAP.get(check, check)
                rule[self.RULE_CHECKER] = check
            except TypeError:
                pass

            name = '%s/%s' % (self.name, key)
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
                                                           _rules=check_rule))
                else:
                    pcls.__setitem__(self, key, ConfigDict(_name=name,
                                                           _rules=value))

            elif isinstance(value, list):
                rule[self.RULE_CHECKER] = False
                if check_rule:
                    pcls.__setitem__(self, key, ConfigList(_name=name,
                                                           _rules=check_rule))
                else:
                    pcls.__setitem__(self, key, ConfigList(_name=name,
                                                           _rules={
                        '_any': [rule[self.RULE_COMMENT], check, None]
                    }))

            elif not isinstance(value, (type(None), int, long, bool,
                                        float, str, unicode)):
                raise TypeError(('Invalid type for default %s = %s'
                                 ) % (name, value))

        def get_rule(self, key):
            if key not in self.rules:
                if '_any' in self.rules:
                    return self.rules['_any']
                raise InvalidKeyError(('Invalid key for %s: %s'
                                       ) % (self.name, key))
            return self.rules[key]

        def get(self, key, default=None):
            if key in self:
                return pcls.__getitem__(self, key)
            if default is None and key in self.rules:
                return self.rules[key][self.RULE_DEFAULT]
            return default

        def __getitem__(self, key):
            if key in self.rules:
                return self.get(key)
            return pcls.__getitem__(self, key)

        def __getattr__(self, attr):
            return self[attr]

        def __passkey__(self, key, value):
            if hasattr(value, 'key'):
                value.key = key

        def __setitem__(self, key, value):
            checker = self.get_rule(key)[self.RULE_CHECKER]
            if not checker is True:
                if checker is False:
                    raise ValueError(('Modifying %s/%s is not allowed'
                                      ) % (self.name, key))
                if isinstance(checker, (list, set, tuple)):
                    if value not in checker:
                        raise ValueError(('Invalid value for %s/%s: %s'
                                          ) % (self.name, key, value))
                elif isinstance(checker, (type, type(RuledContainer))):
                    try:
                        value = checker(value)
                    except (ValueError, TypeError):
                        raise ValueError(('Invalid value for %s/%s: %s'
                                          ) % (self.name, key, value))
                else:
                    raise Exception(('Unknown constraint for %s/%s: %s'
                                     ) % (self.name, key, checker))
            self.__passkey__(key, value)
            pcls.__setitem__(self, key, value)

    return RC


class ConfigList(RuledContainer(list)):
    """
    A sanity-checking, self-documenting list of program settings.

    Instances of this class are usually contained within a ConfigDict.

    >>> lst = ConfigList(_rules={'_any': ['We only like ints', int, 0]})
    >>> lst.append('1')
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
    def _reset(self):
        self.rules = {}
        self[:] = []

    def append(self, value):
        list.append(self, None)
        try:
            self[len(self) - 1] = value
        except:
            self[len(self) - 1:] = []
            raise

    def extend(self, src):
        for val in src:
            self.append(val)

    def __iadd__(self, src):
        self.extend(src)
        return self

    def __passkey__(self, key, value):
        if hasattr(value, 'key'):
            value.key = b36(key).lower()

    def __getitem__(self, key):
        if isinstance(key, (str, unicode)):
            key = int(key, 36)
        return list.__getitem__(self, key)

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

    >>> pot['colors'].append('red')
    >>> pot['colors'].extend(['blue', 'red', 'red'])
    >>> pot['colors']
    ['red', 'blue', 'red', 'red']

    >>> pot['tags'].append({'c': '123', 'x': 'woots'})
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
    NAME = 'config'

    def _reset(self):
        self.rules = {}
        for key in self.keys():
            dict.__delitem__(self, key)

    def __delitem__(self, key):
        raise UsageError('Deleting keys from %s is not allowed' % self.NAME)

    def all_keys(self):
        keys = set(self.keys()) | set(self.rules.keys()) - set(['_any'])
        return list(keys)

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
    RULES = {
        '_any': ['Data directory', 'directory', '']
    }


class ConfigManager(dict): 

    MBOX_CACHE = {}
    RUNNING = {}
    DEFAULT_PATHS = {
        'html_theme': 'static/default', 
        'vcards': 'vcards', 
    }

    CATEGORIES = {
        'cfg': (3, 'User preferences'), 
        'prf': (4, 'User profiles and identities'), 
        'sys': (0, 'Technical system settings'), 
        'tag': (1, 'Tags and filters'), 
    }
    INTS = {
        'fd_cache_size': ('entries', 'sys', 'Max files kept open at once'), 
        'history_length': ('lines', 'sys', 'History length, <0 = no save'), 
        'http_port': ('port', 'sys', 'Listening port for web UI'), 
        'num_results': ('results', 'cfg', 'Search results per page'), 
        'postinglist_kb': ('kilobytes', 'sys', 'Posting list target size'), 
        'rescan_interval': ('seconds', 'cfg', 'New mail check frequency'), 
        'sort_max': ('results', 'sys', 'Max results we sort "well"'), 
        'snippet_max': ('characters', 'sys', 'Max size of metadata snippets'), 
        'gpg_clearsign': ('boolean', 'cfg', 'Inline PGP signatures or attached'), 
    }
    STRINGS = {
        'debug': ('level', 'sys', 'Enable debugging'), 
        'default_order': ('order', 'cfg', 'Default sort order'), 
        'gpg_recipient': ('key ID', 'cfg', 'Encrypt local data to ...'), 
        'gpg_keyserver': ('host:port', 'sys', 'Preferred GPG key server'), 
        'http_host': ('hostname', 'sys', 'Listening host for web UI'), 
        'local_mailbox': ('/dir/path', 'sys', 'Local read/write Maildir'), 
        'mailindex_file': ('/file/path', 'sys', 'Metadata index file'), 
        'postinglist_dir': ('/dir/path', 'sys', 'Search index directory'), 
        'rescan_command': ('shell command', 'cfg', 'Command run before rescanning'), 
        'obfuscate_index': ('key', 'sys', 'Scramble the index using key'), 
    }
    DICTS = {
        'mailbox': ('id=/file/path', 'sys', 'Mailboxes we index'), 
        'my_from': ('email=name', 'prf', 'Name in From: line'), 
        'my_sendmail': ('email=method', 'prf', 'How to send mail'), 
        'filter': ('id=comment', 'tag', 'Human readable description'), 
        'filter_terms': ('id=terms', 'tag', 'Search terms to match on'), 
        'filter_tags': ('id=tags', 'tag', 'Tags to add/remove'), 
        'path': ('ide=/dir/path', 'sys', 'Locations of assorted data'), 
        'tag': ('id=name', 'tag', 'Mailpile tags'), 
    }
    CONFIG_MIGRATE = {
        'from': 'my_from', 
        'sendmail': 'my_sendmail'
    }

    def __init__(self, workdir=None): 
        self.background = None
        self.cron_worker = None
        self.http_worker = None
        self.dumb_worker = self.slow_worker = DumbWorker('Dumb worker', None)
        self.index = None
        self.vcards = {}
        self.workdir = workdir or os.environ.get('MAILPILE_HOME', 
                                                                                         os.path.expanduser('~/.mailpile'))

    def conffile(self): 
        return os.path.join(self.workdir, 'config.rc')

    def key_string(self, key): 
        if ': ' in key:
            key, subkey = key.split(': ', 1)
        else: 
            subkey = None
        if key in self: 
            if key in self.INTS: 
                 return '%s = %s (int)' % (key, self.get(key))
            else: 
                val = self.get(key)
                if subkey: 
                    if subkey in val: 
                        return '%s: %s = %s' % (key, subkey, val[subkey])
                    else: 
                        return '%s: %s is unset' % (key, subkey)
                else: 
                    return '%s = %s' % (key, self.get(key))
        else: 
            return '%s is unset' % key

    def parse_unset(self, session, arg): 
        key = arg.strip().lower()
        if key in self: 
            del self[key]
        elif ': ' in key and key.split(':', 1)[0] in self.DICTS:
            key, subkey = key.split(': ', 1)
            if key in self and subkey in self[key]: 
                del self[key][subkey]
        session.ui.notify(self.key_string(key))
        return True

    def parse_set(self, session, line): 
        key, val = [k.strip() for k in line.split('=', 1)]
        key = key.lower()
        if ': ' in key:
            key, subkey = key.split(': ', 1)
        else: 
            subkey = None
        key = self.CONFIG_MIGRATE.get(key, key)
        if key in self.INTS and subkey is None: 
            try: 
                self[key] = int(val)
            except ValueError: 
                raise UsageError('%s is not an integer' % val)
        elif key in self.STRINGS and subkey is None: 
            self[key] = val
        elif key in self.DICTS and subkey is not None: 
            if key not in self: 
                self[key] = {}
            self[key][subkey.strip()] = val
        else: 
            raise UsageError('Unknown key in config: %s' % key)
        session.ui.notify(self.key_string(key))
        return True

    def parse_config(self, session, line): 
        line = line.strip()
        if line.startswith('#') or not line: 
            pass
        elif '=' in line: 
            self.parse_set(session, line)
        else: 
            raise UsageError('Bad line in config: %s' % line)

    def load(self, session): 
        if not os.path.exists(self.workdir): 
            if session: session.ui.notify('Creating: %s' % self.workdir)
            os.mkdir(self.workdir)
        else: 
            self.index = None
            for key in self.INTS.keys() + self.STRINGS.keys() + self.DICTS.keys(): 
                if key in self: 
                    del self[key]
            try: 
                fd = open(self.conffile(), 'rb')
                try: 
                    decrypt_and_parse_lines(fd, lambda l: self.parse_config(session, l))
                except ValueError: 
                    pass
                fd.close()
            except IOError: 
                pass
        self.load_vcards(session)

    def save(self): 
        if not os.path.exists(self.workdir): 
            session.ui.notify('Creating: %s' % self.workdir)
            os.mkdir(self.workdir)
        fd = gpg_open(self.conffile(), self.get('gpg_recipient'), 'wb')
        fd.write('# Mailpile autogenerated configuration file\n')
        for key in sorted(self.keys()): 
            if key in self.DICTS: 
                for subkey in sorted(self[key].keys()): 
                    fd.write(('%s: %s = %s\n' % (key, subkey, self[key][subkey])).encode('utf-8'))
            else: 
                fd.write(('%s = %s\n' % (key, self[key])).encode('utf-8'))
        fd.close()

    def nid(self, what): 
        if what not in self or not self[what]: 
            return '0'
        else: 
            return b36(1+max([int(k, 36) for k in self[what]]))

    def clear_mbox_cache(self): 
        self.MBOX_CACHE = {}

    def is_editable_message(self, msg_info): 
        print 'MSG_INFO=%s' % msg_info
        for ptr in msg_info[MailIndex.MSG_PTRS].split(', '): 
            if not self.is_editable_mailbox(ptr[: MBX_ID_LEN]):
                return False
        editable = False
        for tid in msg_info[MailIndex.MSG_TAGS].split(', '): 
            # FIXME: Hard-coded tag names are bad
            if self.get('tag', {}).get(tid) in ('Drafts', 'Blank'): 
                editable = True
        return editable

    def is_editable_mailbox(self, mailbox_id): 
        # FIXME: This may be too narrow?
        mailbox_id = (mailbox_id is None and -1) or int(mailbox_id, 36)
        local_mailbox_id = int(self.get('local_mailbox', 'ZZZZZ'), 36)
        return (mailbox_id == local_mailbox_id)

    def open_mailbox(self, session, mailbox_id): 
        pfn = os.path.join(self.workdir, 'pickled-mailbox.%s' % mailbox_id)
        for mid, mailbox_fn in self.get_mailboxes(): 
            if int(mid, 36) == int(mailbox_id, 36): 
                try: 
                    if mid in self.MBOX_CACHE: 
                        self.MBOX_CACHE[mid].update_toc()
                    else: 
                        if session: 
                            session.ui.mark(('%s: Updating: %s'
                                                             ) % (mailbox_id, mailbox_fn))
                        self.MBOX_CACHE[mid] = cPickle.load(open(pfn, 'r'))
                except: 
                    if session: 
                        session.ui.mark(('%s: Opening: %s (may take a while)'
                                                         ) % (mailbox_id, mailbox_fn))
                    mbox = OpenMailbox(mailbox_fn)
                    mbox.editable = self.is_editable_mailbox(mailbox_id)
                    mbox.save(session, to=pfn)
                    self.MBOX_CACHE[mid] = mbox
                return self.MBOX_CACHE[mid]
        raise NoSuchMailboxError('No such mailbox: %s' % mailbox_id)

    def open_local_mailbox(self, session): 
        local_id = self.get('local_mailbox', None)
        if not local_id: 
            mailbox = os.path.join(self.workdir, 'mail')
            mbx = IncrementalMaildir(mailbox)
            local_id = (('0' * MBX_ID_LEN) + self.nid('mailbox'))[-MBX_ID_LEN: ]
            self.parse_set(session, 'mailbox: %s=%s' % (local_id, mailbox))
            self.parse_set(session, 'local_mailbox=%s' % (local_id))
        else: 
            local_id = (('0' * MBX_ID_LEN) + local_id)[-MBX_ID_LEN: ]
        return local_id, self.open_mailbox(session, local_id)

    def filter_swap(self, fid_a, fid_b): 
        tmp = {}
        for key in ('filter', 'filter_terms', 'filter_tags'): 
            tmp[key] = self[key][fid_a]
        for key in ('filter', 'filter_terms', 'filter_tags'): 
            self[key][fid_a] = self[key][fid_b]
        for key in ('filter', 'filter_terms', 'filter_tags'): 
            self[key][fid_b] = tmp[key]

    def filter_move(self, filter_id, filter_new_id): 
        # This just makes sure both exist, will raise of not
        f1, f2 = self['filter'][filter_id], self['filter'][filter_new_id]
        forig = int(filter_id, 36)
        ftarget = int(filter_new_id, 36)
        if forig > ftarget: 
            for fid in reversed(range(ftarget, forig)): 
                self.filter_swap(b36(fid+1).lower(), b36(fid).lower())
        else: 
            for fid in range(forig, ftarget): 
                self.filter_swap(b36(fid).lower(), b36(fid+1).lower())

    def get_filters(self, filter_on=None): 
        filters = self.get('filter', {}).keys()
        filters.sort(key=lambda k: int(k, 36))
        flist = []
        for fid in filters: 
            comment = self.get('filter', {}).get(fid, '')
            terms = unicode(self.get('filter_terms', {}).get(fid, ''))
            tags = unicode(self.get('filter_tags', {}).get(fid, ''))
            if filter_on is not None and terms != filter_on: 
                continue
            flist.append((fid, terms, tags, comment))
        return flist

    def get_from_address(self): 
        froms = self.get('my_from', {})
        for f in froms.keys(): 
            if f.startswith('*'): 
                return '%s <%s>' % (froms[f], f[1: ])
        for f in sorted(froms.keys()): 
            return '%s <%s>' % (froms[f], f)
        return None

    def get_sendmail(self, sender='default', rcpts='-t'): 
        global DEFAULT_SENDMAIL
        sm = self.get('my_sendmail', {})
        return sm.get(sender, sm.get('default', DEFAULT_SENDMAIL)) % {
            'rcpt': ', '.join(rcpts)
        }

    def get_mailboxes(self): 
        def fmt_mbxid(k): 
            k = b36(int(k, 36))
            if len(k) > MBX_ID_LEN: 
                raise ValueError('Mailbox ID too large: %s' % k)
            return (('0' * MBX_ID_LEN) + k)[-MBX_ID_LEN: ]
        mailboxes = self['mailbox'].keys()
        mailboxes.sort()
        return [(fmt_mbxid(k), self['mailbox'][k]) for k in mailboxes]

    def get_tag_id(self, tn): 
        tn = tn.lower()
        try: 
            tid = [t for t in self['tag'] if self['tag'][t].lower() == tn]
            return tid and tid[0] or None
        except KeyError: 
            return None

    def load_vcards(self, session): 
        try: 
            vcard_dir = self.data_directory('vcards')
            for fn in os.listdir(vcard_dir): 
                try: 
                    c = SimpleVCard().load(os.path.join(vcard_dir, fn))
                    c.gpg_recipient = lambda: self.get('gpg_recipient')
                    self.index_vcard(c)
                    session.ui.mark('Loaded %s' % c.email)
                except: 
                    import traceback
                    traceback.print_exc()
                    session.ui.warning('Failed to load vcard %s' % fn)
        except OSError: 
            pass

    def index_vcard(self, c): 
        if c.kind == 'individual': 
            for email, attrs in c.get('EMAIL', []): 
                self.vcards[email.lower()] = c
        else: 
            for handle, attrs in c.get('NICKNAME', []): 
                self.vcards[handle.lower()] = c
        self.vcards[c.random_uid] = c

    def deindex_vcard(self, c): 
        for email, attrs in c.get('EMAIL', []): 
            if email.lower() in self.vcards: 
                if c.kind == 'individual': 
                    del self.vcards[email.lower()]
        for handle, attrs in c.get('NICKNAME', []): 
            if handle.lower() in self.vcards: 
                if c.kind != 'individual': 
                    del self.vcards[handle.lower()]
        if c.random_uid in self.vcards: 
            del self.vcards[c.random_uid]

    def get_vcard(self, email): 
        return self.vcards.get(email.lower(), None)

    def find_vcards(self, terms, kinds=['individual']): 
        results, vcards = [], self.vcards
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
        c.gpg_recipient = lambda: self.get('gpg_recipient')
        if kind == 'individual': 
            c.email = handle
        else: 
            c['NICKNAME'] = handle
        if name is not None: c.fn = name
        if kind is not None: c.kind = kind
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

    def history_file(self): 
        return self.get('history_file', 
                                        os.path.join(self.workdir, 'history'))

    def mailindex_file(self): 
        return self.get('mailindex_file', 
                                        os.path.join(self.workdir, 'mailpile.idx'))

    def postinglist_dir(self, prefix): 
        d = self.get('postinglist_dir', 
                                 os.path.join(self.workdir, 'search'))
        if not os.path.exists(d): os.mkdir(d)
        d = os.path.join(d, prefix and prefix[0] or '_')
        if not os.path.exists(d): os.mkdir(d)
        return d

    def get_index(self, session): 
        if self.index: return self.index
        idx = MailIndex(self)
        idx.load(session)
        self.index = idx
        return idx

    def data_directory(self, ftype, mode='rb', mkdir=False): 
        # This should raise a KeyError if the ftype is unrecognized
        bpath = self.get('path', {}).get(ftype) or self.DEFAULT_PATHS[ftype]
        if not bpath.startswith('/'): 
            cpath = os.path.join(self.workdir, bpath)
            if os.path.exists(cpath) or 'w' in mode: 
                bpath = cpath
                if mkdir and not os.path.exists(cpath): 
                    os.mkdir(cpath)
            else: 
                bpath = os.path.join(os.path.dirname(__file__), '..', bpath)
        return bpath

    def open_file(self, ftype, fpath, mode='rb', mkdir=False): 
        if '..' in fpath: 
            raise ValueError('Parent paths are not allowed')
        bpath = self.data_directory(ftype, mode=mode, mkdir=mkdir)
        fpath = os.path.join(bpath, fpath)
        return fpath, open(fpath, mode)

    def prepare_workers(config, session, daemons=False): 
        # Set globals from config first...
        global APPEND_FD_CACHE_SIZE
        APPEND_FD_CACHE_SIZE = config.get('fd_cache_size', 
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
            rescan_interval = config.get('rescan_interval', None)
            if rescan_interval: 
                def rescan(): 
                    if 'rescan' not in config.RUNNING: 
                        rsc = Rescan(session, 'rescan')
                        rsc.serialize = False
                        config.slow_worker.add_task(None, 'Rescan', rsc.run)
                config.cron_worker.add_task('rescan', rescan_interval, rescan)

        if daemons and not config.http_worker: 
            # Start the HTTP worker if requested
            sspec = (config.get('http_host', 'localhost'), 
                             config.get('http_port', DEFAULT_PORT))
            if sspec[0].lower() != 'disabled' and sspec[1] >= 0: 
                config.http_worker = HttpWorker(session, sspec)
                config.http_worker.start()

    def stop_workers(config): 
        for w in (config.http_worker, config.slow_worker, config.cron_worker): 
            if w: w.quit()


if __name__ == "__main__":
    import doctest
    print '%s' % (doctest.testmod(optionflags=doctest.ELLIPSIS,
                                  extraglobs={'request': None}), )
