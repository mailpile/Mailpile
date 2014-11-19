# This implements our IMAP mail source. It has been tested against the
# following IMAP implementations:
#
#   * Google's GMail (july 2014)
#   * UW IMAPD (10.1.legacy from 2001)
#
#
# IMAP resonses seen in the wild:
#
# GMail:
#
#    Message flags: \* \Answered \Flagged \Draft \Deleted \Seen
#                   $Phishing receipt-handled $NotPhishing Junk
#
#    LIST (\HasNoChildren) "/" "Travel"
#    LIST (\Noselect \HasChildren) "/" "[Gmail]"
#
# UW IMAPD 10.1:
#
#    Message flags: \* \Answered \Flagged \Deleted \Draft \Seen
#
#    LIST (\NoSelect) "/" 17.03.2002
#    LIST (\NoInferiors \Marked) "/" in
#    LIST (\NoInferiors \UnMarked) "/" todays-junk
#
# Fastmail.fm:
#
#    Message flags: \Answered \Flagged \Draft \Deleted \Seen $X-ME-Annot-2
#                   $IsMailingList $IsNotification $HasAttachment $HasTD
#
#    LIST (\Noinferiors \HasNoChildren) "." INBOX
#    LIST (\HasNoChildren \Archive) "." Archive
#    LIST (\HasNoChildren \Drafts) "." Drafts
#    LIST (\HasNoChildren \Junk) "." "Junk Mail"
#    LIST (\HasNoChildren \Sent) "." "Sent Items"
#    LIST (\HasNoChildren \Trash) "." Trash
#
# Mykolab.com:
#
#
#
import os
import re
import socket
import traceback
from imaplib import IMAP4, IMAP4_SSL
from mailbox import Mailbox, Message
from urllib import quote, unquote

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from mailpile.conn_brokers import Master as ConnBroker
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mail_source import BaseMailSource
from mailpile.mailutils import FormatMbxId, MBX_ID_LEN
from mailpile.util import *


IMAP_TOKEN = re.compile('("[^"]*"'
                        '|[\\(\\)]'
                        '|[^\\(\\)"\\s]+'
                        '|\\s+)')


class IMAP_IOError(IOError):
    pass


class WithaBool(object):
    def __init__(self, v): self.v = v
    def __nonzero__(self): return self.v
    def __enter__(self, *a, **kw): return self.v
    def __exit__(self, *a, **kw): return self.v


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
            if isinstance(dline, (str, unicode)):
                m = IMAP_TOKEN.match(dline)
            else:
                print 'WARNING: Unparsed IMAP response data: %s' % (dline,)
                m = None
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
    def __init__(self, session, conn, idle_mailbox=None, idle_callback=None):
        threading.Thread.__init__(self)
        self.daemon = True
        self.session = session
        self._lock = MSrcLock()
        self._conn = conn
        self._idle_mailbox = idle_mailbox
        self._idle_callback = idle_callback
        self._idling = False
        self._selected = None

        for meth in ('append', 'add', 'capability', 'fetch', 'noop',
                     'list', 'login', 'search', 'uid'):
            self.__setattr__(meth, self._mk_proxy(meth))

        self._update_name()
        self.start()

    def _mk_proxy(self, method):
        def proxy_method(*args, **kwargs):
            try:
                assert(self._lock.locked())
                if 'mailbox' in kwargs:
                    # We're sharing this connection, so all mailbox methods
                    # need to tell us which mailbox they're operating on.
                    typ, data = self.select(kwargs['mailbox'])
                    if typ.upper() != 'OK':
                        return (typ, data)
                    del kwargs['mailbox']
                if 'imap' in self.session.config.sys.debug:
                    self.session.ui.debug('%s(%s %s)' % (method, args, kwargs))
                rv = getattr(self._conn, method)(*args, **kwargs)
                if 'imap' in self.session.config.sys.debug:
                    self.session.ui.debug((' => %s' % (rv,))[:240])
                return rv
            except IMAP4.error:
                # We convert IMAP4.error to a subclass of IOError, so
                # things get caught by the already existing error handling
                # code in Mailpile.  We do not catch the assertions, as
                # those are logic errors that should not be suppressed.
                raise IMAP_IOError('Failed %s(%s %s)' % (method, args, kwargs))
            except:
                if 'imap' in self.session.config.sys.debug:
                    self.session.ui.debug(traceback.format_exc())
                raise
        return proxy_method

    def close(self):
        assert(self._lock.locked())
        self._selected = None
        if '(closed)' not in self.name:
            self.name += ' (closed)'
        return self._conn.close()

    def select(self, mailbox='INBOX', readonly=True):
        # This routine caches the SELECT operations, because we will be
        # making lots and lots of superfluous ones "just in case" as part
        # of multiplexing one IMAP connection for multiple mailboxes.
        assert(self._lock.locked())
        if self._selected and self._selected[0] == (mailbox, readonly):
            return self._selected[1]
        rv = self._conn.select(mailbox='"%s"' % mailbox, readonly=readonly)
        if rv[0].upper() == 'OK':
            info = dict(self._conn.response(f) for f in
                        ('FLAGS', 'EXISTS', 'RECENT', 'UIDVALIDITY'))
            self._selected = ((mailbox, readonly), rv, info)
        else:
            info = '(error)'
        if 'imap' in self.session.config.sys.debug:
            self.session.ui.debug('select(%s, %s) = %s %s'
                                  % (mailbox, readonly, rv, info))
        return rv

    def mailbox_info(self, k, default=None):
        if not self._selected or not self._selected[2]:
            return default
        return self._selected[2].get(k, default)

    def _update_name(self):
        name = self._conn and self._conn.host
        if name:
            self.name = name
        elif '(dead)' not in self.name:
            self.name += ' (dead)'

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
        self._update_name()

    def run(self):
        # FIXME: Do IDLE stuff if requested.
        try:
            while self._conn:
                # By default, all this does is send a NOOP every 120 seconds
                # to keep the connection alive (or detect errors).
                for t in range(0, 120):
                    time.sleep(1 if self._conn else 0)
                if self._conn:
                    with self as raw_conn:
                        raw_conn.noop()
        except:
            if 'imap' in self.session.config.sys.debug:
                self.session.ui.debug(traceback.format_exc())
        finally:
            self._conn = None
            self._update_name()


class SharedImapMailbox(Mailbox):
    """
    This implements a Mailbox view of an IMAP folder. The IMAP connection
    itself is obtained as a SharedImapConn from a particular mail source.

    >>> imap = ImapMailSource(session, imap_config)
    >>> mailbox = SharedImapMailbox(session, imap, conn_cls=_MockImap)
    >>> #mailbox.add('From: Bjarni\\r\\nBarely a message')
    """

    def __init__(self, session, mail_source,
                 mailbox_path='INBOX', conn_cls=None):
        self.config = session
        self.source = mail_source
        self.editable = False  # FIXME: this is technically not true
        self.path = mailbox_path
        self.conn_cls = conn_cls
        self._factory = None  # Unused, for Mailbox compatibility

    def open_imap(self):
        return self.source.open(throw=IMAP_IOError, conn_cls=self.conn_cls)

    def timed_imap(self, *args, **kwargs):
        return self.source.timed_imap(*args, **kwargs)

    def _assert(self, test, error):
        if not test:
            raise IMAP_IOError(error)

    def __nonzero__(self):
        try:
            with self.open_imap() as imap:
                ok, data = self.timed_imap(imap.noop, mailbox=self.path)
                return ok
        except (IOError, AttributeError):
            return False

    def add(self, message):
        raise Exception('FIXME: Need to RETURN AN ID.')
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.append, self.path, message=message)
            self._assert(ok, _('Failed to add message'))

    def remove(self, key):
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.store, '+FLAGS', r'\Deleted',
                                       mailbox=self.path)
            self._assert(ok, _('Failed to remove message'))

    def mailbox_info(self, k, default=None):
        with self.open_imap() as imap:
            imap.select(self.path)
            return imap.mailbox_info(k, default=default)

    def get_info(self, key):
        with self.open_imap() as imap:
            uidv, uid = (int(k, 36) for k in key.split('.'))
            ok, data = self.timed_imap(imap.uid, 'FETCH', uid,
                                       # Note: It seems that either python's
                                       #       imaplib, or our parser cannot
                                       #       handle dovecot's ENVELOPE
                                       #       details. So omit that for now.
                                       '(RFC822.SIZE FLAGS)',
                                       mailbox=self.path)
            if not ok:
                raise KeyError
            self._assert(str(uidv) in imap.mailbox_info('UIDVALIDITY', ['0']),
                         _('Mailbox is out of sync'))
            info = dict(zip(*[iter(data[1])]*2))
            info['UIDVALIDITY'] = uidv
            info['UID'] = uid
        return info

    def get(self, key):
        info = self.get_info(key)
        msg_bytes = int(info['RFC822.SIZE'])
        with self.open_imap() as imap:
            msg_data = []

            # FIXME: This will hard fail to download mail, if our internet
            #        connection averages 8 kbps or worse. Better would be to
            #        adapt the chunk size here to actual network performance.
            #
            chunk_size = self.source.timeout * 1024
            chunks = 1 + msg_bytes // chunk_size
            for chunk in range(0, chunks):
                req = '(BODY[]<%d.%d>)' % (chunk * chunk_size, chunk_size)
                # Note: use the raw method, not the convenient parsed version.
                typ, data = self.source.timed(imap.uid,
                                              'FETCH', info['UID'], req,
                                              mailbox=self.path)
                self._assert((typ == 'OK') and (chunk == chunks-1 or
                                                len(data[0][1]) == chunk_size),
                             _('Fetching chunk %d failed') % chunk)
                msg_data.append(data[0][1])

            return info, ''.join(msg_data)

    def get_message(self, key):
        info, payload = self.get(key)
        return Message(payload)

    def get_bytes(self, key):
        info, payload = self.get(key)
        return payload

    def get_file(self, key):
        info, payload = self.get(key)
        return StringIO.StringIO(payload)

    def iterkeys(self):
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.uid, 'SEARCH', None, 'ALL',
                                       mailbox=self.path)
            self._assert(ok, _('Failed to list mailbox contents'))
            validity = imap.mailbox_info('UIDVALIDITY', ['0'])[0]
            return ('%s.%s' % (b36(int(validity)), b36(int(k)))
                    for k in sorted(data))

    def update_toc(self):
        pass

    def get_msg_ptr(self, mboxid, key):
        return '%s%s' % (mboxid, quote(key))

    def get_file_by_ptr(self, msg_ptr):
        return self.get_file(unquote(msg_ptr[MBX_ID_LEN:]))

    def get_msg_size(self, key):
        return long(self.get_info(key).get('RFC822.SIZE', 0))

    def __contains__(self, key):
        try:
            self.get_info(key)
            return True
        except (KeyError):
            return False

    def __len__(self):
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.noop, mailbox=self.path)
            return imap.mailbox_info('EXISTS', ['0'])[0]

    def flush(self):
        pass

    def close(self):
        pass

    def lock(self):
        pass

    def unlock(self):
        pass

    def save(self, *args, **kwargs):
        # SharedImapMailboxes are never pickled to disk.
        pass


class ImapMailSource(BaseMailSource):
    """
    This is a mail source that connects to an IMAP server.

    A single connection is made to the IMAP server, which is then shared
    between the ImapMailSource job and individual mailbox instances.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.imap.ImapMailSource'

    TIMEOUT_INITIAL = 15
    TIMEOUT_LIVE = 60
    CONN_ERRORS = (IOError, IMAP_IOError, IMAP4.error, TimedOut)

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.timeout = self.TIMEOUT_INITIAL
        self.watching = -1
        self.capabilities = set()
        self.conn = None
        self.conn_id = ''

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

    def _conn_id(self):
        return md5_hex('\n'.join([str(self.my_config[k]) for k in
                                  ('host', 'port', 'password', 'username')]))

    def close(self):
        if self.conn:
            self.event.data['connection'] = {
                'live': False,
                'error': [False, _('Nothing is wrong')]
            }
            self.conn.quit()
            self.conn = None

    def open(self, conn_cls=None, throw=False):
        conn = self.conn
        conn_id = self._conn_id()
        if conn:
            try:
                with conn as c:
                    if (conn_id == self.conn_id and
                            self.timed(c.noop)[0] == 'OK'):
                        # Make the timeout longer, so we don't drop things
                        # on every hiccup and so downloads will be more
                        # efficient (chunk size relates to timeout).
                        self.timeout = self.TIMEOUT_LIVE
                        return conn
            except self.CONN_ERRORS + (AttributeError, ):
                pass
            with self._lock:
                if self.conn == conn:
                    self.conn = None
            conn.quit()

        # This facilitates testing, event should already exist in real life.
        if self.event:
            event = self.event
        else:
            event = Event(source=self, flags=Event.RUNNING, data={})

        # Prepare the data section of our event, for keeping state.
        for d in ('mailbox_state',):
            if d not in event.data:
                event.data[d] = {}
        ev = event.data['connection'] = {
            'live': False,
            'error': [False, _('Nothing is wrong')]
        }

        conn = None
        my_config = self.my_config
        mailboxes = my_config.mailbox.values()

        # If we are given a conn class, use that - this allows mocks for
        # testing.
        if not conn_cls:
            want_ssl = (my_config.protocol == 'imap_ssl')
            conn_cls = IMAP4_SSL if want_ssl else IMAP4

        try:
            def mkconn():
                with ConnBroker.context(need=[ConnBroker.OUTGOING_IMAP]):
                    return conn_cls(my_config.host, my_config.port)
            conn = self.timed(mkconn)
            conn.debug = ('imaplib' in self.session.config.sys.debug
                          ) and 4 or 0

            ok, data = self.timed_imap(conn.capability)
            if ok:
                capabilities = set(' '.join(data).upper().split())
            else:
                capabilities = set()

            #if 'STARTTLS' in capabilities and not want_ssl:
            #
            # FIXME: We need to send a STARTTLS and do a switcheroo where
            #        the connection gets encrypted.

            try:
                ok, data = self.timed_imap(conn.login,
                                           my_config.username,
                                           my_config.password)
            except IMAP4.error:
                ok = False
            if not ok:
                ev['error'] = ['auth', _('Invalid username or password')]
                if throw:
                    raise throw(event.data['conn_error'])
                return WithaBool(False)

            with self._lock:
                if self.conn is not None:
                    raise IOError('Woah, we lost a race.')
                self.capabilities = capabilities
                if 'IDLE' in capabilities:
                    self.conn = SharedImapConn(
                        self.session, conn,
                        idle_mailbox='INBOX',
                        idle_callback=self._idle_callback)
                else:
                    self.conn = SharedImapConn(self.session, conn)

            if self.event:
                self._log_status(_('Connected to IMAP server %s'
                                   ) % my_config.host)
            if 'imap' in self.session.config.sys.debug:
                self.session.ui.debug('CONNECTED %s' % self.conn)

            self.conn_id = conn_id
            ev['live'] = True
            return self.conn

        except TimedOut:
            if 'imap' in self.session.config.sys.debug:
                self.session.ui.debug(traceback.format_exc())
            ev['error'] = ['timeout', _('Connection timed out')]
        except (IMAP_IOError, IMAP4.error):
            if 'imap' in self.session.config.sys.debug:
                self.session.ui.debug(traceback.format_exc())
            ev['error'] = ['protocol', _('An IMAP protocol error occurred')]
        except (IOError, AttributeError, socket.error):
            if 'imap' in self.session.config.sys.debug:
                self.session.ui.debug(traceback.format_exc())
            ev['error'] = ['network', _('A network error occurred')]

        try:
            if conn:
                # Close the socket directly, in the hopes this will boot
                # any timed-out operations out of a hung state.
                conn.socket().shutdown(socket.SHUT_RDWR)
                conn.file.close()
        except (AttributeError, IOError, socket.error):
            pass
        if throw:
            raise throw(ev['error'])
        return WithaBool(False)

    def _idle_callback(self, data):
        pass

    def open_mailbox(self, mbx_id, mfn):
        if FormatMbxId(mbx_id) in self.my_config.mailbox:
            try:
                proto_me, path = mfn.split('/', 1)
                if proto_me.startswith('src:'):
                    return SharedImapMailbox(self.session, self,
                                             mailbox_path=path)
            except ValueError:
                pass
        return None

    def _has_mailbox_changed(self, mbx, state):
        src = self.session.config.open_mailbox(self.session,
                                               FormatMbxId(mbx._key),
                                               prefer_local=False)
        uv = state['uv'] = src.mailbox_info('UIDVALIDITY', ['0'])[0]
        ex = state['ex'] = src.mailbox_info('EXISTS', ['0'])[0]
        uvex = '%s/%s' % (uv, ex)
        if uvex == '0/0':
            return True
        return (uvex != self.event.data.get('mailbox_state',
                                            {}).get(mbx._key))

    def _mark_mailbox_rescanned(self, mbx, state):
        uvex = '%s/%s' % (state['uv'], state['ex'])
        if 'mailbox_state' in self.event.data:
            self.event.data['mailbox_state'][mbx._key] = uvex
        else:
            self.event.data['mailbox_state'] = {mbx._key: uvex}

    def _mailbox_name(self, path):
        # len('src:/') = 5
        return path[(5 + len(self.my_config._key)):]

    def _fmt_path(self, path):
        return 'src:%s/%s' % (self.my_config._key, path)

    def discover_mailboxes(self, unused_paths=None):
        config = self.session.config
        existing = self._existing_mailboxes()
        discovered = []
        with self.open() as raw_conn:
            try:
                ok, data = self.timed_imap(raw_conn.list, '', '%')
                while ok and len(data) >= 3:
                    (flags, sep, path), data[:3] = data[:3], []
                    if '[Gmail]' in path:
                        # FIXME: Temp hack to ignore the [Gmail] thing
                        continue
                    path = self._fmt_path(path)
                    if path not in existing:
                        discovered.append((path, flags))
            except self.CONN_ERRORS:
                pass

        for path, flags in discovered:
            idx = config.sys.mailbox.append(path)
            mbx = self.take_over_mailbox(idx)

        return len(discovered)

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
    <SharedImapConn(mock, started ...)>

    >>> sorted(imap.capabilities)
    ['IMAP4REV1', 'X-MAGIC-BEANS']
    """
    DEFAULT_RESULTS = {
        'append': ('OK', []),
        'capability': ('OK', ['X-MAGIC-BEANS', 'IMAP4rev1']),
        'list': ('OK', []),
        'login': ('OK', ['"Welcome, human"']),
        'noop': ('OK', []),
        'select': ('OK', []),
    }
    RESULTS = {}

    def __init__(self, *args, **kwargs):
        self.host = 'mock'
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
        session.config.sys.debug = 'imap'

        username, password = args.pop(0), args.pop(0)
        config.sources.imap.username = username
        config.sources.imap.password = password
        imap = ImapMailSource(session, config.sources.imap)
        with imap.open(throw=IMAP_IOError) as conn:
            print '%s' % (conn.list(), )
        mbx = SharedImapMailbox(config, imap, mailbox_path='INBOX')
        print '%s' % list(mbx.iterkeys())
        for key in args:
            info, payload = mbx.get(key)
            print '%s(%d bytes) = %s\n%s' % (mbx.get_msg_ptr('0000', key),
                                             mbx.get_msg_size(key),
                                             info, payload)

