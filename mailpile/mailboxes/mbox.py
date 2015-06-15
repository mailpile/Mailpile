import errno
import mailbox
import os
import threading

import mailpile.mailboxes
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
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
        self.is_local = False
        self._mtime = 0
        self._save_to = None
        self._encryption_key_func = lambda: None
        self._decryption_key_func = lambda: None
        self._lock = MboxRLock()

    def __enter__(self, *args, **kwargs):
        self._lock.acquire()
        return self

    def __exit__(self, *args, **kwargs):
        self._lock.release()

    def _get_fd(self):
        return open(self._path, 'rb+')

    def __setstate__(self, dict):
        self.__dict__.update(dict)
        self._lock = MboxRLock()
        self.is_local = False
        with self._lock:
            self._save_to = None
            self._encryption_key_func = lambda: None
            self._decryption_key_func = lambda: None
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
        self.update_toc()

    def __getstate__(self):
        odict = self.__dict__.copy()
        # Pickle can't handle function objects.
        for dk in ('_save_to',
                   '_encryption_key_func', '_decryption_key_func',
                   '_file', '_lock', 'parsed'):
            if dk in odict:
                del odict[dk]
        return odict

    def update_toc(self):
        with self._lock:
            fd = self._file

            # FIXME: Should also check the mtime.
            fd.seek(0, 2)
            cur_length = fd.tell()
            cur_mtime = os.path.getmtime(self._path)
            try:
                if (self._file_length == cur_length and
                        self._mtime == cur_mtime):
                    return
            except (NameError, AttributeError):
                pass

            fd.seek(0)
            self._next_key = 0
            self._toc = {}
            start = None
            while True:
                line_pos = fd.tell()
                line = fd.readline()
                if line.startswith('From '):
                    if start is not None:
                        len_nl = ('\r' == line[-2]) and 2 or 1
                        self._toc[self._next_key] = (start, line_pos - len_nl)
                        self._next_key += 1
                    start = line_pos
                elif line == '':
                    if (start is not None) and (start != line_pos):
                        self._toc[self._next_key] = (start, line_pos)
                        self._next_key += 1
                    break

            self._file_length = fd.tell()
            self._mtime = cur_mtime
        self.save(None)

    def save(self, session=None, to=None, pickler=None):
        if to and pickler:
            self._save_to = (pickler, to)
        if self._save_to and len(self) > 0:
            with self._lock:
                pickler, fn = self._save_to
                if session:
                    session.ui.mark(_('Saving %s state to %s') % (self, fn))
                pickler(self, fn)

    def get_msg_size(self, toc_id):
        try:
            with self._lock:
                return self._toc[toc_id][1] - self._toc[toc_id][0]
        except (IndexError, KeyError, IndexError, TypeError):
            return 0

    def get_metadata_keywords(self, toc_id):
        # In an mbox, all metadata is in the message headers.
        return []

    def set_metadata_keywords(self, *args, **kwargs):
        pass

    def get_msg_cs(self, start, cs_size, max_length):
        with self._lock:
            if start is None:
                raise IOError(_('No data found'))
            fd = self._file
            fd.seek(start, 0)
            firstKB = fd.read(min(cs_size, max_length))
            if firstKB == '':
                raise IOError(_('No data found'))
            return b64w(sha1b64(firstKB)[:4])

    def get_msg_cs1k(self, start, max_length):
        return self.get_msg_cs(start, 1024, max_length)

    def get_msg_cs80b(self, start, max_length):
        return self.get_msg_cs(start, 80, max_length)

    def get_msg_ptr(self, mboxid, toc_id):
        with self._lock:
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

    def get_bytes(self, toc_id, *args):
        return self.get_file(toc_id).read(*args)


mailpile.mailboxes.register(90, MailpileMailbox)
