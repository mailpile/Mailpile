import asyncore
import smtpd
import threading
import traceback
from gettext import gettext as _

import mailpile.plugins
import mailpile.config
from mailpile.commands import Command
from mailpile.util import *


##[ Configuration ]##########################################################

mailpile.plugins.register_config_section(
    'sys', 'smtpd', [_('SMTP Daemon'), False, {
        'host': (_('Listening host for SMTP daemon'), 'hostname', 'localhost'),
        'port': (_('Listening port for SMTP daemon'), int, 33412),
    }])


class SMTPChannel(smtpd.SMTPChannel):
    def __init__(self, session, *args, **kwargs):
        smtpd.SMTPChannel.__init__(self, *args, **kwargs)
        self.session = session
        # Lie lie lie lie...
        self.__fqdn = 'cs.utah.edu'

    def push(self, msg):
        if msg.startswith('220'):
            # This is a hack, because these days it is no longer considered
            # reasonable to tell everyone your hostname and version number.
            # Lie lie lie lie! ... https://snowplow.org/tom/worm/worm.html
            smtpd.SMTPChannel.push(self, ('220 cs.utah.edu SMTP '
                                          'Sendmail 5.67; '
                                          'Wed, 2 Nov 1988 20:49'))
        else:
            smtpd.SMTPChannel.push(self, msg)

    # FIXME: We need to override MAIL and RCPT, so we can abort early if
    #        addresses are invalid. We may also want to implement a type of
    #        hashcash in the SMTP dialog.

    # FIXME: We need to put bounds on things so people cannot feed us mail
    #        of unreasonable size and asplode our RAM.


class SMTPServer(smtpd.SMTPServer):
    def __init__(self, session, localaddr):
        self.session = session
        smtpd.SMTPServer.__init__(self, localaddr, None)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            conn, addr = pair
            channel = SMTPChannel(self.session, self, conn, addr)

    def process_message(self, peer, mailfrom, rcpttos, data):
        # We can assume that the mailfrom and rcpttos have checked out
        # and this message is indeed intended for us. Spool it to disk
        # and add to the index!
        # FIXME FIXME FIXME
        print '=====[ We Have Mail! ]========================================='
        print '%s' % data
        print '==============================================================='
        return None


class SMTPWorker(threading.Thread):
    def __init__(self, session):
        self.session = session
        self.quitting = False
        threading.Thread.__init__(self)

    def run(self):
        cfg = self.session.config.sys.smtpd
        server = SMTPServer(self.session, (cfg.host, cfg.port))
        while not self.quitting:
            asyncore.poll(timeout=1.0)
        asyncore.close_all()

    def quit(self, join=True):
        self.quitting = True
        if join:
            try:
                self.join()
            except RuntimeError:
                pass


mailpile.plugins.register_worker(SMTPWorker)
