#!/usr/bin/env python2.7
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
import cPickle
import email.header
import email.parser
import email.utils
import errno
import mailbox
import mimetypes
import os
import traceback
import re
import rfc822
import gzip

from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from smtplib import SMTP, SMTP_SSL

from mailpile import imap_mailbox
from mailpile.util import *
from lxml.html.clean import Cleaner

try:
  from GnuPGInterface import GnuPG
  from mailpile.pgpmime import PGPMimeParser
except ImportError:
  GnuPG = PGPMimeParser = None


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
  if GnuPG and pgpmime:
    message = PGPMimeParser().parse(fd)
  else:
    message = email.parser.Parser().parse(fd)

  message.raw_header = header
  return message

def ExtractEmails(string):
  emails = []
  for w in [sw.strip() for sw in re.compile('[,\s]+').split(string)]:
    if '@' in w:
      if w.startswith('<'): w = w[1:]
      if w.endswith('>'): w = w[:-1]
      emails.append(w)
  return emails

def PrepareMail(email, sender=None, rcpts=None):
  if not sender or not rcpts:
    tree = email.get_message_tree()
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
  rcpts, rr = [], rcpts
  for r in rr:
    rcpts.extend(ExtractEmails(r))

  msg = email.get_msg()

  # Remove headers we don't want to expose
  for bcc in ('bcc', 'Bcc', 'BCc', 'BCC'):
    if bcc in msg:
      del msg['bcc']

  # FIXME: Sign, encrypt, ?

  return (sender, set(rcpts), msg)

def SendMail(session, from_to_msg_tuples):
  for frm, to, msg in from_to_msg_tuples:
    sm_write = sm_close = lambda: True
    sendmail = session.config.get_sendmail(frm, to).strip()
    session.ui.mark('Connecting to %s' % sendmail)
    if sendmail.startswith('|'):
      cmd = sendmail[1:].strip().split()
      proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
      sm_write = proc.stdin.write
      sm_close = proc.stdin.close
      # FIXME: Update session UI with progress info

    elif (sendmail.startswith('smtp:') or
          sendmail.startswith('smtpssl:') or
          sendmail.startswith('smtptls:')):
      host, port = sendmail.split(':', 1)[1].rsplit(':', 1)
      smtp_ssl = sendmail.startswith('smtpssl')
      if '@' in host:
        userpass, host = host.rsplit('@', 1)
        user, pwd = userpass.split(':', 1)
      else:
        user = pwd = None

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
    else:
      raise Exception('Invalid sendmail: %s' % sendmail)

    session.ui.mark('Preparing message...')
    string = str(msg)
    total = len(string)
    while string:
      sm_write(string[:65536])
      string = string[65536:]
      session.ui.mark(('Sending message... (%d%%)'
                       ) % (100 * (total-len(string))/total))
    sm_close()
    session.ui.mark('Message sent, %d bytes' % total)


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


def OpenMailbox(fn):
  if fn.startswith("imap://"):
    # FIXME(halldor): waaaayy too naive - expects imap://username:password@server/mailbox
    url = fn[7:]
    try:
      serverpart, mailbox = url.split("/")
    except ValueError:
      serverpart = url
      mailbox = None
    try:
      userpart, server = serverpart.split("@")
      user, password = userpart.split(":")
    except ValueError:
      raise

    return IncrementalIMAPMailbox(server, user=user, password=password, mailbox=mailbox)
  if os.path.isdir(fn) and os.path.exists(os.path.join(fn, 'cur')):
    return IncrementalMaildir(fn)
  elif os.path.isdir(fn) and os.path.exists(os.path.join(fn, 'db')):
    return IncrementalGmvault(fn)
  else:
    return IncrementalMbox(fn)

class IncrementalIMAPMailbox(imap_mailbox.IMAPMailbox):
  editable = True
  save_to = None
  parsed = {}

  def __setstate__(self, dict):
    self.__dict__.update(dict)
    self.update_toc()

  def __getstate__(self):
    odict = self.__dict__.copy()
    # Pickle can't handle file objects.
    del odict['_mailbox']
    return odict

  def save(self, session=None, to=None):
    if to:
      self.save_to = to
    if self.save_to and len(self) > 0:
      if session: session.ui.mark('Saving state to %s' % self.save_to)
      fd = open(self.save_to, 'w')
      cPickle.dump(self, fd)
      fd.close()

  def unparsed(self):
    return [i for i in self.keys() if i not in self.parsed]

  def mark_parsed(self, i):
    self.parsed[i] = True

  def update_toc(self):
    self._refresh()

  def get_msg_size(self, toc_id):
    fd = self.get_file(toc_id)
    fd.seek(0, 2)
    return fd.tell()

  def get_msg_ptr(self, idx, toc_id):
    return '%s%s' % (idx, toc_id)

  def get_file_by_ptr(self, msg_ptr):
    return self.get_file(msg_ptr[3:])

class IncrementalMaildir(mailbox.Maildir):
  """A Maildir class that supports pickling and a few mailpile specifics."""

  editable = True
  save_to = None
  parsed = {}

  def __setstate__(self, dict):
    self.__dict__.update(dict)
    self.update_toc()

  def save(self, session=None, to=None):
    if to:
      self.save_to = to
    if self.save_to and len(self) > 0:
      if session: session.ui.mark('Saving state to %s' % self.save_to)
      fd = open(self.save_to, 'w')
      cPickle.dump(self, fd)
      fd.close()

  def unparsed(self):
    return [i for i in self.keys() if i not in self.parsed]

  def mark_parsed(self, i):
    self.parsed[i] = True

  def update_toc(self):
    self._refresh()

  def get_msg_size(self, toc_id):
    fd = self.get_file(toc_id)
    fd.seek(0, 2)
    return fd.tell()

  def get_msg_ptr(self, idx, toc_id):
    return '%s%s' % (idx, toc_id)

  def get_file_by_ptr(self, msg_ptr):
    return self.get_file(msg_ptr[3:])

class IncrementalGmvault(IncrementalMaildir):
  """A Gmvault class that supports pickling and a few mailpile specifics."""

  editable = False

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

  editable = False
  last_parsed = 0
  save_to = None

  def __getstate__(self):
    odict = self.__dict__.copy()
    # Pickle can't handle file objects.
    del odict['_file']
    return odict

  def __setstate__(self, dict):
    self.__dict__.update(dict)
    try:
      if not os.path.exists(self._path):
        raise NoSuchMailboxError(self._path)
      self._file = open(self._path, 'rb+')
    except IOError, e:
      if e.errno == errno.ENOENT:
        raise NoSuchMailboxError(self._path)
      elif e.errno == errno.EACCES:
        self._file = open(self._path, 'rb')
      else:
        raise
    self.update_toc()

  def unparsed(self):
    return range(self.last_parsed+1, len(self))

  def mark_parsed(self, i):
    self.last_parsed = i

  def update_toc(self):
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

    self._file.seek(0, 2)
    if self._file_length == self._file.tell(): return

    self._file.seek(self._toc[self._next_key-1][0])
    line = self._file.readline()
    if not line.startswith('From '):
      raise IOError("Mailbox has been modified")

    self._file.seek(self._file_length-len(os.linesep))
    start = None
    while True:
      line_pos = self._file.tell()
      line = self._file.readline()
      if line.startswith('From '):
        if start:
          self._toc[self._next_key] = (start, line_pos - len(os.linesep))
          self._next_key += 1
        start = line_pos
      elif line == '':
        self._toc[self._next_key] = (start, line_pos)
        self._next_key += 1
        break
    self._file_length = self._file.tell()
    self.save(None)

  def save(self, session=None, to=None):
    if to:
      self.save_to = to
    if self.save_to and len(self) > 0:
      if session: session.ui.mark('Saving state to %s' % self.save_to)
      fd = open(self.save_to, 'w')
      cPickle.dump(self, fd)
      fd.close()

  def get_msg_size(self, toc_id):
    return self._toc[toc_id][1] - self._toc[toc_id][0]

  def get_msg_cs1k(self, start, max_length):
    self._file.seek(start, 0)
    firstKB = self._file.read(min(1024, max_length))
    if firstKB == '':
      raise IOError('No data found')
    return b64w(sha1b64(firstKB)[:4])

  def get_msg_ptr(self, idx, toc_id):
    msg_start = self._toc[toc_id][0]
    msg_size = self.get_msg_size(toc_id)
    return '%s%s:%s:%s' % (idx,
                           b36(msg_start),
                           b36(msg_size),
                           self.get_msg_cs1k(msg_start, msg_size))

  def get_file_by_ptr(self, msg_ptr):
    parts = msg_ptr[3:].split(':')
    start = int(parts[0], 36)
    length = int(parts[1], 36)

    # Make sure we can actually read the message
    cs1k = self.get_msg_cs1k(start, length)
    if len(parts) > 2 and cs1k != parts[2][:4]:
      raise IOError('Message not found')

    return mailbox._PartialFile(self._file, start, start+length)


class Email(object):
  """This is a lazy-loading object representing a single email."""

  def __init__(self, idx, msg_idx):
    self.index = idx
    self.config = idx.config
    self.msg_idx = msg_idx
    self.msg_info = None
    self.msg_parsed = None

  def msg_mid(self):
    return b36(self.msg_idx)

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
  def Create(cls, idx, mbx_id, mbx,
             msg_to=None, msg_cc=None, msg_bcc=None, msg_from=None,
             msg_subject=None, msg_text=None, msg_references=None):
    msg = MIMEMultipart()
    msg_date = int(time.time())
    msg_from = msg_from or idx.config.get_from_address()
    if not msg_from:
      raise NoFromAddressError()
    msg['From'] = cls.encoded_hdr(None, 'from', value=msg_from)
    msg['Date'] = email.utils.formatdate(msg_date)
    msg['Message-Id'] = msg_id = email.utils.make_msgid('mailpile')
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
    msg_idx, msg_info = idx.add_new_msg(mbx.get_msg_ptr(mbx_id, msg_key),
                                        msg_id,
                                        msg_date, msg_from, msg_subj, [])
    idx.set_conversation_ids(msg_info[idx.MSG_IDX], msg)
    return cls(idx, msg_idx)

  def is_editable(self):
    return self.config.is_editable_message(self.get_msg_info(self.index.MSG_PTRS))

  MIME_HEADERS = ('mime-version', 'content-type', 'content-disposition',
                  'content-transfer-encoding')
  UNEDITABLE_HEADERS = ('message-id', ) + MIME_HEADERS
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
  def get_editing_string(self, tree):
    lines = []

    # We care about header order and such things...
    hdrs = dict([(h.lower(), h) for h in tree['headers'].keys()
                                if h.lower() not in self.UNEDITABLE_HEADERS])
    hdrs['to'] = hdrs.get('to', 'To')
    hdrs['cc'] = hdrs.get('cc', 'Cc')
    hdrs['bcc'] = hdrs.get('bcc', 'Bcc')
    keys = hdrs.keys()
    keys.sort(key=lambda k: (self.HEADER_ORDER.get(k, 99), k))
    for hdr in [hdrs[k] for k in keys]:
      lines.append('%s: %s' % (hdr, tree['headers'].get(hdr, '')))

    for att in tree['attachments']:
      lines.append('Attachment-%s: %s' % (att['count'],
                                          att['filename'] or '(unnamed)'))

    # FIXME: Add pseudo-headers for GPG stuff?

    lines.append('')
    lines.extend([t['data'].strip() for t in tree['text_parts']])
    lines.append('\n')
    return '\n'.join(lines)

  def make_attachment(self, fn):
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

  def add_attachments(self, filenames):
    if not self.is_editable():
      raise NotEditableError('Mailbox is read-only.')
    msg = self.get_msg()
    for fn in filenames:
      msg.attach(self.make_attachment(fn))
    return self.update_from_msg(msg)

  def update_from_string(self, data):
    if not self.is_editable():
      raise NotEditableError('Mailbox is read-only.')

    newmsg = email.parser.Parser().parsestr(data)
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
      raise NotEditableError('Mailbox is read-only.')

    mbx, ptr, fd = self.get_mbox_ptr_and_fd()
    mbx[ptr[3:]] = newmsg

    # Update the in-memory-index with new sender, subject
    msg_info = self.index.get_msg_by_idx(self.msg_idx)
    msg_info[self.index.MSG_SUBJECT] = self.index.hdr(newmsg, 'subject')
    msg_info[self.index.MSG_FROM] = self.index.hdr(newmsg, 'from')
    self.index.set_msg_by_idx(self.msg_idx, msg_info)
    self.index.set_conversation_ids(msg_info[self.index.MSG_IDX], newmsg)

    # FIXME: What to do about the search index?  Update?
    self.msg_parsed = None
    return self

  def get_msg_info(self, field):
    if not self.msg_info:
      self.msg_info = self.index.get_msg_by_idx(self.msg_idx)
    return self.msg_info[field]

  def get_mbox_ptr_and_fd(self):
    for msg_ptr in self.get_msg_info(self.index.MSG_PTRS).split(','):
      try:
        mbox = self.config.open_mailbox(None, msg_ptr[:3])
        fd = mbox.get_file_by_ptr(msg_ptr)
        # FIXME: How do we know we have the right message?
        return mbox, msg_ptr, fd
      except (IOError, OSError):
        # FIXME: If this pointer is wrong, should we fix the index?
        print '%s not in %s' % (msg_ptr, mbox)
    return None, None, None

  def get_file(self):
    return self.get_mbox_ptr_and_fd()[2]

  def get_msg(self, pgpmime=True):
    if not self.msg_parsed:
      fd = self.get_file()
      if fd:
        self.msg_parsed = ParseMessage(fd, pgpmime=pgpmime)
    if not self.msg_parsed:
      IndexError('Message not found?')
    return self.msg_parsed

  def get_headerprint(self):
    return HeaderPrint(self.get_msg())

  def is_thread(self):
    return ((self.get_msg_info(self.index.MSG_CONV_ID)) or
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
    return [
      self.get_msg_info(self.index.MSG_IDX),
      self.get_msg_info(self.index.MSG_ID),
      self.get_msg_info(self.index.MSG_FROM),
      self.get_msg_info(self.index.MSG_SUBJECT),
      self.get_msg_info(self.index.MSG_DATE),
      self.get_msg_info(self.index.MSG_TAGS).split(','),
      self.is_editable()
    ]

  def extract_attachment(self, session, att_id, name_fmt=None, mode='download'):
    msg = self.get_msg()
    count = 0
    extracted = 0
    filename, attributes = '', {}
    for part in msg.walk():
      mimetype = part.get_content_type()
      if mimetype.startswith('multipart/'):
        continue

      content_id = part.get('content-id', '')
      pfn = part.get_filename() or ''
      count += 1
      if (('*' == att_id)
      or  ('#%s' % count == att_id)
      or  (content_id == att_id)
      or  (mimetype == att_id)
      or  (pfn.lower().endswith('.%s' % att_id))
      or  (pfn == att_id)):

        payload = part.get_payload(None, True) or ''
        attributes = {
          'msg_idx': b36(self.msg_idx),
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

        # FIXME: If we are asked for a preview, we should modify the payload
        #        to be a thumbnail of some sort.

        filesize = len(payload)
        if mode.startswith('inline'):
          attributes['data'] = payload
          session.ui.notify('Extracted attachment %s' % att_id)
        else:
          filename, fd = session.ui.open_for_data(name_fmt=name_fmt,
                                                  attributes=attributes)
          # FIXME: OMG, RAM ugh.
          fd.write(payload)
          fd.close()
          session.ui.notify('Wrote attachment to: %s' % filename)
        extracted += 1
    if 0 == extracted:
      session.ui.notify('No attachments found for: %s' % att_id)
      return None, None
    else:
      return filename, attributes

  def get_message_tree(self):
    tree = {
      'id': self.get_msg_info(self.index.MSG_ID),
      'tags': self.get_msg_info(self.index.MSG_TAGS).split(','),
      'summary': self.get_msg_summary(),
      'headers': {},
      'headers_lc': {},
      'attributes': {},
      'text_parts': [],
      'html_parts': [],
      'attachments': [],
      'conversation': [],
    }

    conv_id = self.get_msg_info(self.index.MSG_CONV_ID)
    if conv_id:
      conv = Email(self.index, int(conv_id, 36))
      tree['conversation'] = convs = [conv.get_msg_summary()]
      for rid in conv.get_msg_info(self.index.MSG_REPLIES).split(','):
        if rid:
          convs.append(Email(self.index, int(rid, 36)).get_msg_summary())

    # FIXME: Decide if this is strict enough or too strict...?
    html_cleaner = Cleaner(page_structure=True, meta=True, links=True,
                           javascript=True, scripts=True, frames=True,
                           embedded=True, safe_attrs_only=True)

    msg = self.get_msg()
    for hdr in msg.keys():
      tree['headers'][hdr] = self.index.hdr(msg, hdr)
      tree['headers_lc'][hdr.lower()] = self.index.hdr(msg, hdr)

    # Note: count algorithm must match that used in extract_attachment above
    count = 0
    for part in msg.walk():
      mimetype = part.get_content_type()
      if mimetype.startswith('multipart/'):
        continue

      count += 1
      if (part.get('content-disposition', 'inline') == 'inline'
      and mimetype in ('text/plain', 'text/html')):
        payload, charset, openpgp = self.decode_payload(part)
        # FIXME: Do something with the openpgp data!
        if (mimetype == 'text/html' or
            '<html>' in payload or
            '</body>' in payload):
          tree['html_parts'].append({
            'openpgp_status': openpgp and openpgp[0] or '',
            'openpgp_data': openpgp and openpgp[1] or '',
            'charset': charset,
            'type': 'html',
            'data': (payload.strip() and html_cleaner.clean_html(payload)) or ''
          })
        else:
          tree['text_parts'].extend(self.parse_text_part(payload, charset,
                                                         openpgp))
      else:
        tree['attachments'].append({
          'mimetype': mimetype,
          'count': count,
          'part': part,
          'length': len(part.get_payload(None, True) or ''),
          'content-id': part.get('content-id', ''),
          'filename': part.get_filename() or ''
        })

    if self.is_editable():
      tree['is_editable'] = True
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
        print 'Decode failed: %s %s' % (charset, e)
    try:
      openpgp = part.openpgp
    except AttributeError:
      openpgp = None
    return payload, charset, openpgp

  def parse_text_part(self, data, charset, openpgp):
    current = {
      'type': 'bogus',
      'charset': charset
    }
    parse = []
    if openpgp:
      parse.append({
        'type': 'pgpbegin%s' % openpgp[0],
        'data': openpgp[1],
        'charset': charset
      })
    block = 'body'
    for line in data.splitlines(True):
      block, ltype = self.parse_line_type(line, block)
      if ltype != current['type']:
        if openpgp:
          ltype = 'pgp%stext' % openpgp[0]
        current = {
          'type': ltype,
          'data': '',
          'charset': charset
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

  PGP_OK = {
    'pgpbeginsigned': 'pgpbeginverified',
    'pgpsignedtext': 'pgpverifiedtext',
    'pgpsignature': 'pgpverification',
    'pgpbegin': 'pgpbeginverified',
    'pgptext': 'pgpsecuretext',
    'pgpend': 'pgpverification',
  }
  def evaluate_pgp(self, tree, check_sigs=True, decrypt=False):
    pgpdata = []
    for part in tree['text_parts']:

      # Handle signed messages
      if check_sigs and GnuPG:
        if part['type'] == 'pgpbeginsigned':
          pgpdata = [part]
        elif part['type'] == 'pgpsignedtext':
          pgpdata.append(part)
        elif part['type'] == 'pgpsignature':
          pgpdata.append(part)
          try:
            message = ''.join([p['data'].encode(p['charset']) for p in pgpdata])
            gpg = GnuPG().run(['--utf8-strings', '--verify'],
                              create_fhs=['stdin', 'stderr'])
            gpg.handles['stdin'].write(message)
            gpg.handles['stdin'].close()
            result = ''
            for fh in ('stderr', ):
              result += gpg.handles[fh].read()
              gpg.handles[fh].close()
            gpg.wait()
            pgpdata[0]['data'] = result.decode('utf-8')+'\n'
            for p in pgpdata:
              p['type'] = self.PGP_OK.get(p['type'], p['type'])
          except IOError:
            part['data'] += result.decode('utf-8')
          except:
            part['data'] += traceback.format_exc()
          pgpdata = []

      if decrypt and GnuPG:
        if part['type'] in ('pgpbegin', 'pgptext'):
          pgpdata.append(part)
        elif part['type'] == 'pgpend':
          pgpdata.append(part)
          try:
            message = ''.join([p['data'] for p in pgpdata])
            gpg = GnuPG().run(['--utf8-strings'],
                              create_fhs=['stdin', 'stdout', 'stderr'])
            gpg.handles['stdin'].write(message)
            gpg.handles['stdin'].close()
            results = {}
            for fh in ('stderr', 'stdout'):
              results[fh] = gpg.handles[fh].read()
              gpg.handles[fh].close()
            gpg.wait()
            pgpdata[0]['data'] = results['stderr'].decode('utf-8')+'\n'
            pgpdata[1]['data'] = self._decode_gpg(message, results['stdout'])
            for p in pgpdata:
              p['type'] = self.PGP_OK.get(p['type'], p['type'])
          except IOError:
            part['data'] += results['stderr'].decode('utf-8')
          except:
            part['data'] += traceback.format_exc()
          pgpdata = []

    return tree

  def _decode_gpg(self, message, decrypted):
    header, body = message.replace('\r\n', '\n').split('\n\n', 1)
    for line in header.lower().split('\n'):
      if line.startswith('charset:'):
        return decrypted.decode(line.split()[1])
    return decrypted.decode('utf-8')

