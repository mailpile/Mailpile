#!/usr/bin/python
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
import email.parser
import errno
import mailbox
import os
import traceback

from mailpile.util import *
from lxml.html.clean import Cleaner

try:
  from GnuPGInterface import GnuPG
  from mailpile.pgpmime import PGPMimeParser
except ImportError:
  GnuPG = PGPMimeParser = None


class NoSuchMailboxError(OSError):
  pass


class IncrementalMbox(mailbox.mbox):
  """A mbox class that supports pickling and a few mailpile specifics."""

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

  def get_msg_ptr(self, idx, toc_id):
    return '%s%s:%s' % (idx,
                        b36(self._toc[toc_id][0]),
                        b36(self.get_msg_size(toc_id)))

  def get_file_by_ptr(self, msg_ptr):
    start, length = msg_ptr[3:].split(':')
    start = int(start, 36)
    length = int(length, 36)
    return mailbox._PartialFile(self._file, start, start+length)


class Email(object):
  """This is a lazy-loading object representing a single email."""

  def __init__(self, idx, msg_idx):
    self.index = idx
    self.config = idx.config
    self.msg_idx = msg_idx
    self.msg_info = None
    self.msg_parsed = None

  def get_msg_info(self, field):
    if not self.msg_info:
      self.msg_info = self.index.get_msg_by_idx(self.msg_idx)
    return self.msg_info[field]

  def get_file(self):
    for msg_ptr in self.get_msg_info(self.index.MSG_PTRS).split(','):
      try:
        mbox = self.config.open_mailbox(None, msg_ptr[:3])
        return mbox.get_file_by_ptr(msg_ptr)
      except (IOError, OSError):
        pass
    return None

  def get_msg(self):
    if not self.msg_parsed:
      fd = self.get_file()
      if fd:
        if GnuPG:
          self.msg_parsed = PGPMimeParser().parse(fd)
        else:
          self.msg_parsed = email.parser.Parser().parse(fd)
    if not self.msg_parsed:
      IndexError('Message not found?')
    return self.msg_parsed

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
      self.get_msg_info(self.index.MSG_TAGS).split(',')
    ]

  def extract_attachment(self, session, att_id, name_fmt=None):
    msg = self.get_msg()
    count = 0
    extracted = 0
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

        payload = part.get_payload(None, True)
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

        fn, fd = session.ui.open_for_data(name_fmt=name_fmt,
                                          attributes=attributes)
        # FIXME: OMG, RAM ugh.
        fd.write(payload)
        fd.close()
        session.ui.notify('Wrote attachment to: %s' % fn)
        extracted += 1
    if 0 == extracted:
      session.ui.notify('No attachments found for: %s' % att_id)

  def get_message_tree(self):
    tree = {
      'id': self.get_msg_info(self.index.MSG_ID),
      'tags': self.get_msg_info(self.index.MSG_TAGS).split(','),
      'summary': self.get_msg_summary(),
      'headers': {},
      'attributes': {},
      'text_parts': [],
      'html_parts': [],
      'attachments': [],
      'conversation': []
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

    # Note: count algorithm must match that used in extract_attachment above
    msg = self.get_msg()
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
          'length': len(part.get_payload(None, True)),
          'content-id': part.get('content-id', ''),
          'filename': part.get_filename() or ''
        })

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
            pgpdata[0]['data'] = result.decode('utf-8')
            for p in pgpdata:
              p['type'] = self.PGP_OK.get(p['type'], p['type'])
          except IOError:
            part['data'] += result.decode('utf-8')
          except:
            part['data'] += traceback.format_exc()

      # FIXME: Handle encrypted messages
      if decrypt:
        pass
 
