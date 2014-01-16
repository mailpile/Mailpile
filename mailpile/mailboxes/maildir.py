import mailbox
import os

import mailpile.mailboxes
from mailpile.mailboxes import UnorderedPicklable


class MailpileMailbox(UnorderedPicklable(mailbox.Maildir, editable=True)):
    """A Maildir class that supports pickling and a few mailpile specifics."""
    supported_platform = None

    @classmethod
    def parse_path(cls, fn):
        if (((cls.supported_platform is None) or
             (cls.supported_platform in system().lower())) and
                os.path.isdir(fn) and
                os.path.exists(os.path.join(fn, 'cur'))):
            return (fn, )
        raise ValueError('Not a Maildir: %s' % fn)


mailpile.mailboxes.register(25, MailpileMailbox)
