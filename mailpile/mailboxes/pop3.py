try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

import poplib
import time
from mailbox import Mailbox, Message

import mailpile.mailboxes
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import UnorderedPicklable
from mailpile.util import *


class POP3Mailbox(Mailbox):
    """
    Basic implementation of POP3 Mailbox.
    """
    def __init__(self, host,
                 user=None, password=None, use_ssl=True, port=None,
                 conn_cls=None):
        """Initialize a Mailbox instance."""
        if conn_cls:
            self._pop3 = conn_cls(host, port or 110)
            self.secure = use_ssl
        elif use_ssl:
            self._pop3 = poplib.POP3_SSL(host, port or 995)
            self.secure = True
        else:
            self._pop3 = poplib.POP3(host, port or 110)
            self.secure = False

        Mailbox.__init__(self, '/')
        self._pop3.user(user)
        self._pop3.pass_(password)
        self._refresh()

    def _refresh(self):
        self._keys = None
        self.iterkeys()

    def __setitem__(self, key, message):
        """Replace the keyed message; raise KeyError if it doesn't exist."""
        raise NotImplementedError('Method must be implemented by subclass')

    def _get(self, key):
        if key not in self.iterkeys():
            raise KeyError('Invalid key: %s' % key)

        ok, lines, octets = self._pop3.retr(key.split(':')[0])
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
        if key not in self.iterkeys():
            raise KeyError('Invalid key: %s' % key)
        ok, info, octets = self._pop3.list(key.split(':', 1)[0]).split()
        return int(octets)

    def iterkeys(self):
        """Return an iterator over keys."""
        # Note: POP3 *without UIDL* provides very few guarantees, but given
        #       the assumption that an old-school POP3 mailbox is a sequential
        # mbox where messages don't change much, we can make each ID depend on
        # itself (offset and size), along with the sizes of the messages before
        # and after it in the list. This will be stable for immutable append-
        # only mailboxes, while detecting many (but not all) changes, except
        # for really sneaky ones where a message is replaced by another of
        # exactly the same size, without anything else changing around it.
        # False positives of IDs becoming invalid will be more common, but
        # are not a serious problem. We may need stronger tests to be sure
        # that an old ID doesn't return the wrong message.
        if self._keys is None:
            keys = []
            try:
                stat, key_list, octets = self._pop3.uidl()
                keys = [k.replace(' ', ':') for k in key_list]
            except poplib.error_proto:
                stat, key_list, octets = self._pop3.list()
                for i in range(0, len(key_list)):
                    ctx = md5_hex(str([key_list[i]] +
                                      key_list[max(0, i-2):i+2]))[:6]
                    keys.append('%s:%s' % (key_list[i].split()[0], ctx))
            self._keys = keys
        return self._keys

    def __contains__(self, key):
        """Return True if the keyed message exists, False otherwise."""
        typ, data = self._pop3.fetch(key, '(RFC822)')
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

    def close(self):
        """Flush and close the mailbox."""
        self._pop3.quit()
        self._pop3 = None
        self._keys = None


class MailpileMailbox(UnorderedPicklable(POP3Mailbox)):
    UNPICKLABLE = ['_pop3']

    @classmethod
    def parse_path(cls, config, path, create=False):
        if path[:5].lower() in ('pop:/', 'pop3:', 'pops:'):
            path = path.split('/')
            proto = path[0][:-1].lower()
            userpart, server = path[2].rsplit("@", 1)
            user, password = userpart.split(":", 1)
            if ":" in server:
                server, port = server.split(":", 1)
            else:
                port = 110
            # WARNING: Order must match POP3Mailbox.__init__(...)
            return (server, user, password, 's' in proto, int(port))
        raise ValueError('Not an IMAP url: %s' % path)


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
        error_proto: -ERR

        >>> pm = POP3Mailbox('localhost', user='a', password='b',
        ...                  conn_cls=_MockPOP3)
        >>> pm.iterkeys()
        ['1:evil', '2:good']

        >>> [msg['subject'] for msg in pm]
        ['Msg 1', 'Msg 2']

        >>> pm.get_msg_size('1:evil'), pm.get_msg_size('2:good')
        (47, 51)

        >>> pm.get_bytes('1:evil')
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
        ['1:2d7fb9', '2:bfdd60']

        >>> [msg['subject'] for msg in pm]
        ['Msg 1', 'Msg 2']
        """
        RESULTS = {'uidl': '-ERR'}

    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)

    if len(sys.argv) > 1:
        mbx = MailpileMailbox(*MailpileMailbox.parse_path({}, sys.argv[1]))
        print '--[ Message 1 ]------------------------------------------'
        print mbx._pop3.list(1)
        print '%s bytes' % mbx.get_msg_size(mbx.iterkeys()[0])
        print mbx._pop3.retr(1)
        print '---------------------------------------------------------'
        print 'Downloading mail and listing subjects, hit CTRL-C to quit'
        for msg in mbx:
            print msg['subject']
            time.sleep(2)
else:
    mailpile.mailboxes.register(10, MailpileMailbox)
