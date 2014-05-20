import random
import smtplib
import socket
import subprocess
import sys

from mailpile.config import ssl, socks
from mailpile.mailutils import CleanMessage, MessageAsString
from mailpile.eventlog import Event


def _AddSocksHooks(cls, SSL=False):

    class Socksified(cls):
        def _get_socket(self, host, port, timeout):
            print ('Creating socket -> %s:%s/%s using %s, SSL=%s'
                   ) % (host, port, timeout, self.socket, SSL)

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


def SendMail(session, from_to_msg_ev_tuples):
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

    # Do the actual delivering...
    for frm, sendmail, to, msg, events in routes:

        if 'sendmail' in session.config.sys.debug:
            sys.stderr.write(_('SendMail: from %s, to %s via %s\n'
                               ) % (frm, to, sendmail))
        sm_write = sm_close = lambda: True
        mark(_('Connecting to %s') % sendmail, events)

        if sendmail.startswith('|'):
            sendmail %= {"rcpt": ",".join(to)}
            cmd = sendmail[1:].strip().split()
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            sm_write = proc.stdin.write
            sm_close = proc.stdin.close
            sm_cleanup = lambda: proc.wait()
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
                sys.stderr.write(_('SMTP connection to: %s:%s as %s@%s\n'
                                   ) % (host, port, user, pwd))

            server = smtp_ssl and SMTP_SSL() or SMTP()
            if proto == 'smtorp':
                server.connect(host, int(port),
                               socket_cls=session.config.get_tor_socket())
            else:
                server.connect(host, int(port))
            server.ehlo()
            if not smtp_ssl:
                # We always try to enable TLS, even if the user just requested
                # plain-text smtp.  But we only throw errors if the user asked
                # for encryption.
                try:
                    server.starttls()
                    server.ehlo()
                except:
                    if sendmail.startswith('smtptls'):
                        raise InsecureSmtpError()
            if user and pwd:
                server.login(user, pwd)

            server.mail(frm)
            for rcpt in to:
                server.rcpt(rcpt)
            server.docmd('DATA')

            def sender(data):
                for line in data.splitlines(1):
                    if line.startswith('.'):
                        server.send('.')
                    server.send(line)

            def closer():
                server.send('\r\n.\r\n')
                server.quit()

            sm_write = sender
            sm_close = closer
            sm_cleanup = lambda: True
        else:
            raise Exception(_('Invalid sendmail command/SMTP server: %s'
                              ) % sendmail)

        mark(_('Preparing message...'), events)
        msg_string = MessageAsString(CleanMessage(session.config, msg))
        total = len(msg_string)
        while msg_string:
            sm_write(msg_string[:20480])
            msg_string = msg_string[20480:]
            mark(('Sending message... (%d%%)'
                  ) % (100 * (total-len(msg_string))/total), events,
                 log=False)
        sm_close()
        sm_cleanup()
        for ev in events:
            for rcpt in to:
                ev.private_data['>'.join([frm, rcpt])] = True
            ev.data['bytes'] = total
            ev.data['delivered'] = len([k for k in ev.private_data
                                        if ev.private_data[k]])
        mark(_n('Message sent, %d byte',
                'Message sent, %d bytes',
                total
                ) % total, events)
