import os
import re
import socket
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
        self.start()

    def __str__(self):
        return '%s: %s' % (threading.Thread.__str__(self),
                           self._conn and self._conn.host or '(dead)')

    def __enter__(self):
        if not self._conn:
            raise IOError('I am dead')
        self._lock.acquire()
        self._stop_idling()
        return self._conn

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
                with self as raw_conn:
                    raw_conn.noop()
                time.sleep(120)
        except:
            pass
        finally:
            self._conn = None


class ImapMailSource(BaseMailSource):
    """
    This is a mail source that connects to an IMAP server.

    A single connection is made to the IMAP server, which is then shared
    between the ImapMailSource job and individual mailbox instances.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.imap.ImapMailSource'

    DEFAULT_TIMEOUT = 15
    CONN_ERRORS = (IOError, AttributeError, IMAP4.error, TimedOut)

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

    def _timed(self, *args, **kwargs):
        return RunTimed(self.timeout, *args, **kwargs)

    def _sleep(self, seconds):
        # FIXME: While we are sleeping, we should switch to IDLE mode
        #        if it is available.
        if 'IDLE' in self.capabilities:
            pass
        return BaseMailSource._sleep(self, seconds)

    def _unlocked_open(self, conn_cls=None):
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
                    if self._timed(conn.noop)[0] == 'OK':
                        return True
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
            conn = self._timed(mkconn)

            ok, data = _parse_imap(self._timed(conn.login,
                                               my_config.username,
                                               my_config.password))
            if not ok:
                event.data['conn_error'] = _('Bad username or password')
                return False

            ok, data = _parse_imap(self._timed(conn.capability))
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

            return True

        except TimedOut:
            event.data['conn_error'] = _('Connection timed out')
        except (socket.error, AttributeError):
            event.data['conn_error'] = _('A network error occurred')
        except IMAP4.error:
            event.data['conn_error'] = _('An IMAP error occurred')
        try:
            if conn:
                # Close the socket directly, in the hopes this will boot
                # any timed-out operations out of a hung state.
                conn.socket().shutdown()
                conn.file.close()
        except (AttributeError, IOError, socket.error):
            pass
        return False

        # FIXME: Set up other things, per examples below...

        # Prepare the data section of our event, for keeping state.
        for d in ('mtimes', 'sizes'):
            if d not in self.event.data:
                event.data[d] = {}

        self._log_status(_('Watching %d IMAP mailboxes') % self.watching)
        return True

    def _idle_callback(self, data):
        pass

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

    def _discover_mailboxes(self, unused_paths):
        print 'Capabilities: %s' % self.capabilities
        with self.conn as raw_conn:
            try:
                ok, data = _parse_imap(self._timed(raw_conn.list))
                while ok and len(data) >= 3:
                    flags, sep, path = data[:3]
                    data[:3] = []
                    print 'Discovered: %s %s' % (self._fmt_path(path), flags)
            except self.CONN_ERRORS:
                pass

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
    True

    >>> sorted(imap.capabilities)
    ['IMAP4REV1', 'X-MAGIC-BEANS']
    """
    DEFAULT_RESULTS = {
        'login': ('OK', ['"Welcome, human"']),
        'capability': ('OK', ['X-MAGIC-BEANS', 'IMAP4rev1']),
        'list': ('OK', [])
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
