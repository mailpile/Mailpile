#!/usr/bin/python
ABOUT="""\
Mailpile.py - a tool for searching and      Copyright 2011, Bjarni R. Einarsson
             organizing piles of e-mail                <http://bre.klaki.net/>

This program is free software: you can redistribute it and/or modify it under
the terms of the  GNU  Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.
"""
###################################################################################
import codecs, datetime, getopt, locale, hashlib, os, random, re
import struct, sys, time
import lxml.html


WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]:\"|;\'\\\<\>\?,\.\/\-]{2,}')
# FIXME: This stoplist may be a bad idea.
STOPLIST = ('an', 'and', 'are', 'as', 'at', 'by', 'for', 'from', 'has', 'in',
            'is', 'og', 'or', 're', 'so', 'the', 'to', 'was')


def b64c(b):
  return b.replace('\n', '').replace('=', '').replace('/', '_')

def sha1b64(s):
  h = hashlib.sha1()
  h.update(s.encode('utf-8'))
  return h.digest().encode('base64')

def strhash(s, length):
  s2 = re.sub('[^0123456789abcdefghijklmnopqrstuvwxyz]+', '', s.lower())
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


# Indexing messages is an append-heavy operation, and some files are
# appended to much more often than others.  This implements a simple
# LRU cache of file descriptors we are appending to.
APPEND_FD_CACHE = {}
APPEND_FD_CACHE_ORDER = []
def flush_append_cache(ratio=1, count=None):
  global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER
  drop = count or ratio*len(APPEND_FD_CACHE)
  for fn in APPEND_FD_CACHE_ORDER[:drop]:
    APPEND_FD_CACHE[fn].close()
    del APPEND_FD_CACHE[fn]
  APPEND_FD_CACHE_ORDER[:drop] = []

def cached_open(filename, mode):
  global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER
  if mode == 'a':
    if filename not in APPEND_FD_CACHE:
      if len(APPEND_FD_CACHE) > 500: flush_append_cache(count=1)
      try:
        APPEND_FD_CACHE[filename] = open(filename, 'a')
      except:
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
      APPEND_FD_CACHE_ORDER.remove(filename)
      del APPEND_FD_CACHE[filename]
    return open(filename, mode)


class PostingList(object):

  MAX_SIZE = 30 # 32k is 8 blocks, we aim for half-filling the last one.
                # Bumping this to 64k performs *much* worse on my laptop.
  HASH_LEN = 12

  @classmethod
  def Optimize(cls, session, idx, force=False):
    flush_append_cache()

    postinglist_kb = session.config.get('postinglist_kb', cls.MAX_SIZE)
    postinglist_dir = session.config.postinglist_dir()

    # Pass 1: Compact all files that are 90% or more of our target size
    for fn in sorted(os.listdir(postinglist_dir)):
      if (force or
          os.path.getsize(os.path.join(postinglist_dir, fn)) >
                                                        900*postinglist_kb):
        session.ui.mark('Pass 1: Compacting >%s<' % fn)
        # FIXME: Remove invalid and deleted messages from posting lists.
        cls(session, fn, sig=fn).save()

    # Pass 2: While mergable pair exists: merge them!
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
      except:
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

  def load(self):
    self.size = 0
    fd, sig = PostingList.GetFile(self.session, self.sig)
    self.filename = sig
    if fd:
      for line in fd:
        self.size += len(line)
        words = line.strip().split('\t')
        if len(words) > 1:
          if words[0] not in self.WORDS: self.WORDS[words[0]] = set()
          self.WORDS[words[0]] |= set(words[1:])
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
    while (compact and
           len(output) > 1024*self.config.get('postinglist_kb', self.MAX_SIZE)
           and len(prefix) < self.HASH_LEN):
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

  def remove(self, eid):
    self.WORDS[self.sig].remove(eid)


class MailIndex(object):

  MSG_IDX     = 0
  MSG_PTR     = 1
  MSG_SIZE    = 2
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

  def load(self, session):
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}
    session.ui.mark('Loading metadata index...')
    try:
      fd = open(self.config.mailindex_file(), 'r')
      for line in fd:
        line = line.strip()
        if line and not line.startswith('#'):
          self.INDEX.append(line)
      fd.close()
    except IOError:
      session.ui.warning(('Metadata index not found: %s'
                          ) % self.config.mailindex_file())
    session.ui.mark('Loaded metadata for %d messages' % len(self.INDEX))

  def save(self, session):
    session.ui.mark("Saving metadata index...")
    fd = open(self.config.mailindex_file(), 'w')
    fd.write('# This is the mailpile.py index file.\n')
    fd.write('# We have %d messages!\n' % len(self.INDEX))
    for item in self.INDEX:
      fd.write(item)
      fd.write('\n')
    fd.close()
    session.ui.mark("Saved metadata index")

  def update_ptrs_and_msgids(self, session):
    session.ui.mark('Updating high level indexes')
    for offset in range(0, len(self.INDEX)):
      message = self.l2m(self.INDEX[offset])
      if len(message) > self.MSG_CONV_ID:
        self.PTRS[message[self.MSG_PTR]] = offset
        self.MSGIDS[message[self.MSG_ID]] = offset
      else:
        print 'Bogus line: %s' % line

  def scan_mbox(self, session, idx, filename):
    import mailbox, email.parser, rfc822

    self.update_ptrs_and_msgids(session)
    session.ui.mark(('%s: Opening mailbox: %s (may take a while)'
                     ) % (idx, filename))
    mbox = mailbox.mbox(filename)
    msg_date = int(time.time())
    added = 0
    for i in range(0, len(mbox)):
      msg_fd = mbox.get_file(i)
      msg_ptr = '%s%s' % (idx, b36(long(msg_fd._pos)))

      parse_status = ('%s: Reading your mail: %d%% (%d/%d messages)'
                      ) % (idx, 100 * i/len(mbox), i, len(mbox))
      if msg_ptr in self.PTRS:
        if (i % 119) == 0: session.ui.mark(parse_status)
        continue
      else:
        session.ui.mark(parse_status)

      # Message new or modified, let's parse it.
      p = email.parser.Parser()
      msg = p.parse(msg_fd)
      def hdr(name, value=None):
        decoded = email.header.decode_header(value or msg[name] or '')
        try:
          return (' '.join([t[0].decode(t[1] or 'iso-8859-1') for t in decoded])
                  ).replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')
        except:
          try:
            return (' '.join([t[0].decode(t[1] or 'utf-8') for t in decoded])
                    ).replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')
          except:
            print 'Boom: %s/%s' % (msg[name], decoded)
            return ''

      msg_id = b64c(sha1b64((hdr('message-id') or msg_ptr).strip()))
      if msg_id in self.MSGIDS:
        # Just update location
        msg_info = self.l2m(self.INDEX[self.MSGIDS[msg_id]])
        msg_info[self.MSG_PTR] = msg_ptr
        self.INDEX[self.MSGIDS[msg_id]] = self.m2l(msg_info)
        self.PTRS[msg_ptr] = self.MSGIDS[msg_id]
      else:
        # Add new message!
        msg_mid = b36(len(self.INDEX))

        try:
          msg_date = int(rfc822.mktime_tz(rfc822.parsedate_tz(hdr('date'))))
        except:
          print 'Date parsing: %s' % (sys.exc_info(), )
          # This is a hack: We assume the messages in the mailbox are in
          # chronological order and just add 1 second to the date of the last
          # message.  This should be a better-than-nothing guess.
          msg_date += 1

        msg_conv = None
        refs = set((hdr('references') + ' ' + hdr('in-reply-to')
                    ).replace(',', ' ').strip().split())
        for ref_id in [b64c(sha1b64(r)) for r in refs]:
          try:
            # Get conversation ID ...
            ref_mid = self.MSGIDS[ref_id]
            msg_conv = self.l2m(self.INDEX[ref_mid])[self.MSG_CONV_ID]
            # Update root of conversation thread
            parent = self.l2m(self.INDEX[int(msg_conv, 36)])
            parent[self.MSG_REPLIES] += '%s,' % msg_mid
            self.INDEX[int(msg_conv, 36)] = self.m2l(parent)
            break
          except:
            pass
        if not msg_conv:
          # FIXME: If subject implies this is a reply, scan back a couple
          #        hundred messages for similar subjects - but not infinitely,
          #        conversations don't last forever.
          msg_conv = msg_mid

        self.index_message(msg_mid, msg, msg_date,
                           hdr('to'), hdr('from'), hdr('subject'),
                           compact=False)

        msg_info = [msg_mid,                  # Our index ID
                    msg_ptr,                  # Location on disk
                    b36(msg_fd.tell()),       # Size?
                    msg_id,                   # Message-ID
                    b36(msg_date),            # Date as a UTC timestamp
                    hdr('from'),              # From:
                    hdr('subject'),           # Subject
                    '',                       # No tags for now
                    '',                       # No replies for now
                    msg_conv]                 # Conversation ID

        self.PTRS[msg_ptr] = self.MSGIDS[msg_id] = len(self.INDEX)
        self.INDEX.append(self.m2l(msg_info))
        added += 1

      if (i % 1000) == 999: self.save(session)

    flush_append_cache()
    if added > 100:
      PostingList.Optimize(session, self)
    session.ui.mark('%s: Indexed mailbox: %s' % (idx, filename))
    return self

  def index_message(self, msg_mid, msg, msg_date,
                    msg_to, msg_from, msg_subject, compact=True):
    keywords = set()
    for part in msg.walk():
      charset = part.get_charset() or 'iso-8859-1'
      if part.get_content_type() == 'text/plain':
        textpart = part.get_payload(None, True)
      elif part.get_content_type() == 'text/html':
        payload = part.get_payload(None, True).decode(charset)
        if payload:
          try:
            textpart = lxml.html.fromstring(payload).text_content()
          except:
            print 'Parsing failed: %s' % payload
            textpart = None
        else:
          textpart = None
      else:
        textpart = None

      att = part.get_filename()
      if att:
        keywords.add('attachment:has')
        keywords |= set([t+':att' for t in re.findall(WORD_REGEXP, att.lower())])
        textpart = (textpart or '') + ' ' + att

      if textpart:
        # FIXME: Does this lowercase non-ASCII characters correctly?
        keywords |= set(re.findall(WORD_REGEXP, textpart.lower()))

    mdate = datetime.date.fromtimestamp(msg_date)
    keywords.add('%s:year' % mdate.year)
    keywords.add('%s:month' % mdate.month)
    keywords.add('%s:day' % mdate.day)
    keywords.add('%s-%s-%s:date' % (mdate.year, mdate.month, mdate.day))

    keywords |= set(re.findall(WORD_REGEXP, msg_subject.lower()))
    keywords |= set(re.findall(WORD_REGEXP, msg_from.lower()))
    keywords |= set([t+':subject' for t in re.findall(WORD_REGEXP, msg_subject.lower())])
    keywords |= set([t+':from' for t in re.findall(WORD_REGEXP, msg_from.lower())])
    keywords |= set([t+':to' for t in re.findall(WORD_REGEXP, msg_to.lower())])
    keywords -= set(STOPLIST)
    for word in keywords:
      try:
        PostingList.Append(session, word, msg_mid, compact=compact)
      except UnicodeDecodeError:
        # FIXME: we just ignore garbage
        pass

  def get_msg_by_idx(self, msg_idx):
    try:
      if msg_idx not in self.CACHE:
        self.CACHE[msg_idx] = self.l2m(self.INDEX[msg_idx])
      return self.CACHE[msg_idx]
    except IndexError:
      return (None, None, None, None, b36(0),
              '(not in index)', '(not in index)', None, None)

  def get_conversation(self, msg_idx):
    return self.get_msg_by_idx(
             int(self.get_msg_by_idx(msg_idx)[self.MSG_CONV_ID], 36))

  def get_replies(self, msg_info):
    return [self.get_msg_by_idx(int(r, 36)) for r
            in msg_info[self.MSG_REPLIES].split(',') if r]

  def search(self, session, searchterms):
    if len(self.CACHE.keys()) > 5000: self.CACHE = {}
    r = []
    for term in searchterms:
      if term in STOPLIST:
        session.ui.warning('Ignoring common word: %s' % term)
        continue

      r.append([])
      rt = r[-1]
      term = term.lower()
      session.ui.mark('Searching...')
      if term.startswith('body:'):
        rt.extend(PostingList(session, term[5:]).hits())
      elif ':' in term:
        t = term.split(':', 1)
        rt.extend(PostingList(session, '%s:%s' % (t[1], t[0])).hits())
      else:
        rt.extend(PostingList(session, term).hits())

    if r:
      results = set(r[0])
      for rt in r[1:]:
        results &= set(rt)
      # Sometimes the scan gets aborted...
      results -= set([b36(len(self.INDEX))])
    else:
      results = set()

    results = [int(r, 36) for r in results]
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


class NullUI(object):
  def print_key(self, key, config): pass
  def reset_marks(self): pass
  def mark(self, progress): pass

  def notify(self, message): print '%s' % message
  def warning(self, message): print 'Warning: %s' % message
  def error(self, message): print 'Error: %s' % message

  def print_intro(self, help=False):
    print ABOUT
    print 'For instructions type `help`, press <CTRL-D> to quit.\n'

  def print_help(self, commands):
    print '\nMailpile understands the following commands:\n'
    last_rank = None
    cmds = commands.keys()
    cmds.sort(key=lambda k: commands[k][3])
    for c in cmds:
      cmd, args, explanation, rank = commands[c]
      if not rank: continue

      if last_rank and int(rank/10) != last_rank: print
      last_rank = int(rank/10)

      print '   %s|%-8.8s %-15.15s %s' % (c[0], cmd.replace('=', ''),
                                          args and ('<%s>' % args) or '',
                                          explanation)
    print


class TextUI(NullUI):
  def __init__(self):
    self.times = []

  def print_key(self, key, config):
    if key in config:
      if key in config.INTS:
        print '%s = %s (int)' % (key, config.get(key))
      else:
        print '%s = %s' % (key, config.get(key))
    else:
      print '%s is unset' % key

  def reset_marks(self):
    t = self.times
    self.times = []
    if t:
      result = 'Elapsed: %.3fs (%s)' % (t[-1][0] - t[0][0], t[-1][1])
      print '%s%s' % (result, ' ' * (79-len(result)))
      return t[-1][0] - t[0][0]
    else:
      return 0

  def mark(self, progress):
    sys.stdout.write('  %s%s\r' % (progress, ' ' * (77-len(progress))))
    sys.stdout.flush()
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
    if not results: return

    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    clen = max(3, len('%d' % len(results)))
    cfmt = '%%%d.%ds' % (clen, clen)
    sfmt = '%%-%d.%ds' % (39-clen, 39-clen)

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

        print (cfmt+' %4.4d-%2.2d-%2.2d  %-25.25s  '+sfmt
               ) % (start + count,
                    msg_date.year, msg_date.month, msg_date.day,
                    self.compact(self.names(msg_from), 25),
                    msg_subj)
      except:
        raise
        print '-- (not in index: %s)' % mid
    session.ui.mark(('Listed %d-%d of %d results'
                     ) % (start+1, start+count, len(results)))
    return (start, count)



class UsageError(Exception):
  pass


class ConfigManager(dict):

  index = None

  INTS = ('postinglist_kb', 'sort_max')
  STRINGS = ('mailindex_file', 'postinglist_dir', 'default_order')
  DICTS = ('mailbox', 'tag')

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
      self[key] = int(val)
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

  def load(self, session):
    if not os.path.exists(self.workdir()):
      session.ui.notify('Creating: %s' % self.workdir())
      os.mkdir(self.workdir())
    else:
      self.index = None
      for key in (self.INTS + self.STRINGS):
        if key in self: del self[key]
      try:
        fd = open(self.conffile(), 'r')
        for line in fd:
          line = line.strip()
          if line.startswith('#') or not line:
            pass
          elif '=' in line:
            self.parse_set(session, line)
          else:
            raise UsageError('Bad line in config: %s' % line)
        fd.close()
      except IOError:
        pass

  def save(self):
    if not os.path.exists(self.workdir()):
      session.ui.notify('Creating: %s' % self.workdir())
      os.mkdir(self.workdir())
    fd = open(self.conffile(), 'w')
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
    idx = self.index = MailIndex(self)
    idx.load(session)
    return idx


class Session(object):

  ui = NullUI()
  order = None
  results = None
  displayed = (0, 0)
  interactive = False

  def __init__(self, config):
    self.config = config

  def error(self, message):
    self.ui.error(message)
    if not self.interactive: sys.exit(1)


COMMANDS = {
  'A:': ('add=',     'path/to/mbox',  'Add a mailbox',                      54),
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
  'U:': ('unset=',   'var',           'Reset a setting to the default',     51),
}
def Action(session, opt, arg):
  config = session.config

  if not opt or opt in ('h', 'help'):
    session.ui.print_help(COMMANDS)

  elif opt in ('A', 'add'):
    if os.path.exists(arg):
      arg = os.path.abspath(arg)
      if config.parse_set(session,
                          'mailbox:%s=%s' % (config.nid('mailbox'), arg)):
        config.save()
    else:
      session.error('No such file/directory: %s' % arg)

  elif opt in ('O', 'optimize'):
    try:
      idx = config.get_index(session)
      filecount = PostingList.Optimize(session, idx,
                                       force=(arg == 'harder'))
      session.ui.reset_marks()
    except KeyboardInterrupt:
      session.ui.mark('Aborted')
      session.ui.reset_marks()

  elif opt in ('P', 'print'):
    session.ui.print_key(arg.strip().lower(), config)

  elif opt in ('U', 'unset'):
    if config.parse_unset(session, arg): config.save()

  elif opt in ('S', 'set'):
    if config.parse_set(session, arg): config.save()

  elif opt in ('R', 'rescan'):
    idx = config.get_index(session)
    session.ui.reset_marks()
    try:
      for fid, fpath in config.get_mailboxes():
        idx.scan_mbox(session, fid, fpath)
        session.ui.mark('\n')
    except KeyboardInterrupt:
      session.ui.mark('Aborted')
    idx.save(session)
    session.ui.reset_marks()

  elif opt in ('L', 'load'):
    config.index = session.results = None
    config.get_index(session)
    session.ui.reset_marks()

  elif opt in ('n', 'next'):
    idx = config.get_index(session)
    session.ui.reset_marks()
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   start=pos+count)
    session.ui.reset_marks()

  elif opt in ('p', 'previous'):
    idx = config.get_index(session)
    session.ui.reset_marks()
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   end=pos)
    session.ui.reset_marks()

  elif opt in ('s', 'search'):
    if not arg: return
    idx = config.get_index(session)
    session.ui.reset_marks()
    # FIXME: This is all rather dumb.  Make it smarter!
    if ':' in arg:
      session.results = list(idx.search(session, arg.lower().split()))
    else:
      session.results = list(idx.search(session,
                             re.findall(WORD_REGEXP, arg.lower())))
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = session.ui.display_results(idx, session.results)
    session.ui.reset_marks()

  elif opt in ('o', 'order'):
    idx = config.get_index(session)
    session.ui.reset_marks()
    session.order = arg or None
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = session.ui.display_results(idx, session.results)
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
      opt = raw_input('mailpile> ').decode('utf-8').strip()
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


if __name__ == "__main__":
  re.UNICODE = 1
  re.LOCALE = 1

  session = Session(ConfigManager())
  session.config.load(session)
  session.ui = TextUI()
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
    session.interactive = True
    session.ui.print_intro(help=True)
    Interact(session)

