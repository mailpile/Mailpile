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

        self._pop3.user(user)
        self._pop3.pass_(password)
        self._keys = None

    def __setitem__(self, key, message):
        """Replace the keyed message; raise KeyError if it doesn't exist."""
        raise NotImplementedError('Method must be implemented by subclass')

    def _get(self, key):
        if key not in self._keys:
            raise KeyError('Invalid key: %s' % key)
        ok, lines, _bytes = self._pop3.retr(key.split(':')[0])
        if not ok.startswith('+OK'):
            raise KeyError('Invalid key: %s' % key)
        return '\r\n'.join(lines)

    def get_message(self, key):
        """Return a Message representation or raise a KeyError."""
        return Message(self._get(key))

    def get_bytes(self, key):
        """Return a byte string representation or raise a KeyError."""
        return self._get(key)

    def get_file(self, key):
        """Return a file-like representation or raise a KeyError."""
        return StringIO.StringIO(self._get(key))

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
                     ctx = md5_hex(str(key_list[max(0, i-2):i+2]))[:6]
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


class MailpileMailbox(UnorderedPicklable(POP3Mailbox)):
    @classmethod
    def parse_path(cls, config, path, create=False):
        if path.startswith("imap://"):
            url = path[7:]
            try:
                serverpart, mailbox = url.split("/")
            except ValueError:
                serverpart = url
                mailbox = None
            userpart, server = serverpart.split("@")
            user, password = userpart.split(":")
            # WARNING: Order must match POP3Mailbox.__init__(...)
            return (server, 110, user, password)
        raise ValueError('Not an IMAP url: %s' % path)

    def __getstate__(self):
        odict = self.__dict__.copy()
        # Pickle can't handle file and function objects.
        del odict['_pop3']
        del odict['_save_to']
        return odict

    def get_msg_size(self, toc_id):
        # FIXME: We should make this less horrible.
        fd = self.get_file(toc_id)
        fd.seek(0, 2)
        return fd.tell()


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
        """
        DEFAULT_RESULTS = {
            'user':  lambda u: '+OK' if (u == 'a') else '-ERR',
            'pass_': lambda u: '+OK Logged in.' if (u == 'b') else '-ERR',
            'noop':  '+OK',
            'list':  ('+OK 2 messages:', ['1 55', '2 44'], 456),
            'uidl':  ('+OK', ['1 evil', '2 good'], 123),
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
                        return r(rval(*args, **kwargs))
                return cmd
            for cmd, rval in dict_merge(self.DEFAULT_RESULTS, self.RESULTS
                                        ).iteritems():
                self.__setattr__(cmd, mkcmd(rval))
    
        def __getattr__(self, attr):
            return self.__getattribute__(attr)

    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)

    if len(sys.argv) > 1:
        args = sys.argv[1:]
        proto, host, port = args.pop(0).split(':')
        if args:
            username, password = args[:2]
        else:
            username = password = None
        mbx = POP3Mailbox(host,
                          port=port, use_ssl=(proto in ('pops', 'tls', 'ssl')),
                          user=username, password=password)
        print 'Downloading mail and listing subjects, hit CTRL-C to quit'
        for key in mbx.iterkeys():
            print mbx.get_message(key)['subject']
            time.sleep(2)
else:
    mailpile.mailboxes.register(10, MailpileMailbox)
