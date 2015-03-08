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

def register(prio, obj):
    global VFS_HANDLERS
    VFS_HANDLERS.append((prio, obj))
    VFS_HANDLERS.sort()


class FilePath(object):
    """
    Wrapper for file-names, to manage the insanity of paths being binary
    data that people insist on treating as strings.
    """
    def __init__(self, cooked_fp=None, binary_fp=None):
        assert((cooked_fp or binary_fp) and not (cooked_fp and binary_fp))
        if cooked_fp:
            if isinstance(cooked_fp, FilePath):
                self.raw_fp = cooked_fp.raw_fp
            elif isinstance(cooked_fp, str) and cooked_fp[-2:] == '=!':
                self.raw_fp = cooked_fp[:-2].decode('base64')
            elif isinstance(cooked_fp, unicode):
                self.raw_fp = cooked_fp.encode('utf-8')
            else:
                self.raw_fp = str(cooked_fp)
        else:
            self.raw_fp = binary_fp

    def __unicode__(self, errors='strict'):
        try:
            return (self.raw_fp[2:] if (self.raw_fp[:2] == './')
                    else self.raw_fp).decode('utf-8', errors)
        except (UnicodeDecodeError, UnicodeEncodeError):
            return self.raw_fp.encode('base64').strip() + '=!'

    def __str__(self):
        return unicode(self).encode('utf-8')

    def startswith(self, stuff): return self.raw_fp.startswith(stuff)
    def endswith(self, stuff): return self.raw_fp.endswith(stuff)
    def display(self): return self.__unicode__('replace')
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
    def __init__(self):
        pass

    @classmethod
    def Accepts(cls, path):
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
            if handler.Accepts(path):
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
    def Accepts(cls, path):
        return True

    def glob_(self, *args, **kwargs): return glob.iglob(*args, **kwargs)
    def open_(self, *args, **kwargs): return open(*args, **kwargs)
    def listdir_(self, *args, **kwargs): return os.listdir(*args, **kwargs)
    def isdir_(self, *args, **kwargs): return os.path.isdir(*args, **kwargs)
    def getsize_(self, *args, **kwargs): return os.path.getsize(*args, **kwargs)
    def exists_(self, *args, **kwargs): return os.path.exists(*args, **kwargs)


register(9999, MailpileVfsLocal())
