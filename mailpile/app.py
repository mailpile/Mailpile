#!/usr/bin/python
APPVER="0.0.0+github"
ABOUT="""\
Mailpile.py          a tool          Copyright 2011-2012, Bjarni R. Einarsson
               for searching and                      <http://bre.klaki.net/>
           organizing piles of e-mail

This program is free software: you can redistribute it and/or modify it under
the terms of the  GNU  Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.
"""
###############################################################################
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
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from urlparse import parse_qs, urlparse
import lxml.html

# This is a hack..
import mailpile.ui
mailpile.ui.ABOUT = ABOUT

from mailpile.util import *
from mailpile.mailutils import *
from mailpile.ui import *
from mailpile.httpd import *
from mailpile.commands import *


##[ The search and index code itself ]#########################################

class PostingList(object):
  """A posting list is a map of search terms to message IDs."""

  MAX_SIZE = 60  # perftest gives: 75% below 500ms, 50% below 100ms
  HASH_LEN = 24

  @classmethod
  def Optimize(cls, session, idx, force=False):
    flush_append_cache()

    postinglist_kb = session.config.get('postinglist_kb', cls.MAX_SIZE)
    postinglist_dir = session.config.postinglist_dir()

    # Pass 1: Compact all files that are 90% or more of our target size
    for fn in sorted(os.listdir(postinglist_dir)):
      if QUITTING: break
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
      if QUITTING: break
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
    return strhash(word, cls.HASH_LEN)

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
    mbox = mailbox_opener(session, idx)
    session.ui.mark('%s: Checking: %s' % (idx, mailbox_fn))

    if mbox.last_parsed+1 == len(mbox): return 0

    if len(self.PTRS.keys()) == 0:
      self.update_ptrs_and_msgids(session)

    added = 0
    msg_date = int(time.time())
    for i in range(mbox.last_parsed+1, len(mbox)):
      if QUITTING: break
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
          elif msg_date < 0:
            session.ui.warning('=%s/%s has a negative date!' % (msg_mid, msg_id))
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
        keywords.extend(re.findall(WORD_REGEXP, textpart.lower()))

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
              '(not in index)', '(not in index)', '', '', '-1')

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


##[ Specialized threads ]######################################################

class Cron(threading.Thread):

  def __init__(self, name, session):
    threading.Thread.__init__(self)
    self.ALIVE = False
    self.name = name
    self.session = session
    self.schedule = {}
    self.sleep = 10

  def add_task(self, name, interval, task):
    self.schedule[name] = [name, interval, task, time.time()]
    self.sleep = 60
    for i in range(1, 61):
      ok = True
      for tn in self.schedule:
        if (self.schedule[tn][1] % i) != 0: ok = False
      if ok: self.sleep = i

  def cancel_task(self, name):
    if name in self.schedule:
      del self.schedule[name]

  def run(self):
    self.ALIVE = True
    while self.ALIVE and not QUITTING:
      now = time.time()
      for task_spec in self.schedule.values():
        name, interval, task, last = task_spec
        if task_spec[3] + task_spec[1] <= now:
          task_spec[3] = now
          task()

      # Some tasks take longer than others...
      delay = time.time() - now + self.sleep
      while delay > 0 and self.ALIVE:
        time.sleep(min(1, delay))
        delay -= 1

  def quit(self, session=None, join=True):
    self.ALIVE = False
    if join: self.join()


class Worker(threading.Thread):

  def __init__(self, name, session):
    threading.Thread.__init__(self)
    self.NAME = name or 'Worker'
    self.ALIVE = False
    self.JOBS = []
    self.LOCK = threading.Condition()
    self.pauses = 0
    self.session = session

  def add_task(self, session, name, task):
    self.LOCK.acquire()
    self.JOBS.append((session, name, task))
    self.LOCK.notify()
    self.LOCK.release()

  def do(self, session, name, task):
    if session and session.main:
      # We run this in the foreground on the main interactive session,
      # so CTRL-C has a chance to work.
      try:
        self.pause(session)
        rv = task()
        self.unpause(session)
      except:
        self.unpause(session)
        raise
    else:
      self.add_task(session, name, task)
      if session:
        rv = session.wait_for_task(name)
        if not rv:
          raise WorkerError()
      else:
        rv = True
    return rv

  def run(self):
    self.ALIVE = True
    while self.ALIVE and not QUITTING:
      self.LOCK.acquire()
      while len(self.JOBS) < 1:
        self.LOCK.wait()
      session, name, task = self.JOBS.pop(0)
      self.LOCK.release()

      try:
        if session:
          session.ui.mark('Starting: %s' % name)
          session.report_task_completed(name, task())
        else:
          task()
      except Exception, e:
        self.session.ui.error('%s failed in %s: %s' % (name, self.NAME, e))
        if session: session.report_task_failed(name)

  def pause(self, session):
    self.LOCK.acquire()
    self.pauses += 1
    if self.pauses == 1:
      self.LOCK.release()
      def pause_task():
        session.report_task_completed('Pause', True)
        session.wait_for_task('Unpause', quiet=True)
      self.add_task(None, 'Pause', pause_task)
      session.wait_for_task('Pause', quiet=True)
    else:
      self.LOCK.release()

  def unpause(self, session):
    self.LOCK.acquire()
    self.pauses -= 1
    if self.pauses == 0:
      session.report_task_completed('Unpause', True)
    self.LOCK.release()

  def die_soon(self, session=None):
    def die():
      self.ALIVE = False
    self.add_task(session, '%s shutdown' % self.NAME, die)

  def quit(self, session=None, join=True):
    self.die_soon(session=session)
    if join: self.join()


##[ The Configuration Manager ]###############################################

class ConfigManager(dict):

  background = None
  cron_worker = None
  http_worker = None
  slow_worker = None
  index = None

  MBOX_CACHE = {}
  RUNNING = {}

  INTS = ('postinglist_kb', 'sort_max', 'num_results', 'fd_cache_size',
          'http_port', 'rescan_interval')
  STRINGS = ('mailindex_file', 'postinglist_dir', 'default_order',
             'gpg_recipient', 'http_host', 'rescan_command', 'debug')
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

  def clear_mbox_cache(self):
    self.MBOX_CACHE = {}

  def open_mailbox(self, session, mailbox_id):
    pfn = os.path.join(self.workdir(), 'pickled-mailbox.%s' % mailbox_id)
    for mid, mailbox_fn in self.get_mailboxes():
      if mid == mailbox_id:
        try:
          if mid in self.MBOX_CACHE:
            self.MBOX_CACHE[mid].update_toc()
          else:
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
    return [(fmt_mbxid(k), self['mailbox'][k]) for k in mailboxes]

  def get_tag_id(self, tn):
    tn = tn.lower()
    tid = [t for t in self['tag'] if self['tag'][t].lower() == tn]
    return tid and tid[0] or None

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

  def prepare_workers(config, session, daemons=False):
    # Set globals from config first...
    global APPEND_FD_CACHE_SIZE
    APPEND_FD_CACHE_SIZE = config.get('fd_cache_size',
                                      APPEND_FD_CACHE_SIZE)

    if not config.background:
      # Create a silent background session
      config.background = Session(config)
      config.background.ui = TextUI()
      config.background.ui.block()

    # Start the workers
    if not config.slow_worker:
      config.slow_worker = Worker('Slow worker', session)
      config.slow_worker.start()
    if daemons and not config.cron_worker:
      config.cron_worker = Cron('Cron worker', session)
      config.cron_worker.start()

      # Schedule periodic rescanning, if requested.
      rescan_interval = config.get('rescan_interval', None)
      if rescan_interval:
        def rescan():
          if 'rescan' not in config.RUNNING:
            config.slow_worker.add_task(None, 'Rescan',
                                        lambda: Action_Rescan(session, config))
        config.cron_worker.add_task('rescan', rescan_interval, rescan)

    if daemons and not config.http_worker:
      # Start the HTTP worker if requested
      sspec = (config.get('http_host', 'localhost'),
               config.get('http_port', DEFAULT_PORT))
      if sspec[0].lower() != 'disabled' and sspec[1] >= 0:
        config.http_worker = HttpWorker(session, sspec)
        config.http_worker.start()

  def stop_workers(config):
    for w in (config.http_worker, config.slow_worker, config.cron_worker):
      if w: w.quit()


##[ Main ]####################################################################

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
          session.error(str(e))
  except EOFError:
    print

  readline.write_history_file(session.config.history_file())

def Main(args):
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
    # Create and start (most) worker threads
    config.prepare_workers(session)

    try:
      opts, args = getopt.getopt(args,
                                 ''.join(COMMANDS.keys()),
                                 [v[0] for v in COMMANDS.values()])
      for opt, arg in opts:
        Action(session, opt.replace('-', ''), arg)
      if args:
        Action(session, args[0], ' '.join(args[1:]))

    except (getopt.GetoptError, UsageError), e:
      session.error(e)


    if not opts and not args:
      # Create and start the rest of the threads, load the index.
      config.prepare_workers(session, daemons=True)
      Action_Load(session, config, quiet=True)
      session.interactive = session.ui.interactive = True
      session.ui.print_intro(help=True, http_worker=config.http_worker)
      Interact(session)

  except KeyboardInterrupt:
    pass

  finally:
    QUITTING = True
    config.stop_workers()

if __name__ == "__main__":
  Main(sys.argv[1:])
