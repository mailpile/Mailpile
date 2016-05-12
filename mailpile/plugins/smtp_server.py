import asyncore
import email.parser
import random
import smtpd
import threading
import traceback

import mailpile.security as security
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils import Email
from mailpile.plugins import PluginManager
from mailpile.smtp_client import sha512_512kCheck, sha512_512kCollide
from mailpile.smtp_client import SMTORP_HASHCASH_RCODE, SMTORP_HASHCASH_FORMAT
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)


##[ Configuration ]##########################################################

_plugins.register_config_section(
    'sys', 'smtpd', [_('SMTP Daemon'), False, {
        'host': (_('Listening host for SMTP daemon'), 'hostname', 'localhost'),
        'port': (_('Listening port for SMTP daemon'), int, 0),
    }])


class SMTPChannel(smtpd.SMTPChannel):
    MAX_MESSAGE_SIZE = 1024 * 1024 * 50
    HASHCASH_WANT_BITS = 8  # Only 128-or-so expensive sha512_512k ops
    HASHCASH_URL = 'https://www.mailpile.is/hashcash/'

    def __init__(self, session, *args, **kwargs):
        smtpd.SMTPChannel.__init__(self, *args, **kwargs)
        self.session = session
        # Lie lie lie lie...
        self.__fqdn = 'cs.utah.edu'
        self.too_much_data = False
        self.is_spam = False
        self.want_hashcash = {}

    def _is_dangerous_address(self, address):
        return False  # FIXME

    def _is_spam_address(self, address):
        return False  # FIXME

    def push(self, msg):
        play_nice_with_threads()
        if msg.startswith('220'):
            # This is a hack, because these days it is no longer considered
            # reasonable to tell everyone your hostname and version number.
            # Lie lie lie lie! ... https://snowplow.org/tom/worm/worm.html
            smtpd.SMTPChannel.push(self, ('220 cs.utah.edu SMTP '
                                          'Sendmail 5.67; '
                                          'Wed, 2 Nov 1988 20:49'))
        else:
            smtpd.SMTPChannel.push(self, msg)

    def _address_ok(self, address):
        if self._is_dangerous_address(address):
            self.is_spam = True
        elif self._is_spam_address(address):
            self.is_spam = True
        return True

    def _challenge(self):
        return '-'.join([str(random.randint(0, 0xfffffff)),
                         str(random.randint(0, 0xfffffff)),
                         str(random.randint(0, 0xfffffff))])

    def _hashgrey_ok(self, address):
        if '#' in address:
            address, solution = address.split('##', 1)
        else:
            solution = None

        want_bits = self.HASHCASH_WANT_BITS
        addrpair = '%s, %s' % (self.__mailfrom, address)
        if solution and addrpair in self.want_hashcash:
            if sha512_512kCheck(self.want_hashcash[addrpair],
                               want_bits, solution):
                return address
            else:
                self.push('550 Hashcash is null and void')
                self.close_when_done()
                return None
        else:
            ch = self.want_hashcash[addrpair] = self._challenge()
            self.push(str(SMTORP_HASHCASH_RCODE) + ' ' +
                      SMTORP_HASHCASH_FORMAT
                      % {'bits': want_bits,
                         'challenge': ch,
                         'url': self.HASHCASH_URL})
            return None

    def smtp_MAIL(self, arg):
        address = self.__getaddr('FROM:', arg) if arg else None
        if not address:
            self.push('501 Syntax: MAIL FROM:<address>')
            return
        if self.__mailfrom:
            self.push('503 Error: nested MAIL command')
            return
        if self._address_ok(address):
            self.__mailfrom = address
            self.push('250 Ok')

    def smtp_RCPT(self, arg):
        if not self.__mailfrom:
            self.push('503 Error: need MAIL command')
            return
        address = self.__getaddr('TO:', arg) if arg else None
        if not address:
            self.push('501 Syntax: RCPT TO: <address>')
            return
        if len(self.__rcpttos) > 0:
            self.push("553 One mail at a time, please")
            self.close_when_done()
        if not self.is_spam:
            address = self._hashgrey_ok(address)
        if address and self._address_ok(address) and not self.is_spam:
            self.__rcpttos.append(address)
            self.push('250 Ok')

    def smtp_DATA(self, arg):
        if self.is_spam:
            self.push("450 I don't like spam!")
            self.close_when_done()
        else:
            smtpd.SMTPChannel.smtp_DATA(arg)

    def collect_incoming_data(self, data):
        if (self.__line and
                sum((len(l) for l in self.__line)) > self.MAX_MESSAGE_SIZE):
            self.push('552 Error: too much data')
            self.close_when_done()
        else:
            smtpd.SMTPChannel.collect_incoming_data(self, data)


class SMTPServer(smtpd.SMTPServer):
    def __init__(self, session, localaddr, **kwargs):
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
        session, config = self.session, self.session.config
        blank_tid = config.get_tags(type='blank')[0]._key
        idx = config.index
        play_nice_with_threads()
        try:
            message = email.parser.Parser().parsestr(data)
            lid, lmbox = config.open_local_mailbox(session)
            e = Email.Create(idx, lid, lmbox, ephemeral_mid=False)
            idx.add_tag(session, blank_tid, msg_idxs=[e.msg_idx_pos],
                        conversation=False)
            e.update_from_msg(session, message)
            idx.remove_tag(session, blank_tid, msg_idxs=[e.msg_idx_pos],
                           conversation=False)
            return None
        except:
            traceback.print_exc()
            return '400 Oops wtf'


class SMTPWorker(threading.Thread):
    def __init__(self, session):
        self.session = session
        self.quitting = False
        threading.Thread.__init__(self)

    def run(self):
        cfg = self.session.config.sys.smtpd
        if cfg.host and cfg.port:
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


class HashCash(Command):
    """Try to collide a hash using the SMTorP algorithm"""
    SYNOPSIS = (None, 'hashcash', None, '<bits> <challenge>')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ()
    COMMAND_SECURITY = security.CC_CPU_INTENSIVE

    def command(self):
        bits, challenge = int(self.args[0]), self.args[1]
        expected = 2 ** bits
        def marker(counter):
            progress = ((1024.0 * counter) / expected) * 100
            self.session.ui.mark('Finding a %d-bit collision for %s (%d%%)'
                                 % (bits, challenge, progress))
        collision = sha512_512kCollide(challenge, bits, callback1k=marker)
        return self._success({
            'challenge': challenge,
            'collision': collision
        })


_plugins.register_worker(SMTPWorker)
_plugins.register_commands(HashCash)
