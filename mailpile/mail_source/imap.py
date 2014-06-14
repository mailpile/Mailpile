import os
import re
import socket
import traceback
from gettext import gettext as _
from imaplib import IMAP4, IMAP4_SSL
from mailbox import Mailbox, Message

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from mailpile.eventlog import Event
from mailpile.util import *
from mailpile.mail_source import BaseMailSource


IMAP_TOKEN = re.compile('("[^"]*"'
                        '|[\\(\\)]'
                        '|[^\\(\\)"\\s]+'
                        '|\\s+)')

DEBUG_IMAP = False


class IMAP_IOError(IOError):
    pass


def _parse_imap(reply):
    """
    This routine will parse common IMAP4 responses into Pythonic data
    structures.

    >>> _parse_imap(('OK', ['One (Two (Th ree)) "Four Five"']))
    (True, ['One', ['Two', ['Th', 'ree']], 'Four Five'])

    >>> _parse_imap(('BAD', ['Sorry']))
    (False, ['Sorry'])
    """
    stack = []
    pdata = []
    for dline in reply[1]:
        while True:
            m = IMAP_TOKEN.match(dline)
            if m:
                token = m.group(0)
                dline = dline[len(token):]
                if token[:1] == '"':
                    pdata.append(token[1:-1])
                elif token[:1] == '(':
                    stack.append(pdata)
                    pdata.append([])
                    pdata = pdata[-1]
                elif token[:1] == ')':
                    pdata = stack.pop(-1)
                elif token[:1] not in (' ', '\t', '\n', '\r'):
                    pdata.append(token)
            else:
                break
    return (reply[0].upper() == 'OK'), pdata


class SharedImapConn(threading.Thread):
    """
    This is a wrapper around an imaplib.IMAP4 connection which facilitates
    sharing of the same conn between different parts of the app.

    If nobody is using the connection and an IDLE callback is specified,
    it will switch to IMAP IDLE mode when not otherwise in use.

    Callers are expected to use the "with sharedconn as conn: ..." syntax.
    """
    def __init__(self, conn, idle_mailbox=None, idle_callback=None):
        threading.Thread.__init__(self)
        self.daemon = True
        self._lock = threading.Lock()
        self._conn = conn
        self._idle_mailbox = idle_mailbox
        self._idle_callback = idle_callback
        self._idling = False
        self._selected = None

        for meth in ('append', 'add', 'capability', 'fetch', 'noop',
                     'list', 'login', 'search'):
            self.__setattr__(meth, self._mk_proxy(meth))

        self.start()

    def _mk_proxy(self, method):
        def proxy_method(*args, **kwargs):
            assert(self._lock.locked())
            try:
                if 'mailbox' in kwargs:
                    # We're sharing this connection, so all mailbox methods
                    # need to tell us which mailbox they're operating on.
                    typ, data = self.select(kwargs['mailbox'])
                    if typ.upper() != 'OK':
                        return (typ, data)
                    del kwargs['mailbox']
                if DEBUG_IMAP:
                    print '%s(%s %s)' % (method, args, kwargs)
                return getattr(self._conn, method)(*args, **kwargs)
            except IMAP4.error:
                # We convert IMAP4.error to a subclass of IOError, so
                # things get caught by the already existing error handling
                # code in Mailpile.  We do not catch the assertions, as
                # those are logic errors that should not be suppressed.
                raise IMAP_IOError('Failed %s(%s %s)' % (method, args, kwargs))
            except:
                traceback.print_exc()
                raise
        return proxy_method

    def close(self):
        assert(self._lock.locked())
        self._selected = None
        return self._conn.close()

    def select(self, mailbox='INBOX', readonly=False):
        # This routine caches the SELECT operations, because we will be
        # making lots and lots of superfluous ones "just in case" as part
        # of multiplexing one IMAP connection for multiple mailboxes.
        assert(self._lock.locked())
        if self._selected and self._selected[0] == (mailbox, readonly):
            return self._selected[1]
        rv = self._conn.select(mailbox=mailbox, readonly=readonly)
        if rv[0].upper() == 'OK':
            self._selected = ((mailbox, readonly), rv)
        if DEBUG_IMAP:
            print 'select(%s, %s) = %s' % (mailbox, readonly, rv)
        return rv

    def __str__(self):
        return '%s: %s' % (threading.Thread.__str__(self),
                           self._conn and self._conn.host or '(dead)')

    def __enter__(self):
        if not self._conn:
            raise IOError('I am dead')
        self._stop_idling()
        self._lock.acquire()
        return self

    def __exit__(self, type, value, traceback):
        self._lock.release()
        self._start_idling()

    def _start_idling(self):
        pass  # FIXME

    def _stop_idling(self):
        pass  # FIXME

    def quit(self):
        self._conn = None

    def run(self):
        # FIXME: Do IDLE stuff if requested.
        try:
            while True:
                # By default, all this does is send a NOOP every 120 seconds
                # to keep the connection alive (or detect errors).
                time.sleep(120)
                with self as raw_conn:
                    raw_conn.noop()
        except:
            if DEBUG_IMAP:
                traceback.print_exc()
        finally:
            self._conn = None


class SharedImapMailbox(Mailbox):
    """
    This implements a Mailbox view of an IMAP folder. The IMAP connection
    itself is obtained as a SharedImapConn from a particular mail source.

    >>> imap = ImapMailSource(session, imap_config)
    >>> mailbox = SharedImapMailbox(config, imap, conn_cls=_MockImap)
    >>> mailbox.add('From: Bjarni\\r\\nBarely a message')
    """

    def __init__(self, config, mail_source,
                 mailbox_path='INBOX', conn_cls=None):
        self.config = config
        self.source = mail_source
        self.path = mailbox_path
        self.conn_cls = conn_cls

    def open_imap(self):
        return self.source.open(throw=IMAP_IOError, conn_cls=self.conn_cls)

    def timed_imap(self, *args, **kwargs):
        return self.source.timed_imap(*args, **kwargs)

    def save(self, *args, **kwargs):
        # SharedImapMailboxes are never pickled to disk.
        pass

    def add(self, message):
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.append, self.path, message=message)
            assert(ok)

    def remove(self, key):
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.store, '+FLAGS', r'\Deleted',
                                       mailbox=self.path)
            assert(ok)

    def _get(self, key):
        with self.open_imap() as imap:
            # Note: uses the raw method, not the convenient parsed version.
            # FIXME: This is downloading mail! Handle timeoutes better!
            typ, data = self.source.timed(imap.fetch, key, '(RFC822)',
                                          mailbox=self.path)
            if typ != 'OK' or not data[0]:
                raise KeyError
            return data[0][1]

    def get_message(self, key):
        return Message(self._get(key))

    def get_bytes(self, key):
        return StringIO.StringIO(self._get(key))

    def iterkeys(self):
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.search, None, 'ALL',
                                       mailbox=self.path)
            assert(ok)
            return data


class ImapMailSource(BaseMailSource):
    """
    This is a mail source that connects to an IMAP server.

    A single connection is made to the IMAP server, which is then shared
    between the ImapMailSource job and individual mailbox instances.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.imap.ImapMailSource'

    DEFAULT_TIMEOUT = 15
    CONN_ERRORS = (IOError, IMAP_IOError, IMAP4.error, TimedOut)

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.timeout = self.DEFAULT_TIMEOUT
        self.watching = -1
        self.capabilities = set()
        self.conn = None

    @classmethod
    def Tester(cls, conn_cls, *args, **kwargs):
        tcls = cls(*args, **kwargs)
        return tcls.open(conn_cls=conn_cls) and tcls or False

    def timed(self, *args, **kwargs):
        return RunTimed(self.timeout, *args, **kwargs)

    def timed_imap(self, *args, **kwargs):
        return _parse_imap(RunTimed(self.timeout, *args, **kwargs))

    def _sleep(self, seconds):
        # FIXME: While we are sleeping, we should switch to IDLE mode
        #        if it is available.
        if 'IDLE' in self.capabilities:
            pass
        return BaseMailSource._sleep(self, seconds)

    def _unlocked_open(self, conn_cls=None, throw=False):
        #
        # When opening an IMAP connection, we need to do a few things:
        #  1. Connect, log in
        #  2. Check the capabilities of the remote server
        #  3. If there is IDLE support, subscribe to all the paths we
        #     are currently watching.

        my_config = self.my_config
        mailboxes = my_config.mailbox.values()
        if self.conn:
            try:
                with self.conn as conn:
                    if self.timed(conn.noop)[0] == 'OK':
                        return self.conn
            except self.CONN_ERRORS:
                self.conn.quit()
        conn = self.conn = None

        # If we are given a conn class, use that - this allows mocks for
        # testing.
        if not conn_cls:
            want_ssl = (my_config.protocol == 'imap_ssl')
            conn_cls = IMAP4_SSL if want_ssl else IMAP4

        # This also facilitates testing, should already exist in real life.
        if self.event:
            event = self.event
        else:
            event = Event(source=self, flags=Event.RUNNING, data={})

        if 'conn_error' in event.data:
            del event.data['conn_error']
        try:
            def mkconn():
                return conn_cls(my_config.host, my_config.port)
            conn = self.timed(mkconn)

            ok, data = self.timed_imap(conn.login,
                                       my_config.username,
                                       my_config.password)
            if not ok:
                event.data['conn_error'] = _('Bad username or password')
                if throw:
                    raise throw(event.data['conn_error'])
                return False

            ok, data = self.timed_imap(conn.capability)
            if ok:
                self.capabilities = set(' '.join(data).upper().split())
            else:
                self.capabilities = set()

            if 'IDLE' in self.capabilities:
                self.conn = SharedImapConn(conn,
                                           idle_mailbox='INBOX',
                                           idle_callback=self._idle_callback)
            else:
                self.conn = SharedImapConn(conn)

            # Prepare the data section of our event, for keeping state.
            for d in ('uidvalidity', 'uidnext'):
                if d not in event.data:
                    event.data[d] = {}

            if self.event:
                self._log_status(_('Connected to IMAP server %s'
                                   ) % my_config.host)
            if DEBUG_IMAP:
                print 'CONNECTED %s' % self.conn
            return self.conn

        except TimedOut:
            event.data['conn_error'] = _('Connection timed out')
        except (IMAP_IOError, IMAP4.error):
            if DEBUG_IMAP:
                traceback.print_exc()
            event.data['conn_error'] = _('An IMAP protocol error occurred')
        except (IOError, AttributeError, socket.error):
            if DEBUG_IMAP:
                traceback.print_exc()
            event.data['conn_error'] = _('A network error occurred')

        try:
            if conn:
                # Close the socket directly, in the hopes this will boot
                # any timed-out operations out of a hung state.
                conn.socket().shutdown(socket.SHUT_RDWR)
                conn.file.close()
        except (AttributeError, IOError, socket.error):
            pass
        if throw:
            raise throw(event.data['conn_error'])
        return False

    def _idle_callback(self, data):
        pass

    def open_mailbox(self, mbx_id, mfn):
        print 'TRYING TO OPEN: %s / %s' % (mbx_id, mfn)
        return False

    def _has_mailbox_changed(self, mbx, state):
        return True
        # FIXME: This is wrong
        mt = state['mt'] = long(os.path.getmtime(self._path(mbx)))
        sz = state['sz'] = long(os.path.getsize(self._path(mbx)))
        return (mt != self.event.data['mtimes'].get(mbx._key) or
                sz != self.event.data['sizes'].get(mbx._key))

    def _mark_mailbox_rescanned(self, mbx, state):
        return True
        # FIXME: This is wrong
        self.event.data['mtimes'][mbx._key] = state['mt']
        self.event.data['sizes'][mbx._key] = state['sz']

    def _fmt_path(self, path):
        return 'src:%s/%s' % (self.my_config._key, path)

    def _unlocked_discover_mailboxes(self, unused_paths):
        config = self.session.config
        existing = self._existing_mailboxes()
        discovered = []
        with self.conn as raw_conn:
            try:
                ok, data = self.timed_imap(raw_conn.list)
                while ok and len(data) >= 3:
                    (flags, sep, path), data[:3] = data[:3], []
                    path = self._fmt_path(path)
                    if path not in existing:
                        discovered.append((path, flags))
            except self.CONN_ERRORS:
                pass

        for path, flags in discovered:
            idx = config.sys.mailbox.append(path)
            mbx = self._unlocked_take_over_mailbox(idx)
            if mbx.policy == 'unknown':
                self.event.data['have_unknown'] = True

    def quit(self, *args, **kwargs):
        if self.conn:
            self.conn.quit()
        return BaseMailSource.quit(self, *args, **kwargs)


##[ Test code follows ]#######################################################

class _MockImap(object):
    """
    Base mock that pretends to be an imaplib IMAP connection.

    >>> imap = ImapMailSource(session, imap_config)
    >>> imap.open(conn_cls=_MockImap)
    <SharedImapConn(...)>

    >>> sorted(imap.capabilities)
    ['IMAP4REV1', 'X-MAGIC-BEANS']
    """
    DEFAULT_RESULTS = {
        'append': ('OK', []),
        'capability': ('OK', ['X-MAGIC-BEANS', 'IMAP4rev1']),
        'list': ('OK', []),
        'login': ('OK', ['"Welcome, human"']),
        'noop': ('OK', [])
    }
    RESULTS = {}

    def __init__(self, *args, **kwargs):
        def mkcmd(rval):
            def cmd(*args, **kwargs):
                return rval
            return cmd
        for cmd, rval in dict_merge(self.DEFAULT_RESULTS, self.RESULTS
                                    ).iteritems():
            self.__setattr__(cmd, mkcmd(rval))

    def __getattr__(self, attr):
        return self.__getattribute__(attr)


class _Mocks(object):
    """
    A bunch of IMAP test classes for testing various configurations.

    >>> ImapMailSource.Tester(_Mocks.NoDns, session, imap_config)
    False

    >>> ImapMailSource.Tester(_Mocks.BadLogin, session, imap_config)
    False
    """
    class NoDns(_MockImap):
        def __init__(self, *args, **kwargs):
            raise socket.gaierror('Oops')

    class BadLogin(_MockImap):
        RESULTS = {'login': ('BAD', ['"Sorry dude"'])}


if __name__ == "__main__":
    import doctest
    import sys
    import mailpile.config
    import mailpile.defaults
    import mailpile.ui

    rules = mailpile.defaults.CONFIG_RULES
    config = mailpile.config.ConfigManager(rules=rules)
    config.sources.imap = {
        'protocol': 'imap_ssl',
        'host': 'imap.gmail.com',
        'port': 993,
        'username': 'nobody',
        'password': 'nowhere'
    }
    session = mailpile.ui.Session(config)
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={'session': session,
                                          'imap_config': config.sources.imap})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)

    args = sys.argv[1:]
    if args:
        DEBUG_IMAP = False

        username, password = args.pop(0), args.pop(0)
        config.sources.imap.username = username
        config.sources.imap.password = password
        imap = ImapMailSource(session, config.sources.imap)
        with imap.open() as conn:
            print '%s' % (conn.list(), )
        mbx = SharedImapMailbox(config, imap, mailbox_path='[Gmail]/All Mail')
        print '%s' % list(mbx.iterkeys())
        for key in args:
            print '%s' % mbx.get_bytes(key).read()

