import os
import random
import re
import thread
import threading
import traceback
import time

import mailpile.util
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import *
from mailpile.mailutils import FormatMbxId
from mailpile.util import *


__all__ = ['mbox', 'maildir', 'imap']


GLOBAL_RESCAN_LOCK = MSrcLock()


class BaseMailSource(threading.Thread):
    """
    MailSources take care of managing a group of mailboxes, synchronizing
    the source with Mailpile's local metadata and/or caches.
    """
    DEFAULT_JITTER = 15         # Fudge factor to tame thundering herds
    SAVE_STATE_INTERVAL = 3600  # How frequently we pickle our state
    INTERNAL_ERROR_SLEEP = 900  # Pause time on error, in seconds
    RESCAN_BATCH_SIZE = 250     # Index at most this many new e-mails at once
    MAX_PATHS = 100             # Abort if asked to scan too many directories

    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.BaseMailSource'

    def __init__(self, session, my_config):
        threading.Thread.__init__(self)
        self.daemon = mailpile.util.TESTING
        self._lock = MSrcRLock()
        self.my_config = my_config
        self.name = my_config.name
        self.session = session
        self.alive = None
        self.event = None
        self.jitter = self.DEFAULT_JITTER
        self._state = 'Idle'
        self._sleeping = None
        self._interrupt = None
        self._rescanning = False
        self._rescan_waiters = []
        self._last_rescan_count = 0
        self._last_saved = time.time()  # Saving right away would be silly

    def __str__(self):
        rv = ': '.join([threading.Thread.__str__(self), self._state])
        if self._sleeping > 0:
            rv += '(%s)' % self._sleeping
        return rv

    def _pfn(self):
        return 'mail-source.%s' % self.my_config._key

    def _load_state(self):
        with self._lock:
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

    def _save_config(self):
        self.session.config.save_worker.add_unique_task(
            self.session, 'Save config', self.session.config.save)

    def _log_status(self, message):
        self.event.message = message
        self.session.config.event_log.log_event(self.event)
        self.session.ui.mark(message)
        if 'sources' in self.session.config.sys.debug:
            self.session.ui.debug('%s: %s' % (self, message))

    def open(self):
        """Open mailboxes or connect to the remote mail source."""
        raise NotImplemented('Please override open in %s' % self)

    def close(self):
        """Close mailboxes or disconnect from the remote mail source."""
        raise NotImplemented('Please override open in %s' % self)

    def _has_mailbox_changed(self, mbx, state):
        """For the default sync_mail routine, report if mailbox changed."""
        raise NotImplemented('Please override _has_mailbox_changed in %s'
                             % self)

    def _mark_mailbox_rescanned(self, mbx, state):
        """For the default sync_mail routine, note mailbox was rescanned."""
        raise NotImplemented('Please override _mark_mailbox_rescanned in %s'
                             % self)

    def _path(self, mbx):
        if mbx.path.startswith('@'):
            return self.session.config.sys.mailbox[mbx.path[1:]]
        else:
            return mbx.path

    def _check_interrupt(self, clear=True):
        if mailpile.util.QUITTING or self._interrupt:
            if clear:
                self._log_status(_('Interrupted: %s')
                                 % (self._interrupt or _('Quitting')))
                self._interrupt = None
            return True
        else:
            return False

    def sync_mail(self):
        """Iterates through all the mailboxes and scans if necessary."""
        def unsorted(l):
            random.shuffle(l)
            return l
        config = self.session.config
        self._last_rescan_count = rescanned = errors = 0
        self._interrupt = None
        batch = self.RESCAN_BATCH_SIZE
        errors = rescanned = 0

        if self.session.config.sys.debug:
            batch //= 5

        ostate = self._state
        for mbx_cfg in unsorted(self.my_config.mailbox.values()):
            try:
                with self._lock:
                    mbx_key = FormatMbxId(mbx_cfg._key)
                    path = self._path(mbx_cfg)
                    if (path in ('/dev/null', '', None)
                            or mbx_cfg.policy in ('ignore', 'unknown')):
                        continue

                # Generally speaking, we only rescan if a mailbox looks like
                # it has changed. However, 1/50th of the time we take a look
                # anyway just in case looks are deceiving.
                state = {}
                if batch > 0 and (self._has_mailbox_changed(mbx_cfg, state) or
                                  random.randint(0, 50) == 10):

                    self._state = 'Waiting... (rescan)'
                    with GLOBAL_RESCAN_LOCK:
                        if self._check_interrupt(clear=False):
                            break
                        count = self.rescan_mailbox(mbx_key, mbx_cfg, path,
                                                    stop_after=batch)

                    if count >= 0:
                        batch -= count
                        complete = ((count == 0 or batch > 0) and
                                    not self._interrupt and
                                    not mailpile.util.QUITTING)
                        if complete:
                            rescanned += 1

                        # If there was a copy, check if it completed
                        if not self.event.data.get('copying',
                                                   {'complete': True}
                                                   ).get('complete'):
                            complete = False
                        # If there was a rescan, check if it completed
                        if not self.event.data.get('rescan',
                                                   {'complete': True}
                                                   ).get('complete'):
                            complete = False
                        # OK, everything looks complete, mark it!
                        if complete:
                            self._mark_mailbox_rescanned(mbx_cfg, state)
                    else:
                        errors += 1
            except (NoSuchMailboxError, IOError, OSError):
                errors += 1
            except:
                self._log_status(_('Internal error'))
                raise

        self._state = 'Waiting... (disco)'
        with GLOBAL_RESCAN_LOCK:
            if not self._check_interrupt():
                self.discover_mailboxes()

        if errors:
            self._log_status(_('Rescanned %d mailboxes, failed to rescan %d'
                               ) % (rescanned, errors))
        else:
            self._log_status(_('Rescanned %d mailboxes') % rescanned)

        self._last_rescan_count = rescanned
        self._state = ostate
        return rescanned

    def _jitter(self, seconds):
        return seconds + random.randint(0, self.jitter)

    def _sleep(self, seconds):
        if self.session.config.sys.debug:
            seconds //= 10
        if self._sleeping != 0:
            self._sleeping = seconds
            while (self.alive and self._sleeping > 0 and
                    not mailpile.util.QUITTING):
                time.sleep(min(1, self._sleeping))
                self._sleeping -= 1
        self._sleeping = None
        play_nice_with_threads()
        return (self.alive and not mailpile.util.QUITTING)

    def _existing_mailboxes(self):
        return set(self.session.config.sys.mailbox +
                   [mbx_cfg.local
                    for mbx_cfg in self.my_config.mailbox.values()
                    if mbx_cfg.local])

    def discover_mailboxes(self, paths=None):
        config = self.session.config
        self._log_status(_('Checking for new mailboxes'))
        ostate, self._state = self._state, 'Discovery'
        try:
            existing = self._existing_mailboxes()
            adding = []
            paths = (paths or self.my_config.discovery.paths)[:]
            while paths:
                raw_fn = paths.pop(0)
                fn = os.path.normpath(os.path.expanduser(raw_fn))
                fn = os.path.abspath(fn)
                if (raw_fn in existing or
                        fn in existing or
                        not os.path.exists(fn)):
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
                mbx_cfg = self.take_over_mailbox(mailbox_idx, save=False)
                if mbx_cfg.policy != 'unknown':
                    del new[mailbox_idx]
            if new:
                self.event.data['have_unknown'] = True

            if adding:
                self._save_config()

            return True
        finally:
            self._state = ostate

    def take_over_mailbox(self, mailbox_idx, save=True):
        config = self.session.config
        disco_cfg = self.my_config.discovery  # Stayin' alive! Stayin' alive!
        with self._lock:
            mailbox_idx = FormatMbxId(mailbox_idx)
            self.my_config.mailbox[mailbox_idx] = {
                'path': '@%s' % mailbox_idx,
                'policy': disco_cfg.policy,
                'process_new': disco_cfg.process_new,
            }
            mbx_cfg = self.my_config.mailbox[mailbox_idx]
            mbx_cfg.apply_tags.extend(disco_cfg.apply_tags)
        mbx_cfg.name = self._mailbox_name(self._path(mbx_cfg))
        if disco_cfg.guess_tags:
            self._guess_tags(mbx_cfg)
        self._create_primary_tag(mbx_cfg, save=False)
        self._create_local_mailbox(mbx_cfg, save=False)
        if save:
            self._save_config()
        return mbx_cfg

    def _guess_tags(self, mbx_cfg):
        if not mbx_cfg.name:
            return
        name = mbx_cfg.name.lower()
        tags = set(mbx_cfg.apply_tags)
        for tagtype in ('inbox', 'drafts', 'sent', 'spam'):
            for tag in self.session.config.get_tags(type=tagtype):
                if (tag.name.lower() in name or
                        _(tag.name).lower() in name):
                    tags.add(tag._key)
        mbx_cfg.apply_tags = sorted(list(tags))

    def _mailbox_name(self, path):
        return path.split('/')[-1]

    def _create_local_mailbox(self, mbx_cfg, save=True):
        config = self.session.config
        disco_cfg = self.my_config.discovery

        if mbx_cfg.local and mbx_cfg.local != '!CREATE':
            if not os.path.exists(mbx_cfg.local):
                path, wervd = config.create_local_mailstore(self.session,
                                                            name=mbx_cfg.local)
                mbx_cfg.local = path
                if save:
                    self._save_config()

        elif mbx_cfg.local == '!CREATE' or disco_cfg.local_copy:
            path, wervd = config.create_local_mailstore(self.session)
            mbx_cfg.local = path
            if save:
                self._save_config()

        return mbx_cfg

    def _create_parent_tag(self, save=True):
        disco_cfg = self.my_config.discovery
        if disco_cfg.parent_tag:
            if disco_cfg.parent_tag == '!CREATE':
                name = (self.my_config.name or
                        (self.my_config.username or '').split('@')[-1] or
                        (disco_cfg.paths and
                         os.path.basename(disco_cfg.paths[0])) or
                        self.my_config._key)
                if len(name) < 4:
                    name = _('Mail: %s') % name
                disco_cfg.parent_tag = name
            disco_cfg.parent_tag = self._create_tag(disco_cfg.parent_tag,
                                                    use_existing=False,
                                                    unique=False)
            return disco_cfg.parent_tag
        else:
            return None

    def _create_primary_tag(self, mbx_cfg, save=True):
        config = self.session.config
        if mbx_cfg.primary_tag and (mbx_cfg.primary_tag in config.tags):
            return

        # Stayin' alive! Stayin' alive!
        disco_cfg = self.my_config.discovery
        if not disco_cfg.create_tag:
            return

        # We configure the primary_tag with a name, if it doesn't have
        # one already.
        if not mbx_cfg.primary_tag:
            mbx_cfg.primary_tag = self._create_tag_name(self._path(mbx_cfg))

        # If we have a policy for this mailbox, we really go and create
        # tags. The gap here allows the user to edit the primary_tag
        # proposal before changing the policy from 'unknown'.
        if mbx_cfg.policy != 'unknown':
            parent = self._create_parent_tag(save=save)
            try:
                mbx_cfg.primary_tag = self._create_tag(mbx_cfg.primary_tag,
                                                       use_existing=False,
                                                       unique=False,
                                                       parent=parent)
                if save:
                    self._save_config()
            except (ValueError, IndexError):
                self.session.ui.debug(traceback.format_exc())

    BORING_FOLDER_RE = re.compile('(?i)^(home|mail|data|user\S*|[^a-z]+)$')

    def _path_to_tagname(self, path):  # -> tag name
        """This converts a path to a tag name."""
        path = path.replace('/.', '/')
        parts = ('/' in path) and path.split('/') or path.split('\\')
        parts = [p for p in parts if not re.match(self.BORING_FOLDER_RE, p)]
        tagname = parts.pop(-1).split('.')[0]
        if self.my_config.name:
            tagname = '%s/%s' % (self.my_config.name, tagname)
        return tagname.replace('_', ' ')

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

    def _create_tag(self, tag_name_or_id,
                    use_existing=True,
                    unique=False, parent=None):  # -> tag ID
        if tag_name_or_id in self.session.config.tags:
            # Short circuit if this is a tag ID for an existing tag
            return tag_name_or_id

        tags = self.session.config.get_tags(tag_name_or_id)
        if tags and unique:
            raise ValueError('Tag name is not unique!')
        elif len(tags) == 1 and use_existing:
            tag_id = tags[0]._key
        elif len(tags) > 1:
            raise ValueError('Tag name matches multiple tags!')
        else:
            from mailpile.plugins.tags import AddTag
            AddTag(self.session, arg=[tag_name_or_id]).run(save=False)
            tags = self.session.config.get_tags(tag_name_or_id)
            if tags:
                if parent:
                    tags[0].parent = parent
                tag_id = tags[0]._key
            else:
                raise ValueError('Failed to create tag?')
        return tag_id

    def interrupt_rescan(self, reason):
        self._interrupt = reason or _('Aborted')
        if self._rescanning:
            self.session.config.index.interrupt = reason

    def _process_new(self, msg, msg_ts, keywords, snippet):
        return ProcessNew(self.session, msg, msg_ts, keywords, snippet)

    def _copy_new_messages(self, mbx_key, mbx_cfg, stop_after=-1):
        session, config = self.session, self.session.config
        self.event.data['copying'] = progress = {
            'running': True,
            'mailbox_id': mbx_key,
            'copied_messages': 0,
            'copied_bytes': 0,
            'complete': False
        }
        try:
            src = config.open_mailbox(session, mbx_key, prefer_local=False)
            loc = config.open_mailbox(session, mbx_key, prefer_local=True)
            if src == loc:
                return

            keys = list(src.iterkeys())
            progress.update({
                'total': len(keys),
                'batch_size': stop_after if (stop_after > 0) else len(keys)
            })
            for key in keys:
                if self._check_interrupt(clear=False):
                    return
                play_nice_with_threads()
                if key not in loc.source_map:
                    session.ui.mark(_('Copying message: %s') % key)
                    data = src.get_bytes(key)
                    loc.add_from_source(key, data)
                    progress['copied_messages'] += 1
                    progress['copied_bytes'] += len(data)
                    stop_after -= 1
                    if stop_after == 0:
                        return
            progress['complete'] = True
        except IOError:
            # These just abort the download/read, which we're going to just
            # take in stride for now.
            pass
        finally:
            progress['running'] = False

    def rescan_mailbox(self, mbx_key, mbx_cfg, path, stop_after=None):
        session, config = self.session, self.session.config

        with self._lock:
            if self._rescanning:
                return -1
            self._rescanning = True

        try:
            ostate, self._state = self._state, 'Rescan(%s, %s)' % (mbx_key,
                                                                   stop_after)
            if mbx_cfg.local or self.my_config.discovery.local_copy:
                self._log_status(_('Copying mail: %s') % path)
                self._create_local_mailbox(mbx_cfg)
                self._copy_new_messages(mbx_key, mbx_cfg,
                                        stop_after=stop_after)
            elif 'copying' in self.event.data:
                del self.event.data['copying']

            with self._lock:
                apply_tags = mbx_cfg.apply_tags[:]
                self._create_primary_tag(mbx_cfg)
                if mbx_cfg.primary_tag:
                    tid = config.get_tag_id(mbx_cfg.primary_tag)
                    if tid:
                        apply_tags.append(tid)

            play_nice_with_threads()
            self._log_status(_('Rescanning: %s') % path)
            if 'rescans' in self.event.data:
                keep = len(self.my_config.mailbox)
                self.event.data['rescans'][:-keep] = []
            return config.index.scan_mailbox(
                session, mbx_key, mbx_cfg.local or path,
                config.open_mailbox,
                process_new=(mbx_cfg.process_new and
                             self._process_new or False),
                apply_tags=(apply_tags or []),
                stop_after=stop_after,
                event=self.event)

        except ValueError:
            session.ui.debug(traceback.format_exc())
            return -1
        finally:
            self._state = ostate
            self._rescanning = False

    def open_mailbox(self, mbx_id, fn):
        # This allows mail sources to override the default mailbox
        # opening mechanism.  Returning false respectfully declines.
        return False

    def is_mailbox(self, fn):
        return False

    def run(self):
        self.alive = True
        self._load_state()
        self.event.flags = Event.RUNNING
        _original_session = self.session

        # If this is the first time we look at this source (it has just
        # been configured), we don't delay, we get right to it.
        first = (len(self.my_config.mailbox) == 0)
        if not first:
            self._sleep(random.randint(0, self.my_config.interval))

        while first or self._sleep(self._jitter(self.my_config.interval)):
            first = False
            if not self.my_config.enabled:
                break

            self.name = self.my_config.name  # In case the config changes
            if not self.session.config.index:
                continue
            waiters, self._rescan_waiters = self._rescan_waiters, []
            for b, e, s in waiters:
                try:
                    b.release()
                except thread.error:
                    pass
                if s:
                    self.session = s
            try:
                if 'traceback' in self.event.data:
                    del self.event.data['traceback']
                if self.open():
                    self.sync_mail()
                next_save_time = self._last_saved + self.SAVE_STATE_INTERVAL
                if self.alive and time.time() >= next_save_time:
                    self._save_state()
                    if not self.my_config.keepalive:
                        self.close()
            except:
                self.event.data['traceback'] = traceback.format_exc()
                self.session.ui.debug(self.event.data['traceback'])
                self._log_status(_('Internal error!  Sleeping...'))
                self._sleep(self.INTERNAL_ERROR_SLEEP)
            finally:
                for b, e, s in waiters:
                    try:
                        e.release()
                    except thread.error:
                        pass
                self.session = _original_session
        self._save_state()
        self.event.flags = Event.COMPLETE
        self._log_status(_('Shut down'))

    def wake_up(self):
        self._sleeping = 0

    def rescan_now(self, session=None, started_callback=None):
        begin, end = MSrcLock(), MSrcLock()
        for l in (begin, end):
            l.acquire()
        try:
            self._rescan_waiters.append((begin, end, session))
            self.wake_up()
            while not begin.acquire(False):
                time.sleep(1)
                if mailpile.util.QUITTING:
                    return self._last_rescan_count
            if started_callback:
                started_callback()
            while not end.acquire(False):
                time.sleep(1)
                if mailpile.util.QUITTING:
                    return self._last_rescan_count
            return self._last_rescan_count
        except KeyboardInterrupt:
            self.interrupt_rescan(_('User aborted'))
            raise
        finally:
            for l in (begin, end):
                try:
                    l.release()
                except thread.error:
                    pass

    def quit(self, join='ignored'):
        self.interrupt_rescan(_('Shut down'))
        self.alive = False
        self.wake_up()


def ProcessNew(session, msg, msg_ts, keywords, snippet):
    if 'r' in msg.get('status', '').lower():
        return False
    keywords.update(['%s:in' % tag._key for tag in
                     session.config.get_tags(type='unread')])
    return True


def MailSource(session, my_config):
    # FIXME: check the plugin and instanciate the right kind of mail source
    #        for this config section.
    if my_config.protocol in ('mbox',):
        from mailpile.mail_source.mbox import MboxMailSource
        return MboxMailSource(session, my_config)
    elif my_config.protocol in ('maildir',):
        from mailpile.mail_source.maildir import MaildirMailSource
        return MaildirMailSource(session, my_config)
    elif my_config.protocol in ('imap', 'imap_ssl'):
        from mailpile.mail_source.imap import ImapMailSource
        return ImapMailSource(session, my_config)
    raise ValueError(_('Unknown mail source protocol: %s'
                       ) % my_config.protocol)
