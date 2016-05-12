import imaplib
import ssl

Commands = {
    'STARTTLS': ('NONAUTH')
}

imaplib.Commands.update(Commands)

class IMAP4(imaplib.IMAP4, object):

    def starttls(self, keyfile = None, certfile = None):
        typ, data = self._simple_command('STARTTLS')
        if typ != 'OK':
            raise self.error('no STARTTLS')
        self.sock = ssl.wrap_socket(self.sock, keyfile, certfile)
        self.file = self.sock.makefile('rb')
        return typ, data
