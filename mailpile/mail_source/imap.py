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

from mailpile.util import *
from mailpile.mail_source import BaseMailSource


IMAP_TOKEN = re.compile('("[^"]*"'
                        '|[\\(\\)]'
                        '|[^\\(\\)"\\s]+'
                        '|\\s+)')


def _parse(reply):
    """
    This routine will parse common IMAP4 responses into Pythonic data
    structures.

    >>> _parse(('OK', ['One (Two (Th ree)) "Four Five"']))
    (True, ['One', ['Two', ['Th', 'ree']], 'Four Five'])

    >>> _parse(('BAD', ['Sorry']))
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


class ImapMailSource(BaseMailSource):
    """
    This is a mail source that connects to an IMAP server.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.imap.ImapMailSource'

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.watching = -1
        self.capabilities = None
        self.conn = None

    @classmethod
    def Tester(cls, conn_cls, *args, **kwargs):
        tcls = cls(*args, **kwargs)
        return tcls.open(conn_cls=conn_cls) and tcls or False

    def _unlocked_open(self, conn_cls=None):
        my_config = self.my_config
        mailboxes = my_config.mailbox.values()
        try:
            if self.conn and self.conn.noop()[0] == 'OK':
                return True
        except IMAP4.error:
            pass

        # If we are given a conn class, use that - this allows mocks for
        # testing.
        if not conn_cls:
            want_ssl = (my_config.protocol == 'imap_ssl')
            conn_cls = IMAP4_SSL if want_ssl else IMAP4

        self.conn = None
        try:
            conn = self.conn = conn_cls(my_config.host, my_config.port)
        except (IMAP4.error, socket.error):
            # FIXME: Event! Network down? Bad host/port?
            return False

        ok, data = _parse(conn.login(my_config.username, my_config.password))
        if not ok:
            # FIXME: Event! Bad login/password?
            return False

        ok, data = _parse(conn.capability())
        if ok:
            self.capabilities = set(' '.join(data).upper().split())
        else:
            self.capabilities = set()

        # FIXME: This is wrong
        return False

        # Prepare the data section of our event, for keeping state.
        for d in ('mtimes', 'sizes'):
            if d not in self.event.data:
                self.event.data[d] = {}

        self._log_status(_('Watching %d IMAP mailboxes') % self.watching)
        return True

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

    def _discover_mailboxes(self, path):
        pass


##[ Test code follows ]#######################################################

class _MockImap(object):
    """
    Base mock that pretends to be an imaplib IMAP connection.

    >>> imap = ImapMailSource(session, imap_config)
    >>> imap.open(conn_cls=_MockImap)
    False

    >>> sorted(imap.capabilities)
    ['IDLE', 'IMAP4REV1']
    """
    DEFAULT_RESULTS = {
        'login': ('OK', ['"Welcome, human"']),
        'capability': ('OK', ['IMAP4rev1 IDLE']),
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
