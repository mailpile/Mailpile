import smtplib
import socket
import subprocess
import sys

from mailpile.config import ssl, socks
from mailpile.mailutils import CleanMessage, MessageAsString


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


def _RouteTuples(session, from_to_msg_tuples):
    tuples = []
    for frm, to, msg in from_to_msg_tuples:
        dest = {}
        for recipient in to:
            route = session.config.get_sendmail(frm, [recipient]).strip()
            dest[route] = dest.get(route, [])
            dest[route].append(recipient)
        for route in dest:
            tuples.append((frm, route, dest[route], msg))
    return tuples


def SendMail(session, from_to_msg_tuples):

    # FIXME: We need to handle the case where we are retrying a message
    #        that we could not deliver before. Some of the tuples may
    # have been delivered already, and some not.  #eventlog

    for frm, sendmail, to, msg in _RouteTuples(session, from_to_msg_tuples):
        if 'sendmail' in session.config.sys.debug:
            sys.stderr.write(_('SendMail: from %s, to %s via %s\n'
                               ) % (frm, to, sendmail))
        sm_write = sm_close = lambda: True
        session.ui.mark(_('Connecting to %s') % sendmail)

        if sendmail.startswith('|'):
            cmd = sendmail[1:].strip().split()
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            sm_write = proc.stdin.write
            sm_close = proc.stdin.close
            sm_cleanup = lambda: proc.wait()
            # FIXME: Update session UI with progress info

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

        session.ui.mark(_('Preparing message...'))
        msg_string = MessageAsString(CleanMessage(session.config, msg))
        total = len(msg_string)
        while msg_string:
            sm_write(msg_string[:20480])
            msg_string = msg_string[20480:]
            session.ui.mark(('Sending message... (%d%%)'
                             ) % (100 * (total-len(msg_string))/total))
        sm_close()
        sm_cleanup()
        session.ui.mark(_('Message sent, %d bytes') % total)
