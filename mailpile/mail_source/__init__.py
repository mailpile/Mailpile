import os
import random
import re
import threading
import traceback
import time

from mailpile.eventlog import Event
from mailpile.mailboxes import *


__all__ = ['mbox', 'maildir']


# Brainstorming:  What does a mail source have to do?
#
# It's a thread that watches for new mail. It can do so using one account
# and one data type, so it can be specialized for the task. For example an
# IMAP source. That one connects to the remote server whenever it can,
# checks which remote folders exist and which have messages we haven't
# yet seen. It downloads the ones we're missing, indexes and assigns
# tags to them. Unless they've been deleted locally, then if we're
# syncing it deletes them from the server as well.
#
# So... we have a thread. Inna loop:
#   It connects.
#   A watcher/syncer subroutine starts up.
#     Inna loop:
#       Folders are discovered. Post/update an event if we see folders
#       that we haven't seen before and can't figure out what they are meant
#       to be. Use IDLE or poll for mail. Download new mail, add to index.
#
# Pointers to mail:
#    Indexed mail is identified by a pointer. Currently that's a combo
#    of mailbox ID and an ID within the mailbox.  When the rest of the
#    app wants to load a message, it currently assumes it can access
#    something that looks like a Python mailbox. We aren't actually using
#    much of that interface, so we could rip it out and replace it.
#    Making the ID reference mail sources instead, and delegating to
#    the mail source read/write mail ops might make sense.
#
#
# ... so how do I get there?  Migration:
#
#    Goal: sys.mailbox goes away.
#    Migration: create a bunch of sources, one per mailbox type or
#               group by were in the FS they are.
#    ... so a mbox mail source.
#    ... and a maildir mail source.
#    So we start with Maildir. WERVD and IMAP inherit from that anyway.
#

class BaseMailSource(threading.Thread):
    """
    MailSources take care of managing a group of mailboxes, synchronizing
    the source with Mailpile's local metadata and/or caches.
    """
    DEFAULT_JITTER = 15
    SAVE_STATE_INTERVAL = 3600
    INTERNAL_ERROR_SLEEP = 900

    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.BaseMailSource'

    def __init__(self, session, my_config):
        threading.Thread.__init__(self)
        self._lock = threading.Lock()
        self.my_config = my_config
        self.session = session
        self.alive = None
        self.event = None
        self.jitter = self.DEFAULT_JITTER
        self._sleeping = None
        self._rescan_waiters = []
        self._last_saved = time.time()  # Saving right away would be silly

        # Make locked versions of a few functions
        self._load_state = self._locked(self._unlocked_load_state)
        self.open = self._locked(self._unlocked_open)
        self.sync_mail = self._locked(self._unlocked_sync_mail)
        self.rescan_mailbox = self._locked(self._unlocked_rescan_mailbox)
        self.take_over_mailbox = self._locked(self._unlocked_take_over_mailbox)

    def _locked(self, func):
        def locked_func(*args, **kwargs):
            try:
                self._lock.acquire()
                return func(*args, **kwargs)
            finally:
                self._lock.release()
        return locked_func

    def _pfn(self):
        return 'mail-source.%s' % self.my_config._key

    def _unlocked_load_state(self):
        config, my_config = self.session.config, self.my_config
        events = list(config.event_log.incomplete(source=self,
                                                  data_id=my_config._key))
        if events:
            self.event = events[0]
        else:
            self.event = config.event_log.log(source=self,
                                              flags=Event.RUNNING,
                                              message=_('Starting up'),
                                              data={'id': my_config._key})

    def _save_state(self):
        self.session.config.event_log.log_event(self.event)

    def _log_status(self, message):
        self.event.message = message
        self.session.config.event_log.log_event(self.event)

    def _unlocked_open(self):
        """Open mailboxes or connect to the remote mail source."""
        raise NotImplemented('Please override _open in %s' % self)

    def _has_mailbox_changed(self, mbx, state):
        """For the default sync_mail routine, report if mailbox changed."""
        raise NotImplemented('Please override _open in %s' % self)

    def _mark_mailbox_rescanned(self, mbx, state):
        """For the default sync_mail routine, note mailbox was rescanned."""
        raise NotImplemented('Please override _open in %s' % self)

    def _unlocked_sync_mail(self):
        """Iterates through all the mailboxes and scans if necessary."""
        config = self.session.config
        rescanned = errors = 0
        for mbx in self.my_config.mailbox.values():
            try:
                state = {}
                if self._has_mailbox_changed(mbx, state):
                    self._log_status(_('Reading mailbox %s') % mbx.path)
                    if self._unlocked_rescan_mailbox(mbx._key):
                        self._mark_mailbox_rescanned(mbx, state)
                        rescanned += 1
                    else:
                        errors += 1
            except (NoSuchMailboxError, IOError, OSError):
                errors += 1
        if errors:
            self._log_status(_('Rescanned %d mailboxes, failed to rescan %d'
                              ) % (rescanned, errors))
        elif rescanned:
            self._log_status(_('Rescanned %d mailboxes') % rescanned)

    def _jitter(self, seconds):
        return seconds + random.randint(0, self.jitter)

    def _sleep(self, seconds):
        if self._sleeping != 0:
            self._sleeping = seconds
            while self.alive and self._sleeping > 0:
                time.sleep(min(1, self._sleeping))
                self._sleeping -= 1
        self._sleeping = None
        return self.alive

    MAX_PATHS = 50000

    def _discover_mailboxes(self, path):
        config = self.session.config
        paths = [path]
        existing = set(config.sys.mailbox +
                       [mbx.path for mbx in self.my_config.mailbox.values()] +
                       [mbx.local for mbx in self.my_config.mailbox.values()
                        if mbx.local])
        adding = []
        while paths:
            raw_fn = paths.pop(0)
            fn = os.path.abspath(os.path.normpath(os.path.expanduser(raw_fn)))
            if raw_fn in existing or fn in existing or not os.path.exists(fn):
                continue
            if self.is_mailbox(fn):
                adding.append(fn)
            if os.path.isdir(fn):
                try:
                    for f in [f for f in os.listdir(fn)
                              if f not in ('.', '..')]:
                        paths.append(os.path.join(fn, f))
                        if len(paths) > self.MAX_PATHS:
                            return False
                except OSError:
                    pass

        new = {}
        for path in adding:
            new[config.sys.mailbox.append(path)] = path
        for mailbox_idx in new.keys():
            mbx = self.take_over_mailbox(mailbox_idx)
            if mbx.policy != 'unknown':
                del new[mailbox_idx]
        if new:
            self.event.data['have_unknown'] = True

        return True

    def _unlocked_take_over_mailbox(self, mailbox_idx):
        config = self.session.config
        disco_cfg = self.my_config.discovery  # Stayin' alive! Stayin' alive!
        self.my_config.mailbox[mailbox_idx] = {
            'path': config.sys.mailbox[mailbox_idx],
            'policy': disco_cfg.policy,
            'process_new': disco_cfg.process_new,
        }
        mbx = self.my_config.mailbox[mailbox_idx]
        mbx.apply_tags.extend(disco_cfg.apply_tags)
        config.sys.mailbox[mailbox_idx] = '@%s' % self.my_config._key
        if disco_cfg.create_tag:
            tag_name_or_id = self._create_tag_name(mbx.path)
            mbx['primary_tag'] = tag_name_or_id
            if disco_cfg.policy != 'unknown':
                try:
                    mbx['primary_tag'] = self._create_tag(tag_name_or_id,
                                                          unique=True)
                except ValueError:
                    pass  # FIXME: This suxors
        if disco_cfg.local_copy:
            path, wervd = config.create_local_mailstore(self.session)
            mbx.local = path
        return mbx

    BORING_FOLDER_RE = re.compile('(?i)^(home|mail|data|user\S*|[^a-z]+)$')

    def _path_to_tagname(self, path):  # -> tag name
        """This converts a path to a tag name."""
        path = path.replace('/.', '/')
        parts = ('/' in path) and path.split('/') or path.split('\\')
        parts = [p for p in parts if not re.match(self.BORING_FOLDER_RE, p)]
        tagname = parts.pop(-1).split('.')[0]
        if self.session.config.get_tags(tagname):
            tagname = '%s/%s' % (parts[-1], tagname)
        return tagname.replace('-', ' ').replace('_', ' ')

    def _unique_tag_name(self, tagname):  # -> unused tag name
        """This makes sure a tagname really is unused"""
        tagnameN, count = tagname, 2
        while self.session.config.get_tags(tagnameN):
            tagnameN = '%s (%s)' % (tagname, count)
            count += 1
        return tagnameN

    def _create_tag_name(self, path):  # -> unique tag name
        """Convert a path to a unique tag name."""
        return self._unique_tag_name(self._path_to_tagname(path))

    def _create_tag(self, tag_name_or_id, unique=False):  # -> tag ID
        tags = self.session.config.get_tags(tag_name_or_id)
        if tags and unique:
            raise ValueError('Tag name is not unique!')
        elif len(tags) == 1:
            tag_id = tags[0]._key
        elif len(tags) > 1:
            raise ValueError('Tag name matches multiple tags!')
        else:
            from mailpile.plugins.tags import AddTag
            AddTag(self.session, arg=[tag_name_or_id]).run(save=False)
            tags = self.session.config.get_tags(tag_name_or_id)
            tag_id = tags[0]._key
        return tag_id

    def _unlocked_rescan_mailbox(self, mbx_key):
        try:
            mbx = self.my_config.mailbox[mbx_key]
            if mbx.policy == 'watch':
                return self._discover_mailboxes(mbx.path)
            if mbx.path == '/dev/null' or mbx.policy in ('ignore', 'unknown'):
                return True
            if mbx.local:
                # FIXME: Should copy any new messages to our local stash
                pass
            self.session.config.index.scan_mailbox(
                self.session, mbx_key, mbx.local or mbx.path,
                self.session.config.open_mailbox)
            return True
        except ValueError:
            return False

    def is_mailbox(self, fn):
        return False

    def run(self):
        self.alive = True
        self._load_state()
        self.event.flags = Event.RUNNING
        _original_session = self.session
        while self._sleep(self._jitter(self.my_config.interval)):
            waiters, self._rescan_waiters = self._rescan_waiters, []
            for b, e, s in waiters:
                b.release()
                if s:
                    self.session = s
            try:
                if 'traceback' in self.event.data:
                    del self.event.data['traceback']
                if self.open():
                    self.sync_mail()
                if (self.alive and time.time() >= self._last_saved +
                                                  self.SAVE_STATE_INTERVAL):
                    self._save_state()
            except:
                self.event.data['traceback'] = traceback.format_exc()
                print self.event.data['traceback']
                self._log_status(_('Internal error!  Sleeping...'))
                self._sleep(self.INTERNAL_ERROR_SLEEP)
                # FIXME: Release any held locks?
            finally:
                for b, e, s in waiters:
                    e.release()
                self.session = _original_session
        self.event.flags = Event.INCOMPLETE
        self.event.message = _('Shutting down')
        self._save_state()

    def wake_up(self):
        self._sleeping = 0

    def rescan_now(self, session=None, started_callback=None):
        begin, end = threading.Lock(), threading.Lock()
        for l in (begin, end):
            l.acquire()
        self._rescan_waiters.append((begin, end, session))
        self.wake_up()
        begin.acquire()
        if started_callback:
            started_callback()
        end.acquire()
        for l in (begin, end):
            l.release()

    def quit(self, join='ignored'):
        self.alive = False
        self.wake_up()


def MailSource(session, my_config):
    # FIXME: check the plugin and instanciate the right kind of mail source
    #        for this config section.
    if my_config.protocol in ('mbox',):
        from mailpile.mail_source.mbox import MboxMailSource
        return MboxMailSource(session, my_config)
    elif my_config.protocol in ('maildir',):
        from mailpile.mail_source.maildir import MaildirMailSource
        return MaildirMailSource(session, my_config)
    raise ValueError(_('Unknown mail source protocol: %s'
                       ) % my_config.protocol)
