# vim: set fileencoding=utf-8 :
#
MBX_ID_LEN = 4  # 4x36 == 1.6 million mailboxes


def FormatMbxId(n):
    if not isinstance(n, (str, unicode)):
        n = b36(n)
    if len(n) > MBX_ID_LEN:
        raise ValueError(_('%s is too large to be a mailbox ID') % n)
    return ('0000' + n).lower()[-MBX_ID_LEN:]


class NotEditableError(ValueError):
    pass


class NoFromAddressError(ValueError):
    pass


class NoRecipientError(ValueError):
    pass


class InsecureSmtpError(IOError):
    def __init__(self, msg, details=None):
        IOError.__init__(self, msg)
        self.error_info = details or {}


class NoSuchMailboxError(OSError):
    pass
