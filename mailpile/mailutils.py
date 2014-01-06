#
## Dear hackers!
##
## It would be great to have more mailbox classes.  They should be derived
## from or implement the same interfaces as Python's native mailboxes, with
## the additional constraint that they support pickling and unpickling using
## cPickle.  The mailbox class is also responsible for generating and parsing
## a "pointer" which should be a short as possible while still encoding the
## info required to locate this message and this message only within the
## larger mailbox.
#
###############################################################################
import copy
import email.header
import email.parser
import email.utils
import errno
import gzip
import mailbox
import mimetypes
import os
import re
import rfc822
import StringIO
import threading
import traceback
from gettext import gettext as _
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from lxml.html.clean import Cleaner
from mailpile.mailboxes.imap import IMAPMailbox
from mailpile.mailboxes.macmail import MacMaildir
from mailpile.util import *
from platform import system
from smtplib import SMTP, SMTP_SSL
from urllib import quote, unquote

from mailpile.gpgi import PGPMimeParser, GnuPG
from mailpile.gpgi import EncryptionInfo, SignatureInfo
from mailpile.mail_generator import Generator


MBX_ID_LEN = 4  # 4x36 == 1.6 million mailboxes


class NotEditableError(ValueError):
    pass

class NoFromAddressError(ValueError):
    pass

class NoRecipientError(ValueError):
    pass

class InsecureSmtpError(ValueError):
    pass

class NoSuchMailboxError(OSError):
    pass


def ParseMessage(fd, pgpmime=True):
    pos = fd.tell()
    header = [fd.readline()]
    while header[-1] not in ('', '\n', '\r\n'):
        line = fd.readline()
        if line.startswith(' ') or line.startswith('\t'):
            header[-1] += line
        else:
            header.append(line)

    fd.seek(pos)
    if pgpmime:
        message = PGPMimeParser().parse(fd)
    else:
        message = email.parser.Parser().parse(fd)

    message.raw_header = header
    return message

def ExtractEmailAndName(string):
    email = (ExtractEmails(string) or [''])[0]
    name = (string.replace(email, '')
                   .replace('<>', '')
                   .replace('"', '')
                   .replace('(', '')
                   .replace(')', '')).strip()
    return email, (name or email)


def ExtractEmails(string):
    emails = []
    startcrap = re.compile('^[\'\"<(]')
    endcrap = re.compile('[\'\">);]$')
    string = string.replace('<', ' <').replace('(', ' (')
    for w in [sw.strip() for sw in re.compile('[,\s]+').split(string)]:
        if '@' in w:
          while startcrap.search(w):
              w = w[1:]
          while endcrap.search(w):
              w = w[:-1]
          # E-mail addresses are only allowed to contain ASCII
          # characters, so we just strip everything else away.
          emails.append(CleanText(w, banned=CleanText.WHITESPACE,
                                     replace='_').clean)
    return emails


def MessageAsString(part, unixfrom=False):
    buf = StringIO.StringIO()
    Generator(buf).flatten(part, unixfrom=unixfrom, linesep='\r\n')
    return buf.getvalue()


def PrepareMail(mailobj, sender=None, rcpts=None):
    if not sender or not rcpts:
        tree = mailobj.get_message_tree()
        sender = sender or tree['headers_lc']['from']
        if not rcpts:
            rcpts = ExtractEmails(tree['headers_lc'].get('to', ''))
            rcpts += ExtractEmails(tree['headers_lc'].get('cc', ''))
            rcpts += ExtractEmails(tree['headers_lc'].get('bcc', ''))
            if not rcpts:
                raise NoRecipientError()
            rcpts += [sender]

    # Cleanup...
    sender = ExtractEmails(sender)[0]
    rcpts, rr = [sender], rcpts
    for r in rr:
        for e in ExtractEmails(r):
            if e not in rcpts:
                rcpts.append(e)

    msg = copy.deepcopy(mailobj.get_msg())

    # Remove headers we don't want to expose
    for bcc in ('bcc', 'Bcc', 'BCc', 'BCC'):
        if bcc in msg:
            del msg[bcc]

    if 'date' not in msg:
        msg['Date'] = email.utils.formatdate()

    # Sign and encrypt
    signatureopt = bool(int(tree['headers_lc'].get('do_sign', 0)))
    encryptopt = bool(int(tree['headers_lc'].get('do_encrypt', 0)))
    gnupg = GnuPG()
    if signatureopt:
        signingstring = MessageAsString(msg)
        #signingstring = re.sub("[\r]{1}[\n]{0}", "\r\n", msg.get_payload()[0].as_string())
        # print ">>>%s<<<" % signingstring.replace("\r", "<CR>").replace("\n", "<LF>")

        signature = gnupg.sign(signingstring, fromkey=sender, armor=True)
        # TODO: Create attachment, attach signature.
        if signature[0] == 0:
            # sigblock = MIMEMultipart(_subtype="signed", protocol="application/pgp-signature")
            # sigblock.attach(msg)
            msg.set_type("multipart/signed")
            msg.set_param("micalg", "pgp-sha1") # need to find this!
            msg.set_param("protocol", "application/pgp-signature")
            sigblock = MIMEText(str(signature[1]), _charset=None)
            sigblock.set_type("application/pgp-signature")
            sigblock.set_param("name", "signature.asc")
            sigblock.add_header("Content-Description", "OpenPGP digital signature")
            sigblock.add_header("Content-Disposition", "attachment; filename=\"signature.asc\"")
            msg.attach(sigblock)
        else:
            # Raise stink about signing having failed.
            pass
        #print signature

    #if encryptopt:
    #    encrypt_to = tree['headers_lc'].get('encrypt_to')
    #    newmsg = gnupg.encrypt(msg.as_string(), encrypt_to)
    #    # TODO: Replace unencrypted message

    # When a mail has been signed or encrypted, it should be saved as such.

    del(msg["do_sign"])
    del(msg["do_encrypt"])
    del(msg["encrypt_to"])

    return (sender, set(rcpts), msg)


def SendMail(session, from_to_msg_tuples):
    for frm, to, msg in from_to_msg_tuples:
        if 'sendmail' in session.config.sys.debug:
            sys.stderr.write(_('SendMail: from %s, to %s\n') % (frm, to))
        sm_write = sm_close = lambda: True
        sendmail = session.config.get_sendmail(frm, to).strip()
        session.ui.mark(_('Connecting to %s') % sendmail)
        if sendmail.startswith('|'):
            cmd = sendmail[1:].strip().split()
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            sm_write = proc.stdin.write
            sm_close = proc.stdin.close
            sm_cleanup = lambda: proc.wait()
            # FIXME: Update session UI with progress info

        elif (sendmail.startswith('smtp:') or
              sendmail.startswith('smtpssl:') or
              sendmail.startswith('smtptls:')):
            host, port = sendmail.split(':', 1)[1].replace('/', '').rsplit(':', 1)
            smtp_ssl = sendmail.startswith('smtpssl')
            if '@' in host:
                userpass, host = host.rsplit('@', 1)
                user, pwd = userpass.split(':', 1)
            else:
                user = pwd = None

            if 'sendmail' in session.config.sys.debug:
                sys.stderr.write(_('SMTP connection to: %s:%s as %s@%s\n'
                                  ) % (host, port, user, pwd))

            server = smtp_ssl and SMTP_SSL() or SMTP()
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
            raise Exception(_('Invalid sendmail: %s') % sendmail)

        session.ui.mark(_('Preparing message...'))
        string = MessageAsString(msg)  #msg.as_string(False)
        total = len(string)
        while string:
            sm_write(string[:65536])
            string = string[65536:]
            session.ui.mark(('Sending message... (%d%%)'
                             ) % (100 * (total-len(string))/total))
        sm_close()
        sm_cleanup()
        session.ui.mark(_('Message sent, %d bytes') % total)


MUA_HEADERS = ('date', 'from', 'to', 'cc', 'subject', 'message-id', 'reply-to',
               'mime-version','content-disposition', 'content-type',
               'user-agent', 'list-id', 'list-subscribe', 'list-unsubscribe',
               'x-ms-tnef-correlator', 'x-ms-has-attach')
DULL_HEADERS = ('in-reply-to', 'references')
def HeaderPrint(message):
    """Generate a fingerprint from message headers which identifies the MUA."""
    headers = message.keys() #[x.split(':', 1)[0] for x in message.raw_header]

    while headers and headers[0].lower() not in MUA_HEADERS:
        headers.pop(0)
    while headers and headers[-1].lower() not in MUA_HEADERS:
        headers.pop(-1)
    headers = [h for h in headers if h.lower() not in DULL_HEADERS]

    return b64w(sha1b64('\n'.join(headers))).lower()


def IsMailbox(fn):
    for mbox_cls in (IncrementalIMAPMailbox,
                     IncrementalWinMaildir,
                     IncrementalMaildir,
                     IncrementalMacMaildir,
                     IncrementalGmvault):
        try:
            if mbox_cls.parse_path(fn):
                return True
        except:
            pass
    try:
        firstline = open(fn, 'r').readline()
        return firstline.startswith('From ')
    except:
        return False


def OpenMailbox(fn):
    for mbox_cls in (IncrementalIMAPMailbox,
                     IncrementalWinMaildir,
                     IncrementalMaildir,
                     IncrementalMacMaildir,
                     IncrementalGmvault):
        try:
            return mbox_cls(*mbox_cls.parse_path(fn))
        except:
            #traceback.print_exc()
            pass
    return IncrementalMbox(fn)


def UnorderedPicklable(parent, editable=False):
    """A factory for generating unordered, picklable mailbox classes."""

    class UnorderedPicklableMailbox(parent):
        def __init__(self, *args, **kwargs):
            parent.__init__(self, *args, **kwargs)
            self.editable = editable
            self._save_to = None
            self.parsed = {}

        def unparsed(self):
            return [i for i in self.keys() if i not in self.parsed]

        def mark_parsed(self, i):
            self.parsed[i] = True

        def __setstate__(self, data):
            self.__dict__.update(data)
            self._save_to = None
            self.update_toc()

        def __getstate__(self):
            odict = self.__dict__.copy()
            # Pickle can't handle function objects.
            del odict['_save_to']
            return odict

        def save(self, session=None, to=None, pickler=None):
            if to and pickler:
                self._save_to = (pickler, to)
            if self._save_to and len(self) > 0:
                pickler, fn = self._save_to
                if session:
                    session.ui.mark('Saving %s state to %s' % (self, fn))
                pickler(self, fn)

        def update_toc(self):
            self._refresh()

        def get_msg_ptr(self, mboxid, toc_id):
            return '%s%s' % (mboxid, quote(toc_id))

        def get_file_by_ptr(self, msg_ptr):
            return self.get_file(unquote(msg_ptr[MBX_ID_LEN:]))

        def get_msg_size(self, toc_id):
            fd = self.get_file(toc_id)
            fd.seek(0, 2)
            return fd.tell()

    return UnorderedPicklableMailbox


class IncrementalIMAPMailbox(UnorderedPicklable(IMAPMailbox)):
    @classmethod
    def parse_path(cls, path):
        if path.startswith("imap://"):
            url = path[7:]
            try:
                serverpart, mailbox = url.split("/")
            except ValueError:
                serverpart = url
                mailbox = None
            userpart, server = serverpart.split("@")
            user, password = userpart.split(":")
            # WARNING: Order must match IMAPMailbox.__init__(...)
            return (server, 993, user, password)
        raise ValueError('Not an IMAP url: %s' % path)

    def __getstate__(self):
        odict = self.__dict__.copy()
        # Pickle can't handle file and function objects.
        del odict['_mailbox']
        del odict['_save_to']
        return odict

    def get_msg_size(self, toc_id):
        # FIXME: We should make this less horrible.
        fd = self.get_file(toc_id)
        fd.seek(0, 2)
        return fd.tell()


class IncrementalMaildir(UnorderedPicklable(mailbox.Maildir, editable=True)):
    """A Maildir class that supports pickling and a few mailpile specifics."""
    supported_platform = None
    @classmethod
    def parse_path(cls, fn):
        if (((cls.supported_platform is None) or
             (cls.supported_platform in system().lower())) and
                os.path.isdir(fn) and
                os.path.exists(os.path.join(fn, 'cur'))):
            return (fn, )
        raise ValueError('Not a Maildir: %s' % fn)


class IncrementalWinMaildir(IncrementalMaildir):
    """A Maildir class for Windows (using ! instead of : in filenames)"""
    supported_platform = 'win'
    colon = '!'


class IncrementalMacMaildir(UnorderedPicklable(MacMaildir)):
    """A Mac Mail.app maildir class that supports pickling etc."""
    @classmethod
    def parse_path(cls, fn):
        if os.path.isdir(fn) and os.path.exists(os.path.join(fn, 'Info.plist')):
            return (fn, )
        raise ValueError('Not a Mac Mail.app Maildir: %s' % fn)


class IncrementalGmvault(IncrementalMaildir):
    """A Gmvault class that supports pickling and a few mailpile specifics."""

    @classmethod
    def parse_path(cls, fn):
        if os.path.isdir(fn) and os.path.exists(os.path.join(fn, 'db')):
            return (fn, )
        raise ValueError('Not a Gmvault: %s' % fn)

    def __init__(self, dirname, factory=rfc822.Message, create=True):
        IncrementalMaildir.__init__(self, dirname, factory, create)

        self._paths = { 'db': os.path.join(self._path, 'db') }
        self._toc_mtimes = { 'db': 0}

    def get_file(self, key):
        """Return a file-like representation or raise a KeyError."""
        fname = self._lookup(key)
        if fname.endswith('.gz'):
            f = gzip.open(os.path.join(self._path, fname), 'rb')
        else:
            f = open(os.path.join(self._path, fname), 'rb')
        return mailbox._ProxyFile(f)

    def _refresh(self):
        """Update table of contents mapping."""
        # Refresh toc
        self._toc = {}
        for path in self._paths:
            for dirpath, dirnames, filenames in os.walk(self._paths[path]):
                for filename in [f for f in filenames if f.endswith(".eml.gz") or f.endswith(".eml")]:
                    self._toc[filename] = os.path.join(dirpath, filename)


class IncrementalMbox(mailbox.mbox):
    """A mbox class that supports pickling and a few mailpile specifics."""

    def __init__(self, *args, **kwargs):
        mailbox.mbox.__init__(self, *args, **kwargs)
        self.editable = False
        self.last_parsed = -1  # Must be -1 or first message won't get parsed
        self._save_to = None
        self._lock = threading.Lock()

    def __getstate__(self):
        odict = self.__dict__.copy()
        # Pickle can't handle file objects.
        del odict['_file']
        del odict['_lock']
        del odict['_save_to']
        return odict

    def _get_fd(self):
        return open(self._path, 'rb+')

    def __setstate__(self, dict):
        self.__dict__.update(dict)
        self._lock = threading.Lock()
        self._lock.acquire()
        self._save_to = None
        try:
            try:
                if not os.path.exists(self._path):
                   raise NoSuchMailboxError(self._path)
                self._file = self._get_fd()
            except IOError, e:
                if e.errno == errno.ENOENT:
                    raise NoSuchMailboxError(self._path)
                elif e.errno == errno.EACCES:
                    self._file = self._get_fd()
                else:
                    raise
        finally:
            self._lock.release()
        self.update_toc()

    def unparsed(self):
        return range(self.last_parsed+1, len(self))

    def mark_parsed(self, i):
        self.last_parsed = i

    def update_toc(self):
        self._lock.acquire()
        try:
            # FIXME: Does this break on zero-length mailboxes?

            # Scan for incomplete entries in the toc, so they can get fixed.
            for i in sorted(self._toc.keys()):
                if i > 0 and self._toc[i][0] is None:
                    self._file_length = self._toc[i-1][0]
                    self._next_key = i-1
                    del self._toc[i-1]
                    del self._toc[i]
                    break
                elif self._toc[i][0] and not self._toc[i][1]:
                    self._file_length = self._toc[i][0]
                    self._next_key = i
                    del self._toc[i]
                    break

            fd = self._file
            self._file.seek(0, 2)
            if self._file_length == fd.tell():
                return

            fd.seek(self._toc[self._next_key-1][0])
            line = fd.readline()
            if not line.startswith('From '):
                raise IOError("Mailbox has been modified")

            fd.seek(self._file_length-len(os.linesep))
            start = None
            while True:
                line_pos = fd.tell()
                line = fd.readline()
                if line.startswith('From '):
                    if start:
                        self._toc[self._next_key] = (start, line_pos - len(os.linesep))
                        self._next_key += 1
                    start = line_pos
                elif line == '':
                    self._toc[self._next_key] = (start, line_pos)
                    self._next_key += 1
                    break
            self._file_length = fd.tell()
        finally:
            self._lock.release()
        self.save(None)

    def save(self, session=None, to=None, pickler=None):
        if to and pickler:
            self._save_to = (pickler, to)
        if self._save_to and len(self) > 0:
            self._lock.acquire()
            try:
                pickler, fn = self._save_to
                if session:
                    session.ui.mark('Saving %s state to %s' % (self, fn))
                pickler(self, fn)
            finally:
                self._lock.release()

    def get_msg_size(self, toc_id):
        return self._toc[toc_id][1] - self._toc[toc_id][0]

    def get_msg_cs(self, start, cs_size, max_length):
        self._lock.acquire()
        try:
            fd = self._file
            fd.seek(start, 0)
            firstKB = fd.read(min(cs_size, max_length))
            if firstKB == '':
                raise IOError(_('No data found'))
            return b64w(sha1b64(firstKB)[:4])
        finally:
            self._lock.release()

    def get_msg_cs1k(self, start, max_length):
        return self.get_msg_cs(start, 1024, max_length)

    def get_msg_cs80b(self, start, max_length):
        return self.get_msg_cs(start, 80, max_length)

    def get_msg_ptr(self, mboxid, toc_id):
        msg_start = self._toc[toc_id][0]
        msg_size = self.get_msg_size(toc_id)
        return '%s%s:%s:%s' % (mboxid,
                               b36(msg_start),
                               b36(msg_size),
                               self.get_msg_cs80b(msg_start, msg_size))

    def get_file_by_ptr(self, msg_ptr):
        parts = msg_ptr[MBX_ID_LEN:].split(':')
        start = int(parts[0], 36)
        length = int(parts[1], 36)

        # Make sure we can actually read the message
        cs80b = self.get_msg_cs80b(start, length)
        if len(parts) > 2:
            cs1k = self.get_msg_cs1k(start, length)
            cs = parts[2][:4]
            if (cs1k != cs and cs80b != cs):
                raise IOError(_('Message not found'))

        # We duplicate the file descriptor here, in case other threads are
        # accessing the same mailbox and moving it around, or in case we have
        # multiple PartialFile objects in flight at once.
        return mailbox._PartialFile(self._get_fd(), start, start + length)


class Email(object):
    """This is a lazy-loading object representing a single email."""

    def __init__(self, idx, msg_idx_pos):
        self.index = idx
        self.config = idx.config
        self.msg_idx_pos = msg_idx_pos
        self.msg_info = None
        self.msg_parsed = None

    def msg_mid(self):
        return b36(self.msg_idx_pos)

    @classmethod
    def encoded_hdr(self, msg, hdr, value=None):
        hdr_value = value or msg[hdr]
        try:
            hdr_value.encode('us-ascii')
        except:
            if hdr.lower() in ('from', 'to', 'cc', 'bcc'):
                addrs = []
                for addr in [a.strip() for a in hdr_value.split(',')]:
                    name, part = [], []
                    words = addr.split()
                    for w in words:
                        if w[0] == '<' or '@' in w:
                            part.append((w, 'us-ascii'))
                        else:
                            name.append(w)
                    if name:
                        name = ' '.join(name)
                        try:
                            part[0:0] = [(name.encode('us-ascii'), 'us-ascii')]
                        except:
                            part[0:0] = [(name, 'utf-8')]
                        addrs.append(email.header.make_header(part).encode())
                hdr_value = ', '.join(addrs)
            else:
              parts = [(hdr_value, 'utf-8')]
              hdr_value = email.header.make_header(parts).encode()
        return hdr_value

    @classmethod
    def Create(cls, idx, mbox_id, mbx,
               msg_to=None, msg_cc=None, msg_bcc=None, msg_from=None,
               msg_subject=None, msg_text=None, msg_references=None):
        msg = MIMEMultipart()
        msg_date = int(time.time())
        msg_from = msg_from or idx.config.get_profile().get('email', None)
        if not msg_from:
            raise NoFromAddressError()
        msg['From'] = cls.encoded_hdr(None, 'from', value=msg_from)
        msg['Date'] = email.utils.formatdate(msg_date)
        msg['Message-Id'] = email.utils.make_msgid('mailpile')
        msg_subj  = (msg_subject or 'New message')
        msg['Subject'] = cls.encoded_hdr(None, 'subject', value=msg_subj)
        if msg_to:
            msg['To'] = cls.encoded_hdr(None, 'to', value=', '.join(set(msg_to)))
        if msg_cc:
            msg['Cc'] = cls.encoded_hdr(None, 'cc', value=', '.join(set(msg_cc)))
        if msg_bcc:
            msg['Bcc'] = cls.encoded_hdr(None, 'bcc', value=', '.join(set(msg_bcc)))
        if msg_references:
            msg['In-Reply-To'] = msg_references[-1]
            msg['References'] = ', '.join(msg_references)
        if msg_text:
            try:
                msg_text.encode('us-ascii')
                charset = 'us-ascii'
            except:
                charset = 'utf-8'
            msg.attach(MIMEText(msg_text, _subtype='plain', _charset=charset))
        msg_key = mbx.add(msg)
        msg_to = []
        msg_ptr = mbx.get_msg_ptr(mbox_id, msg_key)
        msg_id = idx.get_msg_id(msg, msg_ptr)
        msg_idx, msg_info = idx.add_new_msg(msg_ptr,
                                            msg_id, msg_date, msg_from, msg_to,
                                            msg_subj, '', [])
        idx.set_conversation_ids(msg_info[idx.MSG_MID], msg)
        return cls(idx, msg_idx)

    def is_editable(self):
        return self.config.is_editable_message(self.get_msg_info())

    MIME_HEADERS = ('mime-version', 'content-type', 'content-disposition',
                    'content-transfer-encoding')
    UNEDITABLE_HEADERS = ('message-id', ) + MIME_HEADERS
    MANDATORY_HEADERS = ('From', 'To', 'Cc', 'Bcc', 'Subject')
    HEADER_ORDER = {
        'in-reply-to': -2,
        'references': -1,
        'date': 1,
        'from': 2,
        'subject': 3,
        'to': 4,
        'cc': 5,
        'bcc': 6,
    }
    def get_editing_strings(self, tree=None):
        tree = tree or self.get_message_tree()
        strings = {
            'from': '', 'to': '', 'cc': '', 'bcc': '', 'subject': '',
            'attachments': {}
        }
        header_lines = []
        body_lines = []

        # We care about header order and such things...
        hdrs = dict([(h.lower(), h) for h in tree['headers'].keys()
                                    if h.lower() not in self.UNEDITABLE_HEADERS])
        for mandate in self.MANDATORY_HEADERS:
            hdrs[mandate.lower()] = hdrs.get(mandate.lower(), mandate)
        keys = hdrs.keys()
        keys.sort(key=lambda k: (self.HEADER_ORDER.get(k, 99), k))
        lowman = [m.lower() for m in self.MANDATORY_HEADERS]
        for hdr in [hdrs[k] for k in keys]:
            data = tree['headers'].get(hdr, '')
            if hdr.lower() in lowman:
                strings[hdr.lower()] = data
            else:
                header_lines.append('%s: %s' % (hdr, data))

        for att in tree['attachments']:
            strings['attachments'][att['count']] = att['filename'] or '(unnamed)'

        # FIXME: Add pseudo-headers for GPG stuff?

        strings['headers'] = '\n'.join(header_lines)
        strings['body'] = '\n'.join([t['data'].strip()
                                     for t in tree['text_parts']])
        return strings

    def get_editing_string(self, tree):
        estrings = self.get_editing_strings(tree)
        bits = [estrings['headers']]
        for mh in self.MANDATORY_HEADERS:
            bits.append('%s: %s' % (mh, estrings[mh.lower()]))
        bits.append('')
        bits.append(estrings['body'])
        return '\n'.join(bits)

    def make_attachment(self, fn, filedata=None):
        if filedata and fn in filedata:
            data = filedata[fn]
        else:
            data = open(fn, 'rb').read()
        ctype, encoding = mimetypes.guess_type(fn)
        maintype, subtype = (ctype or 'application/octet-stream').split('/', 1)
        if maintype == 'image':
            att = MIMEImage(data, _subtype=subtype)
        else:
            att = MIMEBase(maintype, subtype)
            att.set_payload(data)
            encoders.encode_base64(att)
        att.add_header('Content-Disposition', 'attachment',
                       filename=os.path.basename(fn))
        return att

    def add_attachments(self, filenames, filedata=None):
        if not self.is_editable():
            raise NotEditableError(_('Mailbox is read-only.'))
        msg = self.get_msg()
        for fn in filenames:
            msg.attach(self.make_attachment(fn, filedata=filedata))
        return self.update_from_msg(msg)

    def update_from_string(self, data):
        if not self.is_editable():
            raise NotEditableError(_('Mailbox is read-only.'))

        newmsg = email.parser.Parser().parsestr(data.encode('utf-8'))
        oldmsg = self.get_msg()
        outmsg = MIMEMultipart()

        # Copy over editable headers from the input string, skipping blanks
        for hdr in newmsg.keys():
            if hdr.startswith('Attachment-'):
                pass
            else:
                encoded_hdr = self.encoded_hdr(newmsg, hdr)
                if len(encoded_hdr.strip()) > 0:
                    outmsg[hdr] = encoded_hdr

        # Copy over the uneditable headers from the old message
        for hdr in oldmsg.keys():
            if ((hdr.lower() not in self.MIME_HEADERS)
            and (hdr.lower() in self.UNEDITABLE_HEADERS)):
                outmsg[hdr] = oldmsg[hdr]

        # Copy the message text
        new_body = newmsg.get_payload().decode('utf-8')
        try:
            new_body.encode('us-ascii')
            charset = 'us-ascii'
        except:
            charset = 'utf-8'
        outmsg.attach(MIMEText(new_body, _subtype='plain', _charset=charset))
        # FIXME: Use markdown and template to generate fancy HTML part

        # Copy the attachments we are keeping
        attachments = [h for h in newmsg.keys() if h.startswith('Attachment-')]
        if attachments:
            oldtree = self.get_message_tree()
            for att in oldtree['attachments']:
                hdr = 'Attachment-%s' % att['count']
                if hdr in attachments:
                    # FIXME: Update the filename to match whatever the user typed
                    outmsg.attach(att['part'])
                    attachments.remove(hdr)

        # Attach some new files?
        for hdr in attachments:
            try:
                outmsg.attach(self.make_attachment(newmsg[hdr]))
            except:
                pass # FIXME: Warn user that failed...

        # Save result back to mailbox
        return self.update_from_msg(outmsg)

    def update_from_msg(self, newmsg):
        if not self.is_editable():
            raise NotEditableError(_('Mailbox is read-only.'))

        mbx, ptr, fd = self.get_mbox_ptr_and_fd()
        mbx[ptr[MBX_ID_LEN:]] = newmsg

        # Update the in-memory-index with new sender, subject
        msg_info = self.index.get_msg_at_idx_pos(self.msg_idx_pos)
        msg_info[self.index.MSG_SUBJECT] = self.index.hdr(newmsg, 'subject')
        msg_info[self.index.MSG_FROM] = self.index.hdr(newmsg, 'from')
        self.index.set_msg_at_idx_pos(self.msg_idx_pos, msg_info)
        self.index.set_conversation_ids(msg_info[self.index.MSG_MID], newmsg)

        # FIXME: What to do about the search index?  Update?
        self.msg_parsed = None
        return self

    def get_msg_info(self, field=None):
        if not self.msg_info:
            self.msg_info = self.index.get_msg_at_idx_pos(self.msg_idx_pos)
        if field is None:
            return self.msg_info
        else:
            return self.msg_info[field]

    def get_mbox_ptr_and_fd(self):
        for msg_ptr in self.get_msg_info(self.index.MSG_PTRS).split(','):
            try:
                mbox = self.config.open_mailbox(None, msg_ptr[:MBX_ID_LEN])
                fd = mbox.get_file_by_ptr(msg_ptr)
                # FIXME: How do we know we have the right message?
                return mbox, msg_ptr, fd
            except (IOError, OSError):
                # FIXME: If this pointer is wrong, should we fix the index?
                print '%s not in %s' % (msg_ptr, self)
        return None, None, None

    def get_file(self):
        return self.get_mbox_ptr_and_fd()[2]

    def get_msg_size(self):
        mbox, ptr, fd = self.get_mbox_ptr_and_fd()
        fd.seek(0, 2)
        return fd.tell()

    def get_msg(self, pgpmime=True):
        if not self.msg_parsed:
            fd = self.get_file()
            if fd:
                self.msg_parsed = ParseMessage(fd, pgpmime=pgpmime)
        if not self.msg_parsed:
            IndexError(_('Message not found?'))
        return self.msg_parsed

    def get_headerprint(self):
        return HeaderPrint(self.get_msg())

    def is_thread(self):
        return ((self.get_msg_info(self.index.MSG_CONV_MID)) or
                (0 < len(self.get_msg_info(self.index.MSG_REPLIES))))

    def get(self, field, default=''):
        """Get one (or all) indexed fields for this mail."""
        field = field.lower()
        if field == 'subject':
            return self.get_msg_info(self.index.MSG_SUBJECT)
        elif field == 'from':
            return self.get_msg_info(self.index.MSG_FROM)
        else:
            raw = ' '.join(self.get_msg().get_all(field, default))
            return self.index.hdr(0, 0, value=raw) or raw

    def get_msg_summary(self):
        # We do this first to make sure self.msg_info is loaded
        msg_mid = self.get_msg_info(self.index.MSG_MID)
        return [
            msg_mid,
            self.get_msg_info(self.index.MSG_ID),
            self.get_msg_info(self.index.MSG_FROM),
            self.index.expand_to_list(self.msg_info),
            self.get_msg_info(self.index.MSG_SUBJECT),
            self.get_msg_info(self.index.MSG_SNIPPET),
            self.get_msg_info(self.index.MSG_DATE),
            self.get_msg_info(self.index.MSG_TAGS).split(','),
            self.is_editable()
        ]

    def extract_attachment(self, session, att_id, name_fmt=None, mode='download'):
        msg = self.get_msg()
        count = 0
        extracted = 0
        filename, attributes = '', {}
        for part in (msg.walk() if msg else []):
            mimetype = part.get_content_type()
            if mimetype.startswith('multipart/'):
                continue

            content_id = part.get('content-id', '')
            pfn = part.get_filename() or ''
            count += 1

            if (('*' == att_id)
            or  ('#%s' % count == att_id)
            or  ('part:%s' % count == att_id)
            or  (content_id == att_id)
            or  (mimetype == att_id)
            or  (pfn.lower().endswith('.%s' % att_id))
            or  (pfn == att_id)):

                payload = part.get_payload(None, True) or ''
                attributes = {
                    'msg_mid': self.msg_mid(),
                    'count': count,
                    'length': len(payload),
                    'content-id': content_id,
                    'filename': pfn,
                }
                if pfn:
                    if '.' in pfn:
                        pfn, attributes['att_ext'] = pfn.rsplit('.', 1)
                        attributes['att_ext'] = attributes['att_ext'].lower()
                    attributes['att_name'] = pfn
                if mimetype:
                    attributes['mimetype'] = mimetype

                filesize = len(payload)
                if mode.startswith('inline'):
                    attributes['data'] = payload
                    session.ui.notify(_('Extracted attachment %s') % att_id)
                elif mode.startswith('preview'):
                    attributes['thumb'] = True
                    attributes['mimetype'] = 'image/jpeg'
                    attributes['disposition'] = 'inline'
                    filename, fd = session.ui.open_for_data(name_fmt=name_fmt,
                                                            attributes=attributes)
                    if thumbnail(payload, fd, height=250):
                        session.ui.notify(_('Wrote preview to: %s') % filename)
                    else:
                        session.ui.notify(_('Failed to generate thumbnail'))
                    fd.close()
                else:
                    filename, fd = session.ui.open_for_data(name_fmt=name_fmt,
                                                            attributes=attributes)
                    fd.write(payload)
                    session.ui.notify(_('Wrote attachment to: %s') % filename)
                    fd.close()
                extracted += 1
        if 0 == extracted:
            session.ui.notify(_('No attachments found for: %s') % att_id)
            return None, None
        else:
            return filename, attributes

    def get_message_tags(self):
        tids = self.get_msg_info(self.index.MSG_TAGS).split(',')
        return [self.config.get_tag(t) for t in tids]

    def get_message_tree(self, want=None):
        msg = self.get_msg()
        tree = {
            'id': self.get_msg_info(self.index.MSG_ID)
        }

        for p in 'text_parts', 'html_parts', 'attachments':
            if want is None or p in want:
                tree[p] = []

        if want is None or 'summary' in want:
            tree['summary'] = self.get_msg_summary()

        if want is None or 'tags' in want:
            tree['tags'] = self.get_msg_info(self.index.MSG_TAGS).split(',')

        if want is None or 'conversation' in want:
            tree['conversation'] = {}
            conv_id = self.get_msg_info(self.index.MSG_CONV_MID)
            if conv_id:
                conv = Email(self.index, int(conv_id, 36))
                tree['conversation'] = convs = [conv.get_msg_summary()]
                for rid in conv.get_msg_info(self.index.MSG_REPLIES).split(','):
                    if rid:
                        convs.append(Email(self.index, int(rid, 36)).get_msg_summary())

        if (want is None or 'headers' in want
                         or 'editing_string' in want
                         or 'editing_strings' in want):
            tree['headers'] = {}
            for hdr in msg.keys():
                tree['headers'][hdr] = self.index.hdr(msg, hdr)

        if want is None or 'headers_lc' in want:
            tree['headers_lc'] = {}
            for hdr in msg.keys():
                tree['headers_lc'][hdr.lower()] = self.index.hdr(msg, hdr)

        if want is None or 'header_list' in want:
            tree['header_list'] = [(k, self.index.hdr(msg, k, value=v))
                                   for k, v in msg.items()]

        # FIXME: Decide if this is strict enough or too strict...?
        html_cleaner = Cleaner(page_structure=True, meta=True, links=True,
                               javascript=True, scripts=True, frames=True,
                               embedded=True, safe_attrs_only=True)

        # Note: count algorithm must match that used in extract_attachment above
        count = 0
        for part in msg.walk():
            mimetype = part.get_content_type()
            print "Walking mime %s" % mimetype
            if mimetype.startswith('multipart/') or mimetype == "application/pgp-encrypted":
                continue
            try:
                if mimetype == "application/octet-stream" and part.cryptedcontainer == True:
                    continue
            except:
                pass

            count += 1
            if (part.get('content-disposition', 'inline') == 'inline'
            and mimetype in ('text/plain', 'text/html')):
                payload, charset, encryption_info, signature_info = self.decode_payload(part)
                if (mimetype == 'text/html' or
                      '<html>' in payload or
                      '</body>' in payload):
                    if want is None or 'html_parts' in want:
                        tree['html_parts'].append({
                            'encryption_info': encryption_info,
                            'signature_info': signature_info,
                            'charset': charset,
                            'type': 'html',
                            'data': (payload.strip() and html_cleaner.clean_html(payload)) or ''
                        })
                    if tree['text_parts']:
                        # FIXME: What is going on here?  This seems bad and wrong.
                        tp0 = tree['text_parts'][0]
                        tp0["encryption_info"] = encryption_info
                        tp0["signature_info"] = signature_info
                elif want is None or 'text_parts' in want:
                    tree['text_parts'].extend(self.parse_text_part(payload, charset,
                                                                   encryption_info,
                                                                   signature_info))
            elif want is None or 'attachments' in want:
                tree['attachments'].append({
                    'mimetype': mimetype,
                    'count': count,
                    'part': part,
                    'length': len(part.get_payload(None, True) or ''),
                    'content-id': part.get('content-id', ''),
                    'filename': part.get_filename() or ''
                })

        if self.is_editable():
            if not want or 'editing_strings' in want:
                tree['editing_strings'] = self.get_editing_strings(tree)
            if not want or 'editing_string' in want:
                tree['editing_string'] = self.get_editing_string(tree)

        return tree

    def decode_payload(self, part):
        charset = part.get_charset() or 'utf-8'
        payload = part.get_payload(None, True) or ''
        try:
            payload = payload.decode(charset)
        except UnicodeDecodeError:
            try:
                payload = payload.decode('iso-8859-1')
                charset = 'iso-8859-1'
            except UnicodeDecodeError, e:
                print _('Decode failed: %s %s') % (charset, e)

        try:
            encryption_info = part.encryption_info
        except AttributeError:
            encryption_info = EncryptionInfo()

        try:
            signature_info = part.signature_info
        except AttributeError:
            signature_info = SignatureInfo()

        return payload, charset, encryption_info, signature_info

    def parse_text_part(self, data, charset, encryption_info, signature_info):
        current = {
            'type': 'bogus',
            'charset': charset,
            'encryption_info': encryption_info,
            'signature_info': signature_info,
        }
        parse = []
        block = 'body'
        for line in data.splitlines(True):
            block, ltype = self.parse_line_type(line, block)
            if ltype != current['type']:
                current = {
                    'type': ltype,
                    'data': '',
                    'charset': charset,
                    'encryption_info': encryption_info,
                    'signature_info': signature_info,
                }
                parse.append(current)
            current['data'] += line
        return parse

    def parse_line_type(self, line, block):
        # FIXME: Detect PGP blocks, forwarded messages, signatures, ...
        stripped = line.rstrip()

        if stripped == '-----BEGIN PGP SIGNED MESSAGE-----':
            return 'pgpbeginsigned', 'pgpbeginsigned'
        if block == 'pgpbeginsigned':
            if line.startswith('Hash: ') or stripped == '':
                return 'pgpbeginsigned', 'pgpbeginsigned'
            else:
                return 'pgpsignedtext', 'pgpsignedtext'
        if block == 'pgpsignedtext':
            if (stripped == '-----BEGIN PGP SIGNATURE-----'):
                return 'pgpsignature', 'pgpsignature'
            else:
                return 'pgpsignedtext', 'pgpsignedtext'
        if block == 'pgpsignature':
            if stripped == '-----END PGP SIGNATURE-----':
                return 'pgpend', 'pgpsignature'
            else:
                return 'pgpsignature', 'pgpsignature'

        if stripped == '-----BEGIN PGP MESSAGE-----':
            return 'pgpbegin', 'pgpbegin'
        if block == 'pgpbegin':
            if ':' in line or stripped == '':
                return 'pgpbegin', 'pgpbegin'
            else:
                return 'pgptext', 'pgptext'
        if block == 'pgptext':
            if stripped == '-----END PGP MESSAGE-----':
                return 'pgpend', 'pgpend'
            else:
                return 'pgptext', 'pgptext'

        if block == 'quote':
            if stripped == '':
                return 'quote', 'quote'
        if line.startswith('>') or stripped.endswith(' wrote:'):
            return 'quote', 'quote'

        return 'body', 'text'

    WANT_MSG_TREE_PGP = ('text_parts',)
    PGP_OK = {
      'pgpbeginsigned': 'pgpbeginverified',
      'pgpsignedtext': 'pgpverifiedtext',
      'pgpsignature': 'pgpverification',
      'pgpbegin': 'pgpbeginverified',
      'pgptext': 'pgpsecuretext',
      'pgpend': 'pgpverification',
    }
    def evaluate_pgp(self, tree, check_sigs=True, decrypt=False):
        if 'text_parts' not in tree:
            return tree

        pgpdata = []
        for part in tree['text_parts']:

            # Handle signed messages
            if 'signature_info' not in part:
                part['signature_info'] = SignatureInfo()

            if check_sigs:
                if part['type'] == 'pgpbeginsigned':
                    pgpdata = [part]
                elif part['type'] == 'pgpsignedtext':
                    pgpdata.append(part)
                elif part['type'] == 'pgpsignature':
                    pgpdata.append(part)
                    try:
                        gpg = GnuPG()
                        message = ''.join([p['data'].encode(p['charset']) for p in pgpdata])
                        pgpdata[1]['signature_info'] = gpg.verify(message)
                        pgpdata[0]['data'] = ''
                        pgpdata[2]['data'] = ''
                    except Exception, e:
                        print e

            if "encryption_info" not in part:
                part['encryption_info'] = EncryptionInfo()

            if decrypt:
                if part['type'] in ('pgpbegin', 'pgptext'):
                    pgpdata.append(part)
                elif part['type'] == 'pgpend':
                    pgpdata.append(part)
                    message = ''.join([p['data'] for p in pgpdata])
                    gpg = GnuPG()
                    encryption_info, text = gpg.decrypt(message)
                    pgpdata[1]['encryption_info'] = encryption_info
                    if encryption_info["status"] == "decrypted":
                        pgpdata[1]['data'] = text
                        pgpdata[0]['data'] = ""
                        pgpdata[2]['data'] = ""

        return tree

    def _decode_gpg(self, message, decrypted):
        header, body = message.replace('\r\n', '\n').split('\n\n', 1)
        for line in header.lower().split('\n'):
            if line.startswith('charset:'):
                return decrypted.decode(line.split()[1])
        return decrypted.decode('utf-8')

