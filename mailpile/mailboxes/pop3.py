try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

import poplib
import time
from mailbox import Mailbox, Message

import mailpile.mailboxes
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import UnorderedPicklable
from mailpile.util import *


class UnsupportedProtocolError(Exception):
    pass


class POP3Mailbox(Mailbox):
    """
    Basic implementation of POP3 Mailbox.
    """
    def __init__(self, host,
                 user=None, password=None, use_ssl=True, port=None,
                 debug=False, conn_cls=None):
        """Initialize a Mailbox instance."""
        Mailbox.__init__(self, '/')
        self.host = host
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        self.port = port
        self.debug = debug
        self.conn_cls = conn_cls

        self._lock = MboxRLock()
        self._pop3 = None
        self._connect()

    def _connect(self):
        with self._lock:
            if self._pop3:
                try:
                    self._pop3.noop()
                    return
                except poplib.error_proto:
                    self._pop3 = None

            with ConnBroker.context(need=[ConnBroker.OUTGOING_POP3]):
                if self.conn_cls:
                    self._pop3 = self.conn_cls(self.host, self.port or 110)
                    self.secure = self.use_ssl
                elif self.use_ssl:
                    self._pop3 = poplib.POP3_SSL(self.host, self.port or 995)
                    self.secure = True
                else:
                    self._pop3 = poplib.POP3(self.host, self.port or 110)
                    self.secure = False

            if self.debug:
                self._pop3.set_debuglevel(self.debug)

            self._keys = None
            try:
                self._pop3.user(self.user)
                self._pop3.pass_(self.password)
            except poplib.error_proto:
                raise AccessError()

    def _refresh(self):
        with self._lock:
            self._keys = None
            self.iterkeys()

    def __setitem__(self, key, message):
        """Replace the keyed message; raise KeyError if it doesn't exist."""
        raise NotImplementedError('Method must be implemented by subclass')

    def _get(self, key):
        with self._lock:
            if key not in self.iterkeys():
                raise KeyError('Invalid key: %s' % key)

            self._connect()
            ok, lines, octets = self._pop3.retr(self._km[key])
            if not ok.startswith('+OK'):
                raise KeyError('Invalid key: %s' % key)

        # poplib is stupid in that it loses the linefeeds, so we need to
        # do some guesswork to bring them back to what the server provided.
        # If we don't do this jiggering, then sizes don't match up, which
        # could cause allocation bugs down the line.

        have_octets = sum(len(l) for l in lines)
        if octets == have_octets + len(lines):
            lines.append('')
            return '\n'.join(lines)
        elif octets == have_octets + 2*len(lines):
            lines.append('')
            return '\r\n'.join(lines)
        elif octets == have_octets + len(lines) - 1:
            return '\n'.join(lines)
        elif octets == have_octets + 2*len(lines) - 2:
            return '\r\n'.join(lines)
        else:
            raise ValueError('Length mismatch in message %s' % key)

    def get_message(self, key):
        """Return a Message representation or raise a KeyError."""
        return Message(self._get(key))

    def get_bytes(self, key):
        """Return a byte string representation or raise a KeyError."""
        return self._get(key)

    def get_file(self, key):
        """Return a file-like representation or raise a KeyError."""
        return StringIO.StringIO(self._get(key))

    def get_msg_size(self, key):
        with self._lock:
            self._connect()
            if key not in self.iterkeys():
                raise KeyError('Invalid key: %s' % key)
            ok, info, octets = self._pop3.list(self._km[key]).split()
            return int(octets)

    def stat(self):
        with self._lock:
            self._connect()
            return self._pop3.stat()

    def iterkeys(self):
        """Return an iterator over keys."""
        # Note: POP3 *without UIDL* is useless.  We don't support it.
        with self._lock:
            if self._keys is None:
                self._connect()
                try:
                    stat, key_list, octets = self._pop3.uidl()
                except poplib.error_proto:
                    raise UnsupportedProtocolError()
                self._keys = [tuple(k.split(' ', 1)) for k in key_list]
                self._km = dict([reversed(k) for k in self._keys])
            return [k[1] for k in self._keys]

    def __contains__(self, key):
        """Return True if the keyed message exists, False otherwise."""
        return key in self.iterkeys()

    def __len__(self):
        """Return a count of messages in the mailbox."""
        return len(self.iterkeys())

    def flush(self):
        """Write any pending changes to the disk."""
        self.close()

    def close(self):
        """Flush and close the mailbox."""
        try:
            if self._pop3:
                self._pop3.quit()
        finally:
            self._pop3 = None
            self._keys = None


class MailpileMailbox(UnorderedPicklable(POP3Mailbox)):
    UNPICKLABLE = ['_pop3', '_debug']

    @classmethod
    def parse_path(cls, config, path, create=False):
        path = path.split('/')
        if path and path[0].lower() in ('pop:', 'pop3:',
                                        'pop3_ssl:', 'pop3s:'):
            proto = path[0][:-1].lower()
            userpart, server = path[2].rsplit("@", 1)
            user, password = userpart.rsplit(":", 1)
            if ":" in server:
                server, port = server.split(":", 1)
            else:
                port = 995 if ('s' in proto) else 110

            # This is a hack for GMail
            if 'recent' in path[3:]:
                user = 'recent:' + user

            if not config:
                debug = False
            elif 'pop3' in config.sys.debug:
                debug = 99
            elif 'rescan' in config.sys.debug:
                debug = 1
            else:
                debug = False

            # WARNING: Order must match POP3Mailbox.__init__(...)
            return (server, user, password, 's' in proto, int(port), debug)
        raise ValueError('Not a POP3 url: %s' % path)

    def save(self, *args, **kwargs):
        # Do not save state locally
        pass


##[ Test code follows ]#######################################################

if __name__ == "__main__":
    import doctest
    import sys

    class _MockPOP3(object):
        """
        Base mock that pretends to be a poplib POP3 connection.

        >>> pm = POP3Mailbox('localhost', user='bad', conn_cls=_MockPOP3)
        Traceback (most recent call last):
           ...
        AccessError

        >>> pm = POP3Mailbox('localhost', user='a', password='b',
        ...                  conn_cls=_MockPOP3)
        >>> pm.stat()
        (2, 123456)

        >>> pm.iterkeys()
        ['evil', 'good']

        >>> 'evil' in pm, 'bogon' in pm
        (True, False)

        >>> [msg['subject'] for msg in pm]
        ['Msg 1', 'Msg 2']

        >>> pm.get_msg_size('evil'), pm.get_msg_size('good')
        (47, 51)

        >>> pm.get_bytes('evil')
        'From: test@mailpile.is\\nSubject: Msg 1\\n\\nOh, hi!\\n'

        >>> pm['invalid-key']
        Traceback (most recent call last):
           ...
        KeyError: ...
        """
        TEST_MSG = ('From: test@mailpile.is\r\n'
                    'Subject: Msg N\r\n'
                    '\r\n'
                    'Oh, hi!\r\n')
        DEFAULT_RESULTS = {
            'user': lambda s, u: '+OK' if (u == 'a') else '-ERR',
            'pass_': lambda s, u: '+OK Logged in.' if (u == 'b') else '-ERR',
            'stat': (2, 123456),
            'noop': '+OK',
            'list_': lambda s: ('+OK 2 messages:',
                                ['1 %d' % len(s.TEST_MSG.replace('\r', '')),
                                 '2 %d' % len(s.TEST_MSG)], 0),
            'uidl': ('+OK', ['1 evil', '2 good'], 0),
            'retr': lambda s, m: ('+OK',
                                  s.TEST_MSG.replace('N', m).splitlines(),
                                  len(s.TEST_MSG)
                                  if m[0] == '2' else
                                  len(s.TEST_MSG.replace('\r', ''))),
        }
        RESULTS = {}

        def __init__(self, *args, **kwargs):
            def mkcmd(rval):
                def r(rv):
                    if isinstance(rv, (str, unicode)) and rv[0] != '+':
                        raise poplib.error_proto(rv)
                    return rv

                def cmd(*args, **kwargs):
                    if isinstance(rval, (str, unicode, list, tuple, dict)):
                        return r(rval)
                    else:
                        return r(rval(self, *args, **kwargs))

                return cmd
            for cmd, rval in dict_merge(self.DEFAULT_RESULTS, self.RESULTS
                                        ).iteritems():
                self.__setattr__(cmd, mkcmd(rval))

        def list(self, which=None):
            msgs = self.list_()
            if which:
                return '+OK ' + msgs[1][1-int(which)]
            return msgs

        def __getattr__(self, attr):
            return self.__getattribute__(attr)

    class _MockPOP3_Without_UIDL(_MockPOP3):
        """
        Mock that lacks the UIDL command.

        >>> pm = POP3Mailbox('localhost', user='a', password='b',
        ...                  conn_cls=_MockPOP3_Without_UIDL)
        >>> pm.iterkeys()
        Traceback (most recent call last):
           ...
        UnsupportedProtocolError
        """
        RESULTS = {'uidl': '-ERR'}

    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)

    if len(sys.argv) > 1:
        mbx = MailpileMailbox(*MailpileMailbox.parse_path(None, sys.argv[1]))
        print 'Status is: %s' % (mbx.stat(), )
        print 'Downloading mail and listing subjects, hit CTRL-C to quit'
        for msg in mbx:
            print msg['subject']
            time.sleep(2)

else:
    mailpile.mailboxes.register(10, MailpileMailbox)
