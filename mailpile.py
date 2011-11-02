#!/usr/bin/python
#
# Mailpile.py (C) Copyright 2011, Bjarni R. Einarsson <http://bre.klaki.net/>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the  GNU  Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
###################################################################################
import codecs, datetime, getopt, locale, hashlib, os, random, re
import struct, sys, time
import lxml.html

WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]:\"|;\'\\\<\>\?,\.\/\-]{2,}')
# FIXME: This stoplist may be a bad idea.
STOPLIST = ('an', 'and', 'are', 'as', 'at', 'by', 'for', 'from', 'has', 'is',
            'og', 'or', 're', 'so', 'the', 'to', 'was')

def b64c(b):
  return b.replace('\n', '').replace('=', '').replace('/', '_')

def strhash(s, length):
  s2 = re.sub('[^0123456789abcdefghijklmnopqrstuvwxyz]+', '', s.lower())
  while len(s2) < length:
    h = hashlib.md5()
    h.update(s.encode('utf-8'))
    s2 += b64c(h.digest().encode('base64')).lower()
  return s2[:length]

def b64int(i):
  return re.split("A+$", struct.pack("Q", i)
                               .encode("base64")
                               .replace("=", '').replace("\n", '')
                  )[0].replace("/", "_") or "A"

def intb64(b64):
  padding = "A"*(11-len(b64))
  return struct.unpack("Q", ("%s%s==" % (b64.replace("_", "/"), padding)
                             ).decode("base64"))[0]


class PostingList(object):

  MAX_SIZE = 30 # 32k is 8 blocks, we aim for half-filling the last one.
                # Bumping this to 64k performs *much* worse on my laptop.
  HASH_LEN = 9

  @classmethod
  def Optimize(cls, config):
    postinglist_kb = config.get('postinglist_kb', cls.MAX_SIZE)
    postinglist_dir = config.postinglist_dir()

    # Pass 1: Compact all files
    for fn in sorted(os.listdir(postinglist_dir)):
      lastsize = 'initial'
      config.ui.mark('Pass 1: Compacting %s' % fn)
      cls('%s' % fn, config, sig=fn).save()

    # Pass 2: While mergable pair exists: merge them!
    files = [n for n in os.listdir(postinglist_dir) if len(n) > 1]
    files.sort(key=lambda a: -len(a))
    for fn in files:
      size = os.path.getsize(os.path.join(postinglist_dir, fn)) 
      fnp = fn[:-1]
      while not os.path.exists(os.path.join(postinglist_dir, fnp)):
        fnp = fnp[:-1]
      size += os.path.getsize(os.path.join(postinglist_dir, fnp)) 
      if (size < (1024*postinglist_kb-(cls.HASH_LEN*3))):
        config.ui.mark('Pass 2: Merging %s into %s' % (fn, fnp))
        fd = codecs.open(os.path.join(postinglist_dir, fn), 'r', 'utf-8')
        fdp = codecs.open(os.path.join(postinglist_dir, fnp), 'a', 'utf-8')
        for line in fd:
          fdp.write(line)
        fdp.close()
        fd.close()
        os.remove(os.path.join(postinglist_dir, fn))

    filecount = len(os.listdir(postinglist_dir))
    config.ui.mark('Optimized %s posting lists' % filecount)
    return filecount

  @classmethod
  def Append(cls, word, mail_id, config):
    sig = cls.WordSig(word)
    fd, fn = cls.GetFile(sig, config, mode='a')
    if ((os.path.getsize(os.path.join(config.postinglist_dir(), fn)) >
            (1024*config.get('postinglist_kb', cls.MAX_SIZE))-(cls.HASH_LEN*3))
        and (random.randint(0, 50) == 1)):
      # This will compact the files and split out hot-spots, but we only bother
      # "once in a while" when the files are "big".
      fd.close()
      pls = cls(word, config)
      pls.append(mail_id)
      pls.save()
    else:
      # Quick and dirty append is the default.
      fd.write('%s\t%s\n' % (sig, mail_id))
      fd.close()

  @classmethod
  def WordSig(cls, word):
    return '%s/%s' % (strhash(word, cls.HASH_LEN), word[:8*cls.HASH_LEN])

  @classmethod
  def GetFile(cls, sig, config, mode='r'):
    sig = sig[:cls.HASH_LEN]
    while len(sig) > 0:
      fn = os.path.join(config.postinglist_dir(), sig)
      try:
        if os.path.exists(fn): return (codecs.open(fn, mode, 'utf-8'), sig)
      except:
        pass

      if len(sig) > 1:
        sig = sig[:-1]
      else:
        if 'r' in mode:
          return (sig, None)
        else:
          return (codecs.open(fn, mode, 'utf-8'), sig)
    # Not reached
    return (None, None)

  def __init__(self, word, config, sig=None):
    self.config = config
    self.sig = sig or PostingList.WordSig(word)
    self.word = word
    self.WORDS = {self.sig: set()}
    self.load()

  def load(self):
    self.size = 0
    fd, sig = PostingList.GetFile(self.sig, self.config)
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
    self.config.ui.mark('Formatting prefix %s' % prefix)
    output = []
    for word in self.WORDS:
      if word.startswith(prefix) and len(self.WORDS[word]) > 0:
        output.append('%s\t%s\n' % (word,
                                '\t'.join(['%s' % x for x in self.WORDS[word]])))
    return ''.join(output)

  def save(self, prefix=None):
    prefix = prefix or self.filename
    output = self.fmt_file(prefix)
    while (len(output) > 1024*self.config.get('postinglist_kb', self.MAX_SIZE) and
           len(prefix) < self.HASH_LEN):
      biggest = self.sig
      for word in self.WORDS:
        if len(self.WORDS[word]) > len(self.WORDS[biggest]):
          biggest = word
      if len(biggest) > len(prefix):
        biggest = biggest[:len(prefix)+1]
        self.save(prefix=biggest)

        for key in [k for k in self.WORDS if k.startswith(biggest)]:
          del self.WORDS[key]
        output = self.fmt_file(prefix)

    try:
      if output:
        fd = codecs.open(os.path.join(self.config.postinglist_dir(), prefix),
                         'w', 'utf-8')
        fd.write(output)
        fd.close()
        return len(output)
      else:
        os.remove(os.path.join(self.config.postinglist_dir(), prefix))
        return 0
    except:
#     print 'Warning: %s' % (sys.exc_info(), )
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
  MSG_CONV_ID = 7
  MSG_TAGS    = 8

  def __init__(self, config):
    self.config = config
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}

  def l2m(self, line):
    return line.decode('utf-8').split(u'\t')

  def m2l(self, message):
    return (u'\t'.join([unicode(p) for p in message])).encode('utf-8')

  def load(self):
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}
    self.config.ui.mark('Loading metadata index...')
    try:
      fd = open(self.config.mailindex_file(), 'r')
    except:
      return
    for line in fd:
      line = line.strip()
      if line and not line.startswith('#'):
        self.INDEX.append(line)
    fd.close()
    self.config.ui.mark('Loaded metadata for %d messages' % len(self.INDEX))

  def save(self):
    self.config.ui.mark("Saving metadata index...")
    fd = open(self.config.mailindex_file(), 'w')
    fd.write('# This is the mailpile.py index file.\n')
    fd.write('# We have %d messages!\n' % len(self.INDEX))
    for item in self.INDEX:
      fd.write(item)
      fd.write('\n')
    fd.close()
    self.config.ui.mark("Saved metadata index")

  def update_ptrs_and_msgids(self):
    self.config.ui.mark('Updating high level indexes')
    for offset in range(0, len(self.INDEX)):
      message = self.l2m(self.INDEX[offset])
      if len(message) > self.MSG_CONV_ID:
        self.PTRS[message[self.MSG_PTR]] = offset
        self.MSGIDS[message[self.MSG_ID]] = offset
      else:
        print 'Bogus line: %s' % line

  def scan_mbox(self, idx, filename):
    import mailbox, email.parser, rfc822

    self.update_ptrs_and_msgids()
    self.config.ui.mark(('%s: Opening mailbox: %s (may take a while)'
                         ) % (idx, filename))
    mbox = mailbox.mbox(filename)
    msg_date = int(time.time())
    for i in range(0, len(mbox)):
      msg_fd = mbox.get_file(i)
      msg_ptr = '%s%s' % (idx, b64int(msg_fd._pos))

      parse_status = ('%s: Reading your mail: %d%% (%d/%d messages)'
                      ) % (idx, 100 * i/len(mbox), i, len(mbox))
      if msg_ptr in self.PTRS:
        if (i % 119) == 0: self.config.ui.mark(parse_status)
        continue
      else:
        self.config.ui.mark(parse_status)

      # Message new or modified, let's parse it.
      p = email.parser.Parser()
      msg = p.parse(msg_fd)
      def hdr(name):
        decoded = email.header.decode_header(msg[name] or '')
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

      msg_id = hdr('message-id') or '<%s@mailpile>' % msg_ptr
      if msg_id in self.MSGIDS:
        # Just update location
        msg_info = self.l2m(self.INDEX[self.MSGIDS[msg_id]])
        msg_info[self.MSG_PTR] = msg_ptr
        self.INDEX[self.MSGIDS[msg_id]] = self.m2l(msg_info)
        self.PTRS[msg_ptr] = self.MSGIDS[msg_id]
      else:
        # Add new message!
        try:
          msg_date = int(rfc822.mktime_tz(rfc822.parsedate_tz(hdr('date'))))
        except:
          print 'Date parsing: %s' % (sys.exc_info(), )
          # This is a hack: We assume the messages in the mailbox are in
          # chronological order and just add 1 second to the date of the last
          # message.  This should be a better-than-nothing guess.
          msg_date += 1

        msg_info = [b64int(len(self.INDEX)), # Our index ID
                    msg_ptr,                 # Location on disk
                    0,                       # Size
                    msg_id,                  # Message-ID
                    b64int(msg_date),        # Date as a UTC timestamp
                    hdr('from'),             # From:
                    hdr('subject'),          # Subject
                    0,                       # Conversation ID
                    '']                      # No tags for now

        self.PTRS[msg_ptr] = self.MSGIDS[msg_id] = len(self.INDEX)
        self.INDEX.append(self.m2l(msg_info))
        self.index_message(msg_info, msg, msg_date,
                           hdr('to'), hdr('from'), hdr('subject'))

      if (i % 1000) == 999: self.save()

    self.config.ui.mark('%s: Indexed mailbox: %s' % (idx, filename))
    return self

  def index_message(self, msg_info, msg, msg_date, msg_to, msg_from, msg_subject):
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

    keywords |= set(re.findall(WORD_REGEXP, msg_subject.lower()))
    keywords |= set(re.findall(WORD_REGEXP, msg_from.lower()))
    keywords |= set([t+':subject' for t in re.findall(WORD_REGEXP, msg_subject.lower())])
    keywords |= set([t+':from' for t in re.findall(WORD_REGEXP, msg_from.lower())])
    keywords |= set([t+':to' for t in re.findall(WORD_REGEXP, msg_to.lower())])
    keywords -= set(STOPLIST)
    for word in keywords:
      try:
        PostingList.Append(word, msg_info[0], self.config)
      except UnicodeDecodeError:
        # FIXME: we just ignore garbage
        pass

  def get_by_msg_idx(self, msg_idx):
    return self.l2m(self.INDEX[intb64(msg_idx)])

  def search(self, searchterms):
    r = []
    for term in searchterms:
      r.append([])
      rt = r[-1]
      term = term.lower()
      self.config.ui.mark('Searching...')
      if term.startswith('body:'):
        rt.extend(PostingList(term[5:], self.config).hits())
      elif ':' in term:
        t = term.split(':', 1)
        rt.extend(PostingList('%s:%s' % (t[1], t[0]), self.config).hits())
      else:
        rt.extend(PostingList(term, self.config).hits())

    results = set(r[0])
    for rt in r[1:]:
      results &= set(rt)

    self.config.ui.mark('Found %d results' % len(results))
    return results


class TextUI(object):
  def __init__(self):
    self.times = []

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


class ConfigManager(dict):

  ui = None

  def load(self): pass
  def save(self): pass
  def get_mailboxes(self):
    return [('000', '000'), ('001', '001')]

  def mailindex_file(self):
    return self.get('mailindex_file', 'mailpile.idx')

  def postinglist_dir(self):
    return self.get('postinglist_dir', 'search')

  def get_index(self):
    if 'index' in self: return self['index']
    idx = self['index'] = MailIndex(self)
    idx.load()
    return idx


COMMANDS = {
  'r': 'rescan',
  'a:': 'add=',
  's:': 'search=',
  'S:': 'set=',
  'U:': 'unset=',
  'P:': 'print=',
  'O': 'optimize',
  'l': 'load',
}
def Action(opt, arg, config):
  if opt in ('a', 'add'):
    pass

  elif opt in ('O', 'optimize'):
    try:
      filecount = PostingList.Optimize(config)
      config.ui.reset_marks()
    except KeyboardInterrupt:
      config.ui.mark('Aborted')
      config.ui.reset_marks()

  elif opt in ('P', 'print'):
    key = arg.strip().lower()
    if key in config:
      print '%s = %s' % (key, config[key])
    else:
      print '%s is unset' % key

  elif opt in ('U', 'unset'):
    key = arg.strip().lower()
    if key in config:
      del config[key]
    print '%s is unset' % key

  elif opt in ('S', 'set'):
    key, val = arg.split('=')
    key = key.strip().lower()
    if key.endswith('_kb'):
      config[key] = int(val.strip())
      print '%s = %d (int)' % (key, config[key])
    else:
      config[key] = val.strip()
      print '%s = %s' % (key, config[key])

  elif opt in ('r', 'rescan'):
    idx = config.get_index()
    config.ui.reset_marks()
    try:
      for fid, fpath in config.get_mailboxes():
        idx.scan_mbox(fid, fpath)
        config.ui.mark('\n')
    except KeyboardInterrupt:
      config.ui.mark('Aborted')
    idx.save()
    config.ui.reset_marks()

  elif opt in ('l', 'load'):
    config.get_index()
    config.ui.reset_marks()

  elif opt in ('s', 'search'):
    if not arg: return
    idx = config.get_index()
    config.ui.reset_marks()
    results = idx.search(arg.split())
    count = 0
    for mid in sorted(list(results))[-20:]:
      count += 1
      try:
        msg_info = idx.get_by_msg_idx(mid)
        msg_from = msg_info[idx.MSG_FROM]
        msg_subj = msg_info[idx.MSG_SUBJECT]
        msg_date = datetime.date.fromtimestamp(intb64(msg_info[idx.MSG_DATE]))
        print ('%2.2s %4.4d-%2.2d-%2.2d  %-25.25s  %-38.38s'
               ) % (count, msg_date.year, msg_date.month, msg_date.day,
                    msg_from, msg_subj)
      except:
        print '-- (not in index: %s)' % mid
    config.ui.mark('Listed %d of %d messages' % (count, len(results)))
    config.ui.reset_marks()

  else:
    print 'Unknown command: %s' % opt


def Interact(config):
  import readline
  try:
    while True:
      opt = raw_input('mailpile> ').decode('utf-8').strip()
      if opt:
        if ' ' in opt:
          opt, arg = opt.split(' ', 1)
        else:
          arg = ''
        Action(opt, arg, config)
  except EOFError:
    print


if __name__ == "__main__":
  re.UNICODE = 1
  re.LOCALE = 1

  config = ConfigManager()
  config.load()
  config.ui = TextUI()
  opts, args = getopt.getopt(sys.argv[1:],
                             ''.join(COMMANDS.keys()),
                             COMMANDS.values())

  for opt, arg in opts:
    Action(opt.replace('-', ''), arg, config)

  if not opts:
    Interact(config)

