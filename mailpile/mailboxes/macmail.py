import mailbox
import sys
import os
import warnings
import rfc822
import time
import errno

import mailpile.mailboxes
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import UnorderedPicklable


class _MacMaildirPartialFile(mailbox._PartialFile):
    def __init__(self, fd):
        length = int(fd.readline().strip())
        start = fd.tell()
        stop = start+length
        mailbox._PartialFile.__init__(self, fd, start=start, stop=stop)


class MacMaildirMessage(mailbox.Message):
    def __init__(self, message=None):
        if hasattr(message, "read"):
            length = int(message.readline().strip())
            message = message.read(length)

        mailbox.Message.__init__(self, message)


class MacMaildir(mailbox.Mailbox):
    def __init__(self, dirname, factory=rfc822.Message, create=True):
        mailbox.Mailbox.__init__(self, dirname, factory, create)
        if not os.path.exists(self._path):
            if create:
                raise NotImplemented("Why would we support creation of "
                                     "silly mailboxes?")
            else:
                raise mailbox.NoSuchMailboxError(self._path)

        # What have we here?
        ds = os.listdir(self._path)

        # Okay, MacMaildirs have Info.plist files
        if not 'Info.plist' in ds:
            raise mailbox.FormatError(self._path)

        # Now ignore all the files and dotfiles...
        ds = [d for d in ds if not d.startswith('.')
              and os.path.isdir(os.path.join(self._path, d))]

        # There should be exactly one directory left, which is our "ID".
        if len(ds) == 1:
            self._id = ds[0]
        else:
            raise mailbox.FormatError(self._path)

        # And finally, there's a Data folder (with .emlx files  in it)
        self._mailroot = "%s/%s/Data/" % (self._path, self._id)
        if not os.path.isdir(self._mailroot):
            raise mailbox.FormatError(self._path)

        self._toc = {}
        self._last_read = 0

    def remove(self, key):
        """Remove the message or raise error if nonexistent."""
        safe_remove(os.path.join(self._mailroot, self._lookup(key)))
        try:
            del self._toc[key]
        except:
            pass

    def discard(self, key):
        """If the message exists, remove it."""
        try:
            self.remove(key)
        except KeyError:
            pass
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise

    def __setitem__(self, key, message):
        """Replace a message"""
        raise NotImplemented("Mailpile is readonly, for now.")

    def iterkeys(self):
        self._refresh()
        for key in self._toc:
            try:
                self._lookup(key)
            except KeyError:
                continue
            yield key

    def has_key(self, key):
        self._refresh()
        return key in self._toc

    def __len__(self):
        self._refresh()
        return len(self._toc)

    def _refresh(self):
        self._toc = {}
        paths = [""]

        while not paths == []:
            curpath = paths.pop(0)
            fullpath = os.path.join(self._mailroot, curpath)
            try:
                for entry in os.listdir(fullpath):
                    p = os.path.join(fullpath, entry)
                    if os.path.isdir(p):
                        paths.append(os.path.join(curpath, entry))
                    elif entry[-5:] == ".emlx":
                        self._toc[entry[:-5]] = os.path.join(curpath, entry)
            except (OSError, IOError):
                pass  # Ignore difficulties reading individual folders

    def _lookup(self, key):
        try:
            if os.path.exists(os.path.join(self._mailroot, self._toc[key])):
                return self._toc[key]
        except KeyError:
            pass
        self._refresh()
        try:
            return self._toc[key]
        except KeyError:
            raise KeyError("No message with key %s" % key)

    def get_message(self, key):
        f = open(os.path.join(self._mailroot, self._lookup(key)), 'r')
        msg = MacMaildirMessage(f)
        f.close()
        return msg

    def get_file(self, key):
        f = open(os.path.join(self._mailroot, self._lookup(key)), 'r')
        return _MacMaildirPartialFile(f)


class MailpileMailbox(UnorderedPicklable(MacMaildir)):
    """A Mac Mail.app maildir class that supports pickling etc."""
    @classmethod
    def parse_path(cls, config, fn, create=False):
        if (os.path.isdir(fn)
                and os.path.exists(os.path.join(fn, 'Info.plist'))):
            return (fn, )
        raise ValueError('Not a Mac Mail.app Maildir: %s' % fn)

    def __unicode__(self):
        return _("Mac Maildir %s") % self._mailroot

    def _describe_msg_by_ptr(self, msg_ptr):
        return _("e-mail in file %s") % self._lookup(msg_ptr[MBX_ID_LEN:])


mailpile.mailboxes.register(50, MailpileMailbox)
