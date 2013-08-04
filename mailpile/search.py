#!/usr/bin/env python2.7
import cgi
import codecs
import datetime
import getopt
import email
import hashlib
import locale
import mailbox
import os
import cPickle
import random
import re
import rfc822
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import SocketServer
from urlparse import parse_qs, urlparse
import lxml.html

import mailpile.plugins as plugins
import mailpile.util
from mailpile.util import *
from mailpile.mailutils import NoSuchMailboxError, ExtractEmails, ParseMessage, HeaderPrint
from mailpile.ui import *


class PostingList(object):
  """A posting list is a map of search terms to message IDs."""

  CHARACTERS = 'abcdefghijklmnopqrstuvwxyz0123456789+_'

  MAX_SIZE = 60  # perftest gives: 75% below 500ms, 50% below 100ms
  HASH_LEN = 24

  @classmethod
  def Optimize(cls, session, idx, force=False):
    flush_append_cache()

    postinglist_kb = session.config.get('postinglist_kb', cls.MAX_SIZE)

    # Pass 1: Compact all files that are 90% or more of our target size
    for c in cls.CHARACTERS:
      postinglist_dir = session.config.postinglist_dir(c)
      for fn in sorted(os.listdir(postinglist_dir)):
        if mailpile.util.QUITTING: break
        if (force
        or  os.path.getsize(os.path.join(postinglist_dir, fn)) >
                                                        900*postinglist_kb):
          session.ui.mark('Pass 1: Compacting >%s<' % fn)
          # FIXME: Remove invalid and deleted messages from posting lists.
          cls(session, fn, sig=fn).save()

    # Pass 2: While mergable pair exists: merge them!
    flush_append_cache()
    for c in cls.CHARACTERS:
      postinglist_dir = session.config.postinglist_dir(c)
      files = [n for n in os.listdir(postinglist_dir) if len(n) > 1]
      files.sort(key=lambda a: -len(a))
      for fn in files:
        if mailpile.util.QUITTING: break
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
    filecount = 0
    for c in cls.CHARACTERS:
      filecount += len(os.listdir(session.config.postinglist_dir(c)))
    session.ui.mark('Optimized %s posting lists' % filecount)
    return filecount

  @classmethod
  def Append(cls, session, word, mail_ids, compact=True, sig=None):
    config = session.config
    sig = sig or cls.WordSig(word, config)
    fd, fn = cls.GetFile(session, sig, mode='a')
    if (compact
    and (os.path.getsize(os.path.join(config.postinglist_dir(fn), fn)) >
             (1024*config.get('postinglist_kb', cls.MAX_SIZE))-(cls.HASH_LEN*6))
    and (random.randint(0, 50) == 1)):
      # This will compact the files and split out hot-spots, but we only bother
      # "once in a while" when the files are "big".
      fd.close()
      pls = cls(session, word, sig=sig)
      for mail_id in mail_ids:
        pls.append(mail_id)
      pls.save()
    else:
      # Quick and dirty append is the default.
      fd.write('%s\t%s\n' % (sig, '\t'.join(mail_ids)))

  @classmethod
  def WordSig(cls, word, config):
    return strhash(word, cls.HASH_LEN, obfuscate=config.get('obfuscate_index'))

  @classmethod
  def SaveFile(cls, session, prefix):
    return os.path.join(session.config.postinglist_dir(prefix), prefix)

  @classmethod
  def GetFile(cls, session, sig, mode='r'):
    sig = sig[:cls.HASH_LEN]
    while len(sig) > 0:
      fn = cls.SaveFile(session, sig)
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

  def __init__(self, session, word, sig=None, config=None):
    self.config = config or session.config
    self.session = session
    self.sig = sig or self.WordSig(word, self.config)
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
    fd, self.filename = self.GetFile(self.session, self.sig)
    if fd:
      try:
        self.size = decrypt_and_parse_lines(fd, self.parse_line)
      except ValueError:
        pass
      finally:
        fd.close()

  def fmt_file(self, prefix):
    output = []
    self.session.ui.mark('Formatting prefix %s' % unicode(prefix))
    for word in self.WORDS.keys():
      data = self.WORDS.get(word, [])
      if ((prefix == 'ALL' or word.startswith(prefix)) and len(data) > 0):
        output.append('%s\t%s\n' % (word, '\t'.join(['%s' % x for x in data])))
    return ''.join(output)

  def compact(self, prefix, output):
    while (len(output) > 1024*self.config.get('postinglist_kb', self.MAX_SIZE)
    and    len(prefix) < self.HASH_LEN):
      biggest = self.sig
      for word in self.WORDS:
        if len(self.WORDS.get(word, [])) > len(self.WORDS.get(biggest, [])):
          biggest = word
      if len(biggest) > len(prefix):
        biggest = biggest[:len(prefix)+1]
        self.save(prefix=biggest, mode='a')
        for key in [k for k in self.WORDS if k.startswith(biggest)]:
          del self.WORDS[key]
        output = self.fmt_file(prefix)
    return prefix, output

  def save(self, prefix=None, compact=True, mode='w'):
    prefix = prefix or self.filename
    output = self.fmt_file(prefix)
    if compact:
      prefix, output = self.compact(prefix, output)
    try:
      outfile = self.SaveFile(self.session, prefix)
      self.session.ui.mark('Writing %d bytes to %s' % (len(output), outfile))
      if output:
        try:
          fd = cached_open(outfile, mode)
          fd.write(output)
          return len(output)
        finally:
          if mode != 'a': fd.close()
      elif os.path.exists(outfile):
        os.remove(outfile)
        flush_append_cache()
    except:
      self.session.ui.warning('%s' % (sys.exc_info(), ))
    return 0

  def hits(self):
    return self.WORDS[self.sig]

  def append(self, eid):
    if self.sig not in self.WORDS:
      self.WORDS[self.sig] = set()
    self.WORDS[self.sig].add(eid)
    return self

  def remove(self, eids):
    for eid in eids:
      try:
        self.WORDS[self.sig].remove(eid)
      except KeyError:
        pass
    return self


GLOBAL_POSTING_LIST = None
class GlobalPostingList(PostingList):

  @classmethod
  def Optimize(cls, session, idx, force=False, quick=False):
    pls = GlobalPostingList(session, '')
    count = 0
    keys = sorted(GLOBAL_POSTING_LIST.keys())
    for sig in keys:
      if (count % 50) == 0:
        session.ui.mark(('Updating search index... %d%% (%s)'
                         ) % (count*100 / len(keys), sig))
      pls.migrate(sig, compact=quick)
      count += 1
    pls.save()

    if quick:
      return count
    else:
      return PostingList.Optimize(session, idx, force=force)

  @classmethod
  def SaveFile(cls, session, prefix):
    return os.path.join(session.config.workdir(), 'kw-journal.dat')

  @classmethod
  def GetFile(cls, session, sig, mode='r'):
    try:
      return (cached_open(cls.SaveFile(session, sig), mode), 'kw-journal.dat')
    except (IOError, OSError):
      return (None, 'kw-journal.dat')

  @classmethod
  def Append(cls, session, word, mail_ids, compact=True):
    super(GlobalPostingList, cls).Append(session, word, mail_ids, compact=compact)
    global GLOBAL_POSTING_LIST
    sig = cls.WordSig(word, session.config)
    if GLOBAL_POSTING_LIST is None:
      GLOBAL_POSTING_LIST = {}
    if sig not in GLOBAL_POSTING_LIST:
      GLOBAL_POSTING_LIST[sig] = set()
    for mail_id in mail_ids:
      GLOBAL_POSTING_LIST[sig].add(mail_id)

  def fmt_file(self, prefix):
    return PostingList.fmt_file(self, 'ALL')

  def load(self):
    self.filename = 'kw-journal.dat'
    global GLOBAL_POSTING_LIST
    if GLOBAL_POSTING_LIST:
      self.WORDS = GLOBAL_POSTING_LIST
    else:
      PostingList.load(self)
      GLOBAL_POSTING_LIST = self.WORDS

  def compact(self, prefix, output):
    return prefix, output

  def migrate(self, sig=None, compact=True):
    sig = sig or self.sig
    if sig in self.WORDS and len(self.WORDS[sig]) > 0:
      PostingList.Append(self.session, sig, self.WORDS[sig],
                         sig=sig, compact=compact)
      del self.WORDS[sig]

  def remove(self, eids):
    PostingList(self.session, self.word,
                sig=self.sig, config=self.config).remove(eids).save()
    return PostingList.remove(self, eids)

  def hits(self):
    return (self.WORDS.get(self.sig, set())
           | PostingList(self.session, self.word,
                         sig=self.sig, config=self.config).hits())


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
    self.STATS = {}
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}
    self.CACHE = {}
    self.MODIFIED = set()

  def l2m(self, line):
    return line.decode('utf-8').split(u'\t')

  def m2l(self, message):
    return (u'\t'.join([unicode(p) for p in message])).encode('utf-8')

  def load(self, session=None):
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}
    def process_line(line):
      try:
        line = line.strip()
        if line and not line.startswith('#'):
          pos, ptrs, junk, msgid, rest = line.split('\t', 4)
          pos = int(pos, 36)
          while len(self.INDEX) < pos+1:
            self.INDEX.append('')
          self.INDEX[pos] = line
          self.MSGIDS[msgid] = pos
          for msg_ptr in ptrs:
            self.PTRS[msg_ptr] = pos
      except ValueError:
        pass
    if session: session.ui.mark('Loading metadata index...')
    try:
      fd = open(self.config.mailindex_file(), 'r')
      for line in fd:
        if line.startswith(GPG_BEGIN_MESSAGE):
          for line in decrypt_gpg([line], fd):
            process_line(line)
        else:
          process_line(line)
      fd.close()
    except IOError:
      if session: session.ui.warning(('Metadata index not found: %s'
                                      ) % self.config.mailindex_file())
    if session:
      session.ui.mark('Loaded metadata for %d messages' % len(self.INDEX))

  def save_changes(self, session=None):
    mods, self.MODIFIED = self.MODIFIED, set()
    if mods:
      if session: session.ui.mark("Saving metadata index changes...")
      fd = gpg_open(self.config.mailindex_file(),
                    self.config.get('gpg_recipient'), 'a')
      for pos in mods:
        fd.write(self.INDEX[pos] + '\n')
      fd.close()
      flush_append_cache()
      if session: session.ui.mark("Saved metadata index changes")

  def save(self, session=None):
    self.MODIFIED = set()
    if session: session.ui.mark("Saving metadata index...")
    fd = gpg_open(self.config.mailindex_file(),
                  self.config.get('gpg_recipient'), 'w')
    fd.write('# This is the mailpile.py index file.\n')
    fd.write('# We have %d messages!\n' % len(self.INDEX))
    for item in self.INDEX:
      fd.write(item + '\n')
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

  def try_decode(self, text, charset):
    for cs in (charset, 'iso-8859-1', 'utf-8'):
      if cs:
        try:
          return text.decode(cs)
        except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
          pass
    return "".join(i for i in text if ord(i)<128)

  def hdr(self, msg, name, value=None):
    try:
      if value is None and msg:
        value = msg[name]
      decoded = email.header.decode_header(value or '')
      return (' '.join([self.try_decode(t[0], t[1]) for t in decoded])
              ).replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')
    except email.errors.HeaderParseError:
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
    try:
      mbox = mailbox_opener(session, idx)
      if mbox.editable:
        session.ui.mark('%s: Skipped: %s' % (idx, mailbox_fn))
        return 0
      else:
        session.ui.mark('%s: Checking: %s' % (idx, mailbox_fn))
    except (IOError, OSError, NoSuchMailboxError):
      session.ui.mark('%s: Error opening: %s' % (idx, mailbox_fn))
      return 0

    unparsed = mbox.unparsed()
    if not unparsed:
      return 0

    if len(self.PTRS.keys()) == 0:
      self.update_ptrs_and_msgids(session)

    added = 0
    msg_date = int(time.time())
    for ui in range(0, len(unparsed)):
      if mailpile.util.QUITTING: break

      i = unparsed[ui]
      parse_status = ('%s: Reading your mail: %d%% (%d/%d messages)'
                      ) % (idx, 100 * ui/len(unparsed), ui, len(unparsed))

      msg_ptr = mbox.get_msg_ptr(idx, i)
      if msg_ptr in self.PTRS:
        if (ui % 317) == 0: session.ui.mark(parse_status)
        continue
      else:
        session.ui.mark(parse_status)

      # Message new or modified, let's parse it.
      msg = ParseMessage(mbox.get_file(i), pgpmime=False)
      msg_id = b64c(sha1b64((self.hdr(msg, 'message-id') or msg_ptr).strip()))
      if msg_id in self.MSGIDS:
        self.update_location(session, self.MSGIDS[msg_id], msg_ptr)
        added += 1
      else:
        # Add new message!
        msg_mid = b36(len(self.INDEX))

        try:
          last_date = msg_date
          msg_date = int(rfc822.mktime_tz(
                                   rfc822.parsedate_tz(self.hdr(msg, 'date'))))
          if msg_date > (time.time() + 24*3600):
            session.ui.warning('=%s/%s is from the FUTURE!' % (msg_mid, msg_id))
            # Messages from the future are treated as today's
            msg_date = last_date + 1
          elif msg_date < 1:
            session.ui.warning('=%s/%s is PREHISTORIC!' % (msg_mid, msg_id))
            msg_date = last_date + 1

        except (ValueError, TypeError, OverflowError):
          session.ui.warning('=%s/%s has a bogus date.' % (msg_mid, msg_id))
          if session.config.get('debug'):
            session.ui.say(traceback.format_exc())
          # This is a hack: We assume the messages in the mailbox are in
          # chronological order and just add 1 second to the date of the last
          # message.  This should be a better-than-nothing guess.
          msg_date += 1

        keywords = self.index_message(session, msg_mid, msg_id, msg, msg_date,
                                      mailbox=idx, compact=False,
                                      filter_hooks=[self.filter_keywords])
        tags = [k.split(':')[0] for k in keywords if k.endswith(':tag')]

        msg_idx = len(self.INDEX)
        self.set_msg_by_idx(msg_idx,
                            [msg_mid,                   # Our index ID
                             msg_ptr,                   # Location on disk
                             '',                        # UNUSED
                             msg_id,                    # Message-ID
                             b36(msg_date),             # Date as a UTC timestamp
                             self.hdr(msg, 'from'),     # From:
                             self.hdr(msg, 'subject'),  # Subject
                             ','.join(tags),            # Initial tags
                             '',                        # No replies for now
                             ''])                       # Conversation ID
        self.set_conversation_ids(msg_mid, msg)

        added += 1
        if (added % 1000) == 0:
          GlobalPostingList.Optimize(session, self, quick=True)

    if added:
      mbox.mark_parsed(i)
      mbox.save(session)
    session.ui.mark('%s: Indexed mailbox: %s' % (idx, mailbox_fn))
    return added

  def set_conversation_ids(self, msg_mid, msg):
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
        replies = parent[self.MSG_REPLIES][:-1].split(',')
        if msg_mid not in replies:
          replies.append(msg_mid)
        parent[self.MSG_REPLIES] = ','.join(replies)+','
        self.set_msg_by_idx(int(msg_conv, 36), parent)
        break
      except (KeyError, ValueError, IndexError):
        pass

    msg_idx = int(msg_mid, 36)
    msg_info = self.get_msg_by_idx(msg_idx)

    if not msg_conv:
      # Can we do plain GMail style subject-based threading?
      # FIXME: Is this too aggressive? Make configurable?
      subj = msg_info[self.MSG_SUBJECT].lower().replace('re: ', '')
      date = long(msg_info[self.MSG_DATE], 36)
      for midx in reversed(range(max(0, msg_idx - 250), msg_idx)):
        try:
          m_info = self.get_msg_by_idx(midx)
          if m_info[self.MSG_SUBJECT].lower().replace('re: ', '') == subj:
            msg_conv = m_info[self.MSG_CONV_ID]
            parent = self.get_msg_by_idx(int(msg_conv, 36))
            replies = parent[self.MSG_REPLIES][:-1].split(',')
            if len(replies) < 100:
              if msg_mid not in replies:
                replies.append(msg_mid)
              parent[self.MSG_REPLIES] = ','.join(replies)+','
              self.set_msg_by_idx(int(msg_conv, 36), parent)
              break
          if date - long(m_info[self.MSG_DATE], 36) > 5*24*3600:
            break
        except (KeyError, ValueError, IndexError):
          pass

    if not msg_conv:
      # OK, we are our own conversation root.
      msg_conv = msg_mid

    msg_info[self.MSG_CONV_ID] = msg_conv
    self.set_msg_by_idx(msg_idx, msg_info)

  def add_new_msg(self, msg_ptr, msg_id, msg_date, msg_from, msg_subject, tags):
    msg_idx = len(self.INDEX)
    msg_mid = b36(msg_idx)
    msg_info = [
      msg_mid,                                     # Index ID
      msg_ptr,                                     # Location on disk
      '',                                          # UNUSED
      b64c(sha1b64((msg_id or msg_ptr).strip())),  # Message ID
      b36(msg_date),                               # Date as a UTC timstamp
      msg_from,                                    # From:
      msg_subject,                                 # Subject
      ','.join(tags),                              # Initial tags
      '',                                          # No replies for now
      msg_mid                                      # Conversation ID
    ]
    self.set_msg_by_idx(msg_idx, msg_info)
    return msg_idx, msg_info

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

  def apply_filters(self, session, filter_on, msg_mids=None, msg_idxs=None):
    if msg_idxs is None:
      msg_idxs = [int(mid, 36) for mid in msg_mids]
    if not msg_idxs:
      return
    for fid, trms, tags, c in session.config.get_filters(filter_on=filter_on):
      for t in tags.split():
        tag_id = t[1:].split(':')[0]
        if t[0] == '-':
          self.remove_tag(session, tag_id, msg_idxs=set(msg_idxs))
        else:
          self.add_tag(session, tag_id, msg_idxs=set(msg_idxs))

  def message_keywords(self, session, msg_mid, msg_id, msg, msg_date,
                       mailbox=None):
    keywords = []
    payload = [None]
    for part in msg.walk():
      textpart = payload[0] = None
      ctype = part.get_content_type()
      charset = part.get_charset() or 'iso-8859-1'
      def _loader(p):
        if payload[0] is None:
          payload[0] = self.try_decode(p.get_payload(None, True), charset)
        return payload[0]
      if ctype == 'text/plain':
        textpart = _loader(part)
      elif ctype == 'text/html':
        _loader(part)
        if len(payload[0]) > 3:
          try:
            textpart = lxml.html.fromstring(payload[0]).text_content()
          except:
            session.ui.warning('=%s/%s has bogus HTML.' % (msg_mid, msg_id))
            textpart = payload[0]
        else:
          textpart = payload[0]
      elif 'pgp' in part.get_content_type():
        keywords.append('pgp:has')

      att = part.get_filename()
      if att:
        att = self.try_decode(att, charset)
        keywords.append('attachment:has')
        keywords.extend([t+':att' for t in re.findall(WORD_REGEXP, att.lower())])
        textpart = (textpart or '') + ' ' + att

      if textpart:
        # FIXME: Does this lowercase non-ASCII characters correctly?
        # FIXME: What about encrypted content?
        keywords.extend(re.findall(WORD_REGEXP, textpart.lower()))
        # FIXME: Do this better.
        if '-----BEGIN PGP' in textpart and '-----END PGP' in textpart:
          keywords.append('pgp:has')
        for extract in plugins.get_text_kw_extractors():
          keywords.extend(extract(self, msg, ctype, lambda: textpart))

      for extract in plugins.get_data_kw_extractors():
        keywords.extend(extract(self, msg, ctype, att, part,
                                lambda: _loader(part)))

    keywords.append('%s:id' % msg_id)
    keywords.extend(re.findall(WORD_REGEXP, self.hdr(msg, 'subject').lower()))
    keywords.extend(re.findall(WORD_REGEXP, self.hdr(msg, 'from').lower()))
    if mailbox: keywords.append('%s:mailbox' % mailbox.lower())
    keywords.append('%s:hprint' % HeaderPrint(msg))

    for key in msg.keys():
      key_lower = key.lower()
      if key_lower not in BORING_HEADERS:
        emails = ExtractEmails(self.hdr(msg, key).lower())
        words = set(re.findall(WORD_REGEXP, self.hdr(msg, key).lower()))
        words -= STOPLIST
        keywords.extend(['%s:%s' % (t, key_lower) for t in words])
        keywords.extend(['%s:%s' % (e, key_lower) for e in emails])
        keywords.extend(['%s:email' % e for e in emails])
        if 'list' in key_lower:
          keywords.extend(['%s:list' % t for t in words])

    for extract in plugins.get_meta_kw_extractors():
      keywords.extend(extract(self, msg_mid, msg, msg_date))

    return (set(keywords) - STOPLIST)

  def index_message(self, session, msg_mid, msg_id, msg, msg_date,
                    mailbox=None, compact=True, filter_hooks=[]):
    keywords = self.message_keywords(session, msg_mid, msg_id, msg, msg_date,
                                     mailbox=mailbox)

    for hook in filter_hooks:
      keywords = hook(session, msg_mid, msg, keywords)

    for word in keywords:
      try:
        GlobalPostingList.Append(session, word, [msg_mid], compact=compact)
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
      return [None, None, None, None, b36(0),
              '(not in index)', '(not in index: %s)' % msg_idx, '', '', '-1']

  def set_msg_by_idx(self, msg_idx, msg_info):
    self.MODIFIED.add(msg_idx)
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

  def get_conversation(self, msg_info=None, msg_idx=None):
    if not msg_info:
      msg_info = self.get_msg_by_idx(msg_idx)
    conv_id = msg_info[self.MSG_CONV_ID]
    if conv_id:
      return ([self.get_msg_by_idx(int(conv_id, 36))] +
              self.get_replies(msg_idx=int(conv_id, 36)))
    else:
      return [msg_info]

  def get_replies(self, msg_info=None, msg_idx=None):
    if not msg_info:
      msg_info = self.get_msg_by_idx(msg_idx)
    return [self.get_msg_by_idx(int(r, 36)) for r
            in msg_info[self.MSG_REPLIES].split(',') if r]

  def get_tags(self, msg_info=None, msg_idx=None):
    if not msg_info: msg_info = self.get_msg_by_idx(msg_idx)
    return [r for r in msg_info[self.MSG_TAGS].split(',') if r]

  def add_tag(self, session, tag_id,
              msg_info=None, msg_idxs=None, conversation=False):
    pls = GlobalPostingList(session, '%s:tag' % tag_id)
    if msg_info and msg_idxs is None:
      msg_idxs = set([int(msg_info[self.MSG_IDX], 36)])
    session.ui.mark('Tagging %d messages (%s)' % (len(msg_idxs), tag_id))
    for msg_idx in list(msg_idxs):
      if conversation:
        for reply in self.get_conversation(msg_idx=msg_idx):
          if reply[self.MSG_IDX]:
            msg_idxs.add(int(reply[self.MSG_IDX], 36))
          if msg_idx % 1000 == 0: self.CACHE = {}
    for msg_idx in msg_idxs:
      if msg_idx >= 0 and msg_idx < len(self.INDEX):
        msg_info = self.get_msg_by_idx(msg_idx)
        tags = set([r for r in msg_info[self.MSG_TAGS].split(',') if r])
        tags.add(tag_id)
        msg_info[self.MSG_TAGS] = ','.join(list(tags))
        self.INDEX[msg_idx] = self.m2l(msg_info)
        self.MODIFIED.add(msg_idx)
        pls.append(msg_info[self.MSG_IDX])
      if msg_idx % 1000 == 0: self.CACHE = {}
    pls.save()
    self.CACHE = {}

  def remove_tag(self, session, tag_id,
                 msg_info=None, msg_idxs=None, conversation=False):
    pls = GlobalPostingList(session, '%s:tag' % tag_id)
    if msg_info and msg_idxs is None:
      msg_idxs = set([int(msg_info[self.MSG_IDX], 36)])
    if not msg_idxs:
      return
    session.ui.mark('Untagging conversations (%s)' % (tag_id, ))
    for msg_idx in list(msg_idxs):
      if conversation:
        for reply in self.get_conversation(msg_idx=msg_idx):
          if reply[self.MSG_IDX]:
            msg_idxs.add(int(reply[self.MSG_IDX], 36))
          if msg_idx % 1000 == 0: self.CACHE = {}
    session.ui.mark('Untagging %d messages (%s)' % (len(msg_idxs), tag_id))
    eids = []
    for msg_idx in msg_idxs:
      if msg_idx >= 0 and msg_idx < len(self.INDEX):
        msg_info = self.get_msg_by_idx(msg_idx)
        tags = set([r for r in msg_info[self.MSG_TAGS].split(',') if r])
        if tag_id in tags:
          tags.remove(tag_id)
          msg_info[self.MSG_TAGS] = ','.join(list(tags))
          self.INDEX[msg_idx] = self.m2l(msg_info)
          self.MODIFIED.add(msg_idx)
        eids.append(msg_info[self.MSG_IDX])
      if msg_idx % 1000 == 0: self.CACHE = {}
    pls.remove(eids)
    pls.save()
    self.CACHE = {}

  def search_tag(self, term, hits):
    t = term.split(':', 1)
    t[1] = self.config.get_tag_id(t[1]) or t[1]
    return hits('%s:%s' % (t[1], t[0]))

  def search(self, session, searchterms, keywords=None):
    if keywords:
      def hits(term):
        return [int(h, 36) for h in keywords.get(term, [])]
    else:
      def hits(term):
        session.ui.mark('Searching for %s' % term)
        return [int(h, 36) for h in GlobalPostingList(session, term).hits()]

    # Replace some GMail-compatible terms with what we really use
    for p in ('', '+', '-'):
      while p+'is:unread' in searchterms:
        searchterms[searchterms.index(p+'is:unread')] = p+'tag:New'
      while p+'in:spam' in searchterms:
        searchterms[searchterms.index(p+'in:spam')] = p+'tag:Spam'
      while p+'in:trash' in searchterms:
        searchterms[searchterms.index(p+'in:trash')] = p+'tag:Trash'

    # If first term is a negative search, prepend an all:mail
    if searchterms and searchterms[0] and searchterms[0][0] == '-':
      searchterms[:0] = ['all:mail']

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

      if ':' in term:
        # FIXME: Make search words pluggable!
        if term.startswith('body:'):
          rt.extend(hits(term[5:]))
        elif term == 'all:mail':
          rt.extend(range(0, len(self.INDEX)))
        elif term.startswith('tag:'):
          rt.extend(self.search_tag(term, hits))
        else:
          t = term.split(':', 1)
          fnc = plugins.get_search_term(t[0])
          if fnc:
            rt.extend(fnc(self.config, term, hits))
          else:
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
        results -= set([len(self.INDEX)])
    else:
      results = set()

    if session:
      session.ui.mark('Found %d results' % len(results))
    return results

  def sort_results(self, session, results, how=None):
    force = how or False
    how = how or self.config.get('default_order', 'reverse_date')
    sign = how.startswith('rev') and -1 or 1
    sort_max = self.config.get('sort_max', 2500)
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
      conversations = [(r, int(self.get_msg_by_idx(r)[self.MSG_CONV_ID], 36))
                       for r in results]
      results[:] = []
      chash = {}
      for r, c in conversations:
        if c not in chash:
          results.append(r)
          chash[c] = 1

    results.extend(leftovers)

    session.ui.mark('Sorted messages in %s order' % how)
    return True

  def update_tag_stats(self, session, config, update_tags=None):
    session = session or Session(config)
    new_tid = config.get_tag_id('new')
    new_msgs = (new_tid and GlobalPostingList(session, '%s:tag' % new_tid).hits()
                         or set([]))
    self.STATS.update({
      'ALL': [len(self.INDEX), len(new_msgs)]
    })
    for tid in (update_tags or config.get('tag', {}).keys()):
      if session: session.ui.mark('Counting messages in tag:%s' % tid)
      hits = GlobalPostingList(session, '%s:tag' % tid).hits()
      self.STATS[tid] = [len(hits), len(hits & new_msgs)]

    return self.STATS

