import copy
import cPickle
import io
import jinja2
import json
import os
import socket
import sys
import random
import re
import threading
import traceback
import ConfigParser

from urllib import quote, unquote
from urlparse import urlparse

from mailpile.command_cache import CommandCache
from mailpile.crypto.streamer import DecryptingStreamer
from mailpile.crypto.gpgi import GnuPG
from mailpile.eventlog import EventLog, Event, GetThreadEvent
from mailpile.httpd import HttpWorker
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import OpenMailbox, NoSuchMailboxError, wervd
from mailpile.mailutils import FormatMbxId, MBX_ID_LEN
from mailpile.search import MailIndex
from mailpile.search_history import SearchHistory
from mailpile.security import SecurePassphraseStorage
from mailpile.ui import Session, BackgroundInteraction
from mailpile.util import *
from mailpile.vcard import VCardStore
from mailpile.vfs import vfs, FilePath, MailpileVfsRoot
from mailpile.workers import Worker, ImportantWorker, DumbWorker, Cron
import mailpile.i18n
import mailpile.vfs
import mailpile.util

from mailpile.config.base import *
from mailpile.config.defaults import APPVER
from mailpile.config.detect import socks
from mailpile.www.jinjaloader import MailpileJinjaLoader


MAX_CACHED_MBOXES = 5

GLOBAL_INDEX_CHECK = ConfigLock()
GLOBAL_INDEX_CHECK.acquire()


class ConfigManager(ConfigDict):
    """
    This class manages the live global mailpile configuration. This includes
    the settings themselves, as well as global objects like the index and
    references to any background worker threads.
    """
    @classmethod
    def DEFAULT_WORKDIR(self):
        # The Mailpile environment variable trumps everything
        workdir = os.getenv('MAILPILE_HOME')
        if workdir:
            return workdir

        profile = os.getenv('MAILPILE_PROFILE', 'default')
        if profile == 'default':
            # Backwards compatibility: If the old ~/.mailpile exists, use it.
            workdir = os.path.expanduser('~/.mailpile')
            if os.path.exists(workdir) and os.path.isdir(workdir):
                return workdir

        # FIXME: the logic below should be rewritten to use the appdirs
        #        python packages, as per issue #870

        basedir = None
        if sys.platform.startswith('win'):
            # Obey Windows conventions (more or less?)
            basedir = os.getenv('APPDATA', os.path.expanduser('~'))
        elif sys.platform.startswith('darwin'):
            # Obey Mac OS X conventions
            basedir = os.path.expanduser('~/Library/Application Support')
        else:
            # Assume other platforms are Unixy
            basedir = os.getenv('XDG_DATA_HOME',
                                os.path.expanduser('~/.local/share'))

        return os.path.join(basedir, 'Mailpile', profile)

    @classmethod
    def DEFAULT_SHARED_DATADIR(self):
        # IMPORTANT: This code is duplicated in mailpile-admin.py.
        #            If it needs changing please change both places!
        env_share = os.getenv('MAILPILE_SHARED')
        if env_share is not None:
            return env_share

        # Check if we are running in a virtual env
        # http://stackoverflow.com/questions/1871549/python-determine-if-running-inside-virtualenv
        # We must also check that we are installed in the virtual env,
        # not just that we are running in a virtual env.
        if (hasattr(sys, 'real_prefix') or hasattr(sys, 'base_prefix')) and __file__.startswith(sys.prefix):
            return os.path.join(sys.prefix, 'share', 'mailpile')

        # Check if we've been installed to /usr/local (or equivalent)
        usr_local = os.path.join(sys.prefix, 'local')
        if __file__.startswith(usr_local):
            return os.path.join(usr_local, 'share', 'mailpile')

        # Check if we are in /usr/ (sys.prefix)
        if __file__.startswith(sys.prefix):
            return os.path.join(sys.prefix, 'share', 'mailpile')

        # Else assume dev mode, source tree layout
        return os.path.join(
            os.path.dirname(__file__), '..', '..', 'shared-data')

    def __init__(self, workdir=None, shareddatadir=None, rules={}):
        ConfigDict.__init__(self, _rules=rules, _magic=False)

        self.workdir = os.path.abspath(workdir or self.DEFAULT_WORKDIR())
        mailpile.vfs.register_alias('/Mailpile', self.workdir)

        self.shareddatadir = os.path.abspath(shareddatadir or
                                             self.DEFAULT_SHARED_DATADIR())
        mailpile.vfs.register_alias('/Share', self.shareddatadir)

        self.vfs_root = MailpileVfsRoot(self)
        mailpile.vfs.register_handler(0000, self.vfs_root)

        self.conffile = os.path.join(self.workdir, 'mailpile.cfg')
        self.conf_key = os.path.join(self.workdir, 'mailpile.key')
        self.conf_pub = os.path.join(self.workdir, 'mailpile.rc')

        # If the master key changes, we update the file on save, otherwise
        # the file is untouched. So we keep track of things here.
        self._master_key_ondisk = None
        self._master_key_passgen = -1

        # Make sure we have a silent background session
        self.background = Session(self)
        self.background.ui = BackgroundInteraction(self)

        self.plugins = None
        self.http_worker = None
        self.dumb_worker = DumbWorker('Dumb worker', self.background)
        self.slow_worker = self.dumb_worker
        self.scan_worker = self.dumb_worker
        self.save_worker = self.dumb_worker
        self.other_workers = []
        self.mail_sources = {}

        self.event_log = None
        self.index = None
        self.index_check = GLOBAL_INDEX_CHECK
        self.vcards = {}
        self.search_history = SearchHistory()
        self._mbox_cache = []
        self._running = {}
        self._lock = ConfigRLock()
        self.loaded_config = False

        def cache_debug(msg):
            if self.background and 'cache' in self.sys.debug:
                self.background.ui.debug(msg)
        self.command_cache = CommandCache(debug=cache_debug)

        self.passphrases = {
            'DEFAULT': SecurePassphraseStorage(),
        }

        self.jinja_env = jinja2.Environment(
            loader=MailpileJinjaLoader(self),
            cache_size=400,
            autoescape=True,
            trim_blocks=True,
            extensions=['jinja2.ext.i18n', 'jinja2.ext.with_',
                        'jinja2.ext.do', 'jinja2.ext.autoescape',
                        'mailpile.www.jinjaextensions.MailpileCommand']
        )

        self.cron_schedule = {}
        self.cron_worker = Cron(self.cron_schedule, 'Cron worker', self.background)
        self.cron_worker.daemon = True
        self.cron_worker.start()

        self._magic = True  # Enable the getattr/getitem magic

    def _mkworkdir(self, session):
        if not os.path.exists(self.workdir):
            if session:
                session.ui.notify(_('Creating: %s') % self.workdir)
            os.makedirs(self.workdir, mode=0700)

    def parse_config(self, session, data, source='internal'):
        """
        Parse a config file fragment. Invalid data will be ignored, but will
        generate warnings in the session UI. Returns True on a clean parse,
        False if any of the settings were bogus.

        >>> cfg.parse_config(session, '[config/sys]\\nfd_cache_size = 123\\n')
        True
        >>> cfg.sys.fd_cache_size
        123

        >>> cfg.parse_config(session, '[config/bogus]\\nblabla = bla\\n')
        False
        >>> [l[1] for l in session.ui.log_buffer if 'bogus' in l[1]][0]
        'Invalid (internal): section config/bogus does not exist'

        >>> cfg.parse_config(session, '[config/sys]\\nhistory_length = 321\\n'
        ...                                          'bogus_variable = 456\\n')
        False
        >>> cfg.sys.history_length
        321
        >>> [l[1] for l in session.ui.log_buffer if 'bogus_var' in l[1]][0]
        u'Invalid (internal): section config/sys, ...

        >>> cfg.parse_config(session, '[config/tags/a]\\nname = TagName\\n')
        True
        >>> cfg.tags['a']._key
        'a'
        >>> cfg.tags['a'].name
        u'TagName'
        """
        parser = CommentedEscapedConfigParser()
        parser.readfp(io.BytesIO(str(data)))

        def item_sorter(i):
            try:
                return (int(i[0], 36), i[1])
            except (ValueError, IndexError, KeyError, TypeError):
                return i

        all_okay = True
        for section in parser.sections():
            okay = True
            cfgpath = section.split(':')[0].split('/')[1:]
            cfg = self
            added_parts = []
            for part in cfgpath:
                if cfg.fmt_key(part) in cfg.keys():
                    cfg = cfg[part]
                elif '_any' in cfg.rules:
                    cfg[part] = {}
                    cfg = cfg[part]
                else:
                    if session:
                        msg = _('Invalid (%s): section %s does not '
                                'exist') % (source, section)
                        session.ui.warning(msg)
                    all_okay = okay = False
            items = parser.items(section) if okay else []
            items.sort(key=item_sorter)
            for var, val in items:
                try:
                    cfg[var] = val
                except (ValueError, KeyError, IndexError):
                    if session:
                        msg = _(u'Invalid (%s): section %s, variable %s=%s'
                                ) % (source, section, var, val)
                        session.ui.warning(msg)
                    all_okay = okay = False
        return all_okay

    def load(self, session, *args, **kwargs):
        from mailpile.plugins.core import Rescan

        keep_lockdown = self.sys.lockdown
        with self._lock:
            rv = self._unlocked_load(session, *args, **kwargs)

        # If the app version does not match the config, run setup.
        if self.version != APPVER:
            from mailpile.plugins.setup_magic import Setup
            Setup(session, 'setup').run()

        # Trigger background-loads of everything
        Rescan(session, 'rescan')._idx(wait=False)

        if keep_lockdown:
            self.sys.lockdown = keep_lockdown
        return rv

    def load_master_key(self, passphrase, _raise=None):
        keydata = []

        if passphrase.is_set():
            parser = lambda d: keydata.extend(d)
            try:
                with open(self.conf_key, 'rb') as fd:
                    decrypt_and_parse_lines(fd, parser, self,
                                            newlines=True,
                                            passphrase=passphrase)
            except IOError:
                keydata = []

        if keydata:
            self.passphrases['DEFAULT'].copy(passphrase)
            self.master_key = ''.join(keydata)
            self._master_key_ondisk = self.master_key
            self._master_key_passgen = self.passphrases['DEFAULT'].generation
            return True
        else:
            if _raise is not None:
                raise _raise('Failed to decrypt master key')
            return False

    def _load_config_lines(self, filename, lines):
        collector = lambda ll: lines.extend(ll)
        if os.path.exists(filename):
            with open(filename, 'rb') as fd:
                decrypt_and_parse_lines(fd, collector, self)

    def _discover_plugins(self):
        # Discover plugins and update the config rule to match
        from mailpile.plugins import PluginManager
        self.plugins = PluginManager(config=self, builtin=True).discover([
            os.path.join(self.shareddatadir, 'contrib'),
            os.path.join(self.workdir, 'plugins')
        ])
        self.sys.plugins.rules['_any'][self.RULE_CHECKER
                                       ] = [None] + self.plugins.loadable()

    def _configure_default_plugins(self):
        if len(self.sys.plugins) == 0:
            self.sys.plugins.extend(self.plugins.DEFAULT)
            for plugin in self.plugins.WANTED:
                if plugin in self.plugins.available():
                    self.sys.plugins.append(plugin)
        else:
            for pos in range(0, len(self.sys.plugins)):
                name = self.sys.plugins[pos]
                if name in self.plugins.RENAMED:
                    self.sys.plugins[pos] = self.plugins.RENAMED[name]

    def _unlocked_load(self, session):
        # This method will attempt to load the full configuration.
        #
        # The Mailpile configuration is in two parts:
        #    - public data in "mailpile.rc"
        #    - private data in "mailpile.cfg" (encrypted)
        #
        # This method may successfully load and process from the public part,
        # but fail to load the encrypted part due to a lack of authentication.
        # In this case IOError will be raised.
        #
        self._mkworkdir(session)
        if self.index:
            self.index_check.acquire()
            self.index = None

        # Set the homedir default
        self.rules['homedir'][2] = self.workdir
        self._rules_source['homedir'][2] = self.workdir
        self.reset(rules=False, data=True)
        self.loaded_config = False
        pub_lines, prv_lines = [], []
        try:
            self._load_config_lines(self.conf_pub, pub_lines)
            if os.path.exists(self.conf_key):
                self.load_master_key(self.passphrases['DEFAULT'],
                                     _raise=IOError)
            self._load_config_lines(self.conffile, prv_lines)
        except IOError:
            self.loaded_config = False
            raise
        except (ValueError, OSError):
            # Bad data in config or config doesn't exist: just forge onwards
            pass
        finally:
            ## The following things happen, no matter how loading went...

            # Discover plugins first, as this affects what is or is not valid
            # in the configuration file.
            self._discover_plugins()

            # Parse once (silently), to figure out which plugins to load...
            self.parse_config(None, '\n'.join(pub_lines), source=self.conf_pub)
            self.parse_config(None, '\n'.join(prv_lines), source=self.conffile)

            # Enable translations!
            mailpile.i18n.ActivateTranslation(session, self, self.prefs.language)

            # Configure and load plugins as per config requests
            with mailpile.i18n.i18n_disabled:
                self._configure_default_plugins()
                self.load_plugins(session)

            # Now all the plugins are loaded, reset and parse again!
            self.reset_rules_from_source()
            self.parse_config(session, '\n'.join(pub_lines), source=self.conf_pub)
            self.parse_config(session, '\n'.join(prv_lines), source=self.conffile)

        ## The following events only happen when we've successfully loaded
        ## both config files!

        # Open event log
        dec_key_func = lambda: self.master_key
        enc_key_func = lambda: (self.prefs.encrypt_events and
                                self.master_key)
        self.event_log = EventLog(self.data_directory('event_log',
                                                      mode='rw', mkdir=True),
                                  dec_key_func, enc_key_func
                                  ).load()
        if 'log' in self.sys.debug:
            self.event_log.ui_watch(session.ui)
        else:
            self.event_log.ui_unwatch(session.ui)

        # Load VCards
        self.vcards = VCardStore(self, self.data_directory('vcards',
                                                           mode='rw',
                                                           mkdir=True))

        # Recreate VFS root in case new things have been found
        self.vfs_root.rescan()

        # Load Search History
        self.search_history = SearchHistory.Load(self,
                                                 merge=self.search_history)

        # OK, we're happy
        self.loaded_config = True

    def reset_rules_from_source(self):
        with self._lock:
            self.set_rules(self._rules_source)
            self.sys.plugins.rules['_any'][
                self.RULE_CHECKER] = [None] + self.plugins.loadable()

    def load_plugins(self, session):
        with self._lock:
            from mailpile.plugins import PluginManager
            plugin_list = set(PluginManager.REQUIRED + self.sys.plugins)
            for plugin in plugin_list:
                if plugin is not None:
                    session.ui.mark(_('Loading plugin: %s') % plugin)
                    self.plugins.load(plugin)
            session.ui.mark(_('Processing manifests'))
            self.plugins.process_manifests()
            self.prepare_workers(session)

    def save(self, *args, **kwargs):
        with self._lock:
            self._unlocked_save(*args, **kwargs)

    def _save_master_key(self, keyfile):
        if not self.master_key:
            return False

        # We keep the master key in a file of its own and never delete
        # or overwrite master keys.
        want_renamed_keyfile = None
        master_passphrase = self.passphrases['DEFAULT']
        if (self._master_key_passgen != master_passphrase.generation
                or self._master_key_ondisk != self.master_key):
            if os.path.exists(keyfile):
                want_renamed_keyfile = keyfile + ('.%x' % time.time())

        if not want_renamed_keyfile and os.path.exists(keyfile):
            # Key file exists, nothing needs to be changed. Happy!
            return True

        # Figure out whether we are encrypting to a GPG key, or using
        # symmetric encryption (with the 'DEFAULT' passphrase).
        gpgr = self.prefs.get('gpg_recipient', '').replace(',', ' ')
        tokeys = (gpgr.split()
                  if (gpgr and gpgr not in ('!CREATE', '!PASSWORD'))
                  else None)

        if not tokeys and not master_passphrase.is_set():
            # Without recipients or a passphrase, we cannot save!
            return False

        # FIXME: Create event and capture GnuPG state?
        status, encrypted_key = GnuPG(self).encrypt(self.master_key,
                                                    tokeys=tokeys)
        if status == 0:
            try:
                with open(keyfile + '.new', 'wb') as fd:
                    fd.write(encrypted_key)
                if want_renamed_keyfile:
                    os.rename(keyfile, want_renamed_keyfile)
                os.rename(keyfile + '.new', keyfile)
                self._master_key_ondisk = self.master_key
                self._master_key_passgen = master_passphrase.generation
                return True
            except:
                if (want_renamed_keyfile and
                        os.path.exists(want_renamed_keyfile)):
                    os.rename(want_renamed_keyfile, keyfile)
                raise

        return False

    def _unlocked_save(self, session=None):
        newfile = '%s.new' % self.conffile
        pubfile = self.conf_pub
        keyfile = self.conf_key

        self._mkworkdir(None)
        self.timestamp = int(time.time())

        if session and self.event_log:
            if 'log' in self.sys.debug:
                self.event_log.ui_watch(session.ui)
            else:
                self.event_log.ui_unwatch(session.ui)

        # Save the public config data first
        with open(pubfile, 'wb') as fd:
            fd.write(self.as_config_bytes(_type='public'))

        if not self.loaded_config:
            return

        # Save the master key if necessary (and possible)
        master_key_saved = self._save_master_key(keyfile)

        # This slight over-complication, is a reaction to segfaults in
        # Python 2.7.5's fd.write() method.  Let's just feed it chunks
        # of data and hope for the best. :-/
        config_bytes = self.as_config_bytes(_xtype='public')
        config_chunks = (config_bytes[i:i + 4096]
                         for i in range(0, len(config_bytes), 4096))

        from mailpile.crypto.streamer import EncryptingStreamer
        if self.master_key and master_key_saved:
            subj = self.mailpile_path(self.conffile)
            with EncryptingStreamer(self.master_key,
                                    dir=self.tempfile_dir(),
                                    header_data={'subject': subj},
                                    name='Config') as fd:
                for chunk in config_chunks:
                    fd.write(chunk)
                fd.save(newfile)
        else:
            # This may result in us writing the master key out in the
            # clear, but that is better than losing data. :-(
            with open(newfile, 'wb') as fd:
                for chunk in config_chunks:
                    fd.write(chunk)

        # Keep the last 5 config files around... just in case.
        backup_file(self.conffile, backups=5, min_age_delta=900)
        if sys.platform.startswith('win'):
            try:
                os.remove(self.conffile)
            except WindowsError:
                pass
        os.rename(newfile, self.conffile)

        if not mailpile.util.QUITTING:
            # Enable translations
            mailpile.i18n.ActivateTranslation(None, self, self.prefs.language)

            # Recreate VFS root in case new things have been configured
            self.vfs_root.rescan()

            # Prepare workers
            self.prepare_workers(daemons=self.daemons_started())
            delay = 1
            for mail_source in self.mail_sources.values():
                mail_source.wake_up(after=delay)
                delay += 2
        self.command_cache.mark_dirty([u'!config'])

    def _find_mail_source(self, mbx_id, path=None):
        if path:
            path = FilePath(path).raw_fp
            if path[:5] == '/src:':
                return self.sources[path[5:].split('/')[0]]
            if path[:4] == 'src:':
                return self.sources[path[4:].split('/')[0]]
        for src in self.sources.values():
            # Note: we cannot test 'mbx_id in ...' because of case sensitivity.
            if src.mailbox[FormatMbxId(mbx_id)] is not None:
                return src
        return None

    def get_mailboxes(self, with_mail_source=None,
                            mail_source_locals=False):
        try:
            mailboxes = [(FormatMbxId(k),
                          self.sys.mailbox[k],
                          self._find_mail_source(k))
                          for k in self.sys.mailbox.keys()
                          if self.sys.mailbox[k] != '/dev/null']
        except (AttributeError):
            # Config not loaded, nothing to see here
            return []

        if with_mail_source is True:
            mailboxes = [(i, p, s) for i, p, s in mailboxes if s]
        elif with_mail_source is False:
            mailboxes = [(i, p, s) for i, p, s in mailboxes if not s]
        else:
            pass  # All mailboxes, with or without mail sources

        if mail_source_locals:
            for i in range(0, len(mailboxes)):
                mid, path, src = mailboxes[i]
                mailboxes[i] = (mid,
                                src and src.mailbox[mid].local or path,
                                src)

        mailboxes.sort()
        return mailboxes

    def is_editable_message(self, msg_info):
        for ptr in msg_info[MailIndex.MSG_PTRS].split(','):
            if not self.is_editable_mailbox(ptr[:MBX_ID_LEN]):
                return False
        editable = False
        for tid in msg_info[MailIndex.MSG_TAGS].split(','):
            try:
                if self.tags and self.tags[tid].flag_editable:
                    editable = True
            except (KeyError, AttributeError):
                pass
        return editable

    def is_editable_mailbox(self, mailbox_id):
        try:
            mailbox_id = ((mailbox_id is None and -1) or
                          (mailbox_id == '' and -1) or
                          int(mailbox_id, 36))
            local_mailbox_id = int(self.sys.get('local_mailbox_id', 'ZZZZZ'),
                                   36)
            return (mailbox_id == local_mailbox_id)
        except ValueError:
            return False

    def load_pickle(self, pfn):
        with open(os.path.join(self.workdir, pfn), 'rb') as fd:
            if self.master_key:
                from mailpile.crypto.streamer import DecryptingStreamer
                with DecryptingStreamer(fd,
                                        mep_key=self.master_key,
                                        name='load_pickle'
                                        ) as streamer:
                    rv = cPickle.loads(streamer.read())
                    streamer.verify(_raise=IOError)
                    return rv
            else:
                return cPickle.loads(fd.read())

    def save_pickle(self, obj, pfn, encrypt=True):
        ppath = os.path.join(self.workdir, pfn)
        if encrypt and self.master_key and self.prefs.encrypt_misc:
            from mailpile.crypto.streamer import EncryptingStreamer
            with EncryptingStreamer(self.master_key,
                                    dir=self.tempfile_dir(),
                                    header_data={'subject': pfn},
                                    name='save_pickle') as fd:
                cPickle.dump(obj, fd, protocol=0)
                fd.save(ppath)
        else:
            with open(ppath, 'wb') as fd:
                cPickle.dump(obj, fd, protocol=0)

    def _mailbox_info(self, mailbox_id, prefer_local=True):
        try:
            with self._lock:
                mbx_id = FormatMbxId(mailbox_id)
                mfn = self.sys.mailbox[mbx_id]
                src = self._find_mail_source(mailbox_id, path=mfn)
                pfn = 'pickled-mailbox.%s' % mbx_id.lower()
                if prefer_local and src and src.mailbox[mbx_id] is not None:
                    mfn = src and src.mailbox[mbx_id].local or mfn
                else:
                    pfn += '-R'
        except (KeyError, TypeError):
            traceback.print_exc()
            raise NoSuchMailboxError(_('No such mailbox: %s') % mbx_id)
        return mbx_id, src, FilePath(mfn), pfn

    def save_mailbox(self, session, pfn, mbox):
        mbox.save(session,
                  to=pfn, pickler=lambda o, f: self.save_pickle(o, f))

    def uncache_mailbox(self, session, pfn, drop=True, force_save=False):
        with self._lock:
            mboxes = [c[2] for c in self._mbox_cache if c[0] == pfn]
            if len(mboxes) > 0:
                # At this point, if the mailbox is not in use, there should be
                # exactly 2 references to it: in mboxes and self._mbox_cache.
                # However, sys.getrefcount always returns one extra for itself.
                if sys.getrefcount(mboxes[0]) > 3:
                    if force_save:
                        self.save_mailbox(session, pfn, mboxes[0])
                    return

                # This may be slow, but it has to happen inside the lock
                # otherwise we run the risk of races.
                self.save_mailbox(session, pfn, mboxes[0])
            else:
                # Not found, nothing to do here
                return

            if drop:
                self._mbox_cache = [c for c in self._mbox_cache if c[0] != pfn]
            else:
                keep2 = self._mbox_cache[-MAX_CACHED_MBOXES:]
                keep1 = [c for c in self._mbox_cache[:-MAX_CACHED_MBOXES]
                         if c[0] != pfn]
                self._mbox_cache = keep1 + keep2

    def cache_mailbox(self, session, pfn, mbx_id, mbox):
        with self._lock:
            self._mbox_cache = [c for c in self._mbox_cache if c[0] != pfn]
            self._mbox_cache.append((pfn, mbx_id, mbox))
            flush = [(p[0], p[1])
                     for p in self._mbox_cache[:-MAX_CACHED_MBOXES]]
        for pfn, mbx_id in flush:
            self.save_worker.add_unique_task(
                session, 'Save mailbox %s (drop=%s)' % (mbx_id, False),
                lambda: self.uncache_mailbox(session, pfn, drop=False))

    def flush_mbox_cache(self, session, clear=True, wait=False):
        if wait:
            saver = self.save_worker.do
        else:
            saver = self.save_worker.add_task
        with self._lock:
            flush = [(p[0], p[1]) for p in self._mbox_cache]
        for pfn, mbx_id in flush:
            saver(session,
                  'Save mailbox %s (drop=%s)' % (mbx_id, clear),
                  lambda: self.uncache_mailbox(session, pfn,
                                               drop=clear, force_save=True),
                  unique=True)

    def find_mboxids_and_sources_by_path(self, *paths):
        def _au(p):
            return unicode(p[1:] if (p[:5] == '/src:') else
                           p if (p[:4] == 'src:') else
                           vfs.abspath(p))
        abs_paths = dict((_au(p), [p]) for p in paths)
        with self._lock:
            for sid, src in self.sources.iteritems():
                for mid, info in src.mailbox.iteritems():
                    umfn = _au(self.sys.mailbox[mid])
                    if umfn in abs_paths:
                        abs_paths[umfn].append((mid, src))
                    if info.local:
                        lmfn = _au(info.local)
                        if lmfn in abs_paths:
                            abs_paths[lmfn].append((mid, src))

            for mid, mfn in self.sys.mailbox.iteritems():
                umfn = _au(mfn)
                if umfn in abs_paths:
                    if umfn[:4] == u'src:':
                        src = self.sources.get(umfn[4:].split('/')[0])
                    else:
                        src = None
                    abs_paths[umfn].append((mid, src))

        return dict((p[0], p[1]) for p in abs_paths.values() if p[1:])

    def open_mailbox_path(self, session, path, register=False):
        path = vfs.abspath(path)
        mbox = mbx_mid = mbx_src = None
        with self._lock:
            msmap = self.find_mboxids_and_sources_by_path(unicode(path))
            if msmap:
                mbx_mid, mbx_src = list(msmap.values())[0]

            if register and mbx_mid is None:
                if path.raw_fp.startswith('/src:'):
                    path = FilePath(path.raw_fp[1:])
                    msrc_id = path.raw_fp[4:].split('/')[0]
                    msrc = self.mail_sources.get(msrc_id)
                    if msrc:
                        mbox = msrc.open_mailbox(None, path.raw_fp)
                else:
                    mbox = OpenMailbox(path.raw_fp, self, create=False)
                mbx_mid = self.sys.mailbox.append(unicode(path))

        if mbx_mid is not None:
            mbx_mid = FormatMbxId(mbx_mid)
            if mbox is None:
                mbox = self.open_mailbox(session, mbx_mid, prefer_local=True)
            return (mbx_mid, mbox)
        raise ValueError('Not found')

    def open_mailbox(self, session, mailbox_id,
                     prefer_local=True, from_cache=False):
        mbx_id, src, mfn, pfn = self._mailbox_info(mailbox_id,
                                                   prefer_local=prefer_local)
        with self._lock:
            mbox = dict(((p, m) for p, i, m in self._mbox_cache)
                        ).get(pfn, None)
        try:
            if mbox is None:
                if from_cache:
                    return None
                if session:
                    session.ui.mark(_('%s: Updating: %s') % (mbx_id, mfn))
                mbox = self.load_pickle(pfn)
            if prefer_local and not mbox.is_local:
                mbox = None
            else:
                mbox.update_toc()
        except AttributeError:
            mbox = None
        except KeyboardInterrupt:
            raise
        except IOError:
            pass
        except:
            if self.sys.debug:
                import traceback
                traceback.print_exc()

        if mbox is None:
            if session:
                session.ui.mark(_('%s: Opening: %s (may take a while)'
                                  ) % (mbx_id, mfn))
            editable = self.is_editable_mailbox(mbx_id)
            if src is not None:
                msrc = self.mail_sources.get(src._key)
                mbox = msrc.open_mailbox(mbx_id, mfn.raw_fp) if msrc else None
            if mbox is None:
                mbox = OpenMailbox(mfn.raw_fp, self, create=editable)
            mbox.editable = editable
            mbox.is_local = prefer_local

        # Always set these, they can't be pickled
        mbox._decryption_key_func = lambda: self.master_key
        mbox._encryption_key_func = lambda: (self.prefs.encrypt_mail and
                                             self.master_key)

        # Finally, re-add to the cache
        self.cache_mailbox(session, pfn, mbx_id, mbox)

        return mbox

    def create_local_mailstore(self, session, name=None):
        path = os.path.join(self.workdir, 'mail')
        with self._lock:
            if name is None:
                name = '%5.5x' % random.randint(0, 16**5)
                while os.path.exists(os.path.join(path, name)):
                    name = '%5.5x' % random.randint(0, 16**5)
            if name != '':
                if not os.path.exists(path):
                    root_mbx = wervd.MailpileMailbox(path)
                if name.startswith(path) and '..' not in name:
                    path = name
                else:
                    path = os.path.join(path, os.path.basename(name))

            mbx = wervd.MailpileMailbox(path)
            mbx._decryption_key_func = lambda: self.master_key
            mbx._encryption_key_func = lambda: (self.prefs.encrypt_mail and
                                                self.master_key)
            return FilePath(path), mbx

    def open_local_mailbox(self, session):
        with self._lock:
            local_id = self.sys.get('local_mailbox_id', None)
            if local_id is None or local_id == '':
                mailbox, mbx = self.create_local_mailstore(session, name='')
                local_id = FormatMbxId(self.sys.mailbox.append(mailbox))
                self.sys.local_mailbox_id = local_id
            else:
                local_id = FormatMbxId(local_id)
        return local_id, self.open_mailbox(session, local_id)

    def get_passphrase(self, keyid,
                       description=None, prompt=None, error=None,
                       no_ask=False, no_cache=False):
        if not no_cache:
            keyidL = keyid.lower()
            for sid in self.secrets.keys():
                if sid.endswith(keyidL):
                    secret = self.secrets[sid]
                    if secret.policy == 'always-ask':
                        no_cache = True
                    elif secret.policy == 'fail':
                        return False, None
                    elif secret.policy != 'cache-only':
                        sps = SecurePassphraseStorage(secret.password)
                        return (keyidL, sps)

        if not no_cache:
            if keyid in self.passphrases:
                return (keyid, self.passphrases[keyid])
            if keyidL in self.passphrases:
                return (keyidL, self.passphrases[keyidL])
            for fprint in self.passphrases:
                if fprint.endswith(keyid):
                    return (fprint, self.passphrases[fprint])
                if fprint.lower().endswith(keyidL):
                    return (fprint, self.passphrases[fprint])

        if not no_ask:
            # This will either record details to the event of the currently
            # running command/operation, or register a new event. This does
            # not work as one might hope if ops cross a thread boundary...
            ev = GetThreadEvent(
                create=True,
                message=prompt or _('Please enter your password'),
                source=self)

            details = {'id': keyid}
            if prompt: details['msg'] = prompt
            if error: details['err'] = error
            if description: details['dsc'] = description
            if 'password_needed' in ev.private_data:
                ev.private_data['password_needed'].append(details)
            else:
                ev.private_data['password_needed'] = [details]

            ev.data['password_needed'] = True

            # Post a password request to the event log...
            self.event_log.log_event(ev)

        return None, None

    def get_profile(self, email=None):
        find = email or self.prefs.get('default_email', None)
        default_sig = _('Sent using Mailpile, Free Software '
                        'from www.mailpile.is')
        default_profile = {
            'name': None,
            'email': find,
            'messageroute': self.prefs.default_messageroute,
            'signature': default_sig,
            'crypto_policy': 'none',
            'crypto_format': 'none',
            'vcard': None
        }

        profiles = []
        if find:
            profiles = [self.vcards.get_vcard(find)]
        if not profiles or not profiles[0]:
            profiles = self.vcards.find_vcards([], kinds=['profile'])
        if profiles:
            profiles.sort(key=lambda k: ((0 if k.route else 1),
                                         (-len(k.recent_history())),
                                         (-len(k.sources()))))

        if profiles and profiles[0]:
            profile = profiles[0]
            psig = profile.signature
            proute = profile.route
            default_profile.update({
                'name': profile.fn,
                'email': find or profile.email,
                'signature': psig if (psig is not None) else default_sig,
                'messageroute': (proute if (proute is not None)
                                 else self.prefs.default_messageroute),
                'crypto_policy': profile.crypto_policy or 'none',
                'crypto_format': profile.crypto_format or 'none',
                'vcard': profile
            })

        return default_profile

    def get_route(self, frm, rcpts=['-t']):
        if len(rcpts) == 1:
            if rcpts[0].lower().endswith('.onion'):
                return {"protocol": "smtorp",
                        "host": rcpts[0].split('@')[-1],
                        "port": 25,
                        "username": "",
                        "password": ""}
        routeid = self.get_profile(frm)['messageroute']
        if self.routes[routeid] is not None:
            return self.routes[routeid]
        else:
            raise ValueError(_("Route %s for %s does not exist."
                               ) % (routeid, frm))

    @classmethod
    def getLocaleDirectory(self):
        """Get the gettext translation object, no matter where our CWD is"""
        return os.path.join(self.DEFAULT_SHARED_DATADIR(), "locale")

    def data_directory(self, ftype, mode='rb', mkdir=False):
        """
        Return the path to a data directory for a particular type of file
        data, optionally creating the directory if it is missing.

        >>> p = cfg.data_directory('html_theme', mode='r', mkdir=False)
        >>> p == os.path.abspath('shared-data/default-theme')
        True
        """
        # This should raise a KeyError if the ftype is unrecognized
        bpath = self.sys.path.get(ftype)
        if not bpath.startswith('/'):
            cpath = os.path.join(self.workdir, bpath)
            if os.path.exists(cpath) or 'w' in mode:
                bpath = cpath
                if mkdir and not os.path.exists(cpath):
                    os.mkdir(cpath)
            else:
                bpath = os.path.join(self.shareddatadir, bpath)
        return os.path.abspath(bpath)

    def data_file_and_mimetype(self, ftype, fpath, *args, **kwargs):
        # The theme gets precedence
        core_path = self.data_directory(ftype, *args, **kwargs)
        path, mimetype = os.path.join(core_path, fpath), None

        # If there's still nothing there, check our plugins
        if not os.path.exists(path):
            from mailpile.plugins import PluginManager
            path, mimetype = PluginManager().get_web_asset(fpath, path)

        if os.path.exists(path):
            return path, mimetype
        else:
            return None, None

    def history_file(self):
        return os.path.join(self.workdir, 'history')

    def mailindex_file(self):
        return os.path.join(self.workdir, 'mailpile.idx')

    def mailpile_path(self, path):
        base = (self.workdir + os.sep).replace(os.sep+os.sep, os.sep)
        if path.startswith(base):
            return path[len(base):]

        rbase = os.path.realpath(base) + os.sep
        rpath = os.path.realpath(path)
        if rpath.startswith(rbase):
            return rpath[len(rbase):]

        return path

    def tempfile_dir(self):
        d = os.path.join(self.workdir, 'tmp')
        if not os.path.exists(d):
            os.mkdir(d)
        return d

    def clean_tempfile_dir(self):
        try:
            td = self.tempfile_dir()
            files = os.listdir(td)
            random.shuffle(files)
            for fn in files:
                fn = os.path.join(td, fn)
                if os.path.isfile(fn):
                    safe_remove(fn)
        except (OSError, IOError):
            pass

    def postinglist_dir(self, prefix):
        d = os.path.join(self.workdir, 'search')
        if not os.path.exists(d):
            os.mkdir(d)
        d = os.path.join(d, prefix and prefix[0] or '_')
        if not os.path.exists(d):
            os.mkdir(d)
        return d

    def interruptable_wait_for_lock(self):
        # This construct allows the user to CTRL-C out of things.
        delay = 0.01
        while self._lock.acquire(False) == False:
            if mailpile.util.QUITTING:
                raise KeyboardInterrupt('Quitting')
            time.sleep(delay)
            delay = min(1, delay*2)
        self._lock.release()
        return self._lock

    def get_index(self, session):
        # Note: This is a long-running lock, but having two sets of the
        # index would really suck and this should only ever happen once.
        with self.interruptable_wait_for_lock():
            if self.index:
                return self.index
            idx = MailIndex(self)
            idx.load(session)
            self.index = idx
            try:
                self.index_check.release()
            except:
                pass
            return idx

    def get_tor_socket(self):
        if socks:
            socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5,
                                  'localhost', 9050, True)
        return socks.socksocket

    def open_file(self, ftype, fpath, mode='rb', mkdir=False):
        if '..' in fpath:
            raise ValueError(_('Parent paths are not allowed'))
        fpath, mt = self.data_file_and_mimetype(ftype, fpath,
                                                mode=mode, mkdir=mkdir)
        if not fpath:
            raise IOError(2, 'Not Found')
        return fpath, open(fpath, mode), mt

    def prepare_workers(self, *args, **kwargs):
        with self._lock:
            return self._unlocked_prepare_workers(*args, **kwargs)

    def daemons_started(config, which=None):
        return ((which or config.save_worker)
                not in (None, config.dumb_worker))

    def get_mail_source(config, src_id, start=False):
        ms_thread = config.mail_sources.get(src_id)
        if (ms_thread and not ms_thread.isAlive()):
            ms_thread = None
        if not ms_thread:
            from mailpile.mail_source import MailSource
            src_config = config.sources[src_id]
            ms_thread = MailSource(config.background, src_config)
            if start:
                config.mail_sources[src_id] = ms_thread
                ms_thread.start()
        return ms_thread

    def _unlocked_prepare_workers(config, session=None,
                                  daemons=False, httpd_spec=None):

        # Set our background UI to something that can log.
        if session:
            config.background.ui = BackgroundInteraction(config,
                                                         log_parent=session.ui)

        # Tell conn broker that we exist
        from mailpile.conn_brokers import Master as ConnBroker
        ConnBroker.set_config(config)
        if 'connbroker' in config.sys.debug:
            ConnBroker.debug_callback = lambda msg: config.background.ui.debug(msg)
        else:
            ConnBroker.debug_callback = None

        def start_httpd(sspec=None):
            sspec = sspec or (config.sys.http_host, config.sys.http_port,
                              config.sys.http_path or '')
            if sspec[0].lower() != 'disabled' and sspec[1] >= 0:
                config.http_worker = HttpWorker(config.background, sspec)
                config.http_worker.start()

        # We may start the HTTPD without the loaded config...
        if not config.loaded_config:
            if daemons and not config.http_worker:
                 start_httpd(httpd_spec)
            return

        # Start the other workers
        if daemons:
            for src_id in config.sources.keys():
                try:
                    config.get_mail_source(src_id, start=True)
                except (ValueError, KeyError):
                    pass

            if config.slow_worker == config.dumb_worker:
                config.slow_worker = Worker('Slow worker', config.background)
                config.slow_worker.wait_until = lambda: (
                    (not config.save_worker) or config.save_worker.is_idle())
                config.slow_worker.start()
            if config.scan_worker == config.dumb_worker:
                config.scan_worker = Worker('Scan worker', config.background)
                config.slow_worker.wait_until = lambda: (
                    (not config.save_worker) or config.save_worker.is_idle())
                config.scan_worker.start()
            if config.save_worker == config.dumb_worker:
                config.save_worker = ImportantWorker('Save worker',
                                                     config.background)
                config.save_worker.start()
            if not config.cron_worker:
                config.cron_worker = Cron(
                    config.cron_schedule, 'Cron worker', config.background)
                config.cron_worker.start()
            if not config.http_worker:
                start_httpd(httpd_spec)
            if not config.other_workers:
                from mailpile.plugins import PluginManager
                for worker in PluginManager.WORKERS:
                    w = worker(config.background)
                    w.start()
                    config.other_workers.append(w)

        # Update the cron jobs, if necessary
        if config.cron_worker and config.event_log:
            # Schedule periodic rescanning, if requested.
            rescan_interval = config.prefs.rescan_interval
            if rescan_interval:
                def rescan():
                    from mailpile.plugins.core import Rescan
                    if 'rescan' not in config._running:
                        rsc = Rescan(config.background, 'rescan')
                        rsc.serialize = False
                        config.slow_worker.add_unique_task(
                            config.background, 'Rescan',
                            lambda: rsc.run(slowly=True, cron=True))
                config.cron_worker.add_task('rescan', rescan_interval, rescan)

            def search_history_saver():
                config.save_worker.add_unique_task(
                    config.background, 'save_search_history',
                    lambda: config.search_history.save(config))
            config.cron_worker.add_task('save_search_history', 900,
                                        search_history_saver)

            def refresh_command_cache():
                config.scan_worker.add_unique_task(
                    config.background, 'refresh_command_cache',
                    lambda: config.command_cache.refresh(
                        event_log=config.event_log),
                    first=True)
            config.cron_worker.add_task('refresh_command_cache', 5,
                                        refresh_command_cache)

            from mailpile.postinglist import GlobalPostingList
            def optimizer():
                config.scan_worker.add_unique_task(
                    config.background, 'gpl_optimize',
                    lambda: GlobalPostingList.Optimize(config.background,
                                                       config.index,
                                                       lazy=True,
                                                       ratio=0.25, runtime=15))
            config.cron_worker.add_task('gpl_optimize', 30, optimizer)

            # Schedule plugin jobs
            from mailpile.plugins import PluginManager

            def interval(i):
                if isinstance(i, (str, unicode)):
                    i = config.walk(i)
                return int(i)

            def wrap_fast(func):
                def wrapped():
                    return func(config.background)
                return wrapped

            def wrap_slow(func):
                def wrapped():
                    config.slow_worker.add_unique_task(
                        config.background, job,
                        lambda: func(config.background))
                return wrapped
            for job, (i, f) in PluginManager.FAST_PERIODIC_JOBS.iteritems():
                config.cron_worker.add_task(job, interval(i), wrap_fast(f))
            for job, (i, f) in PluginManager.SLOW_PERIODIC_JOBS.iteritems():
                config.cron_worker.add_task(job, interval(i), wrap_slow(f))

    def stop_workers(config):
        try:
            self.index_check.release()
        except:
            pass

        with config._lock:
            worker_list = (config.mail_sources.values() +
                           config.other_workers +
                           [config.http_worker,
                            config.slow_worker,
                            config.scan_worker,
                            config.cron_worker])
            config.other_workers = []
            config.http_worker = config.cron_worker = None
            config.slow_worker = config.dumb_worker
            config.scan_worker = config.dumb_worker

        for wait in (False, True):
            for w in worker_list:
                if w and w.isAlive():
                    if config.sys.debug and wait:
                        print 'Waiting for %s' % w
                    w.quit(join=wait)

        # Flush the mailbox cache (queues save worker jobs)
        config.flush_mbox_cache(config.background, clear=True)

        # Handle the save worker last, once all the others are
        # no longer feeding it new things to do.
        with config._lock:
            save_worker = config.save_worker
            config.save_worker = config.dumb_worker
        if config.sys.debug:
            print 'Waiting for %s' % save_worker

        from mailpile.postinglist import PLC_CACHE_FlushAndClean
        PLC_CACHE_FlushAndClean(config.background, keep=0)
        config.search_history.save(config)
        save_worker.quit(join=True)

        if config.sys.debug:
            # Hooray!
            print 'All stopped!'


##############################################################################

if __name__ == "__main__":
    import copy
    import doctest
    import sys
    import mailpile.config.base
    import mailpile.config.defaults
    import mailpile.config.manager
    import mailpile.plugins.tags
    import mailpile.ui

    rules = copy.deepcopy(mailpile.config.defaults.CONFIG_RULES)
    rules.update({
        'nest1': ['Nest1', {
            'nest2': ['Nest2', str, []],
            'nest3': ['Nest3', {
                'nest4': ['Nest4', str, []]
            }, []],
        }, {}]
    })
    cfg = mailpile.config.manager.ConfigManager(rules=rules)
    session = mailpile.ui.Session(cfg)
    session.ui = mailpile.ui.SilentInteraction(cfg)
    session.ui.block()

    for tries in (1, 2):
        # This tests that we can set (and reset) dicts of unnested objects
        cfg.tags = {}
        assert(cfg.tags.a is None)
        for tn in range(0, 11):
            cfg.tags.append({'name': 'Test Tag %s' % tn})
        assert(cfg.tags.a['name'] == 'Test Tag 10')

        # This tests the same thing for lists
        #cfg.profiles = []
        #assert(len(cfg.profiles) == 0)
        #cfg.profiles.append({'name': 'Test Profile'})
        #assert(len(cfg.profiles) == 1)
        #assert(cfg.profiles[0].name == 'Test Profile')

        # This is the complicated one: multiple nesting layers
        cfg.nest1 = {}
        assert(cfg.nest1.a is None)
        cfg.nest1.a = {
            'nest2': ['hello', 'world'],
            'nest3': [{'nest4': ['Hooray']}]
        }
        cfg.nest1.b = {
            'nest2': ['hello', 'world'],
            'nest3': [{'nest4': ['Hooray', 'Bravo']}]
        }
        assert(cfg.nest1.a.nest3[0].nest4[0] == 'Hooray')
        assert(cfg.nest1.b.nest3[0].nest4[1] == 'Bravo')

    assert(cfg.sys.http_port ==
           mailpile.config.defaults.CONFIG_RULES['sys'][-1]['http_port'][-1])
    assert(cfg.sys.path.vcards == 'vcards')
    assert(cfg.walk('sys.path.vcards') == 'vcards')

    # Verify that the tricky nested stuff from above persists and
    # load/save doesn't change lists.
    for passes in (1, 2, 3):
        cfg2 = mailpile.config.manager.ConfigManager(rules=rules)
        cfg2.parse_config(session, cfg.as_config_bytes())
        cfg.parse_config(session, cfg2.as_config_bytes())
        assert(cfg2.nest1.a.nest3[0].nest4[0] == 'Hooray')
        assert(cfg2.nest1.b.nest3[0].nest4[1] == 'Bravo')
        assert(len(cfg2.nest1) == 2)
        assert(len(cfg.nest1) == 2)
        assert(len(cfg.tags) == 11)

    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={'cfg': cfg,
                                          'session': session})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
