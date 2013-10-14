APPVER="0.0.0+github"
ABOUT="""\
Mailpile.py          a tool          Copyright 2011-2013, Bjarni R. Einarsson
               for searching and                      <http://bre.klaki.net/>
           organizing piles of e-mail

This program is free software: you can redistribute it and/or modify it under
the terms of either the GNU Affero General Public License as published by the
Free Software Foundation or the Apache License 2.0 as published by the Apache
Software Foundation. See the file COPYING.md for details.
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

import mailpile.util
from mailpile.commands import COMMANDS, Action, Help, HelpSplash, Load, Rescan
from mailpile.vcard import SimpleVCard
from mailpile.mailutils import *
from mailpile.httpd import *
from mailpile.search import *
from mailpile.ui import *
from mailpile.util import *
from mailpile.workers import *

Help.ABOUT = ABOUT
DEFAULT_SENDMAIL = '|/usr/sbin/sendmail -i %(rcpt)s'


##[ The Configuration Manager ]###############################################

class ConfigManager(dict):

  MBOX_CACHE = {}
  RUNNING = {}
  DEFAULT_PATHS = {
    'html_theme':    'static/default',
    'vcards':        'vcards',
  }

  CATEGORIES = {
    'cfg': (3, 'User preferences'),
    'prf': (4, 'User profiles and identities'),
    'sys': (0, 'Technical system settings'),
    'tag': (1, 'Tags and filters'),
  }
  INTS = {
    'fd_cache_size':   ('entries',       'sys', 'Max files kept open at once'),
    'history_length':  ('lines',         'sys', 'History length, <0 = no save'),
    'http_port':       ('port',          'sys', 'Listening port for web UI'),
    'num_results':     ('results',       'cfg', 'Search results per page'),
    'postinglist_kb':  ('kilobytes',     'sys', 'Posting list target size'),
    'rescan_interval': ('seconds',       'cfg', 'New mail check frequency'),
    'sort_max':        ('results',       'sys', 'Max results we sort "well"'),
    'snippet_max':     ('characters',    'sys', 'Max size of metadata snippets'),
    'gpg_clearsign':   ('boolean',       'cfg', 'Inline PGP signatures or attached'),
  }
  STRINGS = {
    'debug':           ('level',         'sys', 'Enable debugging'),
    'default_order':   ('order',         'cfg', 'Default sort order'),
    'gpg_recipient':   ('key ID',        'cfg', 'Encrypt local data to ...'),
    'gpg_keyserver':   ('host:port',     'sys', 'Preferred GPG key server'),
    'http_host':       ('hostname',      'sys', 'Listening host for web UI'),
    'local_mailbox':   ('/dir/path',     'sys', 'Local read/write Maildir'),
    'mailindex_file':  ('/file/path',    'sys', 'Metadata index file'),
    'postinglist_dir': ('/dir/path',     'sys', 'Search index directory'),
    'rescan_command':  ('shell command', 'cfg', 'Command run before rescanning'),
    'obfuscate_index': ('key',           'sys', 'Scramble the index using key'),
  }
  DICTS = {
    'mailbox':         ('id=/file/path', 'sys', 'Mailboxes we index'),
    'my_from':         ('email=name',    'prf', 'Name in From: line'),
    'my_sendmail':     ('email=method',  'prf', 'How to send mail'),
    'filter':          ('id=comment',    'tag', 'Human readable description'),
    'filter_terms':    ('id=terms',      'tag', 'Search terms to match on'),
    'filter_tags':     ('id=tags',       'tag', 'Tags to add/remove'),
    'path':            ('ide=/dir/path', 'sys', 'Locations of assorted data'),
    'tag':             ('id=name',       'tag', 'Mailpile tags'),
  }
  CONFIG_MIGRATE = {
    'from': 'my_from',
    'sendmail': 'my_sendmail'
  }

  def __init__(self, workdir=None):
    self.background = None
    self.cron_worker = None
    self.http_worker = None
    self.dumb_worker = self.slow_worker = DumbWorker('Dumb worker', None)
    self.index = None
    self.vcards = {}
    self.workdir = workdir or os.environ.get('MAILPILE_HOME',
                                             os.path.expanduser('~/.mailpile'))

  def conffile(self):
    return os.path.join(self.workdir, 'config.rc')

  def key_string(self, key):
    if ':' in key:
      key, subkey = key.split(':', 1)
    else:
      subkey = None
    if key in self:
      if key in self.INTS:
         return '%s = %s (int)' % (key, self.get(key))
      else:
        val = self.get(key)
        if subkey:
          if subkey in val:
            return '%s:%s = %s' % (key, subkey, val[subkey])
          else:
            return '%s:%s is unset' % (key, subkey)
        else:
          return '%s = %s' % (key, self.get(key))
    else:
      return '%s is unset' % key

  def parse_unset(self, session, arg):
    key = arg.strip().lower()
    if key in self:
      del self[key]
    elif ':' in key and key.split(':', 1)[0] in self.DICTS:
      key, subkey = key.split(':', 1)
      if key in self and subkey in self[key]:
        del self[key][subkey]
    session.ui.notify(self.key_string(key))
    return True

  def parse_set(self, session, line):
    key, val = [k.strip() for k in line.split('=', 1)]
    key = key.lower()
    if ':' in key:
      key, subkey = key.split(':', 1)
    else:
      subkey = None
    key = self.CONFIG_MIGRATE.get(key, key)
    if key in self.INTS and subkey is None:
      try:
        self[key] = int(val)
      except ValueError:
        raise UsageError('%s is not an integer' % val)
    elif key in self.STRINGS and subkey is None:
      self[key] = val
    elif key in self.DICTS and subkey is not None:
      if key not in self:
        self[key] = {}
      self[key][subkey.strip()] = val
    else:
      raise UsageError('Unknown key in config: %s' % key)
    session.ui.notify(self.key_string(key))
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
    if not os.path.exists(self.workdir):
      if session: session.ui.notify('Creating: %s' % self.workdir)
      os.mkdir(self.workdir)
    else:
      self.index = None
      for key in self.INTS.keys() + self.STRINGS.keys() + self.DICTS.keys():
        if key in self:
          del self[key]
      try:
        fd = open(self.conffile(), 'rb')
        try:
          decrypt_and_parse_lines(fd, lambda l: self.parse_config(session, l))
        except ValueError:
          pass
        fd.close()
      except IOError:
        pass
    self.load_vcards(session)

  def save(self):
    if not os.path.exists(self.workdir):
      session.ui.notify('Creating: %s' % self.workdir)
      os.mkdir(self.workdir)
    fd = gpg_open(self.conffile(), self.get('gpg_recipient'), 'wb')
    fd.write('# Mailpile autogenerated configuration file\n')
    for key in sorted(self.keys()):
      if key in self.DICTS:
        for subkey in sorted(self[key].keys()):
          fd.write(('%s:%s = %s\n' % (key, subkey, self[key][subkey])).encode('utf-8'))
      else:
        fd.write(('%s = %s\n' % (key, self[key])).encode('utf-8'))
    fd.close()

  def nid(self, what):
    if what not in self or not self[what]:
      return '0'
    else:
      return b36(1+max([int(k, 36) for k in self[what]]))

  def clear_mbox_cache(self):
    self.MBOX_CACHE = {}

  def is_editable_message(self, msg_info):
    for ptr in msg_info[MailIndex.MSG_PTRS].split(','):
      if not self.is_editable_mailbox(ptr[:MBX_ID_LEN]):
        return False
    editable = False
    for tid in msg_info[MailIndex.MSG_TAGS].split(','):
      # FIXME: Hard-coded tag names are bad
      if self.get('tag', {}).get(tid) in ('Drafts', 'Blank'):
        editable = True
    return editable

  def is_editable_mailbox(self, mailbox_id):
    # FIXME: This may be too narrow?
    mailbox_id = (mailbox_id is None and -1) or int(mailbox_id, 36)
    local_mailbox_id = int(self.get('local_mailbox', 'ZZZZZ'), 36)
    return (mailbox_id == local_mailbox_id)

  def open_mailbox(self, session, mailbox_id):
    pfn = os.path.join(self.workdir, 'pickled-mailbox.%s' % mailbox_id)
    for mid, mailbox_fn in self.get_mailboxes():
      if int(mid, 36) == int(mailbox_id, 36):
        try:
          if mid in self.MBOX_CACHE:
            self.MBOX_CACHE[mid].update_toc()
          else:
            if session:
              session.ui.mark(('%s: Updating: %s'
                               ) % (mailbox_id, mailbox_fn))
            self.MBOX_CACHE[mid] = cPickle.load(open(pfn, 'r'))
        except:
          if session:
            session.ui.mark(('%s: Opening: %s (may take a while)'
                             ) % (mailbox_id, mailbox_fn))
          mbox = OpenMailbox(mailbox_fn)
          mbox.editable = self.is_editable_mailbox(mailbox_id)
          mbox.save(session, to=pfn)
          self.MBOX_CACHE[mid] = mbox
        return self.MBOX_CACHE[mid]
    raise NoSuchMailboxError('No such mailbox: %s' % mailbox_id)

  def open_local_mailbox(self, session):
    local_id = self.get('local_mailbox', None)
    if not local_id:
      mailbox = os.path.join(self.workdir, 'mail')
      mbx = IncrementalMaildir(mailbox)
      local_id = (('0' * MBX_ID_LEN) + self.nid('mailbox'))[-MBX_ID_LEN:]
      self.parse_set(session, 'mailbox:%s=%s' % (local_id, mailbox))
      self.parse_set(session, 'local_mailbox=%s' % (local_id))
    else:
      local_id = (('0' * MBX_ID_LEN) + local_id)[-MBX_ID_LEN:]
    return local_id, self.open_mailbox(session, local_id)

  def filter_swap(self, fid_a, fid_b):
    tmp = {}
    for key in ('filter', 'filter_terms', 'filter_tags'):
      tmp[key] = self[key][fid_a]
    for key in ('filter', 'filter_terms', 'filter_tags'):
      self[key][fid_a] = self[key][fid_b]
    for key in ('filter', 'filter_terms', 'filter_tags'):
      self[key][fid_b] = tmp[key]

  def filter_move(self, filter_id, filter_new_id):
    # This just makes sure both exist, will raise of not
    f1, f2 = self['filter'][filter_id], self['filter'][filter_new_id]
    forig = int(filter_id, 36)
    ftarget = int(filter_new_id, 36)
    if forig > ftarget:
      for fid in reversed(range(ftarget, forig)):
        self.filter_swap(b36(fid+1).lower(), b36(fid).lower())
    else:
      for fid in range(forig, ftarget):
        self.filter_swap(b36(fid).lower(), b36(fid+1).lower())

  def get_filters(self, filter_on=None):
    filters = self.get('filter', {}).keys()
    filters.sort(key=lambda k: int(k, 36))
    flist = []
    for fid in filters:
      comment = self.get('filter', {}).get(fid, '')
      terms = unicode(self.get('filter_terms', {}).get(fid, ''))
      tags = unicode(self.get('filter_tags', {}).get(fid, ''))
      if filter_on is not None and terms != filter_on:
        continue
      flist.append((fid, terms, tags, comment))
    return flist

  def get_from_address(self):
    froms = self.get('my_from', {})
    for f in froms.keys():
      if f.startswith('*'):
        return '%s <%s>' % (froms[f], f[1:])
    for f in sorted(froms.keys()):
      return '%s <%s>' % (froms[f], f)
    return None

  def get_sendmail(self, sender='default', rcpts='-t'):
    global DEFAULT_SENDMAIL
    sm = self.get('my_sendmail', {})
    return sm.get(sender, sm.get('default', DEFAULT_SENDMAIL)) % {
      'rcpt': ','.join(rcpts)
    }

  def get_mailboxes(self):
    def fmt_mbxid(k):
      k = b36(int(k, 36))
      if len(k) > MBX_ID_LEN:
        raise ValueError('Mailbox ID too large: %s' % k)
      return (('0' * MBX_ID_LEN) + k)[-MBX_ID_LEN:]
    mailboxes = self['mailbox'].keys()
    mailboxes.sort()
    return [(fmt_mbxid(k), self['mailbox'][k]) for k in mailboxes]

  def get_tag_id(self, tn):
    tn = tn.lower()
    try:
      tid = [t for t in self['tag'] if self['tag'][t].lower() == tn]
      return tid and tid[0] or None
    except KeyError:
      return None

  def load_vcards(self, session):
    try:
      vcard_dir = self.data_directory('vcards')
      for fn in os.listdir(vcard_dir):
        try:
          c = SimpleVCard().load(os.path.join(vcard_dir, fn))
          c.gpg_recipient = lambda: self.get('gpg_recipient')
          self.index_vcard(c)
          session.ui.mark('Loaded %s' % c.email)
        except:
          import traceback
          traceback.print_exc()
          session.ui.warning('Failed to load vcard %s' % fn)
    except OSError:
      pass

  def index_vcard(self, c):
    if c.kind == 'individual':
      for email, attrs in c.get('EMAIL', []):
        self.vcards[email.lower()] = c
    else:
      for handle, attrs in c.get('NICKNAME', []):
        self.vcards[handle.lower()] = c
    self.vcards[c.random_uid] = c

  def deindex_vcard(self, c):
    for email, attrs in c.get('EMAIL', []):
      if email.lower() in self.vcards:
        if c.kind == 'individual':
          del self.vcards[email.lower()]
    for handle, attrs in c.get('NICKNAME', []):
      if handle.lower() in self.vcards:
        if c.kind != 'individual':
          del self.vcards[handle.lower()]
    if c.random_uid in self.vcards:
      del self.vcards[c.random_uid]

  def get_vcard(self, email):
    return self.vcards.get(email.lower(), None)

  def find_vcards(self, terms, kinds=['individual']):
    results, vcards = [], self.vcards
    if not terms:
      results = [set([vcards[k].random_uid for k in vcards
                      if (vcards[k].kind in kinds) or not kinds])]
    for term in terms:
      term = term.lower()
      results.append(set([vcards[k].random_uid for k in vcards
                          if (term in k or term in vcards[k].fn.lower())
                          and ((vcards[k].kind in kinds) or not kinds)]))
    while len(results) > 1:
      results[0] &= results.pop(-1)
    results = [vcards[c] for c in results[0]]
    results.sort(key=lambda k: k.fn)
    return results

  def add_vcard(self, handle, name=None, kind=None):
    vcard_dir = self.data_directory('vcards', mode='w', mkdir=True)
    c = SimpleVCard()
    c.filename = os.path.join(vcard_dir, c.random_uid) + '.vcf'
    c.gpg_recipient = lambda: self.get('gpg_recipient')
    if kind == 'individual':
      c.email = handle
    else:
      c['NICKNAME'] = handle
    if name is not None: c.fn = name
    if kind is not None: c.kind = kind
    self.index_vcard(c)
    return c.save()

  def del_vcard(self, email):
    vcard = self.get_vcard(email)
    try:
      if vcard:
        self.deindex_vcard(vcard)
        os.remove(vcard.filename)
        return True
      else:
        return False
    except (OSError, IOError):
      return False

  def history_file(self):
    return self.get('history_file',
                    os.path.join(self.workdir, 'history'))

  def mailindex_file(self):
    return self.get('mailindex_file',
                    os.path.join(self.workdir, 'mailpile.idx'))

  def postinglist_dir(self, prefix):
    d = self.get('postinglist_dir',
                 os.path.join(self.workdir, 'search'))
    if not os.path.exists(d): os.mkdir(d)
    d = os.path.join(d, prefix and prefix[0] or '_')
    if not os.path.exists(d): os.mkdir(d)
    return d

  def get_index(self, session):
    if self.index: return self.index
    idx = MailIndex(self)
    idx.load(session)
    self.index = idx
    return idx

  def data_directory(self, ftype, mode='rb', mkdir=False):
    # This should raise a KeyError if the ftype is unrecognized
    bpath = self.get('path', {}).get(ftype) or self.DEFAULT_PATHS[ftype]
    if not bpath.startswith('/'):
      cpath = os.path.join(self.workdir, bpath)
      if os.path.exists(cpath) or 'w' in mode:
        bpath = cpath
        if mkdir and not os.path.exists(cpath):
          os.mkdir(cpath)
      else:
        bpath = os.path.join(os.path.dirname(__file__), '..', bpath)
    return bpath

  def open_file(self, ftype, fpath, mode='rb', mkdir=False):
    if '..' in fpath:
      raise ValueError('Parent paths are not allowed')
    bpath = self.data_directory(ftype, mode=mode, mkdir=mkdir)
    fpath = os.path.join(bpath, fpath)
    return fpath, open(fpath, mode)

  def prepare_workers(config, session, daemons=False):
    # Set globals from config first...
    global APPEND_FD_CACHE_SIZE
    APPEND_FD_CACHE_SIZE = config.get('fd_cache_size',
                                      APPEND_FD_CACHE_SIZE)

    if not config.background:
      # Create a silent background session
      config.background = Session(config)
      config.background.ui = BackgroundInteraction(config)
      config.background.ui.block()

    # Start the workers
    if config.slow_worker == config.dumb_worker:
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
            rsc = Rescan(session, 'rescan')
            rsc.serialize = False
            config.slow_worker.add_task(None, 'Rescan', rsc.run)
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

  # Negative history means no saving state to disk.
  history_length = session.config.get('history_length', 100)
  if history_length >= 0:
    readline.set_history_length(history_length)
  else:
    readline.set_history_length(-history_length)

  try:
    prompt = session.ui.palette.color('mailpile> ',
                                      color=session.ui.palette.BLACK,
                                      weight=session.ui.palette.BOLD)
    while True:
      session.ui.block()
      opt = raw_input(prompt).decode('utf-8').strip()
      session.ui.unblock()
      if opt:
        if ' ' in opt:
          opt, arg = opt.split(' ', 1)
        else:
          arg = ''
        try:
          session.ui.display_result(Action(session, opt, arg))
        except UsageError, e:
          session.error(unicode(e))
        except UrlRedirectException, e:
          session.error('Tried to redirect to: %s' % e.url)
  except EOFError:
    print

  try:
    if session.config.get('history_length', 100) > 0:
      readline.write_history_file(session.config.history_file())
    else:
      os.remove(session.config.history_file())
  except OSError:
    pass

def Main(args):
  re.UNICODE = 1
  re.LOCALE = 1

  try:
    # Create our global config manager and the default (CLI) session
    config = ConfigManager()
    session = Session(config)
    session.config.load(session)
    session.main = True
    session.ui = UserInteraction(config)
    if sys.stdout.isatty():
      session.ui.palette = ANSIColors()
  except AccessError, e:
    sys.stderr.write('Access denied: %s\n' % e)
    sys.exit(1)

  try:
    # Create and start (most) worker threads
    config.prepare_workers(session)

    try:
      shorta, longa = '', []
      for cls in COMMANDS:
        shortn, longn, urlpath, arglist = cls.SYNOPSIS[:4]
        if arglist:
          if shortn: shortn += ':'
          if longn: longn += '='
        if shortn: shorta += shortn
        if longn: longa.append(longn.replace(' ', '_'))

      opts, args = getopt.getopt(args, shorta, longa)
      for opt, arg in opts:
        Action(session, opt.replace('-', ''), arg.decode('utf-8'))
      if args:
        Action(session, args[0], ' '.join(args[1:]).decode('utf-8'))

    except (getopt.GetoptError, UsageError), e:
      session.error(e)

    if not opts and not args:
      # Create and start the rest of the threads, load the index.
      session.interactive = session.ui.interactive = True
      config.prepare_workers(session, daemons=True)
      Load(session, '').run(quiet=True)
      session.ui.display_result(HelpSplash(session, 'help', []).run())
      Interact(session)

  except KeyboardInterrupt:
    pass

  finally:
    mailpile.util.QUITTING = True
    config.stop_workers()

if __name__ == "__main__":
  Main(sys.argv[1:])
