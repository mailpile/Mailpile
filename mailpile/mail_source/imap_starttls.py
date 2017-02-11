import imaplib
import ssl

Commands = {
    'STARTTLS': ('NONAUTH')
}

imaplib.Commands.update(Commands)

class IMAP4(imaplib.IMAP4, object):

    # This is a bugfix for imaplib's default readline method. It is
    # identical except it raises abort() instead of error() as the
    # internal state will certainly be broken.
    #
    # Note: This would be the function to change if we want to do away
    #       with the line-length limits altogether.
    #
    def readline(self):
        """Read line from remote."""
        line = self.file.readline(imaplib._MAXLINE + 1)
        if len(line) > imaplib._MAXLINE:
            raise self.abort("got more than %d bytes" % imaplib._MAXLINE)
        return line

    def starttls(self, keyfile = None, certfile = None):
        typ, data = self._simple_command('STARTTLS')
        if typ != 'OK':
            raise self.error('no STARTTLS')
        self.sock = ssl.wrap_socket(self.sock, keyfile, certfile)
        self.file = self.sock.makefile('rb')
        return typ, data
