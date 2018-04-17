import os
import ssl
import traceback

from mailpile.auth import IndirectPassword
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.mail_source import BaseMailSource
from mailpile.mailboxes import pop3
from mailpile.mailutils import FormatMbxId, MBX_ID_LEN
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


# We use this to enable "recent mode" on GMail accounts by default.
GMAIL_TLDS = ('gmail.com', 'googlemail.com')


def _open_pop3_mailbox(session, event, host, port,
                       username, password, auth_type,
                       protocol, debug, throw=False):
    cev = event.data['connection'] = {
        'live': False,
        'error': [False, _('Nothing is wrong')]
    }
    try:
        # FIXME: Nothing actually adds gmail or gmail-full to the protocol
        #        yet, so we're stuck in recent mode only for now.
        if (username.lower().split('@')[-1] in GMAIL_TLDS
                or 'gmail' in protocol):
            if 'gmail-full' not in protocol:
                username = 'recent:%s' % username

        if 'ssl' in protocol:
            need = [ConnBroker.OUTGOING_POP3S]
        else:
            need = [ConnBroker.OUTGOING_POP3]

        with ConnBroker.context(need=need):
            return pop3.MailpileMailbox(host,
                                        port=port,
                                        user=username,
                                        password=password,
                                        auth_type=auth_type,
                                        use_ssl=('ssl' in protocol),
                                        session=session,
                                        debug=debug)
    except AccessError:
        cev['error'] = ['auth', _('Invalid username or password'),
                        username, sha1b64(password)]
    except (ssl.CertificateError, ssl.SSLError):
        cev['error'] = ['tls', _('Failed to make a secure TLS connection'),
                        '%s:%s' % (host, port)]
    except (IOError, OSError):
        cev['error'] = ['network', _('A network error occurred')]
        event.data['traceback'] = traceback.format_exc()

    if throw:
        raise throw(cev['error'][1])

    return None


class POP3_IOError(IOError):
    pass


class Pop3MailSource(BaseMailSource):
    """
    This is a mail source that watches over one or more POP3 mailboxes.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.pop3.Pop3MailSource'

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.watching = -1

    def close(self):
        mbx = self.my_config.mailbox.values()[0]
        if mbx:
            pop3 = self.session.config.open_mailbox(self.session,
                                                    FormatMbxId(mbx._key),
                                                    prefer_local=False,
                                                    from_cache=True)
            if pop3:
                pop3.close() 

    def _sleep(self, *args, **kwargs):
        self.close()
        return BaseMailSource._sleep(self, *args, **kwargs)

    def open(self):
        with self._lock:
            mailboxes = self.my_config.mailbox.values()
            if self.watching == len(mailboxes):
                return True
            else:
                self.watching = len(mailboxes)

            for d in ('mailbox_state', ):
                if d not in self.event.data:
                    self.event.data[d] = {}
            self.event.data['connection'] = {
                'live': False,
                'error': [False, _('Nothing is wrong')]
            }

        self._log_status(_('Watching %d POP3 mailboxes') % self.watching)
        return True

    def _has_mailbox_changed(self, mbx, state):
        pop3 = self.session.config.open_mailbox(self.session,
                                                FormatMbxId(mbx._key),
                                                prefer_local=False)
        state['stat'] = stat = '%s' % (pop3.stat(), )
        return (self.event.data.get('mailbox_state', {}).get(mbx._key) != stat)

    def _mark_mailbox_rescanned(self, mbx, state):
        if 'mailbox_state' in self.event.data:
            self.event.data['mailbox_state'][mbx._key] = state['stat']
        else:
            self.event.data['mailbox_state'] = {mbx._key: state['stat']}

    def _fmt_path(self):
        return 'src:%s' % (self.my_config._key,)

    def open_mailbox(self, mbx_id, mfn):
        my_cfg = self.my_config
        if 'src:' in mfn[:5] and FormatMbxId(mbx_id) in my_cfg.mailbox:
            debug = ('pop3' in self.session.config.sys.debug) and 99 or 0
            password = IndirectPassword(self.session.config, my_cfg.password)
            return _open_pop3_mailbox(self.session, self.event,
                                      my_cfg.host, my_cfg.port,
                                      my_cfg.username, password,
                                      my_cfg.auth_type,
                                      my_cfg.protocol, debug,
                                      throw=POP3_IOError)
        return None

    def discover_mailboxes(self, paths=None):
        config = self.session.config
        existing = self._existing_mailboxes()
        if self._fmt_path() not in existing:
            idx = config.sys.mailbox.append(self._fmt_path())
            self.take_over_mailbox(idx)
            return 1
        return 0

    def is_mailbox(self, fn):
        return False

    def _mailbox_name(self, path):
        return _("Inbox")

    def _create_tag(self, *args, **kwargs):
        ptag = kwargs.get('parent')
        try:
            if ptag:
                return self.session.config.get_tags(ptag)[0]._key
        except (IndexError, KeyError):
            pass
        return BaseMailSource._create_tag(self, *args, **kwargs)


def TestPop3Settings(session, settings, event):
    password = IndirectPassword(session.config, settings['password'])
    conn = _open_pop3_mailbox(session, event,
                              settings['host'],
                              int(settings['port']),
                              settings['username'],
                              password,
                              settings.get('auth_type', 'password'),
                              settings['protocol'],
                              True)
    if conn:
        conn.close()
        return True
    return False
