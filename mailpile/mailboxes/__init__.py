## Dear hackers!
##
## It would be great to have more mailbox classes.  They should be derived
## from or implement the same interfaces as Python's native mailboxes, with
## the additional constraint that they support pickling and unpickling using
## cPickle.  The mailbox class is also responsible for generating and parsing
## a "pointer" which should be a short as possible while still encoding the
## info required to locate this message and this message only within the
## larger mailbox.

import time
from urllib import quote, unquote

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.index.mailboxes import MailboxIndex
from mailpile.mailutils import MBX_ID_LEN
from mailpile.util import MboxRLock


__all__ = ['mbox', 'maildir', 'gmvault', 'macmail', 'pop3', 'wervd',
           'MBX_ID_LEN',
           'NoSuchMailboxError', 'IsMailbox', 'OpenMailbox']

MAILBOX_CLASSES = []


class NoSuchMailboxError(OSError):
    pass


def register(prio, cls):
    global MAILBOX_CLASSES
    MAILBOX_CLASSES.append((prio, cls))
    MAILBOX_CLASSES.sort()


def IsMailbox(fn, config):
    for pri, mbox_cls in MAILBOX_CLASSES:
        try:
            if mbox_cls.parse_path(config, fn):
                return (True, mbox_cls)
        except KeyboardInterrupt:
            raise
        except:
            pass
    return False


def OpenMailbox(fn, config, create=False):
    for pri, mbox_cls in MAILBOX_CLASSES:
        try:
            return mbox_cls(
                *mbox_cls.parse_path(config, fn, create=create, allow_empty=True))
        except KeyboardInterrupt:
            raise
        except:
            pass
    raise ValueError('Not a mailbox: %s' % fn)


def UnorderedPicklable(parent, editable=False):
    """A factory for generating unordered, picklable mailbox classes."""

    class UnorderedPicklableMailbox(parent):
        UNPICKLABLE = []

        def __init__(self, *args, **kwargs):
            parent.__init__(self, *args, **kwargs)
            self.editable = editable
            self.source_map = {}
            self.is_local = False
            self._last_updated = None
            self._lock = MboxRLock()
            self._index = None
            self._save_to = None
            self._encryption_key_func = lambda: None
            self._decryption_key_func = lambda: None
            self.__init2__(*args, **kwargs)


        def __init2__(self, *args, **kwargs):
            pass

        def __enter__(self, *args, **kwargs):
            self._lock.acquire()
            return self

        def __exit__(self, *args, **kwargs):
            self._lock.release()

        def __unicode__(self):
            return unicode(str(self))

        def describe_msg_by_ptr(self, msg_ptr):
            try:
                return self._describe_msg_by_ptr(msg_ptr)
            except KeyError:
                return _("message not found in mailbox")

        def _describe_msg_by_ptr(self, msg_ptr):
            return unicode(msg_ptr)

        def __setstate__(self, data):
            self.__dict__.update(data)
            self._lock = MboxRLock()
            with self._lock:
                self._index = None
                self._save_to = None
                self._encryption_key_func = lambda: None
                self._decryption_key_func = lambda: None
                if not hasattr(self, 'source_map'):
                    self.source_map = {}
                if (len(self.source_map) > 0 and
                        not hasattr(self, 'is_local') or not self.is_local):
                    self.is_local = True
                self.update_toc()

        def __getstate__(self):
            odict = self.__dict__.copy()
            # Pickle can't handle function objects.
            for dk in ['_save_to', '_index', '_last_updated',
                       '_encryption_key_func', '_decryption_key_func',
                       '_file', '_lock', 'parsed'] + self.UNPICKLABLE:
                if dk in odict:
                    del odict[dk]
            return odict

        def save(self, session=None, to=None, pickler=None):
            with self._lock:
                if to and pickler:
                    self._save_to = (pickler, to)
                if self._save_to and len(self) > 0:
                    pickler, fn = self._save_to
                    if session:
                        session.ui.mark(_('Saving %s state to %s')
                                        % (self, fn))
                    pickler(self, fn)

        def add_from_source(self, source_id, metadata_kws, *args, **kwargs):
            with self._lock:
                key = self.add(*args, **kwargs)
                self.set_metadata_keywords(key, metadata_kws)
                self.source_map[source_id] = key
            return key

        def update_toc(self):
            self._last_updated = time.time()
            self._refresh()
            self._last_updated = time.time()

        def last_updated(self):
            return self._last_updated

        def get_msg_ptr(self, mboxid, toc_id):
            return '%s%s' % (mboxid, quote(toc_id))

        def get_file(self, *args, **kwargs):
            with self._lock:
                return parent.get_file(self, *args, **kwargs)

        def get_file_by_ptr(self, msg_ptr):
            return self.get_file(unquote(msg_ptr[MBX_ID_LEN:]))

        def remove_by_ptr(self, msg_ptr):
            self._last_updated = time.time()
            return self.remove(unquote(msg_ptr[MBX_ID_LEN:]))

        def get_msg_size(self, toc_id):
            with self._lock:
                fd = self.get_file(toc_id)
                fd.seek(0, 2)
                return fd.tell()

        def get_bytes(self, toc_id, *args):
            with self._lock:
                return self.get_file(toc_id).read(*args)

        def get_string(self, *args, **kwargs):
            with self._lock:
                return parent.get_string(self, *args, **kwargs)

        def get_metadata_keywords(self, toc_id):
            # Subclasses should translate whatever internal metadata they
            # have into mailpile keywords describing message metadata
            return []

        def set_metadata_keywords(self, toc_id, kws):
            pass

        def get_index(self, config, mbx_mid=None):
            with self._lock:
                if self._index is None:
                    self._index = MailboxIndex(config, self, mbx_mid=mbx_mid)
            return self._index

        def remove(self, *args, **kwargs):
            with self._lock:
                self._last_updated = time.time()
                return parent.remove(self, *args, **kwargs)

        def _get_fd(self, *args, **kwargs):
            with self._lock:
                return parent._get_fd(self, *args, **kwargs)

        def _refresh(self, *args, **kwargs):
            with self._lock:
                return parent._refresh(self, *args, **kwargs)

        def __setitem__(self, *args, **kwargs):
            with self._lock:
                self._last_updated = time.time()
                return parent.__setitem__(self, *args, **kwargs)

        def __getitem__(self, *args, **kwargs):
            with self._lock:
                return parent.__getitem__(self, *args, **kwargs)


    return UnorderedPicklableMailbox
