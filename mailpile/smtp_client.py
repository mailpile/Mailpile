import random
import hashlib
import smtplib
import socket
import subprocess
import sys
from gettext import ngettext as _n

import mailpile.util
from mailpile.util import *
from mailpile.config import ssl, socks
from mailpile.mailutils import CleanMessage, MessageAsString
from mailpile.eventlog import Event


def Sha512Check(challenge, bits, solution):
    hexchars = bits // 4
    wanted = '0' * hexchars
    digest = hashlib.sha512('-'.join([solution, challenge])).hexdigest()
    return (digest[:hexchars] == wanted)


def Sha512Collide(challenge, bits, callback100k=None):
    sha512 = hashlib.sha512
    hexchars = bits // 4
    wanted = '0' * hexchars
    for i in xrange(1, 0x100):
        if callback100k is not None:
            callback100k(i)
        challenge_i = '-'.join([str(i), challenge])
        for j in xrange(0, 102400):
            collision = '-'.join([str(j), challenge_i])
            digest = sha512(collision).hexdigest()
            if digest[:hexchars] == wanted:
                return '-'.join(collision.split('-')[:2])
    return None


SMTORP_HASHCASH_RCODE = 450
SMTORP_HASHCASH_PREFIX = 'Please collide'
SMTORP_HASHCASH_FORMAT = (SMTORP_HASHCASH_PREFIX +
                          ' %(bits)d,%(challenge)s or retry. See: %(url)s')

def SMTorP_HashCash(rcpt, msg, callback100k=None):
    bits_challenge_etc = msg[len(SMTORP_HASHCASH_PREFIX):].strip()
    bits, challenge = bits_challenge_etc.split()[0].split(',', 1)
    return '%s##%s' % (rcpt, Sha512Collide(challenge, int(bits),
                                           callback100k=callback100k))


def _AddSocksHooks(cls, SSL=False):

    class Socksified(cls):
        def _get_socket(self, host, port, timeout):
            new_socket = self.socket()
            new_socket.connect((host, port))

            if SSL and ssl is not None:
                new_socket = ssl.wrap_socket(new_socket,
                                             self.keyfile, self.certfile)
                self.file = smtplib.SSLFakeFile(new_socket)

            return new_socket

        def connect(self, host='localhost', port=0, socket_cls=None):
            self.socket = socket_cls or socket.socket
            return cls.connect(self, host=host, port=port)

    return Socksified


class SMTP(_AddSocksHooks(smtplib.SMTP)):
    pass

if ssl is not None:
    class SMTP_SSL(_AddSocksHooks(smtplib.SMTP_SSL, SSL=True)):
        pass
else:
    SMTP_SSL = SMTP


class SendMailError(IOError):
    pass


def _RouteTuples(session, from_to_msg_ev_tuples):
    tuples = []
    for frm, to, msg, events in from_to_msg_ev_tuples:
        dest = {}
        for recipient in to:
            # If any of the events thinks this message has been delivered,
            # then don't try to send it again.
            frm_to = '>'.join([frm, recipient])
            for ev in (events or []):
                if ev.private_data.get(frm_to, False):
                    recipient = None
                    break
            if recipient:
                route = {"protocol": "",
                         "username": "",
                         "password": "",
                         "command": "",
                         "host": "",
                         "port": 25
                         }
                route.update(session.config.get_sendmail(frm, [recipient]))
                if route["command"]:
                    txtroute = "|%(command)s" % route
                else:
                    txtroute = "%(protocol)s://%(username)s:%(password)s@" \
                               + "%(host)s:%(port)d"
                    txtroute %= route

                dest[txtroute] = dest.get(txtroute, [])
                dest[txtroute].append(recipient)
        for route in dest:
            tuples.append((frm, route, dest[route], msg, events))
    return tuples


def SendMail(session, msg_mid, from_to_msg_ev_tuples):
    routes = _RouteTuples(session, from_to_msg_ev_tuples)

    # Randomize order of routes, so we don't always try the broken
    # one first. Any failure will bail out, but we do keep track of
    # our successes via. the event, so eventually everything sendable
    # should get sent.
    routes.sort(key=lambda k: random.randint(0, 10))

    # Update initial event state before we go through and start
    # trying to deliver stuff.
    for frm, sendmail, to, msg, events in routes:
        for ev in (events or []):
            for rcpt in to:
                ev.private_data['>'.join([frm, rcpt])] = False

    for frm, sendmail, to, msg, events in routes:
        for ev in events:
            ev.data['recipients'] = len(ev.private_data.keys())
            ev.data['delivered'] = len([k for k in ev.private_data
                                        if ev.private_data[k]])

    def mark(msg, events, log=True):
        for ev in events:
            ev.flags = Event.RUNNING
            ev.message = msg
            if log:
                session.config.event_log.log_event(ev)
        session.ui.mark(msg)

    def fail(msg, events):
        mark(msg, events, log=True)
        for ev in events:
            ev.data['last_error'] = msg
        raise SendMailError(msg)

    def smtp_do_or_die(msg, events, method, *args, **kwargs):
        rc, msg = method(*args, **kwargs)
        if rc != 250:
           fail(msg + ' (%s %s)' % (rc, msg), events)

    # Do the actual delivering...
    for frm, sendmail, to, msg, events in routes:
        frm_vcard = session.config.vcards.get_vcard(frm)

        if 'sendmail' in session.config.sys.debug:
            sys.stderr.write(_('SendMail: from %s (%s), to %s via %s\n'
                               ) % (frm,
                                    frm_vcard and frm_vcard.random_uid or '',
                                    to, sendmail.split('@')[-1]))
        sm_write = sm_close = lambda: True

        mark(_('Connecting to %s') % sendmail.split('@')[-1], events)

        if sendmail.startswith('|'):
            sendmail %= {"rcpt": ",".join(to)}
            cmd = sendmail[1:].strip().split()
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            sm_startup = None
            sm_write = proc.stdin.write
            def sm_close():
                proc.stdin.close()
                rv = proc.wait()
                if rv != 0:
                    fail(_('%s failed with exit code %d') % (cmd, rv), events)
            sm_cleanup = lambda: [proc.stdin.close(), proc.wait()]
            # FIXME: Update session UI with progress info
            for ev in events:
                ev.data['proto'] = 'subprocess'
                ev.data['command'] = cmd[0]

        elif (sendmail.startswith('smtp:') or
              sendmail.startswith('smtorp:') or
              sendmail.startswith('smtpssl:') or
              sendmail.startswith('smtptls:')):
            proto = sendmail.split(':', 1)[0]
            host, port = sendmail.split(':', 1
                                        )[1].replace('/', '').rsplit(':', 1)
            smtp_ssl = proto in ('smtpssl', )  # FIXME: 'smtorp'
            if '@' in host:
                userpass, host = host.rsplit('@', 1)
                user, pwd = userpass.split(':', 1)
            else:
                user = pwd = None

            for ev in events:
                ev.data['proto'] = proto
                ev.data['host'] = host
                ev.data['auth'] = bool(user and pwd)

            if 'sendmail' in session.config.sys.debug:
                sys.stderr.write(_('SMTP connection to: %s:%s as %s\n'
                                   ) % (host, port, user or '(anon)'))

            server = (smtp_ssl and SMTP_SSL or SMTP
                      )(local_hostname='mailpile.local', timeout=25)
            def sm_startup():
                if 'sendmail' in session.config.sys.debug:
                    server.set_debuglevel(1)
                if proto == 'smtorp':
                    server.connect(host, int(port),
                                   socket_cls=session.config.get_tor_socket())
                else:
                    server.connect(host, int(port))
                if not smtp_ssl:
                    # We always try to enable TLS, even if the user just requested
                    # plain-text smtp.  But we only throw errors if the user asked
                    # for encryption.
                    try:
                        server.starttls()
                    except:
                        if sendmail.startswith('smtptls'):
                            raise InsecureSmtpError()
                if user and pwd:
                    try:
                        server.login(user, pwd)
                    except smtplib.SMTPAuthenticationError:
                        fail(_('Invalid username or password'), events)

                smtp_do_or_die(_('Sender rejected by SMTP server'),
                               events, server.mail, frm)
                for rcpt in to:
                    rc, msg = server.rcpt(rcpt)
                    if (rc == SMTORP_HASHCASH_RCODE and
                            msg.startswith(SMTORP_HASHCASH_PREFIX)):
                        rc, msg = server.rcpt(SMTorP_HashCash(rcpt, msg))
                    if rc != 250:
                        fail(_('Server rejected recpient: %s') % rcpt, events)
                rcode, rmsg = server.docmd('DATA')
                if rcode != 354:
                    fail(_('Server rejected DATA: %s %s') % (rcode, rmsg))

            def sm_write(data):
                for line in data.splitlines(True):
                    if line.startswith('.'):
                        server.send('.')
                    server.send(line)

            def sm_close():
                server.send('\r\n.\r\n')
                smtp_do_or_die(_('Error spooling mail'),
                               events, server.getreply)

            def sm_cleanup():
                if hasattr(server, 'sock'):
                    server.close()
        else:
            fail(_('Invalid sendmail command/SMTP server: %s') % sendmail)

        try:
            # Run the entire connect/login sequence in a single timer...
            if sm_startup:
                RunTimed(30, sm_startup)

            mark(_('Preparing message...'), events)
            msg_string = MessageAsString(CleanMessage(session.config, msg))
            total = len(msg_string)
            while msg_string:
                if mailpile.util.QUITTING:
                    raise TimedOut(_('Quitting'))
                mark(('Sending message... (%d%%)'
                      ) % (100 * (total-len(msg_string))/total), events,
                     log=False)
                RunTimed(20, sm_write, msg_string[:20480])
                msg_string = msg_string[20480:]
            RunTimed(10, sm_close)

            mark(_n('Message sent, %d byte',
                    'Message sent, %d bytes',
                    total
                    ) % total, events)
            for ev in events:
                for rcpt in to:
                    vcard = session.config.vcards.get_vcard(rcpt)
                    if vcard:
                        vcard.record_history('send', time.time(), msg_mid)
                        if frm_vcard and vcard.sending_profile(rcpt)[0]:
                            vcard.prefer_sender(rcpt, frm_vcard)
                        vcard.save()
                    ev.private_data['>'.join([frm, rcpt])] = True
                ev.data['bytes'] = total
                ev.data['delivered'] = len([k for k in ev.private_data
                                            if ev.private_data[k]])
        finally:
            sm_cleanup()
