import mailpile.mailboxes
import mailpile.mailboxes.maildir as maildir

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n


class MailpileMailbox(maildir.MailpileMailbox):
    """A Maildir class for Windows (using ! instead of : in filenames)"""
    supported_platform = 'win'
    colon = '!'


mailpile.mailboxes.register(20, MailpileMailbox)
