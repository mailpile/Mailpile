import random
import hashlib
import smtplib
import socket
import ssl
import sys
import time

import mailpile.util
from mailpile.auth import IndirectPassword
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.config.detect import ssl, socks
from mailpile.mailutils import CleanMessage, MessageAsString
from mailpile.mailutils import InsecureSmtpError
from mailpile.safe_popen import Popen, PIPE
from mailpile.util import *
from mailpile.vcard import VCardLine


def sha512_512k(data):
    #
    # This abuse of sha512 forces it to work with at least 512kB of data,
    # no matter what it started with. On each iteration, we add one
    # hexdigest to the front of the string (to prevent reuse of state).
    # Each hexdigest is 128 bytes, so that gives:
    #
    # Total == 128 * (0 + 1 + 2 + ... + 90) + 128 == 128 * 4096 == 524288
    #
    # Max memory use is sadly only 10KB or so - hardly memory-hard. :-)
    # Oh well!  I'm no cryptographer, and yes, we should probably just
    # be using scrypt.
    #
    sha512 = hashlib.sha512
    for i in range(0, 91):
        data = sha512(data).hexdigest() + data
    return sha512(data).hexdigest()


def sha512_512kCheck(challenge, bits, solution):
    hexchars = bits // 4
    wanted = '0' * hexchars
    digest = sha512_512k('-'.join([solution, challenge]))
    return (digest[:hexchars] == wanted)


def sha512_512kCollide(challenge, bits, callback1k=None):
    hexchars = bits // 4
    wanted = '0' * hexchars
    for i in xrange(1, 0x10000):
        if callback1k is not None:
            callback1k(i)
        challenge_i = '-'.join([str(i), challenge])
        for j in xrange(0, 1024):
            collision = '-'.join([str(j), challenge_i])
            if sha512_512k(collision)[:hexchars] == wanted:
                return '-'.join(collision.split('-')[:2])
    return None


SMTORP_HASHCASH_RCODE = 450
SMTORP_HASHCASH_PREFIX = 'Please collide'
SMTORP_HASHCASH_FORMAT = (SMTORP_HASHCASH_PREFIX +
                          ' %(bits)d,%(challenge)s or retry. See: %(url)s')


def SMTorP_HashCash(rcpt, msg, callback1k=None):
    bits_challenge_etc = msg[len(SMTORP_HASHCASH_PREFIX):].strip()
    bits, challenge = bits_challenge_etc.split()[0].split(',', 1)

    def cb(*args, **kwargs):
        play_nice_with_threads()
        if callback1k:
            callback1k(*args, **kwargs)

    return '%s##%s' % (rcpt, sha512_512kCollide(challenge, int(bits),
                                                callback1k=cb))


class SMTP(smtplib.SMTP):
    pass

if ssl is not None:
    class SMTP_SSL(smtplib.SMTP_SSL):
        pass
else:
    SMTP_SSL = SMTP


class SendMailError(IOError):
    def __init__(self, msg, details=None):
        IOError.__init__(self, msg)
        self.error_info = details or {}


def _RouteTuples(session, from_to_msg_ev_tuples, test_route=None):
    tuples = []
    for frm, to, msg, events in from_to_msg_ev_tuples:
        rcpts = {}
        routes = {}
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
                         "auth_type": "",
                         "command": "",
                         "host": "",
                         "port": 25}

                if test_route:
                    route.update(test_route)
                else:
                    route.update(session.config.get_route(frm, [recipient]))

                # Group together recipients that use the same route
                rid = '/'.join(sorted(['%s' % (k, )
                                       for k in route.iteritems()]))
                routes[rid] = route
                rcpts[rid] = rcpts.get(rid, [])
                rcpts[rid].append(recipient)
        for rid in rcpts:
            tuples.append((frm, routes[rid], rcpts[rid], msg, events))
    return tuples


def SendMail(session, msg_mid, from_to_msg_ev_tuples,
             test_only=False, test_route=None):
    routes = _RouteTuples(session, from_to_msg_ev_tuples,
                          test_route=test_route)

    # Randomize order of routes, so we don't always try the broken
    # one first. Any failure will bail out, but we do keep track of
    # our successes via. the event, so eventually everything sendable
    # should get sent.
    routes.sort(key=lambda k: random.randint(0, 10))

    # Update initial event state before we go through and start
    # trying to deliver stuff.
    for frm, route, to, msg, events in routes:
        for ev in (events or []):
            for rcpt in to:
                ev.private_data['>'.join([frm, rcpt])] = False

    for frm, route, to, msg, events in routes:
        for ev in events:
            ev.data['recipients'] = len(ev.private_data.keys())
            ev.data['delivered'] = len([k for k in ev.private_data
                                        if ev.private_data[k]])

    def mark(msg, events, log=True, clear_errors=False):
        for ev in events:
            ev.flags = Event.RUNNING
            ev.message = msg
            if clear_errors:
                if 'last_error' in ev.data:
                    del ev.data['last_error']
                if 'last_error_details' in ev.data:
                    del ev.data['last_error_details']
            if log:
                session.config.event_log.log_event(ev)
        session.ui.mark(msg)

    def fail(msg, events, details=None, exception=SendMailError):
        mark(msg, events, log=True)
        for ev in events:
            ev.data['last_error'] = msg
            if details:
                ev.data['last_error_details'] = details
        raise exception(msg, details=details)

    def smtp_do_or_die(msg, events, method, *args, **kwargs):
        rc, msg = method(*args, **kwargs)
        if rc != 250:
            fail(msg + ' (%s %s)' % (rc, msg), events,
                 details={'smtp_error': '%s: %s' % (rc, msg)})

    # Do the actual delivering...
    for frm, route, to, msg, events in routes:
        route_description = route['command'] or route['host']

        frm_vcard = session.config.vcards.get_vcard(frm)
        update_to_vcards = msg and msg["x-mp-internal-pubkeys-attached"]

        if 'sendmail' in session.config.sys.debug:
            sys.stderr.write(_('SendMail: from %s (%s), to %s via %s\n')
                             % (frm, frm_vcard and frm_vcard.random_uid or '',
                                to, route_description))
        sm_write = sm_close = lambda: True

        mark(_('Sending via %s') % route_description, events, clear_errors=True)

        if route['command']:
            # Note: The .strip().split() here converts our cmd into a list,
            #       which should ensure that Popen does not spawn a shell
            #       with potentially exploitable arguments.
            cmd = (route['command'] % {"rcpt": ",".join(to)}).strip().split()
            proc = Popen(cmd, stdin=PIPE, long_running=True)
            sm_startup = None
            sm_write = proc.stdin.write

            def sm_close():
                proc.stdin.close()
                rv = proc.wait()
                if rv != 0:
                    fail(_('%s failed with exit code %d') % (cmd, rv), events,
                         details={'failed_command': cmd,
                                  'exit_code': rv})

            sm_cleanup = lambda: [proc.stdin.close(), proc.wait()]
            # FIXME: Update session UI with progress info
            for ev in events:
                ev.data['proto'] = 'subprocess'
                ev.data['command'] = cmd[0]

        elif route['protocol'] in ('smtp', 'smtorp', 'smtpssl', 'smtptls'):
            proto = route['protocol']
            host, port = route['host'], route['port']
            user = route['username']
            pwd = IndirectPassword(session.config, route['password'])
            auth_type = route['auth_type'] or ''
            smtp_ssl = proto in ('smtpssl', )  # FIXME: 'smtorp'

            for ev in events:
                ev.data['proto'] = proto
                ev.data['host'] = host
                ev.data['auth'] = bool(user and pwd)

            if 'sendmail' in session.config.sys.debug:
                sys.stderr.write(_('SMTP connection to: %s:%s as %s\n'
                                   ) % (host, port, user or '(anon)'))

            serverbox = [None]
            def sm_connect_server():
                server = (smtp_ssl and SMTP_SSL or SMTP
                          )(local_hostname='mailpile.local', timeout=25)
                if 'sendmail' in session.config.sys.debug:
                    server.set_debuglevel(1)
                if smtp_ssl or proto in ('smtorp', 'smtptls'):
                    conn_needs = [ConnBroker.OUTGOING_ENCRYPTED]
                else:
                    conn_needs = [ConnBroker.OUTGOING_SMTP]
                try:
                    with ConnBroker.context(need=conn_needs) as ctx:
                        server.connect(host, int(port))
                    server.ehlo_or_helo_if_needed()
                except (IOError, OSError, smtplib.SMTPServerDisconnected):
                    fail(_('Failed to connect to %s') % host, events,
                         details={'connection_error': True})

                return server

            def sm_startup():
                try:
                    server = sm_connect_server()
                    if not smtp_ssl:
                        # We always try to enable TLS, even if the user just
                        # requested plain-text smtp.  But we only throw errors
                        # if the user asked for encryption.
                        try:
                            server.starttls()
                            server.ehlo_or_helo_if_needed()
                        except:
                            if proto == 'smtptls':
                                raise
                            else:
                                server = sm_connect_server()
                except (ssl.CertificateError, ssl.SSLError):
                    fail(_('Failed to make a secure TLS connection'),
                         events,
                         details={
                             'tls_error': True,
                             'server': '%s:%d' % (host, port)},
                         exception=InsecureSmtpError)

                serverbox[0] = server

                if user:
                    try:
                        if auth_type.lower() == 'oauth2':
                            from mailpile.plugins.oauth import OAuth2
                            tok_info = OAuth2.GetFreshTokenInfo(session, user)
                            if not (user and tok_info and tok_info.access_token):
                                fail(_('Access denied by mail server'),
                                     events,
                                     details={'oauth_error': True,
                                              'username': user})
                            authstr = (OAuth2.XOAuth2Response(user, tok_info)
                                       ).encode('base64').replace('\n', '')
                            server.docmd('AUTH', 'XOAUTH2 ' + authstr)
                        else:
                            server.login(user.encode('utf-8'),
                                         (pwd or '').encode('utf-8'))
                    except UnicodeDecodeError:
                        fail(_('Bad character in username or password'),
                             events,
                             details={'authentication_error': True,
                                      'username': user})
                    except smtplib.SMTPAuthenticationError:
                        fail(_('Invalid username or password'), events,
                             details={'authentication_error': True,
                                      'username': user})
                    except smtplib.SMTPException:
                        # If the server does not support authentication, assume
                        # it's passwordless and try to carry one anyway.
                        pass

                smtp_do_or_die(_('Sender rejected by SMTP server'),
                               events, server.mail, frm)
                for rcpt in to:
                    rc, msg = server.rcpt(rcpt)
                    if (rc == SMTORP_HASHCASH_RCODE and
                            msg.startswith(SMTORP_HASHCASH_PREFIX)):
                        rc, msg = server.rcpt(SMTorP_HashCash(rcpt, msg))
                    if rc != 250:
                        fail(_('Server rejected recipient: %s') % rcpt, events)
                rcode, rmsg = server.docmd('DATA')
                if rcode != 354:
                    fail(_('Server rejected DATA: %s %s') % (rcode, rmsg))

            def sm_write(data):
                server = serverbox[0]
                for line in data.splitlines(True):
                    if line.startswith('.'):
                        server.send('.')
                    server.send(line)

            def sm_close():
                server = serverbox[0]
                server.send('\r\n.\r\n')
                smtp_do_or_die(_('Error spooling mail'),
                               events, server.getreply)

            def sm_cleanup():
                server = serverbox[0]
                if hasattr(server, 'sock'):
                    server.close()
        else:
            fail(_('Invalid route: %s') % route, events)

        try:
            # Run the entire connect/login sequence in a single timer, but
            # give it plenty of time in case the network is lame.
            if sm_startup:
                RunTimed(300, sm_startup)

            if test_only:
                return True

            mark(_('Preparing message...'), events)

            msg_string = MessageAsString(CleanMessage(session.config, msg))
            total = len(msg_string)
            while msg_string:
                if mailpile.util.QUITTING:
                    raise TimedOut(_('Quitting'))
                mark(('Sending message... (%d%%)'
                      ) % (100 * (total-len(msg_string))/total), events,
                     log=False)
                RunTimed(120, sm_write, msg_string[:20480])
                msg_string = msg_string[20480:]
            RunTimed(30, sm_close)

            mark(_n('Message sent, %d byte',
                    'Message sent, %d bytes',
                    total
                    ) % total, events)

            for ev in events:
                for rcpt in to:
                    vcard = session.config.vcards.get_vcard(rcpt)
                    if vcard:
                        vcard.record_history('send', time.time(), msg_mid)
                        if frm_vcard:
                            vcard.prefer_sender(rcpt, frm_vcard)
                        if update_to_vcards:
                            vcard.pgp_key_shared = int(time.time())
                        vcard.save()
                    ev.private_data['>'.join([frm, rcpt])] = True
                ev.data['bytes'] = total
                ev.data['delivered'] = len([k for k in ev.private_data
                                            if ev.private_data[k]])
        finally:
            sm_cleanup()
    return True
