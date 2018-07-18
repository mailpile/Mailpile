import errno
import mailbox
import os
import re
import threading
import time
import traceback

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.index.mailboxes import MailboxIndex
from mailpile.mailboxes import MBX_ID_LEN, NoSuchMailboxError
from mailpile.util import *


class MboxIndex(MailboxIndex):
    pass


class MailpileMailbox(mailbox.mbox):
    """A mbox class that supports pickling and a few mailpile specifics."""
    RE_STATUS = re.compile(
        '^(X-)?Status:\s*\S+', flags=re.IGNORECASE|re.MULTILINE)

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
        self._cs = {}
        mailbox.mbox.__init__(self, *args, **kwargs)
        self.editable = False
        self.is_local = False
        self._last_updated = 0
        self._mtime = 0
        self._index = None
        self._save_to = None
        self._encryption_key_func = lambda: None
        self._decryption_key_func = lambda: None
        self._lock = MboxRLock()

    def __enter__(self, *args, **kwargs):
        self._lock.acquire()
        self.lock()
        return self

    def __exit__(self, *args, **kwargs):
        self.unlock()
        self._lock.release()

    def __unicode__(self):
        return _("Unix mbox at %s") % self._path

    def describe_msg_by_ptr(self, msg_ptr):
        try:
            parts, start, length = self._parse_ptr(msg_ptr)
            return _("message at bytes %d..%d") % (start, start + length)
        except KeyError:
            return _("message not found in mailbox")

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
        for dk in ('_save_to', '_index', '_last_updated',
                   '_encryption_key_func', '_decryption_key_func',
                   '_file', '_lock', 'parsed'):
            if dk in odict:
                del odict[dk]
        return odict

    def last_updated(self):
        return self._last_updated

    def keys(self):
        self.update_toc()
        return mailbox.mbox.keys(self)

    def toc_values(self):
        self.update_toc()
        return self._toc.values()

    def update_toc(self):
        fd = self._get_fd()
        fd.seek(0, 2)
        cur_length = fd.tell()
        cur_mtime = os.path.getmtime(self._path)
        try:
            if (self._file_length == cur_length and
                    self._mtime == cur_mtime):
                return
        except (NameError, AttributeError):
            pass

        with self._lock:
            fd.seek(0)
            self._next_key = 0
            self._toc = {}
            self._cs = {}
            data = ''
            start = None
            len_nl = 1
            while True:
                self._last_updated = time.time()
                line_pos = fd.tell()
                line = fd.readline()
                if line.startswith('From '):
                    if start is not None:
                        len_nl = ('\r' == line[-2]) and 2 or 1
                        cs4k = self.get_msg_cs4k(0, 0, data[:-len_nl])
                        self._toc[self._next_key] = (start, line_pos - len_nl)
                        self._cs[cs4k] = self._next_key
                        self._cs[self._next_key] = cs4k
                        self._next_key += 1
                    start = line_pos
                    data = line
                elif line == '':
                    if (start is not None) and (start != line_pos):
                        cs4k = self.get_msg_cs4k(0, 0, data[:-len_nl])
                        self._toc[self._next_key] = (start, line_pos - len_nl)
                        self._cs[cs4k] = self._next_key
                        self._cs[self._next_key] = cs4k
                        self._next_key += 1
                    break
                elif len(data) < (4096 + len_nl):
                    data += line
            self._file = fd
            self._file_length = fd.tell()
            self._mtime = cur_mtime
        self.save(None)

    def _generate_toc(self):
        self.update_toc()

    def __setitem__(self, *args, **kwargs):
        with self._lock:
            mailbox.mbox.__setitem__(self, *args, **kwargs)

    def __delitem__(self, *args, **kwargs):
        with self._lock:
            mailbox.mbox.__delitem__(self, *args, **kwargs)

    def save(self, session=None, to=None, pickler=None):
        if to and pickler:
            self._save_to = (pickler, to)
        if self._save_to and len(self) > 0:
            with self._lock:
                pickler, fn = self._save_to
                if session:
                    session.ui.mark(_('Saving %s state to %s') % (self, fn))
                pickler(self, fn)

    def _locked_flush_without_tempfile(self):
        """Dangerous, but we need this for /var/mail/USER on many Linuxes"""
        with open(self._path, 'rb+') as new_file:
            new_toc = {}
            for key in sorted(self._toc.keys()):
                start, stop = self._toc[key]
                new_start = new_file.tell()
                while True:
                    buf = self._file.read(min(4096, stop-self._file.tell()))
                    if buf == '':
                        break
                    new_file.write(buf)
                new_toc[key] = (new_start, new_file.tell())
            new_file.truncate()
        self._file.seek(0, 0)
        self._toc = new_toc
        self._pending = False
        self._pending_sync = False

    def flush(self, *args, **kwargs):
        with self._lock:
            self._last_updated = time.time()
            try:
                if kwargs.get('in_place', False):
                    self._locked_flush_without_tempfile()
                else:
                    mailbox.mbox.flush(self, *args, **kwargs)
            except OSError:
                if '_create_temporary' in traceback.format_exc():
                    self._locked_flush_without_tempfile()
                else:
                    raise
            self._last_updated = time.time()

    def clear(self, *args, **kwargs):
        with self._lock:
            mailbox.mbox.clear(self, *args, **kwargs)

    def get_msg_size(self, toc_id):
        try:
            with self._lock:
                # Note: This is 1 byte less than the TOC measures, because
                #       the final newline is ommitted. The From line is
                #       included though.
                start, stop = self._toc[toc_id]
                return (stop - start)
        except (IndexError, KeyError, IndexError, TypeError):
            return 0

    def get_metadata_keywords(self, toc_id):
        # In an mbox, all metadata is in the message headers.
        return []

    def set_metadata_keywords(self, *args, **kwargs):
        pass

    def get_index(self, config, mbx_mid=None):
        with self._lock:
            if self._index is None:
                self._index = MboxIndex(config, self, mbx_mid=mbx_mid)
        return self._index

    def get_msg_cs(self, start, cs_size, max_length, chars=4, data=None):
        """Generate a checksum of a given length, ignoring Status headers."""
        if data is None:
            if start is None:
                raise IOError('No data found (start=None)')
            with self._lock:
                fd = self._file
                fd.seek(start, 0)
                data = fd.read(min(cs_size, max_length))
                if data == '':
                    raise IOError('No data found at %s:%s'
                                  % (start, max_length))
        elif len(data) >= cs_size:
            data = data[:cs_size]
        return b64w(sha1b64(
            re.sub(self.RE_STATUS, 'Status: ?', data))[:chars])

    def get_msg_cs4k(self, start, max_length, data=None):
        """A 48-bit (6*8) checksum of the first 4k of message data."""
        return self.get_msg_cs(start, 4096, max_length, chars=8, data=data)

    def get_msg_cs80b(self, start, max_length, data=None):
        """A 24-bit (6*4) checksum of the first 80 bytes of message data."""
        return self.get_msg_cs(start, 80, max_length, data=data)

    def get_msg_ptr(self, mboxid, toc_id, data=None):
        with self._lock:
            msg_start = self._toc[toc_id][0]
            msg_size = self.get_msg_size(toc_id)
            if (toc_id in self._cs) and (data is None):
                msg_cs = self._cs[toc_id]
            else:
                msg_cs = self.get_msg_cs4k(msg_start, msg_size, data=data)
            return '%s%s:%s:%s' % (
                mboxid, b36(msg_start), b36(msg_size), msg_cs)

    def _parse_ptr(self, msg_ptr):
        parts = msg_ptr[MBX_ID_LEN:].split(':')
        start = int(parts[0], 36)
        length = int(parts[1], 36)
        if len(parts) > 2:
            if parts[2] in self._cs:
                start, end = self._toc[self._cs[parts[2]]]
                length = end - start
        return parts, start, length

    def _verify_ptr_checksums(self, msg_ptr, start, ignored_fd):
        """Check whether the msg_ptr checksums match the data at [start]."""
        with self._lock:
            parts, ignored_start, length = self._parse_ptr(msg_ptr)
            cs80b = self.get_msg_cs80b(start, length)
            if len(parts) > 2:
                cs4k = self.get_msg_cs4k(start, length)
                cs = parts[2]
                if (cs4k != cs and cs80b != cs):
                    return False
        return True

    def _possible_message_locations(self, msg_ptr, max_locations=15):
        """Yield possible locations for messages of a given size."""
        with self._lock:
            parts, pstart, length = self._parse_ptr(msg_ptr)

            # This is where it is SUPPOSED to be, always check that first.
            starts = [pstart]

            # Extend the list with other messages of the right size.
            # We accept two lengths, because there were off-by-one errors
            # in older versions of Mailpile. :-(
            starts.extend(sorted([
                b for b, e in self.toc_values()
                if length in (e-b, e-b+1) and b != pstart]))

        # Yield up to max_locations positions
        for i, start in enumerate(starts[:max_locations]):
            yield (start, length)

    def _get_SSLP_by_ptr(self, msg_ptr, verifier=None, from_=False):
        if verifier is None:
            verifier = self._verify_ptr_checksums
        tries = []
        length = None
        for from_start, length in self._possible_message_locations(msg_ptr):
            # We duplicate the file descriptor here, in case other threads
            # are accessing the same mailbox and moving it around, or in
            # case we have multiple PartialFile objects in flight at once.
            tries.append(str(from_start))
            try:
                start = from_start
                stop = from_start + length
                fd = self._get_fd()
                if not from_:
                    fd.seek(start)
                    length -= len(fd.readline())
                    start = fd.tell()
                pf = mailbox._PartialFile(fd, start, stop)
                if verifier(msg_ptr, from_start, pf):
                    return (from_start, start, length, pf)
            except IOError:
                pass
        err = '%s: %s %s@%s' % (
            _('Message not found'), msg_ptr, length, '/'.join(tries))
        raise IOError(err)

    def update(self, *args, **kwargs):
        with self._lock:
            self._cs = {}  # FIXME
            return mailbox.mbox.update(self, *args, **kwargs)

    def discard(self, *args, **kwargs):
        with self._lock:
            self._cs = {}  # FIXME
            return mailbox.mbox.discard(self, *args, **kwargs)

    def remove(self, *args, **kwargs):
        with self._lock:
            self._cs = {}  # FIXME
            return mailbox.mbox.remove(self, *args, **kwargs)

    def get_file_by_ptr(self, msg_ptr, verifier=None, from_=False):
        with self._lock:
            from_start, start, length, pfile = self._get_SSLP_by_ptr(
                msg_ptr, verifier=verifier, from_=from_)
        return pfile

    def remove_by_ptr(self, msg_ptr):
        with self._lock:
            from_start, start, length, pfile = self._get_SSLP_by_ptr(msg_ptr)
            keys = [k for k in self._toc if self._toc[k][0] == from_start]
            if keys:
                return self.remove(keys[0])
        raise KeyError('Not found: %s' % msg_ptr)

    def get_bytes(self, toc_id, *args, **kwargs):
        with self._lock:
            return self.get_file(toc_id, *args, **kwargs).read()

    def get_file(self, *args, **kwargs):
        with self._lock:
            return mailbox.mbox.get_file(self, *args, **kwargs)


if __name__ == "__main__":
    import tempfile, time, sys
    verbose = ('-v' in sys.argv) or ('--verbose' in sys.argv)
    wait = ('-w' in sys.argv) or ('--wait' in sys.argv)

    MSG_TEMPLATE = """\
From bre@mailpile.is  Mon Jan  1 08:14:00 2018
Return-Path: <bre@mailpile.is>
Subject: %(subject)s
Message-ID: <%(msgid)s>
Content-Length: %(length)s

%(content)s"""

    problems = tests = 0
    with tempfile.NamedTemporaryFile() as tf:
        lengths = []
        for count in range(0, 35):
             body = ''.join([
                 'Hello world, this is a message!\n'
                 ] * ((27 * (100-count)) % 1230))
             message = (MSG_TEMPLATE % {
                 'subject': 'Test message #%d' % count,
                 'msgid': '%d@example.com' % count,
                 'length': len(body),
                 'content': body})
             lengths.append(len(message))
             tf.write(message)
             tf.write("\n")
        tf.flush()
        if verbose or wait:
            print 'Temporary mailbox in: %s' % tf.name
        if wait:
            raw_input('Press ENTER to continue...')

        pmbx = mailbox.mbox(tf.name)
        mmbx = MailpileMailbox(tf.name)
        ptrs = []
        for i, key in enumerate(mmbx.keys()):
             msg_ptr = mmbx.get_msg_ptr('0000', key)
             o_size = lengths[i]
             c_size = mmbx.get_msg_size(key)
             f_size = len(mmbx.get_bytes(key, from_=True))
             f2size = len(mmbx.get_file_by_ptr(msg_ptr, from_=True).read())
             result = 'ok' if (o_size == c_size == f_size == f2size) else 'BAD'
             if verbose or result != 'ok':
                 print "%-3.3s [%s/%s/%s] %s ?= %s ?= %s ?= %s" % (
                     result, i, key, msg_ptr, o_size, c_size, f_size, f2size)
             if result != 'ok':
                 problems += 1
             tests += 1
             ptrs.append([msg_ptr, f2size])

        # Remove some messages, bypassing MailpileMailbox
        deletions = [0, 5, 10, 15, 34]
        for d in reversed(sorted(deletions)):
            del pmbx[d]
        pmbx.flush()

        # Remove a message using MailpileMailbox
        try:
            tests += 1
            deletions.append(1)
            mmbx.remove_by_ptr(ptrs[1][0])
            mmbx.flush()
        except KeyError:
            problems += 1

        for i, (msg_ptr, f2size) in enumerate(ptrs):
            tests += 1
            if i in deletions:
                try:
                    mmbx.get_file_by_ptr(msg_ptr, from_=True).read()
                    problems += 1
                    print('BAD Found deleted message %s' % msg_ptr)
                except IOError:
                    if verbose:
                        print('ok  IOError on message %s' % msg_ptr)
                continue
            f3size = len(mmbx.get_file_by_ptr(msg_ptr, from_=True).read())
            if (f2size != f3size):
                problems += 1
                print('BAD Message %s: wrong size in new location' % msg_ptr)
            elif verbose:
                print('ok  Message %s found in new location' % msg_ptr)

        # This is formatted to look like doctest results...
        print 'TestResults(failed=%d, attempted=%d)' % (problems, tests)
        if wait:
            raw_input('Tests finished. Press ENTER to clean up...')

    if problems:
        sys.exit(1)
else:
    import mailpile.mailboxes
    mailpile.mailboxes.register(90, MailpileMailbox)
