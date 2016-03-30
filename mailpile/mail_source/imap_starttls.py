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
        self.sock = ssl.wrap_socket(self.sock,
            keyfile,
            certfile,
            ssl_version=ssl.PROTOCOL_TLSv1)
        self.file = self.sock.makefile('rb')
        self.__capability__()
        return typ, data

    def __capability__(self):
        typ, dat = super(IMAP4, self).capability()
        if dat == [None]:
            raise self.error('no CAPABILITY response from server')
        self.capabilities = tuple(dat[-1].upper().split())
