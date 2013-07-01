import logging
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from imaplib import IMAP4, IMAP4_SSL
from mailbox import Mailbox, Message

logger = logging.getLogger(__name__)

class IMAPMailbox(Mailbox):
    """
    Basic implementation of IMAP Mailbox. Needs a lot of work.

    As of now only get_* is implemented.
    """
    def __init__(self, host, port=993, user=None, password=None, mailbox=None, use_ssl=True, factory=None):
        """Initialize a Mailbox instance."""
        logger.debug("Opening IMAP mailbox %s:%d. SSL:%s" % (host, port, use_ssl))
        if use_ssl:
            self._mailbox = IMAP4_SSL(host, port)
        else:
            self._mailbox = IMAP4(host, port)
        self._mailbox.login(user, password)
        if not mailbox:
            mailbox = "INBOX"
        self.mailbox = mailbox
        self._mailbox.select(mailbox)
        self._factory = factory

    def add(self, message):
        """Add message and return assigned key."""
        # TODO(halldor): not tested...
        self._mailbox.append(self.mailbox, message=message)

    def remove(self, key):
        """Remove the keyed message; raise KeyError if it doesn't exist."""
        # TODO(halldor): not tested...
        self._mailbox.store(key, "+FLAGS", r"\Deleted")

    def __setitem__(self, key, message):
        """Replace the keyed message; raise KeyError if it doesn't exist."""
        raise NotImplementedError('Method must be implemented by subclass')

    def _get(self, key):
        logger.debug("Fetching %s" % key)
        typ, data = self._mailbox.fetch(key, '(RFC822)')
        response = data[0]
        if typ != "OK" or response is None:
            raise KeyError
        return response[1]

    def get_message(self, key):
        """Return a Message representation or raise a KeyError."""
        return Message(self._get(key))

    def get_bytes(self, key):
        """Return a byte string representation or raise a KeyError."""
        raise NotImplementedError('Method must be implemented by subclass')

    def get_file(self, key):
        """Return a file-like representation or raise a KeyError."""
        message = self._get(key)
        fd = StringIO.StringIO()
        fd.write(message)
        fd.seek(0)
        return fd

    def iterkeys(self):
        """Return an iterator over keys."""
        typ, data = self._mailbox.search(None, "ALL")
        return data[0].split()

    def __contains__(self, key):
        """Return True if the keyed message exists, False otherwise."""
        typ, data = self._mailbox.fetch(key, '(RFC822)')
        response = data[0]
        if response is None:
            return False
        return True

    def __len__(self):
        """Return a count of messages in the mailbox."""
        return len(self.iterkeys())

    def flush(self):
        """Write any pending changes to the disk."""
        raise NotImplementedError('Method must be implemented by subclass')

    def lock(self):
        """Lock the mailbox."""
        raise NotImplementedError('Method must be implemented by subclass')

    def unlock(self):
        """Unlock the mailbox if it is locked."""
        raise NotImplementedError('Method must be implemented by subclass')

    def close(self):
        """Flush and close the mailbox."""
        self._mailbox.close()
        self._mailbox.logout()

    # Whether each message must end in a newline
    _append_newline = False
