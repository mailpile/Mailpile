import mailbox
import os
import threading

import mailpile.mailboxes
from mailpile.mailboxes import MBX_ID_LEN, NoSuchMailboxError
from mailpile.util import *


class MailpileMailbox(mailbox.mbox):
    """A mbox class that supports pickling and a few mailpile specifics."""

    @classmethod
    def parse_path(cls, config, fn, create=False):
        try:
            firstline = open(fn, 'r').readline()
            if firstline.startswith('From '):
                return (fn, )
        except:
            if create and not os.path.exists(fn):
                return (fn, )
            pass
        raise ValueError('Not an mbox: %s' % fn)

    def __init__(self, *args, **kwargs):
        mailbox.mbox.__init__(self, *args, **kwargs)
        self.editable = False
        self.last_parsed = -1  # Must be -1 or first message won't get parsed
        self._save_to = None
        self._encryption_key_func = lambda: None
        self._lock = threading.Lock()

    def __getstate__(self):
        odict = self.__dict__.copy()
        # Pickle can't handle file objects.
        del odict['_file']
        del odict['_lock']
        del odict['_save_to']
        del odict['_encryption_key_func']
        return odict

    def _get_fd(self):
        return open(self._path, 'rb+')

    def __setstate__(self, dict):
        self.__dict__.update(dict)
        self._lock = threading.Lock()
        self._lock.acquire()
        self._save_to = None
        self._encryption_key_func = lambda: None
        try:
            try:
                if not os.path.exists(self._path):
                    raise NoSuchMailboxError(self._path)
                self._file = self._get_fd()
            except IOError, e:
                if e.errno == errno.ENOENT:
                    raise NoSuchMailboxError(self._path)
                elif e.errno == errno.EACCES:
                    self._file = self._get_fd()
                else:
                    raise
        finally:
            self._lock.release()
        self.update_toc()

    def unparsed(self):
        return range(self.last_parsed+1, len(self))

    def mark_parsed(self, i):
        self.last_parsed = i

    def update_toc(self):
        self._lock.acquire()
        try:
            # FIXME: Does this break on zero-length mailboxes?

            # Scan for incomplete entries in the toc, so they can get fixed.
            for i in sorted(self._toc.keys()):
                if i > 0 and self._toc[i][0] is None:
                    self._file_length = self._toc[i-1][0]
                    self._next_key = i-1
                    del self._toc[i-1]
                    del self._toc[i]
                    break
                elif self._toc[i][0] and not self._toc[i][1]:
                    self._file_length = self._toc[i][0]
                    self._next_key = i
                    del self._toc[i]
                    break

            fd = self._file
            self._file.seek(0, 2)
            if self._file_length == fd.tell():
                return

            fd.seek(self._toc[self._next_key-1][0])
            line = fd.readline()
            if not line.startswith('From '):
                raise IOError(_("Mailbox has been modified"))

            fd.seek(self._file_length-len(os.linesep))
            start = None
            while True:
                line_pos = fd.tell()
                line = fd.readline()
                if line.startswith('From '):
                    if start:
                        self._toc[self._next_key] = (
                            start, line_pos - len(os.linesep))
                        self._next_key += 1
                    start = line_pos
                elif line == '':
                    self._toc[self._next_key] = (start, line_pos)
                    self._next_key += 1
                    break
            self._file_length = fd.tell()
        finally:
            self._lock.release()
        self.save(None)

    def save(self, session=None, to=None, pickler=None):
        if to and pickler:
            self._save_to = (pickler, to)
        if self._save_to and len(self) > 0:
            self._lock.acquire()
            try:
                pickler, fn = self._save_to
                if session:
                    session.ui.mark(_('Saving %s state to %s') % (self, fn))
                pickler(self, fn)
            finally:
                self._lock.release()

    def get_msg_size(self, toc_id):
        return self._toc[toc_id][1] - self._toc[toc_id][0]

    def get_msg_cs(self, start, cs_size, max_length):
        self._lock.acquire()
        try:
            fd = self._file
            fd.seek(start, 0)
            firstKB = fd.read(min(cs_size, max_length))
            if firstKB == '':
                raise IOError(_('No data found'))
            return b64w(sha1b64(firstKB)[:4])
        finally:
            self._lock.release()

    def get_msg_cs1k(self, start, max_length):
        return self.get_msg_cs(start, 1024, max_length)

    def get_msg_cs80b(self, start, max_length):
        return self.get_msg_cs(start, 80, max_length)

    def get_msg_ptr(self, mboxid, toc_id):
        msg_start = self._toc[toc_id][0]
        msg_size = self.get_msg_size(toc_id)
        return '%s%s:%s:%s' % (mboxid,
                               b36(msg_start),
                               b36(msg_size),
                               self.get_msg_cs80b(msg_start, msg_size))

    def get_file_by_ptr(self, msg_ptr):
        parts = msg_ptr[MBX_ID_LEN:].split(':')
        start = int(parts[0], 36)
        length = int(parts[1], 36)

        # Make sure we can actually read the message
        cs80b = self.get_msg_cs80b(start, length)
        if len(parts) > 2:
            cs1k = self.get_msg_cs1k(start, length)
            cs = parts[2][:4]
            if (cs1k != cs and cs80b != cs):
                raise IOError(_('Message not found'))

        # We duplicate the file descriptor here, in case other threads are
        # accessing the same mailbox and moving it around, or in case we have
        # multiple PartialFile objects in flight at once.
        return mailbox._PartialFile(self._get_fd(), start, start + length)


mailpile.mailboxes.register(90, MailpileMailbox)
