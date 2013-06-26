#!/usr/bin/python
APPVER="0.0.0+github"
ABOUT="""\
Mailpile.py          a tool          Copyright 2011-2013, Bjarni R. Einarsson
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
import mailpile.util
mailpile.ui.ABOUT = ABOUT

from mailpile.commands import COMMANDS, Action_Load, Action_Rescan
from mailpile.mailutils import *
from mailpile.httpd import *
from mailpile.search import *
from mailpile.ui import *
from mailpile.util import *

DEFAULT_SENDMAIL = '|/usr/sbin/sendmail -i %(rcpt)s'


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
    while self.ALIVE and not mailpile.util.QUITTING:
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
    while self.ALIVE and not mailpile.util.QUITTING:
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


class DumbWorker(Worker):
  def add_task(self, session, name, task):
    try:
      self.LOCK.acquire()
      return task()
    finally:
      self.LOCK.release()
  def do(self, session, name, task):
    return self.add_task(session, name, task)
  def run(self):
    pass


##[ The Configuration Manager ]###############################################

class ConfigManager(dict):

  MBOX_CACHE = {}
  RUNNING = {}
  DEFAULT_PATHS = {
    'html_template': 'static/default',
  }

  INTS = ('postinglist_kb', 'sort_max', 'num_results', 'fd_cache_size',
          'http_port', 'rescan_interval')
  STRINGS = ('mailindex_file', 'postinglist_dir', 'default_order',
             'gpg_recipient', 'gpg_keyserver',
             'http_host', 'rescan_command', 'debug', 'local_mailbox')
  DICTS = ('mailbox', 'tag', 'filter', 'filter_terms', 'filter_tags',
           'from', 'sendmail', 'path')

  def __init__(self):
    self.background = None
    self.cron_worker = None
    self.http_worker = None
    self.dumb_worker = self.slow_worker = DumbWorker('Dumb worker', None)
    self.index = None

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
      self[key][subkey.strip()] = val
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
        fd = open(self.conffile(), 'rb')
        try:
          for line in fd:
            if line.startswith(GPG_BEGIN_MESSAGE):
              for line in decrypt_gpg([line], fd):
                self.parse_config(session, line.decode('utf-8'))
            else:
              self.parse_config(session, line.decode('utf-8'))
        except ValueError:
          pass
        fd.close()
      except IOError:
        pass

  def save(self):
    if not os.path.exists(self.workdir()):
      session.ui.notify('Creating: %s' % self.workdir())
      os.mkdir(self.workdir())
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

  def open_mailbox(self, session, mailbox_id):
    pfn = os.path.join(self.workdir(), 'pickled-mailbox.%s' % mailbox_id)
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
          mbox.editable = (mailbox_id == self.get('local_mailbox', None))
          mbox.save(session, to=pfn)
          self.MBOX_CACHE[mid] = mbox
        return self.MBOX_CACHE[mid]
    raise NoSuchMailboxError('No such mailbox: %s' % mailbox_id)

  def open_local_mailbox(self, session):
    local_id = self.get('local_mailbox', None)
    if not local_id:
      mailbox = os.path.join(self.workdir(), 'mail')
      mbx = IncrementalMaildir(mailbox)
      local_id = ('0000%s' % self.nid('mailbox'))[-3:]
      self.parse_set(session, 'mailbox:%s=%s' % (local_id, mailbox))
      self.parse_set(session, 'local_mailbox=%s' % (local_id))
    return local_id, self.open_mailbox(session, local_id)

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
    froms = self.get('from', {})
    for f in froms.keys():
      if f.startswith('*'):
        return '%s <%s>' % (froms[f], f[1:])
    for f in sorted(froms.keys()):
      return '%s <%s>' % (froms[f], f)
    return None

  def get_sendmail(self, sender='default', rcpts='-t'):
    global DEFAULT_SENDMAIL
    sm = self.get('sendmail', {})
    return sm.get(sender, sm.get('default', DEFAULT_SENDMAIL)) % {
      'rcpt': ','.join(rcpts)
    }

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
    try:
      tid = [t for t in self['tag'] if self['tag'][t].lower() == tn]
      return tid and tid[0] or None
    except KeyError:
      return None

  def history_file(self):
    return self.get('history_file',
                    os.path.join(self.workdir(), 'history'))

  def mailindex_file(self):
    return self.get('mailindex_file',
                    os.path.join(self.workdir(), 'mailpile.idx'))

  def postinglist_dir(self, prefix):
    d = self.get('postinglist_dir',
                 os.path.join(self.workdir(), 'search'))
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

  def open_file(self, ftype, fpath, mode='rb'):
    if '..' in fpath:
      raise ValueError('Parent paths are not allowed')

    # This should raise a KeyError if the ftype is unrecognized
    bpath = self.get('path', {}).get(ftype) or self.DEFAULT_PATHS[ftype]
    if not bpath.startswith('/'):
      cpath = os.path.join(self.workdir(), bpath)
      if os.path.exists(cpath) or 'w' in mode:
        bpath = cpath
      else:
        bpath = os.path.join('.SELF', bpath)

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
      config.background.ui = TextUI()
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
      opts, args = getopt.getopt(args, ''.join([k for k in COMMANDS.keys()
                                                if not k[0] == '_']),
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
    mailpile.util.QUITTING = True
    config.stop_workers()

if __name__ == "__main__":
  Main(sys.argv[1:])
