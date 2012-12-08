#!/usr/bin/python
import cgi
import codecs
import datetime
import email.parser
import getopt
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
import SocketServer
from urlparse import parse_qs, urlparse
import lxml.html

import mailpile.util
from mailpile.util import *
from mailpile.mailutils import NoSuchMailboxError
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
  def Append(cls, session, word, mail_id, compact=True):
    config = session.config
    sig = cls.WordSig(word)
    fd, fn = cls.GetFile(session, sig, mode='a')
    if (compact
    and (os.path.getsize(os.path.join(config.postinglist_dir(fn), fn)) >
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
    return strhash(word, cls.HASH_LEN)

  @classmethod
  def GetFile(cls, session, sig, mode='r'):
    sig = sig[:cls.HASH_LEN]
    while len(sig) > 0:
      fn = os.path.join(session.config.postinglist_dir(sig), sig)
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
      outfile = os.path.join(self.config.postinglist_dir(prefix), prefix)
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
    self.STATS = {}
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
      decoded = email.header.decode_header(value or msg[name] or '')
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
      session.ui.mark('%s: Checking: %s' % (idx, mailbox_fn))
    except (IOError, OSError, NoSuchMailboxError):
      session.ui.mark('%s: Error opening: %s' % (idx, mailbox_fn))
      return 0

    if mbox.last_parsed+1 == len(mbox): return 0

    if len(self.PTRS.keys()) == 0:
      self.update_ptrs_and_msgids(session)

    added = 0
    msg_date = int(time.time())
    for i in range(mbox.last_parsed+1, len(mbox)):
      if mailpile.util.QUITTING: break
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
                                      mailbox=idx, compact=False,
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
                    mailbox=None, compact=True, filter_hooks=[]):
    keywords = []
    for part in msg.walk():
      charset = part.get_charset() or 'iso-8859-1'
      if part.get_content_type() == 'text/plain':
        textpart = self.try_decode(part.get_payload(None, True), charset)
      elif part.get_content_type() == 'text/html':
        payload = self.try_decode(part.get_payload(None, True), charset)
        if len(payload) > 3:
          try:
            textpart = lxml.html.fromstring(payload).text_content()
          except:
            session.ui.warning('=%s/%s has bogus HTML.' % (msg_mid, msg_id))
            textpart = payload
        else:
          textpart = payload
      else:
        textpart = None

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

    mdate = datetime.date.fromtimestamp(msg_date)
    keywords.append('%s:year' % mdate.year)
    keywords.append('%s:month' % mdate.month)
    keywords.append('%s:day' % mdate.day)
    keywords.append('%s-%s-%s:date' % (mdate.year, mdate.month, mdate.day))
    keywords.append('%s:id' % msg_id)
    keywords.extend(re.findall(WORD_REGEXP, self.hdr(msg, 'subject').lower()))
    keywords.extend(re.findall(WORD_REGEXP, self.hdr(msg, 'from').lower()))
    if mailbox: keywords.append('%s:mailbox' % mailbox.lower())

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
              '(not in index)', '(not in index: %s)' % msg_idx, '', '', '-1')

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

  def get_conversation(self, msg_info=None, msg_idx=None):
    if not msg_info:
      msg_info = self.get_msg_by_idx(msg_idx)
    conv_id = msg_info[self.MSG_CONV_ID]
    if conv_id:
      return [msg_info] + self.get_replies(msg_idx=int(conv_id, 36))
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
        return keywords.get(term, [])
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
        rt.extend([int(h, 36) for h in hits(term[5:])])
      elif term == 'all:mail':
        rt.extend(range(0, len(self.INDEX)))
      elif ':' in term:
        t = term.split(':', 1)
        rt.extend([int(h, 36) for h in hits('%s:%s' % (t[1], t[0]))])
      else:
        rt.extend([int(h, 36) for h in hits(term)])

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
    new_msgs = (new_tid and PostingList(session, '%s:tag' % new_tid).hits()
                         or set([]))
    self.STATS.update({
      'ALL': [len(self.INDEX), len(new_msgs)]
    })
    for tid in (update_tags or config.get('tag', {}).keys()):
      if session: session.ui.mark('Counting messages in tag:%s' % tid)
      hits = PostingList(session, '%s:tag' % tid).hits()
      self.STATS[tid] = [len(hits), len(hits & new_msgs)]

    return self.STATS

