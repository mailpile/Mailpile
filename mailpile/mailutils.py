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
import cPickle, email.parser, mailbox, os

from mailpile.util import *


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
        self.msg_parsed = email.parser.Parser().parse(fd)
    if not self.msg_parsed:
      IndexError('Message not found?')
    return self.msg_parsed

  def is_thread(self):
    return (0 < len(self.get_msg_info(self.index.MSG_REPLIES)))

  def get(self, field, default=None):
    """Get one (or all) indexed fields for this mail."""
    field = field.lower()
    if field == 'subject':
      return self.get_msg_info(self.index.MSG_SUBJECT)
    elif field == 'from':
      return self.get_msg_info(self.index.MSG_FROM)
    else:
      return self.get_msg().get(field, default)

  def get_body_text(self):
    for part in self.get_msg().walk():
      charset = part.get_charset() or 'iso-8859-1'
      if part.get_content_type() == 'text/plain':
        return part.get_payload(None, True).decode(charset)
    return ''

