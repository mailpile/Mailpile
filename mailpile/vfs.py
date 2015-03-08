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
import glob
import os
import posixpath


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
    def __init__(self, cooked_fp=None, binary_fp=None):
        assert((cooked_fp or binary_fp) and not (cooked_fp and binary_fp))
        if cooked_fp:
            if isinstance(cooked_fp, FilePath):
                self.raw_fp = cooked_fp.raw_fp
            elif isinstance(cooked_fp, str) and cooked_fp[-2:] == '=!':
                self.raw_fp = self.unalias(cooked_fp[:-2].decode('base64'))
            elif isinstance(cooked_fp, unicode):
                self.raw_fp = self.unalias(cooked_fp.encode('utf-8'))
            else:
                self.raw_fp = self.unalias(str(cooked_fp))
        else:
            self.raw_fp = binary_fp

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
        return FilePath(binary_fp=joined)


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

    @classmethod
    def path_join(cls, fp, *fps):
        return FilePath(fp).join(*fps)

    @classmethod
    def open(cls, fp, *args, **kwargs):
        return cls.open_(FilePath(fp).raw_fp, *args, **kwargs)

    @classmethod
    def glob(cls, fp, *args, **kwargs):
        return [FilePath(binary_fp=f) for f in
                cls.glob_(FilePath(fp).raw_fp, *args, **kwargs)]

    @classmethod
    def listdir(cls, fp, *args, **kwargs):
        return [FilePath(binary_fp=f) for f in
                cls.listdir_(FilePath(fp).raw_fp, *args, **kwargs)]

    @classmethod
    def isdir(cls, fp, *args, **kwargs):
        return cls.isdir_(FilePath(fp).raw_fp, *args, **kwargs)

    @classmethod
    def ismailbox(cls, fp, *args, **kwargs):
        return cls.ismailbox_(FilePath(fp).raw_fp, *args, **kwargs)

    @classmethod
    def getsize(cls, fp, *args, **kwargs):
        return cls.getsize_(FilePath(fp).raw_fp, *args, **kwargs)

    @classmethod
    def exists(cls, fp, *args, **kwargs):
        return cls.exists_(FilePath(fp).raw_fp, *args, **kwargs)

    @classmethod
    def _fixme(self):
        raise NotImplementedError('FIXME')

    glob_ = _fixme
    open_ = _fixme
    listdir_ = _fixme
    isdir_ = _fixme
    ismailbox_ = _fixme
    getsize_ = _fixme
    exists_ = _fixme


class MailpileVFS(MailpileVfsBase):
    """
    This is a router object that implements the VFS interface but,
    delegating calls to individual implementations depending on 
    """
    @classmethod
    def _delegate(cls, path):
        for prio, handler in VFS_HANDLERS:
            if handler.Handles(path):
                return handler
        raise IOError('Invalid path: %s' % path)

    @classmethod
    def glob_(self, path, *args, **kwargs):
        return self._delegate(path).glob_(path, *args, **kwargs)

    @classmethod
    def open_(self, path, *args, **kwargs):
        return self._delegate(path).open_(path, *args, **kwargs)

    @classmethod
    def listdir_(self, path, *args, **kwargs):
        return self._delegate(path).listdir_(path, *args, **kwargs)

    @classmethod
    def isdir_(self, path, *args, **kwargs):
        return self._delegate(path).isdir_(path, *args, **kwargs)

    @classmethod
    def ismailbox_(self, path, *args, **kwargs):
        return self._delegate(path).ismailbox_(path, *args, **kwargs)

    @classmethod
    def getsize_(self, path, *args, **kwargs):
        return self._delegate(path).getsize_(path, *args, **kwargs)

    @classmethod
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
    def isdir_(self, *args, **kwargs): return os.path.isdir(*args, **kwargs)
    def getsize_(self, *args, **kwargs): return os.path.getsize(*args, **kwargs)
    def exists_(self, *args, **kwargs): return os.path.exists(*args, **kwargs)


vfs = MailpileVFS
register_handler(9999, MailpileVfsLocal())
register_alias('/Home', os.path.expanduser('~'))
