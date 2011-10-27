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
import locale, hashlib, mailbox, os, re, sys, time
import email.parser
import lxml.html


def b64int(i):
  h = hex(int(i))[2:]
  h = (len(h) & 1) and '0'+h or h
  return h.decode('hex').encode('base64').strip().replace('=', '')


class ConfigManager(dict):
  def load(self): pass
  def save(self): pass
  def parse(self, args): pass
  def mailindex_file(self): return self.get('mailindex_file', 'mailpile.idx')
  def postinglist_dir(self): return self.get('postinglist_dir', 'search')


class PostingListStore(object):

  def __init__(self, word, config):
    self.config = config

    h = hashlib.md5()
    h.update(word)
    self.md5 = h.hexdigest().lower()

    self.word = word
    self.WORDS = {self.md5: set()}

    self.load()

  def load(self):
    self.size = 0
    md5 = self.md5
    while len(md5) > 1:
      self.filename = md5
      try:
        fd = open(os.path.join(self.config.postinglist_dir(), self.filename), 'r')
        for line in fd:
          self.size += len(line)
          words = line.strip().split('\t')
          if len(words) > 1:
            if words[0] not in self.WORDS: self.WORDS[words[0]] = set()
            self.WORDS[words[0]] |= set([int(x) for x in words[1:]])
        fd.close()
        return
      except:
        md5 = md5[:-1]

  def save(self, prefix=None):
    if prefix is None:
      if self.size > 100000 and len(self.WORDS.keys()) > 0:
        for c in range(0, 16):
          self.save(prefix='%s%x' % (self.filename, c))
        os.remove(os.path.join(self.config.postinglist_dir(), prefix))
        return
      else:
        prefix = self.filename

    fd = None
    for word in self.WORDS:
      if word.startswith(prefix) and len(self.WORDS[word]) > 0:
        if not fd:
          fd = open(os.path.join(self.config.postinglist_dir(), prefix), 'w')
        fd.write('%s\t%s\n' % (word,
                               '\t'.join(['%s' % x for x in self.WORDS[word]])))
    if fd: fd.close()

  def hits(self):
    return self.WORDS[self.md5]

  def append(self, eid):
    self.WORDS[self.md5].add(int(eid))

  def remove(self, eid):
    self.WORDS[self.md5].remove(int(eid))


class MailIndex(object):
  def __init__(self, config):
    self.config = config
    self.INDEX = []
    self.PTRS = {}
    self.MSGIDS = {}

  def load(self):
    pass

  def save(self):
    fd = open(self.config.mailindex_file(), 'w')
    for item in self.INDEX:
      fd.write('\t'.join([('%s' % i).replace('\n', ' ')
                                    .replace('\t', ' ') for i in item]))
      fd.write('\n')
    fd.close()

  def scan_mbox(self, idx, filename):
    mbox = mailbox.mbox(filename)
    for i in range(0, len(mbox)):
      msg_fd = mbox.get_file(i)
      msg_ptr = '%s%s' % (idx, b64int(msg_fd._pos))

      if msg_ptr in self.PTRS: continue

      # Message new or modified, let's parse it.
      p = email.parser.Parser()
      msg = p.parse(msg_fd)
      msg_id = msg['message-id'] or msg_ptr

      if msg_id in self.MSGIDS:
        self.MSGIDS[msg_id][1] = msg_ptr
      else:
        msg_info = [len(self.INDEX),        # Our index ID
                    msg_ptr,                # Location on disk
                    0,                      # Size
                    msg_id,                 # Message-ID
                    msg['date'] or '',      # Parsed Date:
                    msg['from'] or '',      # From:
                    msg['to'] or '',        # To:
                    msg['subject'] or '',   # Subject
                    0,                      # Conversation ID
                    '']
        self.INDEX.append(msg_info)                    # No tags for now
        self.PTRS[msg_ptr] = self.MSGIDS[msg_id] = msg_info
        self.index_message(msg_info, msg)
        print 'Added: %s' % msg_id

    return self

  def index_message(self, msg_info, msg):
    keywords = set()
    for part in msg.walk():
      charset = part.get_charset() or 'iso8859-1'
      if part.get_content_type() == 'text/plain':
        textpart = part.get_payload(None, True)
      elif part.get_content_type() == 'text/html':
        textpart = lxml.html.fromstring(part.get_payload(None, True)
                                            .decode(charset)).text_content()
      else:
        textpart = None
      if textpart:
        # FIXME: Does this lowercase non-ASCII characters correctly?
        keywords |= set(re.findall(re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]:\"|;\'\\'
                                              '\<\>\?,\.\/\-]{2,}'),
                                   textpart.lower()))
    for word in keywords:
      try:
        pl = PostingListStore(word.encode('utf8'), self.config)
        pl.append(msg_info[0])
        pl.save()
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

