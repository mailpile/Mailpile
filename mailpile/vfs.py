# This is a very simple virtual file system abstraction for Mailpile.
#
# The purpose of this code is not to be a general-purpose VFS layer, but
# to solve these specific problems within Mailpile:
#
#   - Provide a uniform, pluggable interface for browsing both traditional
#     filesystems, remote IMAP servers and pretty much anything else within
#     the app that fits well into the filesystem metaphor.
#
#   - Provide a uniform, pluggable interface within Mailpile for working
#     with traditional filesystems which allows Mailpile's data to be
#     stored either locally or remotely.
#
#   - Get rid of absolute paths in Mailpile's configuration, so Mailpile's
#     settings and data can be moved around.
#
#   - Localize the code which deals with character sets and visual
#     representation of file names and paths to one place.
#
import copy
import glob
import os
import posixpath

from mailpile.i18n import gettext as _


VFS_HANDLERS = []
VFS_ALIASES = {}


def register_handler(prio, obj):
    global VFS_HANDLERS
    VFS_HANDLERS.append((prio, obj))
    VFS_HANDLERS.sort()

def register_alias(name, prefix):
    global VFS_ALIASES
    assert(name[:1] == '/')
    VFS_ALIASES[name] = prefix


class FilePath(object):
    """
    Wrapper for file-names, to manage the insanity of paths being binary
    data that people insist on treating as strings. This is also where we
    add and remove the /PREFIX$ stuff from paths.

    The Mailpile VFS knows to use the raw_fp attribute instead of the
    unicode() or str() representation, those methods expose data which
    is suitable for writing to a config file or JSON stream.
    """
    def __init__(self, cooked_fp=None, binary_fp=None, flags=None):
        assert((cooked_fp or binary_fp) and not (cooked_fp and binary_fp))
        if cooked_fp:
            if isinstance(cooked_fp, FilePath):
                self.raw_fp = cooked_fp.raw_fp
                flags = cooked_fp.flags if (flags is None) else flags
            elif (isinstance(cooked_fp, (str, unicode)) and
                    cooked_fp[-2:] == '=!'):
                self.raw_fp = self.unalias(cooked_fp[:-2].decode('base64'))
            elif isinstance(cooked_fp, unicode):
                self.raw_fp = self.unalias(cooked_fp.encode('utf-8'))
            else:
                self.raw_fp = self.unalias(str(cooked_fp))
        else:
            self.raw_fp = binary_fp
        self.flags = flags

    @classmethod
    def unalias(self, fp):
        if '$' in fp:
            alias, path = fp.split('$', 1)
            if alias in VFS_ALIASES:
                return VFS_ALIASES[alias] + path
        return fp

    @classmethod
    def alias(self, fp):
        while fp[:2] == './':
            fp = fp[2:]
        alias, prefix = None, ''
        for a, p in VFS_ALIASES.iteritems():
            if len(p) > len(prefix) and fp.startswith(p):
                alias, prefix = a, p
        if alias:
            return '$'.join([alias, fp[len(prefix):]])
        return fp

    def __unicode__(self, errors='strict'):
        """Render file path as a cooked unicode string"""
        raw_fp = self.alias(self.raw_fp)
        try:
            return raw_fp.decode('utf-8', errors)
        except (UnicodeDecodeError, UnicodeEncodeError):
            return raw_fp.encode('base64').strip() + '=!'

    def __str__(self):
        """Render file path as a cooked string"""
        return unicode(self).encode('utf-8')

    def __eq__(self, other):
        return unicode(self) == unicode(other)

    def encoded(self):
        return self.alias(self.raw_fp).encode('base64').strip() + '=!'

    def display(self):
        """Lossy, user-friendly representation of this path."""
        return self.__unicode__('replace')

    def display_basename(self):
        """Lossy, user-friendly representation of path's base name."""
        return posixpath.basename(self.__unicode__('replace'))

    def startswith(self, stuff): return self.raw_fp.startswith(stuff)
    def endswith(self, stuff): return self.raw_fp.endswith(stuff)
    def lower(self): return self.__unicode__('replace').lower()
    def upper(self): return self.__unicode__('replace').upper()

    def join(self, *fpaths):
        joined = posixpath.join(self.raw_fp,
                                *[FilePath(fp).raw_fp for fp in fpaths])
        return FilePath(binary_fp=joined, flags=FilePath(fpaths[-1]).flags)


class MailpileVfsBase(object):
    """
    Base class for VFS Handler objects.
    """
    FS_ROOT = None

    def __init__(self):
        pass

    @classmethod
    def Handles(cls, path):
        if cls.FS_ROOT:
            return path.startswith(cls.FS_ROOT)
        return False

    def path_join(cls, fp, *fps):
        return FilePath(fp).join(*fps)

    def open(cls, fp, *args, **kwargs):
        return cls.open_(FilePath(fp).raw_fp, *args, **kwargs)

    # FIXME: Give us an open mailbox object, or raise IOError
    def open_mailbox(cls, fp, *args, **kwargs):
        return cls.open_(FilePath(fp).raw_fp, *args, **kwargs)

    def glob(cls, fp, *args, **kwargs):
        return [FilePath(binary_fp=f) for f in
                cls.glob_(FilePath(fp).raw_fp, *args, **kwargs)]

    def listdir(cls, fp, *args, **kwargs):
        return [(f if isinstance(f, FilePath) else FilePath(binary_fp=f))
                for f in cls.listdir_(FilePath(fp).raw_fp, *args, **kwargs)]

    def getinfo(cls, fp, config):
        return cls.getinfo_(FilePath(fp).raw_fp, config)

    def getinfo_(cls, fp, config):
        fp = FilePath(fp)
        ap = cls.abspath(fp)
        return {
            'path': ap,
            'flags': cls.getflags(fp, config),
            'bytes': cls.getsize(fp),
            'display_name': cls.display_name(fp, config),
            'display_path': unicode(ap),
            'encoded': ap.encoded()
        }

    def display_name(cls, fp, config):
        return cls.display_name_(FilePath(fp).raw_fp, config)

    def display_name_(cls, fp, config):
        return FilePath(fp).display_basename()

    def abspath(cls, fp):
        return FilePath(binary_fp=cls.abspath_(FilePath(fp).raw_fp))

    def getflags(cls, fp, config):
        return cls.getflags_(FilePath(fp).raw_fp, config)

    def getflags_(cls, fp, config):
        # By default, this method just checks isdir_ and mailbox_type_,
        # but subclasses can override this (and even do things the other
        # way around, e.g. for IMAP).
        flags, fp = [], FilePath(fp)
        mailbox_type = cls.mailbox_type_(fp.raw_fp, config)
        flags.extend(['Mailbox', mailbox_type[1]] if mailbox_type else
                     ['NoSelect'])
        flags.extend(['Directory'] if cls.isdir_(fp.raw_fp) else
                     ['HasNoChildren', 'NoInferiors'])
        if cls.ismailsource_(fp.raw_fp):
            flags.append('MailSource')
        return flags

    def isdir(cls, fp):
        return cls.isdir_(FilePath(fp).raw_fp)

    def ismailsource(cls, fp):
        return cls.ismailsource_(FilePath(fp).raw_fp)

    def mailbox_type(cls, fp, config):
        return cls.mailbox_type_(FilePath(fp).raw_fp, config)

    def getsize(cls, fp):
        return cls.getsize_(FilePath(fp).raw_fp)

    def exists(cls, fp):
        return cls.exists_(FilePath(fp).raw_fp)

    def _fixme(self):
        raise NotImplementedError('FIXME')

    glob_ = _fixme
    open_ = _fixme
    listdir_ = _fixme
    abspath_ = _fixme
    isdir_ = _fixme
    ismailsource_ = _fixme
    mailbox_type_ = _fixme
    getsize_ = _fixme
    exists_ = _fixme


class MailpileVFS(MailpileVfsBase):
    """
    This is a router object that implements the VFS interface but,
    delegating calls to individual implementations.
    """
    def _delegate(cls, path):
        for prio, handler in VFS_HANDLERS:
            if handler.Handles(path):
                return handler
        raise IOError('Invalid path: %s' % path)

    def glob_(self, path, *args, **kwargs):
        return self._delegate(path).glob_(path, *args, **kwargs)

    def open_(self, path, *args, **kwargs):
        return self._delegate(path).open_(path, *args, **kwargs)

    def listdir_(self, path, *args, **kwargs):
        return self._delegate(path).listdir_(path, *args, **kwargs)

    def abspath_(self, path, *args, **kwargs):
        return self._delegate(path).abspath_(path, *args, **kwargs)

    def isdir_(self, path, *args, **kwargs):
        return self._delegate(path).isdir_(path, *args, **kwargs)

    def getflags_(self, path, *args, **kwargs):
        return self._delegate(path).getflags_(path, *args, **kwargs)

    def ismailsource_(self, path, *args, **kwargs):
        return self._delegate(path).ismailsource_(path, *args, **kwargs)

    def mailbox_type_(self, path, config):
        return self._delegate(path).mailbox_type_(path, config)

    def getsize_(self, path, *args, **kwargs):
        return self._delegate(path).getsize_(path, *args, **kwargs)

    def display_name_(self, path, *args, **kwargs):
        return self._delegate(path).display_name_(path, *args, **kwargs)

    def exists_(self, path, *args, **kwargs):
        return self._delegate(path).exists_(path, *args, **kwargs)


class MailpileVfsLocal(MailpileVfsBase):
    """
    Local filesystem VFS handler; pipes through to built-in Python API.

    FIXME: Our VFS uses Unix separators for everything, which implies that
           all the functions below need path mapping wrappers for other
           operating systems (Windows, in particular).
    """
    @classmethod
    def Handles(cls, path):
        return True

    def glob_(self, *args, **kwargs): return glob.iglob(*args, **kwargs)
    def open_(self, *args, **kwargs): return open(*args, **kwargs)
    def listdir_(self, *args, **kwargs): return os.listdir(*args, **kwargs)
    def abspath_(self, path): return os.path.abspath(path)
    def isdir_(self, path): return os.path.isdir(path)
    def ismailsource_(self, fp): return False
    def mailbox_type_(self, path, config):
        from mailpile.mailboxes import IsMailbox
        return IsMailbox(path, config)
    def getsize_(self, path): return os.path.getsize(path)
    def exists_(self, path): return os.path.exists(path)


class MailpileVfsRoot(MailpileVfsBase):
    """
    This VFS implements a fancy root listing, including things like:

       - Discovery of Thunderbird, Mail.app and Unix mail spools
       - Listing configured sources
       - Shortcut to the user's Home$
       - Shortcuts to any root level registered VFSes

    """
    def __init__(self, config):
        self.config = config
        self.rescan()

    def rescan(self):
        self.entries = {
            'home': (FilePath('/Home$'), _('My Files')),
#           'config': (FilePath('/Config$'), _('Settings')),
        }
        self._discover_mail_spool()
# FIXME: enable post beta III
#       self._discover_thunderbird()
        self._discover_local_mailboxes()

    def _discover_mail_spool(self):
        user = os.getenv('USER')
        for search in ('/var/mail', '/var/spool/mail'):
            if user and os.path.isdir(search):
                spool_path = os.path.join(search, user)
                if os.path.exists(spool_path):
                    spool_path = os.path.normpath(spool_path)
                    self.entries['spool'] = (FilePath(spool_path),
                                             _('Unix mail spool'))
                    return

    def _discover_local_mailboxes(self):
        """
        This exposes at the root local mailboxes which would not be listed
        otherwise, because their path falls outside of the user's home
        directory.
        """
        user_home = os.path.expanduser('~')
        for mbx_id, path, ms in self.config.get_mailboxes():
            path = FilePath(path)
            if (path.raw_fp[:4] != 'src:' and
                    not vfs.abspath(path).startswith(user_home)):
                path = FilePath(os.path.normpath(path.raw_fp))
                if not [e for e in self.entries if self.entries[e][0] == path]:
                    self.entries[mbx_id] = (path, path.display_basename())

    def _discover_thunderbird(self):
        for search in ('~/.thunderbird', ):
            tbird_home = os.path.expanduser(search)
            if os.path.exists(tbird_home):
                for profile in os.listdir(tbird_home):
                    profpath = os.path.join(tbird_home, profile)
                    if os.path.exists(os.path.join(profpath, 'Mail')):
                        eid = 'tbird-%s' % profile
                        name = 'Thunderbird %s' % profile.split('.', 1)[-1]
                        self.entries[eid] = (FilePath(profpath), name)

    def _entries(self):
        e = copy.copy(self.entries)
        for msid, msobj in self.config.mail_sources.iteritems():
            if not msobj.my_config.enabled:
                continue
            e['msrc.%s' % msid] = (FilePath('/src:%s' % msid), msobj.name,
                                   'MailSource')
        return e

    def Handles(self, path):
        path = FilePath(path).raw_fp
        return (path == '/') or (path[1:] in self._entries())

    def glob_(self, *args, **kwargs):
        return self.listdir_()

    def listdir_(self, fp, *args, **kwargs):
        return self._entries().keys() if (fp == '/') else []

    def display_name_(self, fp, config):
        try:
            return unicode(self._entries()[fp[1:]][1])
        except KeyError:
            return _('Mailpile VFS')

    def open_(self, fp, *args, **kwargs):
        raise IOError('Cannot open entries in /')

    def abspath_(self, fp):
        return ('/' if (fp == '/') else
                vfs.abspath(self._entries()[fp[1:]][0]).raw_fp)

    def isdir_(self, fp):
        return True if (fp == '/') else vfs.isdir(self._entries()[fp[1:]][0])

    def ismailsource_(self, fp):
        return (False if (fp == '/') else
                'MailSource' in self._entries()[fp[1:]][2:])

    def mailbox_type_(self, fp, config):
        if fp == '/':
            return False
        return vfs.mailbox_type(self._entries()[fp[1:]][0], config)

    def getsize_(self, fp):
        return True if (fp == '/') else vfs.getsize(self._entries()[fp[1:]][0])

    def exists_(self, fp):
        return True if (fp == '/') else vfs.exists(self._entries()[fp[1:]][0])


vfs = MailpileVFS()
register_handler(9999, MailpileVfsLocal())
register_alias('/Home', os.path.expanduser('~'))
