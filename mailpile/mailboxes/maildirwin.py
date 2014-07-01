import mailpile.mailboxes
import mailpile.mailboxes.maildir as maildir
from gettext import gettext as _


class MailpileMailbox(maildir.MailpileMailbox):
    """A Maildir class for Windows (using ! instead of : in filenames)"""
    supported_platform = 'win'
    colon = '!'


mailpile.mailboxes.register(20, MailpileMailbox)
