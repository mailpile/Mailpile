import mailbox
import os
import sys

import mailpile.mailboxes
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import UnorderedPicklable


class MailpileMailbox(UnorderedPicklable(mailbox.Maildir, editable=True)):
    """A Maildir class that supports pickling and a few mailpile specifics."""
    supported_platform = None

    @classmethod
    def parse_path(cls, config, fn, create=False):
        if (((cls.supported_platform is None) or
             (cls.supported_platform == sys.platform[:3].lower())) and
                ((os.path.isdir(fn) and
                  os.path.exists(os.path.join(fn, 'cur'))) or
                 (create and not os.path.exists(fn)))):
            return (fn, )
        raise ValueError('Not a Maildir: %s' % fn)

    def _refresh(self):
        with self._lock:
            mailbox.Maildir._refresh(self)
            # Dotfiles are not mail. Ignore them.
            for t in [k for k in self._toc.keys() if k.startswith('.')]:
                del self._toc[t]

    def __unicode__(self):
        return _("Maildir at %s") % self._path

    def _describe_msg_by_ptr(self, msg_ptr):
        return _("e-mail in file %s") % self._lookup(msg_ptr[MBX_ID_LEN:])

    def get_metadata_keywords(self, toc_id):
        subdir, name = os.path.split(self._lookup(toc_id))
        if self.colon in name:
            flags = name.split(self.colon)[-1]
            if flags[:2] == '2,':
                return ['%s:maildir' % c for c in flags[2:]]
        return []


mailpile.mailboxes.register(25, MailpileMailbox)
