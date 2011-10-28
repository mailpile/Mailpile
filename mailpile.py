#!/usr/bin/python
#
# Mailpile.py (C) Copyright 2011, Bjarni R. Einarsson <http://bre.klaki.net/>
#
# This program maintains and interacts with a high-performance local e-mail
# index.  Goals:
#
#   - Support GMail-like conversations, filters and searches
#   - Sub-200ms search results on single core and single disk, for mailboxes
#     with X00000 messages (after the index has been loaded into RAM).
#   - Compatibility with standard Unix mailboxes.
#   - Be usable as a back-end for a modern personal web-mail solution.
#
# Strategy:
#
#   - Searches will be answered using posting lists stored in files on disk
#     (10-50ms access times for non-huge posting lists: the pathological 'a'
#     posting list will probably take 300ms or so, which can be fixed by only
#     reading the final desired N results... if we care).
#
#   - Information required to display results (To, From, Subject, ...) lives
#     in a RAM-based index, populated when the user logs on.  Average message
#     overhead should be <300B, allowing 100000 e-mails in 30MB of RAM.
#
#   - User-editable tags also live in the RAM index and can be quickly searched
#     using sequential scans from the rear end of the index.
#
###################################################################################
import codecs, locale, hashlib, mailbox, os, random, re, sys, time
import email.parser
import lxml.html


def b64c(b):
  return b.replace('\n', '').replace('=', '').replace('/', '_')

def b64int(i):
  h = hex(int(i))[2:]
  h = (len(h) & 1) and '0'+h or h
  return b64c(h.decode('hex').encode('base64'))


class ConfigManager(dict):
  def load(self): pass
  def save(self): pass
  def parse(self, args): pass
  def mailindex_file(self): return self.get('mailindex_file', 'mailpile.idx')
  def postinglist_dir(self): return self.get('postinglist_dir', 'search')


class PostingListStore(object):

  MAX_SIZE = 12*1024

  @classmethod
  def Append(cls, word, mail_id, config):
    sig = cls.WordSig(word)
    fd, fn = cls.GetFile(sig, config, mode='a')
    fd.write('%s\t%s\n' % (sig, mail_id))
    fd.close()
    # Compact the file if it's gotten too "big"
    if os.path.getsize(os.path.join(config.postinglist_dir(), fn)) > cls.MAX_SIZE:
      if fn != sig or random.randint(0, 50) == 1:
        cls(word, config).save()

  @classmethod
  def WordSig(cls, word):
    h = hashlib.sha1()
    h.update(word)
    return b64c(h.digest().encode('base64'))

  @classmethod
  def GetFile(cls, sig, config, mode='r'):
    while len(sig) > 0:
      fn = os.path.join(config.postinglist_dir(), sig)
      try:
        if os.path.exists(fn): return (open(fn, mode), sig)
      except:
        pass

      if len(sig) > 1:
        sig = sig[:-1]
      else:
        if 'r' in mode:
          return (sig, None)
        else:
          return (open(fn, mode), sig)
    # Not reached
    return (None, None)

  def __init__(self, word, config):
    self.config = config
    self.sig = PostingListStore.WordSig(word)
    self.word = word
    self.WORDS = {self.sig: set()}
    self.load()

  def load(self):
    self.size = 0
    fd, sig = PostingListStore.GetFile(self.sig, self.config)
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
    output = '' 
    for word in self.WORDS:
      if word.startswith(prefix) and len(self.WORDS[word]) > 0:
        output += '%s\t%s\n' % (word,
                                '\t'.join(['%s' % x for x in self.WORDS[word]]))
    return output

  def save(self, prefix=None):
    prefix = prefix or self.filename
    output = self.fmt_file(prefix)

    if len(output) > self.MAX_SIZE:
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

    if output:
      fd = open(os.path.join(self.config.postinglist_dir(), prefix), 'w')
      fd.write(output)
      fd.close()
    else:
      os.remove(os.path.join(self.config.postinglist_dir(), prefix))

  def hits(self):
    return self.WORDS[self.sig]

  def append(self, eid):
    self.WORDS[self.sig].add(eid)

  def remove(self, eid):
    self.WORDS[self.sig].remove(eid)


class MailIndex(object):
  def __init__(self, config):
    self.config = config
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}

  def load(self):
    fd = codecs.open(self.config.mailindex_file(), 'r', 'utf-8')
    for line in fd:
      line = line.strip()
      if line and not line.startswith('#'):
        message = line.split('\t')
        self.INDEX.append(message)
        self.PTRS[message[1]] = message
        self.MSGIDS[message[3]] = message
    fd.close()

  def save(self):
    fd = codecs.open(self.config.mailindex_file(), 'w', 'utf-8')
    fd.write('# This is the mailpile.py index file.\n')
    fd.write('# We have %d messages!\n' % len(self.INDEX))
    for item in self.INDEX:
      fd.write('\t'.join([('%s' % i) for i in item]))
      fd.write('\n')
    fd.close()

  def scan_mbox(self, idx, filename):
    mbox = mailbox.mbox(filename)
    for i in range(0, len(mbox)):
      msg_fd = mbox.get_file(i)
      msg_ptr = '%s%s' % (idx, b64int(msg_fd._pos))

      if msg_ptr in self.PTRS:
        print 'Skipped: %s (%s)' % (msg_ptr, self.PTRS[msg_ptr][0])
        continue

      # Message new or modified, let's parse it.
      p = email.parser.Parser()
      msg = p.parse(msg_fd)
      msg_id = msg['message-id'] or msg_ptr

      if msg_id in self.MSGIDS:
        # Just update location
        self.MSGIDS[msg_id][1] = msg_ptr
        self.PTRS[msg_ptr] = self.MSGIDS[msg_id]
        print 'Updated: %s (%s)' % (msg_ptr, self.PTRS[msg_ptr][0])
      else:
        # Add new message!
        def hdr(name):
          decoded = email.header.decode_header(msg[name] or '')
          try:
            return (''.join([t[0].decode(t[1] or 'iso-8859-1') for t in decoded])
                    ).replace('\t', ' ').replace('\n', ' ')
          except:
            try:
              return (''.join([t[0].decode(t[1] or 'utf-8') for t in decoded])
                      ).replace('\t', ' ').replace('\n', ' ')
            except:
              print 'Boom: %s/%s' % (msg[name], decoded)
              return ''

        msg_info = [b64int(len(self.INDEX)), # Our index ID
                    msg_ptr,                 # Location on disk
                    0,                       # Size
                    msg_id,                  # Message-ID
                    hdr('date'),             # Parsed Date:
                    hdr('from'),             # From:
                    hdr('subject'),          # Subject
                    0,                       # Conversation ID
                    '']                      # No tags for now

        self.INDEX.append(msg_info)
        self.PTRS[msg_ptr] = self.MSGIDS[msg_id] = msg_info
        self.index_message(msg_info, msg)
        print 'Added: %s' % msg_id

      if (i % 100) == 99: self.save()

    return self

  def index_message(self, msg_info, msg):
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
      if textpart:
        # FIXME: Does this lowercase non-ASCII characters correctly?
        keywords |= set(re.findall(re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]:\"|;\'\\'
                                              '\<\>\?,\.\/\-]{2,}'),
                                   textpart.lower()))
    for word in keywords:
      try:
        PostingListStore.Append(word.encode('utf-8'), msg_info[0], self.config)
      except UnicodeDecodeError:
        # FIXME: we just ignore garbage
        pass

 

if __name__ == "__main__":
  re.UNICODE = 1
  re.LOCALE = 1

  config = ConfigManager()
  config.parse(sys.argv[1:])

  index = MailIndex(config)
  index.load();
  index.scan_mbox('000', '000')
  index.save()

