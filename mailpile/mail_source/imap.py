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
import imaplib
import os
import re
import socket
import select
import ssl
import traceback
import time
from imaplib import IMAP4_SSL, CRLF
from mailbox import Mailbox, Message
from urllib import quote, unquote

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

import mailpile.mail_source.imap_utf7
from mailpile.auth import IndirectPassword
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.index.mailboxes import MailboxIndex
from mailpile.mail_source import BaseMailSource
from mailpile.mail_source.imap_starttls import IMAP4
from mailpile.mailutils import FormatMbxId, MBX_ID_LEN
from mailpile.plugins.oauth import OAuth2
from mailpile.util import *
from mailpile.vfs import FilePath


# Raise imaplib's default maximum line length to something long and
# silly. Some versions of Python ship with this set too low for the
# Real World (no matter what the RFCs say).
imaplib._MAXLINE = 10 * 1024 * 1024


IMAP_TOKEN = re.compile('("[^"]*"'
                        '|[\\(\\)]'
                        '|[^\\(\\)"\\s]+'
                        '|\\s+)')

# These are mailbox names we avoid downloading (by default)
BLACKLISTED_MAILBOXES = (
    'drafts',
    '[gmail]/important',
    '[gmail]/starred',
    'openpgp_keys'
)

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
    if not reply or len(reply) < 2:
        return False, []
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


class ImapMailboxIndex(MailboxIndex):
    pass


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
        self._can_idle = False
        self._idling = False
        self._selected = None

        for meth in ('append', 'add', 'authenticate', 'capability', 'fetch',
                     'noop', 'store', 'expunge', 'close',
                     'list', 'login', 'logout', 'namespace', 'search', 'uid'):
            self.__setattr__(meth, self._mk_proxy(meth))

        self._update_name()
        self.start()

    def _mk_proxy(self, method):
        def proxy_method(*args, **kwargs):
            try:
                safe_assert(self._lock.locked())
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

            # This is annoyingly repetetive because the imaplib error classes
            # are subclassed in a strange way.
            #
            # In short, we convert imaplib's error, abort and readonly into
            # a subclass of IOError, so Mailplie's common logic can handle
            # things gracefully. In the case of abort, we also kill the
            # connection because it's probably in an unworkable state.
            #
            except IMAP4.readonly:
                if 'imap' in self.session.config.sys.debug:
                    self.session.ui.debug(traceback.format_exc())
                raise IMAP_IOError('Readonly: %s(%s %s)' % (method, args, kwargs))
            except IMAP4.abort:
                if 'imap' in self.session.config.sys.debug:
                    self.session.ui.debug(traceback.format_exc())
                self._shutdown()
                raise IMAP_IOError('Abort: %s(%s %s)' % (method, args, kwargs))
            except IMAP4.error:
                if 'imap' in self.session.config.sys.debug:
                    self.session.ui.debug(traceback.format_exc())
                raise IMAP_IOError('Error: %s(%s %s)' % (method, args, kwargs))
            except:
                # Default is no-op, just re-raise the exception. This includes
                # the assertions above; they're logic errors we don't want to
                # suppress.
                raise
        return proxy_method

    def _shutdown(self):
        if self._conn:
            self._conn.shutdown()
            self._conn = None
            self._update_name()

    def close(self):
        safe_assert(self._lock.locked())
        self._selected = None
        if '(closed)' not in self.name:
            self.name += ' (closed)'
        return self._conn.close()

    def select(self, mailbox='INBOX', readonly=False):
        # This routine caches the SELECT operations, because we will be
        # making lots and lots of superfluous ones "just in case" as part
        # of multiplexing one IMAP connection for multiple mailboxes.
        safe_assert(self._lock.locked())
        if self._selected and self._selected[0] == (mailbox, readonly):
            return self._selected[1]
        elif self._selected:
            self._conn.close()
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
        self._stop_idling()
        return self

    def __exit__(self, type, value, traceback):
        self._start_idling()
        self._lock.release()

    def _start_idling(self):
        self._can_idle = True

    def _stop_idling(self):
        self._can_idle = False

    def _imap_idle(self):
        if not self._conn:
            return

        self._can_idle = True
        self.select(self._idle_mailbox)
        if 'imap' in self.session.config.sys.debug:
            logger = self.session.ui.debug
        else:
            logger = lambda x: True

        def send_line(data):
            logger('> %s' % data)
            self._conn.send('%s%s' % (data, CRLF))

        def get_line():
            data = self._conn._get_line().rstrip()
            logger('< %s' % data)
            return data

        try:
            send_line('%s IDLE' % self._conn._new_tag())
            while self._can_idle and not get_line().startswith('+ '):
                pass
            while True:
                rl = wl = xl = None
                try:
                    rl, wl, xl = select.select([self._conn.sock], [], [], 1)
                except socket.error:
                    pass
                if mailpile.util.QUITTING or not self._can_idle:
                    break
                elif rl and self._idle_callback(get_line()):
                    self._selected = None
                    break
            send_line('DONE')
            # Note: We let the IDLE response drop on the floor, don't care.
        except (socket.error, OSError), val:
            raise self._conn.abort('socket error: %s' % val)

    def quit(self):
        with self._lock:
            try:
                if self._conn and self._conn.file:
                    if self._selected:
                        self._conn.close()
                    self.logout()
            except (IOError, IMAP4.error, AttributeError):
                pass
            self._can_idle = False
            self._conn = None
            self._update_name()

    def run(self):
        try:
            idle_counter = 0
            while self._conn:
                # By default, all this does is send a NOOP every 120 seconds
                # to keep the connection alive (or detect errors).
                for t in range(0, 120):
                    time.sleep(1 if self._conn else 0)
                    if self._can_idle and self._idle_mailbox:
                        idle_counter += 1
                        # Once we've been in "can idle" state for 5: IDLE!
                        if idle_counter >= 5:
                            with self as raw_conn:
                                self._imap_idle()
                    else:
                        idle_counter = 0

                if self._conn:
                    with self as raw_conn:
                        raw_conn.noop()
        except:
            if 'imap' in self.session.config.sys.debug:
                self.session.ui.debug(traceback.format_exc())
        finally:
            self.quit()


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
        self._last_updated = None
        self._index = None
        self._factory = None  # Unused, for Mailbox compatibility
        self._broken = None

    def open_imap(self):
        return self.source.open(throw=IMAP_IOError, conn_cls=self.conn_cls)

    def timed_imap(self, *args, **kwargs):
        return self.source.timed_imap(*args, **kwargs)

    def last_updated(self):
        return self._last_updated

    def _assert(self, test, error):
        if not test:
            raise IMAP_IOError(error)

    def __nonzero__(self):
        if self._broken is not None:
            return not self._broken
        try:
            with self.open_imap() as imap:
                ok, data = self.timed_imap(imap.noop, mailbox=self.path)
                self._broken = False
        except (IOError, AttributeError):
            self._broken = True
        return not self._broken

    def add(self, message):
        raise Exception('FIXME: Need to RETURN AN ID.')
        self._broken = None
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.append, self.path, message=message)
            self._last_updated = time.time()
            self._assert(ok, _('Failed to add message'))
        self._broken = False

    def remove(self, key):
        self._broken = None
        with self.open_imap() as imap:
            uidv, uid = (int(k, 36) for k in key.split('.'))
            ok, data = self.timed_imap(imap.uid, 'STORE', uid,
                                       '+FLAGS', '(\Deleted)',
                                       mailbox=self.path)
            self._last_updated = time.time()
            self._assert(ok, _('Failed to remove message'))
        self._broken = False

    def mailbox_info(self, k, default=None):
        self._broken = None
        with self.open_imap() as imap:
            imap.select(self.path)
            return imap.mailbox_info(k, default=default)
        self._broken = False

    def get_info(self, key):
        self._broken = None
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
                raise KeyError(key)
            self._assert(str(uidv) in imap.mailbox_info('UIDVALIDITY', ['0']),
                         _('Mailbox is out of sync'))
            info = dict(zip(*[iter(data[1])]*2))
            info['UIDVALIDITY'] = uidv
            info['UID'] = uid
        self._broken = False
        return info

    def get(self, key, _bytes=None):
        info = self.get_info(key)
        if 'UID' not in info:
            raise KeyError(key)

        # FIXME: This will hard fail to download mail, if our internet
        #        connection averages 8 kbps or worse. Better would be to
        #        adapt the chunk size here to actual network performance.
        #
        chunk_size = self.source.timeout * 1024
        chunk = 0
        msg_data = []
        if _bytes and chunk_size > _bytes:
            chunk_size = _bytes

        # Some IMAP servers misreport RFC822.SIZE, so we cannot really know
        # how much data to expect. So we just FETCH chunk until one comes up
        # short or empty and assume that's it...
        while chunk >= 0:
            req = '(BODY.PEEK[]<%d.%d>)' % (chunk * chunk_size, chunk_size)
            with self.open_imap() as imap:
                # Note: use the raw method, not the convenient parsed version.
                typ, data = self.source.timed(imap.uid,
                                              'FETCH', info['UID'], req,
                                              mailbox=self.path)
            self._assert(typ == 'OK',
                         _('Fetching chunk %d failed') % chunk)
            msg_data.append(data[0][1])
            if len(data[0][1]) < chunk_size:
                chunk = -1
            else:
                chunk += 1
            if _bytes and chunk * chunk_size > _bytes:
                chunk = -1

        # FIXME: Should we add a sanity check and complain if we got
        #        significantly less data than expected via. RFC822.SIZE?
        return info, ''.join(msg_data)

    def get_message(self, key):
        info, payload = self.get(key)
        return Message(payload)

    def get_bytes(self, key, *args):
        info, payload = self.get(key, *args)
        return payload

    def get_file(self, key):
        info, payload = self.get(key)
        return StringIO.StringIO(payload)

    def iterkeys(self):
        self._broken = None
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.uid, 'SEARCH', None, 'ALL',
                                       mailbox=self.path)
            self._assert(ok, _('Failed to list mailbox contents'))
            validity = imap.mailbox_info('UIDVALIDITY', ['0'])[0]
        self._broken = False
        return ('%s.%s' % (b36(int(validity)), b36(int(k)))
                for k in sorted(data))

    def keys(self):
        return list(self.iterkeys())

    def update_toc(self):
        self._last_updated = time.time()

    def get_msg_ptr(self, mboxid, key):
        return '%s%s' % (mboxid, quote(key))

    def get_file_by_ptr(self, msg_ptr):
        return self.get_file(unquote(msg_ptr[MBX_ID_LEN:]))

    def get_msg_size(self, key):
        return long(self.get_info(key).get('RFC822.SIZE', 0))

    def get_metadata_keywords(self, key):
        # Translate common IMAP flags into the maildir vocabulary
        flags = [f.lower() for f in self.get_info(key).get('FLAGS', '')]
        mkws = []
        for char, flag in (('s', '\\seen'),
                           ('r', '\\answered'),
                           ('d', '\\draft'),
                           ('f', '\\flagged'),
                           ('t', '\\deleted')):
           if flag in flags:
               mkws.append('%s:maildir' % char)
        return mkws

    def __contains__(self, key):
        try:
            self.get_info(key)
            return True
        except (KeyError):
            return False

    def __len__(self):
        self._broken = None
        with self.open_imap() as imap:
            ok, data = self.timed_imap(imap.noop, mailbox=self.path)
            return imap.mailbox_info('EXISTS', ['0'])[0]
        self._broken = False

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

    def get_index(self, config, mbx_mid=None):
        if self._index is None:
            self._index = ImapMailboxIndex(config, self, mbx_mid=mbx_mid)
        return self._index

    def __unicode__(self):
        if self:
            return _("IMAP: %s") % self.path
        else:
            return _("IMAP: %s (not logged in)") % self.path

    def describe_msg_by_ptr(self, msg_ptr):
        if self:
            return _("e-mail with ID %s") % unquote(msg_ptr[MBX_ID_LEN:])
        else:
            return _("remote mailbox is inavailable")


def _connect_imap(session, settings, event,
                  conn_cls=None, timeout=30, throw=False,
                  logged_in_cb=None, source=None):

    def timed(*args, **kwargs):
        if source is not None:
            kwargs['unique_thread'] = 'imap/%s' % (source.my_config._key,)
        return RunTimed(timeout, *args, **kwargs)

    def timed_imap(*args, **kwargs):
        if source is not None:
            kwargs['unique_thread'] = 'imap/%s' % (source.my_config._key,)
        return _parse_imap(RunTimed(timeout, *args, **kwargs))

    conn = None
    try:
        # Prepare the data section of our event, for keeping state.
        for d in ('mailbox_state',):
            if d not in event.data:
                event.data[d] = {}
        ev = event.data['connection'] = {
            'live': False,
            'error': [False, _('Nothing is wrong')]
        }

        # If we are given a conn class, use that - this allows mocks for
        # testing.
        if not conn_cls:
            req_stls = (settings.get('protocol') == 'imap_tls')
            want_ssl = (settings.get('protocol') == 'imap_ssl')
            conn_cls = IMAP4_SSL if want_ssl else IMAP4
        else:
            req_stls = want_ssl = False

        def mkconn():
            if want_ssl:
                need = [ConnBroker.OUTGOING_IMAPS]
            else:
                need = [ConnBroker.OUTGOING_IMAP]
            with ConnBroker.context(need=need):
                return conn_cls(settings.get('host'),
                                int(settings.get('port')))
        conn = timed(mkconn)
        if hasattr(conn, 'sock'):
            conn.sock.settimeout(120)
        conn.debug = ('imaplib' in session.config.sys.debug) and 4 or 0

        ok, data = timed_imap(conn.capability)
        if ok:
            capabilities = set(' '.join(data).upper().split())
        else:
            capabilities = set()

        if req_stls or ('STARTTLS' in capabilities and not want_ssl):
            try:
                ok, data = timed_imap(conn.starttls)
                if ok:
                    # Fetch capabilities again after STARTTLS
                    ok, data = timed_imap(conn.capability)
                    capabilities = set(' '.join(data).upper().split())
                    # Update the protocol to avoid getting downgraded later
                    if settings.get('protocol', '') != 'imap_ssl':
                        settings['protocol'] = 'imap_tls'
            except (IMAP4.error, IOError, socket.error):
                ok = False
            if not ok:
                ev['error'] = [
                    'tls',
                    _('Failed to make a secure TLS connection'),
                    '%s:%s' % (settings.get('host'), settings.get('port'))]
                if throw:
                    raise throw(ev['error'][1])
                return WithaBool(False)

        username = password = ""
        try:
            error_type = 'auth'
            error_msg = _('Invalid username or password')
            username = settings.get('username', '').encode('utf-8')
            password = IndirectPassword(
                session.config,
                settings.get('password', '')
                ).encode('utf-8')

            if (settings.get('auth_type', '').lower() == 'oauth2'
                    and 'AUTH=XOAUTH2' in capabilities):
                error_type = 'oauth2'
                error_msg = _('Access denied by mail server')
                token_info = OAuth2.GetFreshTokenInfo(session, username)
                if not (username and token_info and token_info.access_token):
                    raise ValueError("Missing configuration")
                ok, data = timed_imap(
                    conn.authenticate, 'XOAUTH2',
                    lambda challenge: OAuth2.XOAuth2Response(username,
                                                             token_info))
                if not ok:
                    token_info.access_token = ''

            else:
                ok, data = timed_imap(conn.login, username, password)

        except (IMAP4.error, UnicodeDecodeError, ValueError):
            ok, data = False, None
        if not ok:
            auth_summary = ''
            if source is not None:
                auth_summary = source._summarize_auth()
            ev['error'] = [error_type, error_msg, username, auth_summary]
            if throw:
                raise throw(ev['error'][1])
            return WithaBool(False)

        if logged_in_cb is not None:
            logged_in_cb(conn, ev, capabilities)

        return conn

    except TimedOut:
        if 'imap' in session.config.sys.debug:
            session.ui.debug(traceback.format_exc())
        ev['error'] = ['timeout', _('Connection timed out')]
    except (ssl.CertificateError, ssl.SSLError):
        if 'imap' in session.config.sys.debug:
            session.ui.debug(traceback.format_exc())
        ev['error'] = ['tls', _('Failed to make a secure TLS connection'),
                       '%s:%s' % (settings.get('host'), settings.get('port'))]
    except (IMAP_IOError, IMAP4.error):
        if 'imap' in session.config.sys.debug:
            session.ui.debug(traceback.format_exc())
        ev['error'] = ['protocol', _('An IMAP protocol error occurred')]
    except (IOError, AttributeError, socket.error):
        if 'imap' in session.config.sys.debug:
            session.ui.debug(traceback.format_exc())
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

    return None


class ImapMailSource(BaseMailSource):
    """
    This is a mail source that connects to an IMAP server.

    A single connection is made to the IMAP server, which is then shared
    between the ImapMailSource job and individual mailbox instances.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.imap.ImapMailSource'

    TIMEOUT_INITIAL = 60
    TIMEOUT_LIVE = 120
    CONN_ERRORS = (IOError, IMAP_IOError, IMAP4.error, TimedOut)


    class MailSourceVfs(BaseMailSource.MailSourceVfs):
        """Expose the IMAP tree to the VFS layer."""
        def _imap_path(self, path):
            if path[:1] == '/':
                path = path[1:]
            return path[len(self.root.raw_fp):]

        def _imap(self, *args, **kwargs):
            return self.source.timed_imap(*args, **kwargs)

        def listdir_(self, where, **kwargs):
            results = []
            path = self._imap_path(where)
            prefix, pathsep = self.source._namespace_info(path)
            with self.source.open() as conn:
                if not conn:
                    raise socket.error(_('Not connected to IMAP server.'))
                if path:
                    ok, data = self._imap(conn.list, path + pathsep, '%')
                else:
                    ok, data = self._imap(conn.list, '', '%')
                while ok and len(data) >= 3:
                    (flags, sep, path), data[:3] = data[:3], []
                    flags = [f.lower() for f in flags]
                    self.source._cache_flags(path, flags)
                    results.append('/' + self.source._fmt_path(path))
            return results

        def getflags_(self, fp, cfg):
            if self.root == fp:
                return BaseMailSource.MailSourceVfs.getflags_(self, fp, cfg)
            flags = [flag.lower().replace('\\', '') for flag in
                     self.source._cache_flags(self._imap_path(fp)) or []]
            if not ('hasnochildren' in flags or 'noinferiors' in flags):
                flags.append('Directory')
            if not ('noselect' in flags):
                flags.append('Mailbox')
            return flags

        def abspath_(self, fp):
            return fp

        def display_name_(self, fp, config):
            return FilePath(fp).display_basename()

        def isdir_(self, fp):
            if self.root == fp:
                return True
            flags = self.source._cache_flags(self._imap_path(fp)) or []
            return not ('hasnochildren' in flags or 'noinferiors' in flags)

        def getsize_(self, path):
            return None


    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.timeout = self.TIMEOUT_INITIAL
        self.last_op = 0
        self.watching = -1
        self.capabilities = set()
        self.logged_in_at = None
        self.namespaces = {'private': []}
        self.flag_cache = {}
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

    def _conn_id(self):
        def e(s):
            try:
                return unicode(s).encode('utf-8')
            except UnicodeDecodeError:
                return unicode(s).encode('utf-8', 'replace')
        return md5_hex('\n'.join([e(self.my_config[k]) for k in
                                  ('host', 'port', 'password', 'username')]))

    def close(self):
        with self._lock:
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
                    now = time.time()
                    if (conn_id == self.conn_id and
                            (now < self.last_op + 120 or
                             self.timed(c.noop)[0] == 'OK')):
                        # Make the timeout longer, so we don't drop things
                        # on every hiccup and so downloads will be more
                        # efficient (chunk size relates to timeout).
                        self.timeout = self.TIMEOUT_LIVE
                        if now >= self.last_op + 120:
                            self.last_op = now
                        return conn
            except self.CONN_ERRORS + (AttributeError, ):
                pass
            with self._lock:
                if self.conn == conn:
                    self.conn = None
            conn.quit()

        my_config = self.my_config

        # This facilitates testing, event should already exist in real life.
        if self.event:
            event = self.event
        else:
            event = Event(source=self, flags=Event.RUNNING, data={})

        def logged_in_cb(conn, ev, capabilities):
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

                if 'NAMESPACE' in capabilities:
                    ok, data = self.timed_imap(conn.namespace)
                    if ok:
                        prv, oth, shr = data
                        self.namespaces = {
                            'private': prv if (prv != 'NIL') else [],
                            'others': oth if (oth != 'NIL') else [],
                            'shared': shr if (shr != 'NIL') else []
                        }

            if self.event:
                self._log_status(_('Connected to IMAP server %s'
                                   ) % my_config.host)
            if 'imap' in self.session.config.sys.debug:
                self.session.ui.debug('CONNECTED %s' % self.conn)
                self.session.ui.debug('CAPABILITIES %s' % self.capabilities)
                self.session.ui.debug('NAMESPACES %s' % self.namespaces)

            self.conn_id = conn_id
            ev['live'] = True

        conn = _connect_imap(self.session, self.my_config, event,
                             conn_cls=conn_cls,
                             timeout=self.timeout,
                             throw=throw,
                             logged_in_cb=logged_in_cb,
                             source=self)
        if conn:
            self.logged_in_at = time.time()
            return self.conn
        else:
            return WithaBool(False)

    def _idle_callback(self, data):
        if 'EXISTS' in data:
            # Stop sleeping and check for mail
            self.wake_up()
            return True
        else:
            return False

    def _check_keepalive(self):
        alive_for = time.time() - self.logged_in_at
        if (not self.my_config.keepalive) or alive_for > (12 * 3600):
            if ('IDLE' not in self.capabilities or
                    alive_for > self.my_config.interval):
                self.close()

    def open_mailbox(self, mbx_id, mfn):
        try:
            proto_me, path = mfn.split('/', 1)
            if proto_me.startswith('src:%s' % self.my_config._key):
                return SharedImapMailbox(self.session, self, mailbox_path=path)
        except ValueError:
            pass
        return None

    def _get_mbx_id_and_mfn(self, mbx_cfg):
        mbx_id = FormatMbxId(mbx_cfg._key)
        return mbx_id, self.session.config.sys.mailbox[mbx_id]

    def _has_mailbox_changed(self, mbx_cfg, state):
        shared_mbox = self.open_mailbox(*self._get_mbx_id_and_mfn(mbx_cfg))
        uv = state['uv'] = shared_mbox.mailbox_info('UIDVALIDITY', ['0'])[0]
        ex = state['ex'] = shared_mbox.mailbox_info('EXISTS', ['0'])[0]
        uvex = '%s/%s' % (uv, ex)
        if uvex == '0/0':
            return True
        return (uvex != self.event.data.get('mailbox_state',
                                            {}).get(mbx_cfg._key))

    def _mark_mailbox_rescanned(self, mbx, state):
        uvex = '%s/%s' % (state['uv'], state['ex'])
        if 'mailbox_state' in self.event.data:
            self.event.data['mailbox_state'][mbx._key] = uvex
        else:
            self.event.data['mailbox_state'] = {mbx._key: uvex}

    def _namespace_info(self, path):
        for which, nslist in self.namespaces.iteritems():
            for prefix, pathsep in nslist:
                if path.startswith(prefix):
                    return prefix, pathsep or '/'
        # This is a hack for older servers that don't do NAMESPACE
        if path.startswith('INBOX.'):
            return 'INBOX', '.'
        return '', '/'

    def _default_policy(self, mbx_cfg):
        if self._mailbox_path(self._path(mbx_cfg)
                              ).lower() in BLACKLISTED_MAILBOXES:
            return 'ignore'
        else:
            return 'inherit'

    def _msg_key_order(self, key):
        return [int(k, 36) for k in key.split('.')]

    def _strip_file_extension(self, mbx_path):
        return mbx_path  # Yes, a no-op :)

    def _decode_path(self, path):
        try:
            return path.decode('imap4-utf-7')
        except:
            return path

    def _mailbox_path(self, mbx_path):
        # len('src:/') = 5
        return str(mbx_path[(5 + len(self.my_config._key)):])

    def _mailbox_path_split(self, mbx_path):
        path = self._mailbox_path(mbx_path)
        prefix, pathsep = self._namespace_info(path)
        return [self._decode_path(p) for p in path.split(pathsep)]

    def _mailbox_name(self, mbx_path):
        path = self._mailbox_path(mbx_path)
        prefix, pathsep = self._namespace_info(path)
        return self._decode_path(path[len(prefix):])

    def _fmt_path(self, path):
        return 'src:%s/%s' % (self.my_config._key, path)

    def discover_mailboxes(self, paths=None):
        config = self.session.config
        ostate = self.on_event_discovery_starting()
        try:
            paths = (paths or self.my_config.discovery.paths)[:]
            max_mailboxes = self.my_config.discovery.max_mailboxes
            existing = self._existing_mailboxes()
            mailboxes = []

            with self.open() as raw_conn:
                for p in paths:
                    mailboxes += self._walk_mailbox_path(raw_conn, str(p))

            discovered = [mbx for mbx in mailboxes if mbx not in existing]
            if len(discovered) > max_mailboxes - len(existing):
                discovered = discovered[:max_mailboxes - len(existing)]
                self.on_event_discovery_toomany()

            self.set_event_discovery_state('adding')
            for path in discovered:
                idx = config.sys.mailbox.append(path)
                mbx = self.take_over_mailbox(idx)

            return len(discovered)
        finally:
            self.on_event_discovery_done(ostate)

    def _cache_flags(self, path, flags=None):
        path = self._fmt_path(path)
        if flags is not None:
            self.flag_cache[path] = flags
        return self.flag_cache.get(path)

    def _walk_mailbox_path(self, conn, prefix):
        """
        Walks the IMAP path recursively and returns a list of all found
        mailboxes.
        """
        mboxes = []
        subtrees = []
        # We go over the maximum slightly here, so the calling code can
        # detect that we want to go over the limits and can ask the user
        # whether that's OK.
        max_mailboxes = 5 + self.my_config.discovery.max_mailboxes
        try:
            ok, data = self.timed_imap(conn.list, prefix, '%')
            while ok and len(data) >= 3:
                (flags, sep, path), data[:3] = data[:3], []
                flags = [f.lower() for f in flags]
                if '\\noselect' not in flags:
                    # We cache the flags for this mailbox, they may tell
                    # use useful things about what kind of mailbox it is.
                    self._cache_flags(path, flags)
                    mboxes.append(self._fmt_path(path))
                if '\\haschildren' in flags:
                    subtrees.append('%s%s' % (path, sep))
                if len(mboxes) > max_mailboxes:
                    break
            for path in subtrees:
                if len(mboxes) < max_mailboxes:
                    mboxes.extend(self._walk_mailbox_path(conn, path))
        except self.CONN_ERRORS:
            pass
        finally:
            return mboxes

    def quit(self, *args, **kwargs):
        if self.conn:
            self.conn.quit()
        return BaseMailSource.quit(self, *args, **kwargs)


def TestImapSettings(session, settings, event,
                     timeout=ImapMailSource.TIMEOUT_INITIAL):
    conn = _connect_imap(session, settings, event, timeout=timeout)
    if conn:
        try:
            conn.socket().shutdown(socket.SHUT_RDWR)
            conn.file.close()
        except (IOError, OSError, socket.error):
            pass
        return True
    return False


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
    import mailpile.config.defaults
    import mailpile.config.manager
    import mailpile.ui

    rules = mailpile.config.defaults.CONFIG_RULES
    config = mailpile.config.manager.ConfigManager(rules=rules)
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
