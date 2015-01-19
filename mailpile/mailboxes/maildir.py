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


mailpile.mailboxes.register(25, MailpileMailbox)
