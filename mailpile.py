#!/usr/bin/python
ABOUT="""\
Mailpile.py - a tool for searching and      Copyright 2011, Bjarni R. Einarsson
             organizing piles of e-mail                <http://bre.klaki.net/>

This program is free software: you can redistribute it and/or modify it under
the terms of the  GNU  Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.
"""
###############################################################################
import cgi, codecs, datetime, email.parser, getopt, hashlib, locale, mailbox
import os, cPickle, random, re, rfc822, socket, struct, subprocess, sys
import tempfile, threading, time
import SocketServer
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from urlparse import parse_qs, urlparse
import lxml.html


global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER, APPEND_FD_CACHE_SIZE
global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT

DEFAULT_PORT = 33411

WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]:\"|;\'\\\<\>\?,\.\/\-]{2,}')

STOPLIST = set(['an', 'and', 'are', 'as', 'at', 'by', 'for', 'from',
                'has', 'http', 'in', 'is', 'it', 'mailto', 'og', 'or',
                're', 'so', 'the', 'to', 'was'])

BORING_HEADERS = ('received', 'date',
                  'content-type', 'content-disposition', 'mime-version',
                  'dkim-signature', 'domainkey-signature', 'received-spf')


class WorkerError(Exception):
  pass

class UsageError(Exception):
  pass

class AccessError(Exception):
  pass


def b64c(b):
  return b.replace('\n', '').replace('=', '').replace('/', '_')

def sha1b64(s):
  h = hashlib.sha1()
  h.update(s.encode('utf-8'))
  return h.digest().encode('base64')

def strhash(s, length):
  s2 = re.sub('[^0123456789abcdefghijklmnopqrstuvwxyz]+', '',
              s.lower())[:(length-4)]
  while len(s2) < length:
    s2 += b64c(sha1b64(s)).lower()
  return s2[:length]

def b36(number):
  alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  base36 = ''
  while number:
    number, i = divmod(number, 36)
    base36 = alphabet[i] + base36
  return base36 or alphabet[0]

GPG_BEGIN_MESSAGE = '-----BEGIN PGP MESSAGE'
GPG_END_MESSAGE = '-----END PGP MESSAGE'
def decrypt_gpg(lines, fd):
  for line in fd:
    lines.append(line)
    if line.startswith(GPG_END_MESSAGE):
      break

  gpg = subprocess.Popen(['gpg', '--batch'],
                         stdin=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         stdout=subprocess.PIPE)
  lines = gpg.communicate(input=''.join(lines))[0].splitlines(True)
  if gpg.wait() != 0:
    raise AccessError("GPG was unable to decrypt the data.")

  return  lines

def gpg_open(filename, recipient, mode):
  fd = open(filename, mode)
  if recipient and ('a' in mode or 'w' in mode):
    gpg = subprocess.Popen(['gpg', '--batch', '-aer', recipient],
                           stdin=subprocess.PIPE,
                           stdout=fd)
    return gpg.stdin
  return fd


# Indexing messages is an append-heavy operation, and some files are
# appended to much more often than others.  This implements a simple
# LRU cache of file descriptors we are appending to.
APPEND_FD_CACHE = {}
APPEND_FD_CACHE_SIZE = 500
APPEND_FD_CACHE_ORDER = []
def flush_append_cache(ratio=1, count=None):
  drop = count or int(ratio*len(APPEND_FD_CACHE_ORDER))
  for fn in APPEND_FD_CACHE_ORDER[:drop]:
    APPEND_FD_CACHE[fn].close()
    del APPEND_FD_CACHE[fn]
  APPEND_FD_CACHE_ORDER[:drop] = []

def cached_open(filename, mode):
  if mode == 'a':
    if filename not in APPEND_FD_CACHE:
      if len(APPEND_FD_CACHE) > APPEND_FD_CACHE_SIZE:
        flush_append_cache(count=1)
      try:
        APPEND_FD_CACHE[filename] = open(filename, 'a')
      except (IOError, OSError):
        # Too many open files?  Close a bunch and try again.
        flush_append_cache(ratio=0.3)
        APPEND_FD_CACHE[filename] = open(filename, 'a')
      APPEND_FD_CACHE_ORDER.append(filename)
    else:
      APPEND_FD_CACHE_ORDER.remove(filename)
      APPEND_FD_CACHE_ORDER.append(filename)
    return APPEND_FD_CACHE[filename]
  else:
    if filename in APPEND_FD_CACHE:
      APPEND_FD_CACHE[filename].close()
      del APPEND_FD_CACHE[filename]
      try:
        APPEND_FD_CACHE_ORDER.remove(filename)
      except ValueError:
        pass
    return open(filename, mode)


##[ Enhanced mailbox and message classes ]#####################################

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
    self._update_toc()

  def _update_toc(self):
    self._file.seek(0, 2)
    if self._file_length == self._file.tell(): return

    self._file.seek(self._toc[self._next_key-1][0])
    line = self._file.readline()
    if not line.startswith('From '):
      raise IOError("Mailbox has been modified")

    self._file.seek(self._file_length)
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


##[ The search and index code itself ]#########################################

class PostingList(object):
  """A posting list is a map of search terms to message IDs."""

  MAX_SIZE = 60  # perftest gives: 75% below 500ms, 50% below 100ms
  HASH_LEN = 12

  @classmethod
  def Optimize(cls, session, idx, force=False):
    flush_append_cache()

    postinglist_kb = session.config.get('postinglist_kb', cls.MAX_SIZE)
    postinglist_dir = session.config.postinglist_dir()

    # Pass 1: Compact all files that are 90% or more of our target size
    for fn in sorted(os.listdir(postinglist_dir)):
      if (force
      or  os.path.getsize(os.path.join(postinglist_dir, fn)) >
                                                        900*postinglist_kb):
        session.ui.mark('Pass 1: Compacting >%s<' % fn)
        # FIXME: Remove invalid and deleted messages from posting lists.
        cls(session, fn, sig=fn).save()

    # Pass 2: While mergable pair exists: merge them!
    flush_append_cache()
    files = [n for n in os.listdir(postinglist_dir) if len(n) > 1]
    files.sort(key=lambda a: -len(a))
    for fn in files:
      size = os.path.getsize(os.path.join(postinglist_dir, fn))
      fnp = fn[:-1]
      while not os.path.exists(os.path.join(postinglist_dir, fnp)):
        fnp = fnp[:-1]
      size += os.path.getsize(os.path.join(postinglist_dir, fnp))
      if (size < (1024*postinglist_kb-(cls.HASH_LEN*6))):
        session.ui.mark('Pass 2: Merging %s into %s' % (fn, fnp))
        fd = cached_open(os.path.join(postinglist_dir, fn), 'r')
        fdp = cached_open(os.path.join(postinglist_dir, fnp), 'a')
        try:
          for line in fd:
            fdp.write(line)
        except:
          flush_append_cache()
          raise
        finally:
          fd.close()
          os.remove(os.path.join(postinglist_dir, fn))

    flush_append_cache()
    filecount = len(os.listdir(postinglist_dir))
    session.ui.mark('Optimized %s posting lists' % filecount)
    return filecount

  @classmethod
  def Append(cls, session, word, mail_id, compact=True):
    config = session.config
    sig = cls.WordSig(word)
    fd, fn = cls.GetFile(session, sig, mode='a')
    if (compact
    and (os.path.getsize(os.path.join(config.postinglist_dir(), fn)) >
             (1024*config.get('postinglist_kb', cls.MAX_SIZE))-(cls.HASH_LEN*6))
    and (random.randint(0, 50) == 1)):
      # This will compact the files and split out hot-spots, but we only bother
      # "once in a while" when the files are "big".
      fd.close()
      pls = cls(session, word)
      pls.append(mail_id)
      pls.save()
    else:
      # Quick and dirty append is the default.
      fd.write('%s\t%s\n' % (sig, mail_id))

  @classmethod
  def WordSig(cls, word):
    return strhash(word, cls.HASH_LEN*2)

  @classmethod
  def GetFile(cls, session, sig, mode='r'):
    sig = sig[:cls.HASH_LEN]
    while len(sig) > 0:
      fn = os.path.join(session.config.postinglist_dir(), sig)
      try:
        if os.path.exists(fn): return (cached_open(fn, mode), sig)
      except (IOError, OSError):
        pass

      if len(sig) > 1:
        sig = sig[:-1]
      else:
        if 'r' in mode:
          return (None, sig)
        else:
          return (cached_open(fn, mode), sig)
    # Not reached
    return (None, None)

  def __init__(self, session, word, sig=None):
    self.config = session.config
    self.session = session
    self.sig = sig or PostingList.WordSig(word)
    self.word = word
    self.WORDS = {self.sig: set()}
    self.load()

  def parse_line(self, line):
    words = line.strip().split('\t')
    if len(words) > 1:
      if words[0] not in self.WORDS: self.WORDS[words[0]] = set()
      self.WORDS[words[0]] |= set(words[1:])

  def load(self):
    self.size = 0
    fd, sig = PostingList.GetFile(self.session, self.sig)
    self.filename = sig
    if fd:
      try:
        for line in fd:
          self.size += len(line)
          if line.startswith(GPG_BEGIN_MESSAGE):
            for line in decrypt_gpg([line], fd):
              self.parse_line(line)
          else:
            self.parse_line(line)
      except ValueError:
        pass
      finally:
        fd.close()

  def fmt_file(self, prefix):
    output = []
    self.session.ui.mark('Formatting prefix %s' % unicode(prefix))
    for word in self.WORDS:
      if word.startswith(prefix) and len(self.WORDS[word]) > 0:
        output.append('%s\t%s\n' % (word,
                               '\t'.join(['%s' % x for x in self.WORDS[word]])))
    return ''.join(output)

  def save(self, prefix=None, compact=True, mode='w'):
    prefix = prefix or self.filename
    output = self.fmt_file(prefix)
    while (compact
    and    len(output) > 1024*self.config.get('postinglist_kb', self.MAX_SIZE)
    and    len(prefix) < self.HASH_LEN):
      biggest = self.sig
      for word in self.WORDS:
        if len(self.WORDS[word]) > len(self.WORDS[biggest]):
          biggest = word
      if len(biggest) > len(prefix):
        biggest = biggest[:len(prefix)+1]
        self.save(prefix=biggest, mode='a')

        for key in [k for k in self.WORDS if k.startswith(biggest)]:
          del self.WORDS[key]
        output = self.fmt_file(prefix)

    try:
      outfile = os.path.join(self.config.postinglist_dir(), prefix)
      if output:
        try:
          fd = cached_open(outfile, mode)
          fd.write(output)
          return len(output)
        finally:
          if mode != 'a': fd.close()
      elif os.path.exists(outfile):
        os.remove(outfile)
    except:
      self.session.ui.warning('%s' % (sys.exc_info(), ))
    return 0

  def hits(self):
    return self.WORDS[self.sig]

  def append(self, eid):
    self.WORDS[self.sig].add(eid)
    return self

  def remove(self, eid):
    try:
      self.WORDS[self.sig].remove(eid)
    except KeyError:
      pass
    return self


class MailIndex(object):
  """This is a lazily parsing object representing a mailpile index."""

  MSG_IDX     = 0
  MSG_PTRS    = 1
  MSG_UNUSED  = 2  # Was size, now reserved for other fun things
  MSG_ID      = 3
  MSG_DATE    = 4
  MSG_FROM    = 5
  MSG_SUBJECT = 6
  MSG_TAGS    = 7
  MSG_REPLIES = 8
  MSG_CONV_ID = 9

  def __init__(self, config):
    self.config = config
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}
    self.CACHE = {}

  def l2m(self, line):
    return line.decode('utf-8').split(u'\t')

  def m2l(self, message):
    return (u'\t'.join([unicode(p) for p in message])).encode('utf-8')

  def load(self, session=None):
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}
    if session: session.ui.mark('Loading metadata index...')
    try:
      fd = open(self.config.mailindex_file(), 'r')
      try:
        for line in fd:
          if line.startswith(GPG_BEGIN_MESSAGE):
            for line in decrypt_gpg([line], fd):
              line = line.strip()
              if line and not line.startswith('#'):
                self.INDEX.append(line)
          else:
            line = line.strip()
            if line and not line.startswith('#'):
              self.INDEX.append(line)
      except ValueError:
        pass
      fd.close()
    except IOError:
      if session: session.ui.warning(('Metadata index not found: %s'
                                      ) % self.config.mailindex_file())
    if session:
      session.ui.mark('Loaded metadata for %d messages' % len(self.INDEX))

  def save(self, session=None):
    if session: session.ui.mark("Saving metadata index...")
    fd = gpg_open(self.config.mailindex_file(),
                  self.config.get('gpg_recipient'), 'w')
    fd.write('# This is the mailpile.py index file.\n')
    fd.write('# We have %d messages!\n' % len(self.INDEX))
    for item in self.INDEX:
      fd.write(item)
      fd.write('\n')
    fd.close()
    flush_append_cache()
    if session: session.ui.mark("Saved metadata index")

  def update_ptrs_and_msgids(self, session):
    session.ui.mark('Updating high level indexes')
    for offset in range(0, len(self.INDEX)):
      message = self.l2m(self.INDEX[offset])
      if len(message) > self.MSG_CONV_ID:
        self.MSGIDS[message[self.MSG_ID]] = offset
        for msg_ptr in message[self.MSG_PTRS].split(','):
          self.PTRS[msg_ptr] = offset
      else:
        session.ui.warning('Bogus line: %s' % line)

  def hdr(self, msg, name, value=None):
    decoded = email.header.decode_header(value or msg[name] or '')
    try:
      return (' '.join([t[0].decode(t[1] or 'iso-8859-1') for t in decoded])
              ).replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')
    except (UnicodeDecodeError, LookupError):
      try:
        return (' '.join([t[0].decode('utf-8') for t in decoded])
                ).replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')
      except UnicodeDecodeError:
        session.ui.warning('Boom: %s/%s' % (msg[name], decoded))
        return ''

  def update_location(self, session, msg_idx, msg_ptr):
    msg_info = self.get_msg_by_idx(msg_idx)
    msg_ptrs = msg_info[self.MSG_PTRS].split(',')
    self.PTRS[msg_ptr] = msg_idx

    # If message was seen in this mailbox before, update the location
    for i in range(0, len(msg_ptrs)):
      if (msg_ptrs[i][:3] == msg_ptr[:3]):
        msg_ptrs[i] = msg_ptr
        msg_ptr = None
        break

    # Otherwise, this is a new mailbox, record this sighting as well!
    if msg_ptr: msg_ptrs.append(msg_ptr)
    msg_info[self.MSG_PTRS] = ','.join(msg_ptrs)
    self.set_msg_by_idx(msg_idx, msg_info)

  def scan_mailbox(self, session, idx, mailbox_fn, mailbox_opener):
    mbox = mailbox_opener(session, idx)
    session.ui.mark('%s: Scanning: %s' % (idx, mailbox_fn))

    if mbox.last_parsed+1 == len(mbox): return 0

    if len(self.PTRS.keys()) == 0:
      self.update_ptrs_and_msgids(session)

    added = 0
    msg_date = int(time.time())
    for i in range(mbox.last_parsed+1, len(mbox)):
      parse_status = ('%s: Reading your mail: %d%% (%d/%d messages)'
                      ) % (idx, 100 * i/len(mbox), i, len(mbox))

      msg_ptr = mbox.get_msg_ptr(idx, i)
      if msg_ptr in self.PTRS:
        if (i % 317) == 0: session.ui.mark(parse_status)
        continue
      else:
        session.ui.mark(parse_status)

      # Message new or modified, let's parse it.
      p = email.parser.Parser()
      msg = p.parse(mbox.get_file(i))
      msg_id = b64c(sha1b64((self.hdr(msg, 'message-id') or msg_ptr).strip()))
      if msg_id in self.MSGIDS:
        self.update_location(session, self.MSGIDS[msg_id], msg_ptr)
        added += 1
      else:
        # Add new message!
        msg_mid = b36(len(self.INDEX))

        try:
          msg_date = int(rfc822.mktime_tz(
                                   rfc822.parsedate_tz(self.hdr(msg, 'date'))))
        except ValueError:
          session.ui.warning('Date parsing: %s' % (sys.exc_info(), ))
          # This is a hack: We assume the messages in the mailbox are in
          # chronological order and just add 1 second to the date of the last
          # message.  This should be a better-than-nothing guess.
          msg_date += 1

        msg_conv = None
        refs = set((self.hdr(msg, 'references')+' '+self.hdr(msg, 'in-reply-to')
                    ).replace(',', ' ').strip().split())
        for ref_id in [b64c(sha1b64(r)) for r in refs]:
          try:
            # Get conversation ID ...
            ref_mid = self.MSGIDS[ref_id]
            msg_conv = self.get_msg_by_idx(ref_mid)[self.MSG_CONV_ID]
            # Update root of conversation thread
            parent = self.get_msg_by_idx(int(msg_conv, 36))
            parent[self.MSG_REPLIES] += '%s,' % msg_mid
            self.set_msg_by_idx(int(msg_conv, 36), parent)
            break
          except (KeyError, ValueError, IndexError):
            pass
        if not msg_conv:
          # FIXME: If subject implies this is a reply, scan back a couple
          #        hundred messages for similar subjects - but not infinitely,
          #        conversations don't last forever.
          msg_conv = msg_mid

        keywords = self.index_message(session, msg_mid, msg_id, msg, msg_date,
                                      compact=False,
                                      filter_hooks=[self.filter_keywords])
        tags = [k.split(':')[0] for k in keywords if k.endswith(':tag')]

        self.set_msg_by_idx(len(self.INDEX),
                            [msg_mid,                   # Our index ID
                             msg_ptr,                   # Location on disk
                             '',                        # UNUSED
                             msg_id,                    # Message-ID
                             b36(msg_date),             # Date as a UTC timestamp
                             self.hdr(msg, 'from'),     # From:
                             self.hdr(msg, 'subject'),  # Subject
                             ','.join(tags),            # Initial tags
                             '',                        # No replies for now
                             msg_conv])                 # Conversation ID
        added += 1

    if added:
      mbox.last_parsed = i
      mbox.save(session)
    session.ui.mark('%s: Indexed mailbox: %s' % (idx, mailbox_fn))
    return added

  def filter_keywords(self, session, msg_mid, msg, keywords):
    keywordmap = {}
    msg_idx_list = [msg_mid]
    for kw in keywords:
      keywordmap[kw] = msg_idx_list

    for fid, terms, tags, comment in session.config.get_filters():
      if (terms == '*'
      or  len(self.search(None, terms.split(), keywords=keywordmap)) > 0):
        for t in tags.split():
          kw = '%s:tag' % t[1:]
          if t[0] == '-':
            if kw in keywordmap: del keywordmap[kw]
          else:
            keywordmap[kw] = msg_idx_list

    return set(keywordmap.keys())

  def index_message(self, session, msg_mid, msg_id, msg, msg_date,
                    compact=True, filter_hooks=[]):
    keywords = []
    for part in msg.walk():
      charset = part.get_charset() or 'iso-8859-1'
      if part.get_content_type() == 'text/plain':
        textpart = part.get_payload(None, True).decode(charset)
      elif part.get_content_type() == 'text/html':
        payload = part.get_payload(None, True).decode(charset)
        if payload:
          try:
            textpart = lxml.html.fromstring(payload).text_content()
          except:
            session.ui.warning('Parsing failed: %s' % payload)
            textpart = None
        else:
          textpart = None
      else:
        textpart = None

      att = part.get_filename()
      if att:
        keywords.append('attachment:has')
        keywords.extend([t+':att' for t in re.findall(WORD_REGEXP, att.lower())])
        textpart = (textpart or '') + ' ' + att

      if textpart:
        # FIXME: Does this lowercase non-ASCII characters correctly?
        keywords.extend(re.findall(WORD_REGEXP, textpart.lower()))

    mdate = datetime.date.fromtimestamp(msg_date)
    keywords.append('%s:year' % mdate.year)
    keywords.append('%s:month' % mdate.month)
    keywords.append('%s:day' % mdate.day)
    keywords.append('%s-%s-%s:date' % (mdate.year, mdate.month, mdate.day))
    keywords.append('%s:id' % msg_id)
    keywords.extend(re.findall(WORD_REGEXP, self.hdr(msg, 'subject').lower()))
    keywords.extend(re.findall(WORD_REGEXP, self.hdr(msg, 'from').lower()))

    for key in msg.keys():
      key_lower = key.lower()
      if key_lower not in BORING_HEADERS:
        words = set(re.findall(WORD_REGEXP, self.hdr(msg, key).lower()))
        words -= STOPLIST
        keywords.extend(['%s:%s' % (t, key_lower) for t in words])
        if 'list' in key_lower:
          keywords.extend(['%s:list' % t for t in words])

    keywords = set(keywords)
    keywords -= STOPLIST

    for hook in filter_hooks:
      keywords = hook(session, msg_mid, msg, keywords)

    for word in keywords:
      try:
        PostingList.Append(session, word, msg_mid, compact=compact)
      except UnicodeDecodeError:
        # FIXME: we just ignore garbage
        pass

    return keywords

  def get_msg_by_idx(self, msg_idx):
    try:
      if msg_idx not in self.CACHE:
        self.CACHE[msg_idx] = self.l2m(self.INDEX[msg_idx])
      return self.CACHE[msg_idx]
    except IndexError:
      return (None, None, None, None, b36(0),
              '(not in index)', '(not in index)', None, None)

  def set_msg_by_idx(self, msg_idx, msg_info):
    if msg_idx < len(self.INDEX):
      self.INDEX[msg_idx] = self.m2l(msg_info)
    elif msg_idx == len(self.INDEX):
      self.INDEX.append(self.m2l(msg_info))
    else:
      raise IndexError('%s is outside the index' % msg_idx)

    if msg_idx in self.CACHE:
      del(self.CACHE[msg_idx])

    self.MSGIDS[msg_info[self.MSG_ID]] = msg_idx
    for msg_ptr in msg_info[self.MSG_PTRS]:
      self.PTRS[msg_ptr] = msg_idx

  def get_conversation(self, msg_idx):
    return self.get_msg_by_idx(
             int(self.get_msg_by_idx(msg_idx)[self.MSG_CONV_ID], 36))

  def get_replies(self, msg_info=None, msg_idx=None):
    if not msg_info: msg_info = self.get_msg_by_idx(msg_idx)
    return [self.get_msg_by_idx(int(r, 36)) for r
            in msg_info[self.MSG_REPLIES].split(',') if r]

  def get_tags(self, msg_info=None, msg_idx=None):
    if not msg_info: msg_info = self.get_msg_by_idx(msg_idx)
    return [r for r in msg_info[self.MSG_TAGS].split(',') if r]

  def add_tag(self, session, tag_id, msg_info=None, msg_idxs=None):
    pls = PostingList(session, '%s:tag' % tag_id)
    if not msg_idxs:
      msg_idxs = [int(msg_info[self.MSG_IDX], 36)]
    session.ui.mark('Tagging %d messages (%s)' % (len(msg_idxs), tag_id))
    for msg_idx in list(msg_idxs):
      for reply in self.get_replies(msg_idx=msg_idx):
        if reply[self.MSG_IDX]:
          msg_idxs.add(int(reply[self.MSG_IDX], 36))
        if msg_idx % 1000 == 0: self.CACHE = {}
    for msg_idx in msg_idxs:
      msg_info = self.get_msg_by_idx(msg_idx)
      tags = set([r for r in msg_info[self.MSG_TAGS].split(',') if r])
      tags.add(tag_id)
      msg_info[self.MSG_TAGS] = ','.join(list(tags))
      self.INDEX[msg_idx] = self.m2l(msg_info)
      pls.append(msg_info[self.MSG_IDX])
      if msg_idx % 1000 == 0: self.CACHE = {}
    pls.save()
    self.CACHE = {}

  def remove_tag(self, session, tag_id, msg_info=None, msg_idxs=None):
    pls = PostingList(session, '%s:tag' % tag_id)
    if not msg_idxs:
      msg_idxs = [int(msg_info[self.MSG_IDX], 36)]
    session.ui.mark('Untagging conversations (%s)' % (tag_id, ))
    for msg_idx in list(msg_idxs):
      for reply in self.get_replies(msg_idx=msg_idx):
        if reply[self.MSG_IDX]:
          msg_idxs.add(int(reply[self.MSG_IDX], 36))
        if msg_idx % 1000 == 0: self.CACHE = {}
    session.ui.mark('Untagging %d messages (%s)' % (len(msg_idxs), tag_id))
    for msg_idx in msg_idxs:
      msg_info = self.get_msg_by_idx(msg_idx)
      tags = set([r for r in msg_info[self.MSG_TAGS].split(',') if r])
      if tag_id in tags:
        tags.remove(tag_id)
        msg_info[self.MSG_TAGS] = ','.join(list(tags))
        self.INDEX[msg_idx] = self.m2l(msg_info)
      pls.remove(msg_info[self.MSG_IDX])
      if msg_idx % 1000 == 0: self.CACHE = {}
    pls.save()
    self.CACHE = {}

  def search(self, session, searchterms, keywords=None):
    if keywords:
      def hits(term):
        return set(keywords.get(term, []))
    else:
      def hits(term):
        session.ui.mark('Searching for %s' % term)
        return PostingList(session, term).hits()

    if len(self.CACHE.keys()) > 5000: self.CACHE = {}
    r = []
    for term in searchterms:
      if term in STOPLIST:
        if session:
          session.ui.warning('Ignoring common word: %s' % term)
        continue

      if term[0] in ('-', '+'):
        op = term[0]
        term = term[1:]
      else:
        op = None

      r.append((op, []))
      rt = r[-1][1]
      term = term.lower()

      if term.startswith('body:'):
        rt.extend(hits(term[5:]))
      elif ':' in term:
        t = term.split(':', 1)
        rt.extend(hits('%s:%s' % (t[1], t[0])))
      else:
        rt.extend(hits(term))

    if r:
      results = set(r[0][1])
      for (op, rt) in r[1:]:
        if op == '+':
          results |= set(rt)
        elif op == '-':
          results -= set(rt)
        else:
          results &= set(rt)
      # Sometimes the scan gets aborted...
      if not keywords:
        results -= set([b36(len(self.INDEX))])
    else:
      results = set()

    results = [int(r, 36) for r in results]
    if session:
      session.ui.mark('Found %d results' % len(results))
    return results

  def sort_results(self, session, results, how=None):
    force = how or False
    how = how or self.config.get('default_order', 'reverse_date')
    sign = how.startswith('rev') and -1 or 1
    sort_max = self.config.get('sort_max', 5000)
    if not results: return

    if len(results) > sort_max and not force:
      session.ui.warning(('Over sort_max (%s) results, sorting badly.'
                          ) % sort_max)
      results.sort()
      if sign < 0: results.reverse()
      leftovers = results[sort_max:]
      results[sort_max:] = []
    else:
      leftovers = []

    session.ui.mark('Sorting messages in %s order...' % how)
    try:
      if how == 'unsorted':
        pass
      elif how.endswith('index'):
        results.sort()
      elif how.endswith('random'):
        now = time.time()
        results.sort(key=lambda k: sha1b64('%s%s' % (now, k)))
      elif how.endswith('date'):
        results.sort(key=lambda k: long(self.get_msg_by_idx(k)[self.MSG_DATE], 36))
      elif how.endswith('from'):
        results.sort(key=lambda k: self.get_msg_by_idx(k)[self.MSG_FROM])
      elif how.endswith('subject'):
        results.sort(key=lambda k: self.get_msg_by_idx(k)[self.MSG_SUBJECT])
      else:
        session.ui.warning('Unknown sort order: %s' % how)
        results.extend(leftovers)
        return False
    except:
      session.ui.warning('Sort failed, sorting badly.  Partial index?')

    if sign < 0: results.reverse()

    if 'flat' not in how:
      conversations = [int(self.get_msg_by_idx(r)[self.MSG_CONV_ID], 36)
                       for r in results]
      results[:] = []
      chash = {}
      for c in conversations:
        if c not in chash:
          results.append(c)
          chash[c] = 1

    results.extend(leftovers)

    session.ui.mark('Sorted messages in %s order' % how)
    return True


##[ User Interface classes ]###################################################

class NullUI(object):

  interactive = False
  buffering = False
  buffered = []

  def print_key(self, key, config): pass
  def reset_marks(self, quiet=False): pass
  def mark(self, progress): pass

  def flush(self):
    while len(self.buffered) > 0:
      self.buffered.pop(0)()

  def block(self):
    self.buffering = True

  def unblock(self):
    self.flush()
    self.buffering = False

  def say(self, text='', newline='\n', fd=sys.stdout):
    def sayit():
      fd.write(text.encode('utf-8')+newline)
      fd.flush()
    self.buffered.append(sayit)
    if not self.buffering: self.flush()

  def notify(self, message): self.say(str(message))
  def warning(self, message): self.say('Warning: %s' % message)
  def error(self, message): self.say('Error: %s' % message)

  def print_intro(self, help=False, http_worker=None):
    if http_worker:
      http_status = 'on: http://%s:%s/' % http_worker.httpd.sspec
    else:
      http_status = 'disabled.'
    self.say('\n'.join([ABOUT,
                        'The web interface is %s' % http_status,
                        '',
                        'For instructions type `help`, press <CTRL-D> to quit.',
                        '']))

  def print_help(self, commands, tags=None):
    self.say('Commands:')
    last_rank = None
    cmds = commands.keys()
    cmds.sort(key=lambda k: commands[k][3])
    for c in cmds:
      cmd, args, explanation, rank = commands[c]
      if not rank: continue

      if last_rank and int(rank/10) != last_rank: self.say()
      last_rank = int(rank/10)

      self.say('    %s|%-8.8s %-15.15s %s' % (c[0], cmd.replace('=', ''),
                                              args and ('<%s>' % args) or '',
                                              explanation))
    if tags:
      self.say('\nTags:  (use a tag as a command to display tagged messages)',
               '\n  ')
      tags.sort()
      for i in range(0, len(tags)):
        self.say('%-18.18s ' % tags[i], newline=(i%4==3) and '\n  ' or '')
    self.say('\n')

  def print_filters(self, config):
    self.say('  ID  Tags                   Terms')
    for fid, terms, tags, comment in config.get_filters():
      self.say((' %3.3s %-23.23s %-20.20s %s'
                ) % (fid,
        ' '.join(['%s%s' % (t[0], config['tag'][t[1:]]) for t in tags.split()]),
                     (terms == '*') and '(all new mail)' or terms or '(none)',
                     comment or '(none)'))

  def display_messages(self, emails, raw=False, sep='', fd=sys.stdout):
    for email in emails:
      self.say(sep, fd=fd)
      if raw:
        for line in email.get_file().readlines():
          try:
            line = line.decode('utf-8')
          except UnicodeDecodeError:
            try:
              line = line.decode('iso-8859-1')
            except:
              line = '(MAILPILE DECODING FAILED)\n'
          self.say(line, newline='', fd=fd)
      else:
        for hdr in ('Date', 'To', 'From', 'Subject'):
          self.say('%s: %s' % (hdr, email.get(hdr, '(unknown)')), fd=fd)
        self.say('\n%s' % email.get_body_text(), fd=fd)


class TextUI(NullUI):
  def __init__(self):
    self.times = []

  def print_key(self, key, config):
    if ':' in key:
      key, subkey = key.split(':', 1)
    else:
      subkey = None

    if key in config:
      if key in config.INTS:
        self.say('%s = %s (int)' % (key, config.get(key)))
      else:
        val = config.get(key)
        if subkey:
          if subkey in val:
            self.say('%s:%s = %s' % (key, subkey, val[subkey]))
          else:
            self.say('%s:%s is unset' % (key, subkey))
        else:
          self.say('%s = %s' % (key, config.get(key)))
    else:
      self.say('%s is unset' % key)

  def reset_marks(self, quiet=False):
    t = self.times
    self.times = []
    if t:
      if not quiet:
        result = 'Elapsed: %.3fs (%s)' % (t[-1][0] - t[0][0], t[-1][1])
        self.say('%s%s' % (result, ' ' * (79-len(result))))
      return t[-1][0] - t[0][0]
    else:
      return 0

  def mark(self, progress):
    self.say('  %s%s\r' % (progress, ' ' * (77-len(progress))),
             newline='', fd=sys.stderr)
    self.times.append((time.time(), progress))

  def name(self, sender):
    words = re.sub('["<>]', '', sender).split()
    nomail = [w for w in words if not '@' in w]
    if nomail: return ' '.join(nomail)
    return ' '.join(words)

  def names(self, senders):
    if len(senders) > 3:
      return re.sub('["<>]', '', ','.join([x.split()[0] for x in senders]))
    return ','.join([self.name(s) for s in senders])

  def compact(self, namelist, maxlen):
    l = len(namelist)
    while l > maxlen:
      namelist = re.sub(',[^, \.]+,', ',,', namelist, 1)
      if l == len(namelist): break
      l = len(namelist)
    namelist = re.sub(',,,+,', ' .. ', namelist, 1)
    return namelist

  def display_results(self, idx, results, start=0, end=None, num=20):
    if not results: return (0, 0)

    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    clen = max(3, len('%d' % len(results)))
    cfmt = '%%%d.%ds' % (clen, clen)

    count = 0
    for mid in results[start:start+num]:
      count += 1
      try:
        msg_info = idx.get_msg_by_idx(mid)
        msg_subj = msg_info[idx.MSG_SUBJECT]

        msg_from = [msg_info[idx.MSG_FROM]]
        msg_from.extend([r[idx.MSG_FROM] for r in idx.get_replies(msg_info)])

        msg_date = [msg_info[idx.MSG_DATE]]
        msg_date.extend([r[idx.MSG_DATE] for r in idx.get_replies(msg_info)])
        msg_date = datetime.date.fromtimestamp(max([
                                                int(d, 36) for d in msg_date]))

        msg_tags = '<'.join(sorted([re.sub("^.*/", "", idx.config['tag'].get(t, t))
                                    for t in idx.get_tags(msg_info=msg_info)]))
        msg_tags = msg_tags and (' <%s' % msg_tags) or '  '

        sfmt = '%%-%d.%ds%%s' % (41-(clen+len(msg_tags)),41-(clen+len(msg_tags)))
        self.say((cfmt+' %4.4d-%2.2d-%2.2d %-25.25s '+sfmt
                  ) % (start + count,
                       msg_date.year, msg_date.month, msg_date.day,
                       self.compact(self.names(msg_from), 25),
                       msg_subj, msg_tags))
      except (IndexError, ValueError):
        self.say('-- (not in index: %s)' % mid)
    session.ui.mark(('Listed %d-%d of %d results'
                     ) % (start+1, start+count, len(results)))
    return (start, count)

  def display_messages(self, emails, raw=False, sep='', fd=None):
    if not fd and self.interactive:
      viewer = subprocess.Popen(['less'], stdin=subprocess.PIPE)
      fd = viewer.stdin
    else:
      fd = sys.stdout
      viewer = None
    try:
      NullUI.display_messages(self, emails, raw=raw, sep=('_' * 80), fd=fd)
    except IOError, e:
      pass
    if viewer:
      fd.close()
      viewer.wait()


class HtmlUI(TextUI):

  buffered_html = []

  def say(self, text='', newline='\n', fd=None):
    if text.startswith('\r') and self.buffered_html:
      self.buffered_html[-1] = (text+newline).replace('\r', '')
    else:
      self.buffered_html.append(text+newline)

  def render_html(self):
    html = (''.join(self.buffered_html)
              .replace('&', '&amp;')
              .replace('>', '&gt;')
              .replace('<', '&lt;'))
    self.buffered_html = []
    return '<pre>' + html + '</pre>'


##[ The Configuration Manager ]###############################################

class ConfigManager(dict):

  http_worker = None
  slow_worker = None
  index = None

  MBOX_CACHE = {}

  INTS = ('postinglist_kb', 'sort_max', 'num_results', 'fd_cache_size',
          'http_port')
  STRINGS = ('mailindex_file', 'postinglist_dir', 'default_order',
             'gpg_recipient', 'http_host')
  DICTS = ('mailbox', 'tag', 'filter', 'filter_terms', 'filter_tags')

  def workdir(self):
    return os.environ.get('MAILPILE_HOME', os.path.expanduser('~/.mailpile'))

  def conffile(self):
    return os.path.join(self.workdir(), 'config.rc')

  def parse_unset(self, session, arg):
    key = arg.strip().lower()
    if key in self:
      del self[key]
    elif ':' in key and key.split(':', 1)[0] in self.DICTS:
      key, subkey = key.split(':', 1)
      if key in self and subkey in self[key]:
        del self[key][subkey]
    session.ui.print_key(key, self)
    return True

  def parse_set(self, session, line):
    key, val = [k.strip() for k in line.split('=', 1)]
    key = key.lower()
    if key in self.INTS:
      try:
        self[key] = int(val)
      except ValueError:
        raise UsageError('%s is not an integer' % val)
    elif key in self.STRINGS:
      self[key] = val
    elif ':' in key and key.split(':', 1)[0] in self.DICTS:
      key, subkey = key.split(':', 1)
      if key not in self:
        self[key] = {}
      self[key][subkey] = val
    else:
      raise UsageError('Unknown key in config: %s' % key)
    session.ui.print_key(key, self)
    return True

  def parse_config(self, session, line):
    line = line.strip()
    if line.startswith('#') or not line:
      pass
    elif '=' in line:
      self.parse_set(session, line)
    else:
      raise UsageError('Bad line in config: %s' % line)

  def load(self, session):
    if not os.path.exists(self.workdir()):
      if session: session.ui.notify('Creating: %s' % self.workdir())
      os.mkdir(self.workdir())
    else:
      self.index = None
      for key in (self.INTS + self.STRINGS):
        if key in self: del self[key]
      try:
        fd = open(self.conffile(), 'r')
        try:
          for line in fd:
            if line.startswith(GPG_BEGIN_MESSAGE):
              for line in decrypt_gpg([line], fd):
                self.parse_config(session, line)
            else:
              self.parse_config(session, line)
        except ValueError:
          pass
        fd.close()
      except IOError:
        pass

  def save(self):
    if not os.path.exists(self.workdir()):
      session.ui.notify('Creating: %s' % self.workdir())
      os.mkdir(self.workdir())
    fd = gpg_open(self.conffile(), self.get('gpg_recipient'), 'w')
    fd.write('# Mailpile autogenerated configuration file\n')
    for key in sorted(self.keys()):
      if key in self.DICTS:
        for subkey in sorted(self[key].keys()):
          fd.write('%s:%s = %s\n' % (key, subkey, self[key][subkey]))
      else:
        fd.write('%s = %s\n' % (key, self[key]))
    fd.close()

  def nid(self, what):
    if what not in self or not self[what]:
      return '0'
    else:
      return b36(1+max([int(k, 36) for k in self[what]]))

  def open_mailbox(self, session, mailbox_id):
    pfn = os.path.join(self.workdir(), 'pickled-mailbox.%s' % mailbox_id)
    for mid, mailbox_fn in self.get_mailboxes():
      if mid == mailbox_id:
        if mid not in self.MBOX_CACHE:
          try:
            if session:
              session.ui.mark(('%s: Updating: %s'
                               ) % (mailbox_id, mailbox_fn))
            self.MBOX_CACHE[mid] = cPickle.load(open(pfn, 'r'))
          except (IOError, EOFError):
            if session:
              session.ui.mark(('%s: Opening: %s (may take a while)'
                               ) % (mailbox_id, mailbox_fn))
            mbox = IncrementalMbox(mailbox_fn)
            mbox.save(session, to=pfn)
            self.MBOX_CACHE[mid] = mbox
        if mid in self.MBOX_CACHE:
          return self.MBOX_CACHE[mid]
    raise IndexError('No such mailbox: %s' % mailbox_id)

  def get_filters(self):
    filters = self.get('filter', {}).keys()
    filters.sort(key=lambda k: int(k, 36))
    flist = []
    for fid in filters:
      comment = self.get('filter', {}).get(fid, '')
      terms = unicode(self.get('filter_terms', {}).get(fid, ''))
      tags = unicode(self.get('filter_tags', {}).get(fid, ''))
      flist.append((fid, terms, tags, comment))
    return flist

  def get_mailboxes(self):
    def fmt_mbxid(k):
      k = b36(int(k, 36))
      if len(k) > 3:
        raise ValueError('Mailbox ID too large: %s' % k)
      return ('000'+k)[-3:]
    mailboxes = self['mailbox'].keys()
    mailboxes.sort()
    mailboxes.reverse()
    return [(fmt_mbxid(k), self['mailbox'][k]) for k in mailboxes]

  def history_file(self):
    return self.get('history_file',
                    os.path.join(self.workdir(), 'history'))

  def mailindex_file(self):
    return self.get('mailindex_file',
                    os.path.join(self.workdir(), 'mailpile.idx'))

  def postinglist_dir(self):
    d = self.get('postinglist_dir',
                 os.path.join(self.workdir(), 'search'))
    if not os.path.exists(d): os.mkdir(d)
    return d

  def get_index(self, session):
    if self.index: return self.index
    idx = MailIndex(self)
    idx.load(session)
    self.index = idx
    return idx


##[ Sessions and User Commands ]###############################################

class Worker(threading.Thread):

  def __init__(self, name, session):
    threading.Thread.__init__(self)
    self.NAME = name or 'Worker'
    self.ALIVE = False
    self.JOBS = []
    self.LOCK = threading.Condition()
    self.session = session

  def add_task(self, session, name, task, post_task=None):
    self.LOCK.acquire()
    self.JOBS.append((session, name, task, post_task))
    self.LOCK.notify()
    self.LOCK.release()

  def do(self, session, name, task):
    if session and session.main:
      # We run this in the foreground on the main interactive session,
      # so CTRL-C has a chance to work.
      try:
        self.flush(session, wait=1)
        self.pause()
        rv = task()
      except KeyboardInterrupt:
        raise
      finally:
        self.unpause()
    else:
      self.add_task(session, name, task)
      if session:
        rv = session.wait_for_task()
        if not rv:
          raise WorkerError()
      else:
        rv = True
    return rv

  def run(self):
    self.ALIVE = True
    while self.ALIVE:
      self.LOCK.acquire()
      while len(self.JOBS) < 1:
        self.LOCK.wait()
      session, name, task, post_task = self.JOBS.pop(0)
      self.LOCK.release()

      try:
        if session:
          session.ui.mark('Starting: %s' % name)
          session.report_task_completed(task(), name)
        else:
          task()
      except Exception, e:
        self.session.ui.error('%s failed in %s: %s' % (name, self.NAME, e))
        if session: session.report_task_failed()

      if post_task:
        try:
          post_task()
        except:
          pass

  def flush(self, session, wait=0):
    self.add_task(session, 'Flush', lambda: True, lambda: time.sleep(wait))
    session.wait_for_task(quiet=True)

  def pause(self):
    self.LOCK.acquire()

  def unpause(self):
    self.LOCK.release()

  def die_soon(self, session=None):
    def die():
      self.ALIVE = False
    self.add_task(session, '%s shutdown' % self.NAME, die)

  def quit(self, session=None):
    self.die_soon(session=session)
    self.join()


class Session(object):

  main = False
  interactive = False

  ui = NullUI()
  order = None
  results = []
  searched = []
  displayed = (0, 0)
  task_result = None

  def __init__(self, config):
    self.config = config
    self.wait_lock = threading.Condition()

  def report_task_completed(self, result, name):
    self.wait_lock.acquire()
    self.task_result = result
    self.wait_lock.notify()
    self.wait_lock.release()

  def report_task_failed(self):
    self.report_task_completed(None)

  def wait_for_task(self, quiet=False):
    self.wait_lock.acquire()
    self.task_result = None
    self.wait_lock.wait()
    self.wait_lock.release()
    self.ui.reset_marks(quiet=quiet)
    return self.task_result

  def error(self, message):
    self.ui.error(message)
    if not self.interactive: sys.exit(1)


COMMANDS = {
  'A:': ('add=',     'path/to/mbox',  'Add a mailbox',                      54),
  'F:': ('filter=',  'options',       'Add/edit/delete auto-tagging rules', 56),
  'h':  ('help',     '',              'Print help on how to use mailpile',   0),
  'L':  ('load',     '',              'Load the metadata index',            11),
  'n':  ('next',     '',              'Display next page of results',       31),
  'o:': ('order=',   '[rev-]what',   ('Sort by: date, from, subject, '
                                      'random or index'),                   33),
  'O':  ('optimize', '',              'Optimize the keyword search index',  12),
  'p':  ('previous', '',              'Display previous page of results',   32),
  'P:': ('print=',   'var',           'Print a setting',                    52),
  'R':  ('rescan',   '',              'Scan all mailboxes for new messages',13),
  's:': ('search=',  'terms ...',     'Search!',                            30),
  'S:': ('set=',     'var=value',     'Change a setting',                   50),
  't:': ('tag=',     '[+|-]tag msg',  'Tag or untag search results',        34),
  'T:': ('addtag=',  'tag',           'Create a new tag',                   55),
  'U:': ('unset=',   'var',           'Reset a setting to the default',     51),
  'v:': ('view=',    '[raw] m1 ...',  'View one or more messages',          35),
}
def Choose_Messages(session, words):
  msg_ids = set()
  for what in words:
    if what.lower() == 'these':
      b, c = session.displayed
      msg_ids |= set(session.results[b:b+c])
    elif what.lower() == 'all':
      msg_ids |= set(session.results)
    elif what.startswith('='):
      try:
        msg_ids.add(session.results[int(what[1:], 36)])
      except:
        session.ui.warning('What message is %s?' % (what, ))
    elif '-' in what:
      try:
        b, e = what.split('-')
        msg_ids |= set(session.results[int(b)-1:int(e)])
      except:
        session.ui.warning('What message is %s?' % (what, ))
    else:
      try:
        msg_ids.add(session.results[int(what)-1])
      except:
        session.ui.warning('What message is %s?' % (what, ))
  return msg_ids

def Action_Load(session, config, reset=False, wait=True):
  if not reset and config.index:
    return config.index
  def do_load():
    if reset:
      config.index = None
      session.results = []
      session.searched = []
      session.displayed = (0, 0)
    idx = config.get_index(session)
    if session:
      session.ui.reset_marks()
    return idx
  if wait:
    return config.slow_worker.do(session, 'Load', do_load)
  else:
    config.slow_worker.add_task(session, 'Load', do_load)
    return None

def Action_Tag(session, opt, arg, save=True):
  idx = Action_Load(session, session.config)
  try:
    words = arg.split()
    op = words[0][0]
    tag = words[0][1:]
    tag_id = [t for t in session.config['tag']
              if session.config['tag'][t].lower() == tag.lower()][0]

    msg_ids = Choose_Messages(session, words[1:])
    if op == '-':
      idx.remove_tag(session, tag_id, msg_idxs=msg_ids)
    else:
      idx.add_tag(session, tag_id, msg_idxs=msg_ids)

    session.ui.reset_marks()

    if save:
      # Background save makes things feel fast!
      session.config.slow_worker.add_task(None, 'Save index', idx.save)

    return True

  except (TypeError, ValueError, IndexError):
    session.ui.reset_marks()
    session.ui.error('That made no sense: %s %s' % (opt, arg))
    return False

def Action_Filter_Add(session, config, flags, args):
  terms = ('new' in flags) and ['*'] or session.searched
  if args and args[0][0] == '=':
    tag_id = args.pop(0)[1:]
  else:
    tag_id = config.nid('filter')

  if not terms or (len(args) < 1):
    raise UsageError('Need search term and flags')

  tags, tids = [], []
  while args and args[0][0] in ('-', '+'):
    tag = args.pop(0)
    tags.append(tag)
    tids.append([tag[0]+t for t in config['tag']
                 if config['tag'][t].lower() == tag[1:].lower()][0])

  if not args:
    args = ['Filter for %s' % ' '.join(tags)]

  if 'notag' not in flags and 'new' not in flags:
    for tag in tags:
      if not Action_Tag(session, 'filter/tag', '%s all' % tag, save=False):
        raise UsageError()

  if (config.parse_set(session, ('filter:%s=%s'
                                 ) % (tag_id, ' '.join(args)))
  and config.parse_set(session, ('filter_tags:%s=%s'
                                 ) % (tag_id, ' '.join(tids)))
  and config.parse_set(session, ('filter_terms:%s=%s'
                                 ) % (tag_id, ' '.join(terms)))):
    session.ui.reset_marks()
    def save_filter():
      config.save()
      config.index.save(None)
    config.slow_worker.add_task(None, 'Save filter', save_filter)
  else:
    raise Exception('That failed, not sure why?!')

def Action_Filter_Delete(session, config, flags, args):
  if len(args) < 1 or args[0] not in config.get('filter', {}):
    raise UsageError('Delete what?')

  fid = args[0]
  if (config.parse_unset(session, 'filter:%s' % fid)
  and config.parse_unset(session, 'filter_tags:%s' % fid)
  and config.parse_unset(session, 'filter_terms:%s' % fid)):
    config.save()
  else:
    raise Exception('That failed, not sure why?!')

def Action_Filter_Move(session, config, flags, args):
  raise Exception('Unimplemented')

def Action_Filter(session, opt, arg):
  config = session.config
  args = arg.split()
  flags = []
  while args and args[0] in ('add', 'set', 'delete', 'move', 'list',
                             'new', 'notag'):
    flags.append(args.pop(0))
  try:
    if 'delete' in flags:
      return Action_Filter_Delete(session, config, flags, args)
    elif 'move' in flags:
      return Action_Filter_Move(session, config, flags, args)
    elif 'list' in flags:
      return session.ui.print_filters(config)
    else:
      return Action_Filter_Add(session, config, flags, args)
  except UsageError:
    pass
  except Exception, e:
    session.error(e)
    return
  session.ui.say(
    'Usage: filter [new] [notag] [=ID] <[+|-]tags ...> [description]\n'
    '       filter delete <id>\n'
    '       filter move <id> <pos>\n'
    '       filter list')

def Action_Rescan(session, config):
  idx = config.index
  count = 1
  try:
    for fid, fpath in config.get_mailboxes():
      count += idx.scan_mailbox(session, fid, fpath, config.open_mailbox)
      session.ui.mark('\n')
    count -= 1
    if not count: session.ui.mark('Nothing changed')
  except KeyboardInterrupt:
    session.ui.mark('Aborted')
  finally:
    if count: idx.save(session)
  session.ui.reset_marks()
  return True

def Action_Optimize(session, config, arg):
  try:
    idx = config.index
    filecount = PostingList.Optimize(session, idx,
                                     force=(arg == 'harder'))
    session.ui.reset_marks()
  except KeyboardInterrupt:
    session.ui.mark('Aborted')
    session.ui.reset_marks()
  return True

def Action(session, opt, arg):
  config = session.config
  num_results = config.get('num_results', 20)

  if not opt or opt in ('h', 'help'):
    session.ui.print_help(COMMANDS,
                          session.config.get('tag', {}).values())

  elif opt in ('A', 'add'):
    if os.path.exists(arg):
      arg = os.path.abspath(arg)
      if config.parse_set(session,
                          'mailbox:%s=%s' % (config.nid('mailbox'), arg)):
        config.slow_worker.add_task(None, 'Save config', lambda: config.save())
    else:
      session.error('No such file/directory: %s' % arg)

  elif opt in ('T', 'addtag'):
    if (arg
    and ' ' not in arg
    and arg.lower() not in [v.lower() for v in config['tag'].values()]):
      if config.parse_set(session,
                          'tag:%s=%s' % (config.nid('tag'), arg)):
        config.slow_worker.add_task(None, 'Save config', lambda: config.save())
    else:
      session.error('Invalid tag: %s' % arg)

  elif opt in ('F', 'filter'):
    Action_Filter(session, opt, arg)

  elif opt in ('O', 'optimize'):
    config.slow_worker.do(session, 'Optimize',
                          lambda: Action_Optimize(session, config, arg))

  elif opt in ('P', 'print'):
    session.ui.print_key(arg.strip().lower(), config)

  elif opt in ('U', 'unset'):
    if config.parse_unset(session, arg):
      config.slow_worker.add_task(None, 'Save config', lambda: config.save())

  elif opt in ('S', 'set'):
    if config.parse_set(session, arg):
      config.slow_worker.add_task(None, 'Save config', lambda: config.save())

  elif opt in ('R', 'rescan'):
    Action_Load(session, config)
    config.slow_worker.do(session, 'Rescan',
                          lambda: Action_Rescan(session, config))

  elif opt in ('L', 'load'):
    Action_Load(session, config, reset=True)

  elif opt in ('n', 'next'):
    idx = Action_Load(session, config)
    session.ui.reset_marks()
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   start=pos+count,
                                                   num=num_results)
    session.ui.reset_marks()

  elif opt in ('p', 'previous'):
    idx = Action_Load(session, config)
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   end=pos,
                                                   num=num_results)
    session.ui.reset_marks()

  elif opt in ('t', 'tag'):
    Action_Tag(session, opt, arg)

  elif opt in ('o', 'order'):
    idx = Action_Load(session, config)
    session.order = arg or None
    idx.sort_results(session, session.results,
                     how=session.order)
    session.displayed = session.ui.display_results(idx, session.results,
                                                   num=num_results)
    session.ui.reset_marks()

  elif (opt in ('s', 'search')
        or opt.lower() in [t.lower() for t in config['tag'].values()]):
    idx = Action_Load(session, config)

    # FIXME: This is all rather dumb.  Make it smarter!
    if opt not in ('s', 'search'):
      tid = [t for t in config['tag'] if config['tag'][t].lower() == opt.lower()]
      session.searched = ['tag:%s' % tid[0]]
    elif ':' in arg or '-' in arg or '+' in arg:
      session.searched = arg.lower().split()
    else:
      session.searched = re.findall(WORD_REGEXP, arg.lower())

    session.results = list(idx.search(session, session.searched))
    idx.sort_results(session, session.results,
                     how=session.order)
    session.displayed = session.ui.display_results(idx, session.results,
                                                   num=num_results)
    session.ui.reset_marks()

  elif opt in ('v', 'view'):
    args = arg.split()
    if args and args[0].lower() == 'raw':
      raw = args.pop(0)
    else:
      raw = False
    idx = Action_Load(session, config)
    emails = [Email(idx, i) for i in Choose_Messages(session, args)]
    session.ui.display_messages(emails, raw=raw)
    session.ui.reset_marks()

  else:
    raise UsageError('Unknown command: %s' % opt)


def Interact(session):
  import readline
  try:
    readline.read_history_file(session.config.history_file())
  except IOError:
    pass
  readline.set_history_length(100)

  try:
    while True:
      session.ui.block()
      opt = raw_input('mailpile> ').decode('utf-8').strip()
      session.ui.unblock()
      if opt:
        if ' ' in opt:
          opt, arg = opt.split(' ', 1)
        else:
          arg = ''
        try:
          Action(session, opt, arg)
        except UsageError, e:
          session.error(e)
  except EOFError:
    print

  readline.write_history_file(session.config.history_file())


##[ Web and XML-RPC Interface ]###############################################


class HttpRequestHandler(SimpleXMLRPCRequestHandler):

  PAGE_HEAD = "<html><head>"
  PAGE_LANDING_CSS = """\
 body {text-align: center; background: #f7f7f7; color: #000; font-size: 2em; font-family: monospace; padding-top: 50px;}
 #search input {width: 170px;}"""
  PAGE_CONTENT_CSS = """\
 body {background: #f7f7f7; font-family: monospace; color: #000;}
 body, div, h1, #header {padding: 0; margin: 0;}
 #heading, #pile {padding: 5px 10px;}
 #heading {font-size: 3.75em; padding-left: 15px; padding-top: 15px; display: inline-block;}
 #pile {z-index: -3; color: #666; font-size: 0.6em; position: absolute; top: 0; left: 0; text-align: center;}
 #search {display: inline-block;}
 #search input {width: 400px;}"""
  PAGE_BODY = """\
</head><body><div id=header>
 <h1 id=heading>M<span style="font-size: 0.8em;">AILPILE</span>!</h1>
 <form method=post id=search><input type="text" size=100 name="q">
 <input type=hidden name=sid value='%(session_id)s'></form>
 <p id=pile>to: from:<br>subject: email<br>@ to: subject: list-id:<br>envelope
 from: to sender: spam to:<br>from: search GMail @ in-reply-to: GPG bounce<br>
 subscribe 419 v1agra from: envelope-to: @ SMTP hello!</p>
</div><div id=content>"""
  PAGE_TAIL = "</div></body></html>"

  def send_standard_headers(self, header_list=[],
                            cachectrl='private', mimetype='text/html'):
    if mimetype.startswith('text/') and ';' not in mimetype:
      mimetype += ('; charset=utf-8')
    self.send_header('Cache-Control', cachectrl)
    self.send_header('Content-Type', mimetype)
    for header in header_list:
      self.send_header(header[0], header[1])
    self.end_headers()

  def send_full_response(self, message, code=200, msg='OK', mimetype='text/html',
                         header_list=[], suppress_body=False):
    message = unicode(message).encode('utf-8')
    self.log_request(code, message and len(message) or '-')
    self.wfile.write('HTTP/1.1 %s %s\r\n' % (code, msg))
    if code == 401:
      self.send_header('WWW-Authenticate',
                       'Basic realm=MP%d' % (time.time()/3600))
    self.send_header('Content-Length', len(message or ''))
    self.send_standard_headers(header_list=header_list, mimetype=mimetype)
    if not suppress_body:
      self.wfile.write(message or '')

  def render_page(self, body='', title=None, css=None, variables=None):
    title = title or 'A huge pile of mail'
    variables = variables or {'session_id': ''}
    css = css or (body and self.PAGE_CONTENT_CSS or self.PAGE_LANDING_CSS)
    return '\n'.join([self.PAGE_HEAD % variables,
                      '<title>', title, '</title>',
                      '<style type="text/css">', css, '</style>',
                      self.PAGE_BODY % variables, body,
                      self.PAGE_TAIL % variables])

  def do_POST(self):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    if path.startswith('/xmlrpc/'):
      return SimpleXMLRPCRequestHandler.do_POST(self)

    post_data = { }
    try:
      clength = int(self.headers.get('content-length'))
      ctype, pdict = cgi.parse_header(self.headers.get('content-type'))
      if ctype == 'multipart/form-data':
        post_data = cgi.parse_multipart(self.rfile, pdict)
      elif ctype == 'application/x-www-form-urlencoded':
        if clength > 5*1024*1024:
          raise ValueError('OMG, input too big')
        post_data = cgi.parse_qs(self.rfile.read(clength), 1)
      else:
        raise ValueError('Unknown content-type')

    except (IOError, ValueError), e:
      body = 'POST geborked: %s' % e
      vlist = {'session_id': ''}
      self.send_full_response(self.render_page(body=body,
                                               title='Internal Error',
                                               variables=vlist),
                              code=500)
      return None
    return self.do_GET(post_data=post_data)

  def do_HEAD(self):
    return self.do_GET(suppress_body=True)

  def do_GET(self, post_data={}, suppress_body=False):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    query_data = parse_qs(query)

    session_id = post_data.get('sid', query_data.get('sid', [None]))[0]
    session_id, session = self.server.get_session(session_id, create=HtmlUI)

    args = post_data.get('q', query_data.get('q', ['']))[0].split()
    if args:
      try:
        Action(session, args[0], ' '.join(args[1:]))
        body = session.ui.render_html()
        title = 'Uhm'
      except UsageError, e:
        body = 'Oops: %s' % e
        title = 'Error'
    else:
      body = ''
      title = None

    variables = {
      'session_id': session_id
    }
    self.send_full_response(self.render_page(body=body,
                                             title=title,
                                             variables=variables),
                            suppress_body=suppress_body)

  def log_message(self, fmt, *args):
    self.server.session.ui.say(fmt % (args))


class HttpServer(SocketServer.ThreadingMixIn, SimpleXMLRPCServer):
  def __init__(self, session, sspec, handler):
    SimpleXMLRPCServer.__init__(self, sspec, handler)
    self.session = session
    self.sessions = {}
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sspec = (sspec[0] or 'localhost', self.socket.getsockname()[1])

  def get_session(self, sid=None, create=False):
    if not sid: sid = b36(int(time.time())) # FIXME: Insecure
    if sid not in self.sessions:
      if create:
        session = Session(self.session.config)
        session.ui = create()
        self.sessions[sid] = session
      else:
        return (sid, None)
    return (sid, self.sessions[sid])


class HttpWorker(threading.Thread):
  def __init__(self, session, sspec):
    threading.Thread.__init__(self)
    self.httpd = HttpServer(session, sspec, HttpRequestHandler)
    self.session = session

  def run(self):
    self.httpd.serve_forever()

  def quit(self):
    self.httpd.shutdown()


##[ Main ]####################################################################

if __name__ == "__main__":
  re.UNICODE = 1
  re.LOCALE = 1

  try:
    # Create our global config manager and the default (CLI) session
    config = ConfigManager()
    session = Session(config)
    session.config.load(session)
    session.main = True
    session.ui = TextUI()
  except AccessError, e:
    sys.stderr.write('Access denied: %s\n' % e)
    sys.exit(1)

  try:
    # Create and start worker threads
    config.slow_worker = Worker('Slow worker', session)
    config.slow_worker.start()

    # Start the HTTP worker?
    sspec = (config.get('http_host', 'localhost'),
             config.get('http_port', DEFAULT_PORT))
    if sspec[0].lower() != 'disabled' and sspec[1] >= 0:
      config.http_worker = HttpWorker(session, sspec)
      config.http_worker.start()

    # Set globals from config here ...
    APPEND_FD_CACHE_SIZE = session.config.get('fd_cache_size',
                                              APPEND_FD_CACHE_SIZE)

    try:
      opts, args = getopt.getopt(sys.argv[1:],
                                 ''.join(COMMANDS.keys()),
                                 [v[0] for v in COMMANDS.values()])
      for opt, arg in opts:
        Action(session, opt.replace('-', ''), arg)
      if args:
        Action(session, args[0], ' '.join(args[1:]))

    except (getopt.GetoptError, UsageError), e:
      session.error(e)

    if not opts and not args:
      config.slow_worker.add_task(None, 'Load',
                                  lambda: Action_Load(None, config))
      session.interactive = session.ui.interactive = True
      session.ui.print_intro(help=True, http_worker=config.http_worker)
      Interact(session)

  finally:
    for w in (config.http_worker, config.slow_worker):
      if w: w.quit()

