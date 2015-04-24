import email.generator
import email.message
import mailbox
import StringIO
import sys

import mailpile.mailboxes
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import UnorderedPicklable
from mailpile.crypto.streamer import *
from mailpile.util import safe_remove


class MailpileMailbox(UnorderedPicklable(mailbox.Maildir, editable=True)):
    """A Maildir class that supports pickling and a few mailpile specifics."""
    supported_platform = None

    @classmethod
    def parse_path(cls, config, fn, create=False):
        if (((cls.supported_platform is None) or
             (cls.supported_platform == sys.platform[:3].lower())) and
                ((os.path.isdir(fn) and
                  os.path.exists(os.path.join(fn, 'cur')) and
                  os.path.exists(os.path.join(fn, 'wervd.ver'))) or
                 (create and not os.path.exists(fn)))):
            return (fn, )
        raise ValueError('Not a Maildir: %s' % fn)

    def __init2__(self, *args, **kwargs):
        open(os.path.join(self._path, 'wervd.ver'), 'w+b').write('0')

    def remove(self, key):
        # FIXME: Remove all the copies of this message!
        with self._lock:
            fn = os.path.join(self._path, self._lookup(key))
            del self._toc[key]
        safe_remove(fn)

    def _refresh(self):
        with self._lock:
            mailbox.Maildir._refresh(self)
            # WERVD mail names don't have dots in them
            for t in [k for k in self._toc.keys() if '.' in k]:
                del self._toc[t]
        safe_remove()  # Try to remove any postponed removals

    def _get_fd(self, key):
        with self._lock:
            fd = open(os.path.join(self._path, self._lookup(key)), 'rb')
            mep_key = self._decryption_key_func()
        if mep_key:
            fd = DecryptingStreamer(fd, mep_key=mep_key, name='WERVD')
        return fd

    def get_message(self, key):
        """Return a Message representation or raise a KeyError."""
        with self._lock:
            with self._get_fd(key) as fd:
                if self._factory:
                    return self._factory(fd)
                else:
                    return mailbox.MaildirMessage(fd)

    def get_string(self, key):
        with self._lock:
            with self._get_fd(key) as fd:
                return fd.read()

    def get_file(self, key):
        with self._lock:
            return StringIO.StringIO(self.get_string(key))

    def add(self, message, copies=1):
        """Add message and return assigned key."""
        key = self._encryption_key_func()
        es = None
        try:
            tmpdir = os.path.join(self._path, 'tmp')
            if key:
                es = EncryptingStreamer(key,
                                        dir=tmpdir, name='WERVD',
                                        delimited=False)
            else:
                es = ChecksummingStreamer(dir=tmpdir, name='WERVD')
            self._dump_message(message, es)
            es.finish()

            # We are using the MD5 to detect file system corruption, not in a
            # security context - so using as little as 40 bits should be fine.
            saved = False
            key = None
            for l in range(10, len(es.outer_md5sum)):
                key = es.outer_md5sum[:l]
                fn = os.path.join(self._path, 'new', key)
                if not os.path.exists(fn):
                    es.save(fn)
                    saved = self._toc[key] = os.path.join('new', key)
                    break
            if not saved:
                raise mailbox.ExternalClashError(_('Could not find a filename '
                                                   'for the message.'))

            for cpn in range(1, copies):
                fn = os.path.join(self._path, 'new', '%s.%s' % (key, cpn))
                with mailbox._create_carefully(fn) as ofd:
                    es.save_copy(ofd)

            return key
        finally:
            if es is not None:
                es.close()

    def _dump_message(self, message, target):
        if isinstance(message, email.message.Message):
            gen = email.generator.Generator(target, False, 0)
            gen.flatten(message)
        elif isinstance(message, str):
            target.write(message)
        else:
            raise TypeError(_('Invalid message type: %s') % type(message))

    def __setitem__(self, key, message):
        raise IOError(_('Mailbox messages are immutable'))


mailpile.mailboxes.register(15, MailpileMailbox)
