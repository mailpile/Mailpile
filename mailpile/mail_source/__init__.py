import datetime
import os
import random
import re
import thread
import threading
import traceback
import time

import mailpile.util
import mailpile.vfs
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import *
from mailpile.mailutils import FormatMbxId
from mailpile.util import *
from mailpile.vfs import vfs, FilePath, MailpileVfsBase


__all__ = ['local', 'imap', 'pop3']


class BaseMailSource(threading.Thread):
    """
    MailSources take care of managing a group of mailboxes, synchronizing
    the source with Mailpile's local metadata and/or caches.
    """
    DEFAULT_JITTER = 15         # Fudge factor to tame thundering herds
    SAVE_STATE_INTERVAL = 3600  # How frequently we pickle our state
    INTERNAL_ERROR_SLEEP = 900  # Pause time on error, in seconds
    RESCAN_BATCH_SIZE = 200     # Index at most this many new e-mails at once
    MAX_PATHS = 2000            # Limit how many directories we scan at once

    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.BaseMailSource'


    class MailSourceVfs(MailpileVfsBase):
        """Generic VFS layer for this mail source."""
        def __init__(self, config, source, *args, **kwargs):
            MailpileVfsBase.__init__(self, *args, **kwargs)
            self.config = config
            self.source = source
            self.root = FilePath('/src:%s' % self.source.my_config._key)

        def _get_mbox_id(self, path):
            return path[len(self.root.raw_fp)+1:]

        def Handles(self, path):
            path = FilePath(path)
            return (self.root == path or
                    path.raw_fp.startswith(self.root.raw_fp))

        def glob_(self, *args, **kwargs):
            return self.listdir_(*args, **kwargs)

        def listdir_(self, where, **kwargs):
            return [m for m in self.source.my_config.mailbox.keys()]

        def open_(self, fp, *args, **kwargs):
            raise IOError('Cannot open Mail Source entries (yet)')

        def abspath_(self, path):
            if not path.startswith(self.root.raw_fp):
                path = self.root.join(path).raw_fp
            if path == self.root:
                return path
            try:
                mbox_id = self._get_mbox_id(path)
                path = self.config.sys.mailbox[mbox_id]
                if path.startswith('src:'):
                    return '/%s' % path
                return path
            except (ValueError, KeyError, IndexError):
                raise OSError('Not found: %s' % path)

        def isdir_(self, fp):
            return (self.root == fp)

        def ismailsource_(self, fp):
            return (self.root == fp)

        def mailbox_type_(self, fp, config):
            return False if (fp == self.root) else 'source'  # Fixme

        def getsize_(self, path):
            return None

        def display_name_(self, path, config):
            if (self.root == path):
                return (self.source.my_config.name or
                        self.source.my_config._key)
            try:
                mbox_id = self._get_mbox_id(path)
                return self.source.my_config.mailbox[mbox_id].name
            except (ValueError, KeyError, IndexError):
                raise OSError('Not found: %s' % path)

        def exists_(self, fp):
            return ((self.root == fp) or
                    (fp[len(self.root)+1:] in self.source.my_config.mailbox))


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
        self._loop_count = 0
        self._last_rescan_count = 0
        self._last_rescan_completed = False
        self._last_rescan_failed = False
        self._last_saved = time.time()  # Saving right away would be silly
        ms_vfs = self.MailSourceVfs(session.config, self)
        mailpile.vfs.register_handler(5000, ms_vfs)

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
                if my_config.enabled:
                    self.event.message = _('Starting up')
                else:
                    self.event.message = _('Disabled')
            else:
                self.event = config.event_log.log(
                    source=self,
                    flags=Event.RUNNING,
                    message=_('Starting up'),
                    data={'id': my_config._key})
            self.event.data['name'] = my_config.name or _('Mail Source')
            if 'counters' not in self.event.data:
                self.event.data['counters'] = {}
            for c in ('copied_messages',
                      'indexed_messages',
                      'unknown_policies'):
                if c not in self.event.data['counters']:
                    self.event.data['counters'][c] = 0

    def _save_state(self):
        self.session.config.event_log.log_event(self.event)

    def _save_config(self):
        self.session.config.save_worker.add_unique_task(
            self.session, 'Save config', self.session.config.save)

    def _log_status(self, message, clear_errors=False):
        # If the user renames our parent_tag, we assume the name change too.
        self.update_name_to_match_tag()
        if clear_errors:
            err = self.event.data.get('connection', {}).get('error', [False])
            if err[0]:
                err[:] = [False, _('Nothing is wrong')]
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

    def _check_interrupt(self, log=True, clear=True):
        if not self._interrupt:
            full_path = self.session.config.need_more_disk_space()
            if full_path is not None:
                self._interrupt = _('Insufficient free space in %s'
                                    ) % full_path
        if (mailpile.util.QUITTING or
                self._interrupt or
                not self.my_config.enabled):
            if log:
                self._log_status(_('Interrupted: %s')
                                     % (self._interrupt or _('Shutting down')),
                                 clear_errors=(not self._interrupt))
            if clear:
                self._interrupt = None
            return True
        else:
            return False

    def _mailbox_sort_key(self, m):
        return md5_hex(str(self._loop_count), m.name)

    def _sorted_mailboxes(self):
        mailboxes = self.my_config.mailbox.values()
        mailboxes.sort(key=lambda m: (
            'inbox' in m.name.lower() and 1 or 2,
            'sent' in m.name.lower() and 1 or 2,
            'spam' in m.name.lower() and 1 or 2,  # For training filters!
            '[Gmail]' in m.name and 2 or 1,       # This goes last...
            self._mailbox_sort_key(m)))
        return mailboxes

    def _policy(self, mbx_cfg):
        policy = mbx_cfg.policy
        if policy == 'inherit':
            return self.my_config.discovery.policy
        return policy

    def update_name_to_match_tag(self):
        parent_tag_id = self.my_config.discovery.parent_tag
        if parent_tag_id and parent_tag_id != '!CREATE':
            tag = self.session.config.get_tag(parent_tag_id)
            if tag and self.name != tag.name:
                self.name = self.my_config.name = tag.name
                if self.event:
                    self.event.data['name'] = self.name

    def sync_mail(self):
        """Iterates through all the mailboxes and scans if necessary."""
        config = self.session.config
        self._last_rescan_count = rescanned = errors = 0
        self._last_rescan_completed = False
        self._last_rescan_failed = False
        self._interrupt = None
        batch = min(self._loop_count * 20, self.RESCAN_BATCH_SIZE)
        errors = rescanned = 0

        all_completed = True
        ostate = self._state
        plan = self._sorted_mailboxes()
        self.event.data['plan'] = [[m._key, _('Pending'), m.name] for m in plan]
        event_plan = dict((mp[0], mp) for mp in self.event.data['plan'])
        if plan and random.randint(0, 10) == 1:
            random_plan = [m._key for m in random.sample(plan, 1)]
        else:
            random_plan = []

        for mbx_cfg in plan:
            play_nice_with_threads(weak=True)

            if self._check_interrupt(clear=False):
                all_completed = False
                break
            try:
                with self._lock:
                    mbx_key = FormatMbxId(mbx_cfg._key)
                    path = self._path(mbx_cfg)
                    policy = self._policy(mbx_cfg)
                    if (path in ('/dev/null', '', None)
                            or policy in ('ignore', 'unknown')):
                        event_plan[mbx_cfg._key][1] = _('Skipped')
                        continue

                # Generally speaking, we only rescan if a mailbox looks like
                # it has changed. However, every once in a while (see logic
                # around random_mailboxes above) we check anyway just in case
                # looks are deceiving.
                state = {}
                if batch < 1:
                    event_plan[mbx_cfg._key][1] = _('Postponed')

                elif (self._has_mailbox_changed(mbx_cfg, state) or
                        mbx_cfg.local == '!CREATE' or
                        mbx_cfg._key in random_plan):
                    event_plan[mbx_cfg._key][1] = _('Working ...')

                    this_batch = max(5, int(0.7 * batch))
                    self._state = 'Waiting... (rescan)'
                    if self._check_interrupt(clear=False):
                        all_completed = False
                        break
                    count = self.rescan_mailbox(mbx_key, mbx_cfg, path,
                                                stop_after=this_batch)

                    if count >= 0:
                        self.event.data['counters'
                                        ]['indexed_messages'] += count
                        batch -= count
                        this_batch -= count
                        complete = ((count == 0 or this_batch > 0) and
                                    not self._interrupt and
                                    not mailpile.util.QUITTING)
                        if complete:
                            rescanned += 1

                        # If there was a copy, check if it completed
                        cstate = self.event.data.get('copying') or {}
                        if not cstate.get('complete', True):
                            complete = False

                        # If there was a rescan, check if it completed
                        rstate = self.event.data.get('rescan') or {}
                        if not rstate.get('complete', True):
                            complete = False

                        # OK, everything looks complete, mark it!
                        if complete:
                            event_plan[mbx_cfg._key][1] = _('Completed')
                            self._mark_mailbox_rescanned(mbx_cfg, state)
                        else:
                            event_plan[mbx_cfg._key][1] = _('Indexed %d'
                                                            ) % count
                            all_completed = False
                            if count == 0 and ('sources' in config.sys.debug):
                                time.sleep(60)
                    else:
                        event_plan[mbx_cfg._key][1] = _('Failed')
                        self._last_rescan_failed = True
                        all_completed = False
                        errors += 1

                else:
                    event_plan[mbx_cfg._key][1] = _('Unchanged')

            except (NoSuchMailboxError, IOError, OSError) as e:
                event_plan[mbx_cfg._key][1] = '%s: %s' % (_('Error'), e)
                self._last_rescan_failed = True
                errors += 1
            except Exception as e:
                event_plan[mbx_cfg._key][1] = '%s: %s' % (
                    _('Internal error'), e)
                self._last_rescan_failed = True
                self._log_status(_('Internal error'))
                raise

        self._last_rescan_completed = all_completed
        discovered = 0
        if not self._check_interrupt():
            self._state = 'Waiting... (disco)'
            self._log_status(_('Checking for new mailboxes'))
            discovered = self.discover_mailboxes()

        self._state = 'Done'
        status = []
        if discovered > 0:
            status.append(_('Discovered %d mailboxes') % discovered)
            self._last_rescan_completed = False
        if rescanned > 0:
            status.append(_('Processed %d mailboxes') % rescanned)
        if errors:
            status.append(_('Failed to process %d') % errors)
        if not status:
            status.append(_('No new mail at %s'
                            ) % datetime.datetime.today().strftime('%H:%M'))

        self._log_status(', '.join(status))
        self._last_rescan_count = rescanned
        self._state = ostate
        return rescanned

    def _jitter(self, seconds):
        return seconds + random.randint(0, self.jitter)

    def _sleeping_is_ok(self, slept):
        return True

    def _sleep(self, seconds):
        enabled = self.my_config.enabled
        self._sleeping = seconds
        while (self.alive and
                self._sleeping > 0 and
                self._sleeping_is_ok(seconds - self._sleeping) and
                enabled == self.my_config.enabled and
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

    def _update_unknown_state(self):
        have_unknown = 0
        for mailbox in self.my_config.mailbox.values():
            if mailbox.policy == 'unknown':
                have_unknown += 1
        self.event.data['counters']['unknown_policies'] = have_unknown
        self.event.data['have_unknown'] = (have_unknown > 0)

    def reset_event_discovery_state(self):
        for k in ('discovery_error', 'discovery_limit', 'discovery_state'):
            if k in self.event.data:
                del self.event.data[k]

    def set_event_discovery_state(self, state=None, error=None, status=None):
        self.event.data['discovery_limit'] = (
            self.my_config.discovery.max_mailboxes)
        if state is not None:
            self.event.data['discovery_state'] = state
        if error is not None:
            self.event.data['discovery_error'] = error
        if status is not None:
            self._log_status(status)

    def on_event_discovery_starting(self):
        ostate, self._state = self._state, 'Discovery'
        self.reset_event_discovery_state()
        self.set_event_discovery_state(
            'scanning', status=_('Checking for new mailboxes'))
        return ostate

    def on_event_discovery_toomany(self):
        self.set_event_discovery_state(
            error='toomany',
            status=_('Too many mailboxes found! Raise limits to continue.'))
        self._sleep(15)

    def on_event_discovery_done(self, ostate):
        self.set_event_discovery_state('done')
        self._state = ostate

    def discover_mailboxes(self, paths=None):
        config = self.session.config
        ostate = self.on_event_discovery_starting()
        try:
            existing = self._existing_mailboxes()
            max_mailboxes = self.my_config.discovery.max_mailboxes
            max_mailboxes -= len(existing)
            adding = []
            paths = [(p.encode('utf-8') if isinstance(p, unicode) else p)
                     for p in (paths or self.my_config.discovery.paths)]
            paths.sort()
            while paths:
                raw_fn = paths.pop(0)
                if 'sources' in config.sys.debug:
                    self.session.ui.mark(_('Checking for new mailboxes in %s'
                                           ) % raw_fn.decode('utf-8'))

                fn = os.path.normpath(os.path.expanduser(raw_fn))
                fn = os.path.abspath(fn)
                if not os.path.exists(fn):
                    continue

                is_mailbox = False
                if (raw_fn not in existing and
                        fn not in existing and
                        fn not in adding):
                    if self.is_mailbox(fn):
                        adding.append(fn)
                        is_mailbox = True
                    if len(adding) > max_mailboxes:
                        break

                if os.path.isdir(fn):
                    try:
                        max_paths = self.MAX_PATHS - len(paths)
                        subdirs = [f for f in os.listdir(fn)
                                   if f not in ('.', '..')]

                        if len(subdirs) > (max_paths/2):
                            # If we are hitting our limits, randomize.
                            random.shuffle(subdirs)
                        else:
                            # Otherwise, do things in an orderly fashion.
                            subdirs.sort()

                        for f in subdirs[:max_paths/2]:
                            nfn = os.path.join(fn, f)
                            if is_mailbox and f in ('cur', 'new', 'tmp'):
                                pass  # Skip Maildir special directories
                            elif (len(paths) <= self.MAX_PATHS and
                                    os.path.isdir(nfn)):
                                paths.append(nfn)
                            elif self.is_mailbox(nfn):
                                paths.append(nfn)
                            play_nice_with_threads(weak=True)
                    except OSError:
                        pass

                    # This may have been a bit of work, take a break.
                    play_nice_with_threads()

                if len(adding) > max_mailboxes:
                    break

            if len(adding) > max_mailboxes:
                self.on_event_discovery_toomany()

            self.set_event_discovery_state('adding')
            play_nice_with_threads()
            new = {}
            for path in adding:
                new[config.sys.mailbox.append(path)] = path
            for mailbox_idx in new.keys():
                mbx_cfg = self.take_over_mailbox(mailbox_idx, save=False)
                if self._policy(mbx_cfg) != 'unknown':
                    del new[mailbox_idx]

            if adding:
                self._save_config()

            return len(adding)
        finally:
            self.on_event_discovery_done(ostate)

    def _default_policy(self, mbx_cfg):
        return 'inherit'

    def take_over_mailbox(self, mailbox_idx,
                          policy=None, create_local=None, save=True,
                          guess_tags=None, apply_tags=None):
        config = self.session.config
        disco_cfg = self.my_config.discovery  # Stayin' alive! Stayin' alive!
        with self._lock:
            mailbox_idx = FormatMbxId(mailbox_idx)
            self.my_config.mailbox[mailbox_idx] = {
                'path': '@%s' % mailbox_idx,
                'policy': policy or 'inherit',
                'process_new': disco_cfg.process_new,
                'local': '!CREATE' if create_local else '',
            }
            mbx_cfg = self.my_config.mailbox[mailbox_idx]
            mbx_cfg.apply_tags.extend(disco_cfg.apply_tags)
            if apply_tags:
                mbx_cfg.apply_tags.extend(t for t in apply_tags if t)
        mbx_cfg.policy = policy or self._default_policy(mbx_cfg)
        mbx_cfg.name = self._mailbox_name(self._path(mbx_cfg))
        if guess_tags is None:
            guess_tags = disco_cfg.guess_tags
        if guess_tags:
            self._guess_tags(mbx_cfg)
        self._create_primary_tag(mbx_cfg, save=False)
        self._create_local_mailbox(mbx_cfg, save=False)
        if save:
            self._save_config()
        return mbx_cfg

    def _guess_tags(self, mbx_cfg):
        if not mbx_cfg.name:
            return
        mbx_cfg.apply_tags = sorted(list(
            set(mbx_cfg.apply_tags) |
            self.session.config.guess_tags(mbx_cfg.name)))

    def _strip_file_extension(self, path):
        return path.rsplit('.', 1)[0]

    def _mailbox_path_split(self, path):
        return ('/' in path) and path.split('/') or path.split('\\')

    def _mailbox_name(self, path):
        return self._mailbox_path_split(path)[-1]

    def _create_local_mailbox(self, mbx_cfg, save=True):
        config = self.session.config
        disco_cfg = self.my_config.discovery

        if mbx_cfg.local and mbx_cfg.local != '!CREATE':
            if not vfs.exists(mbx_cfg.local):
                config.flush_mbox_cache(self.session)
                path, wervd = config.create_local_mailstore(self.session,
                                                            name=mbx_cfg.local)
                wervd.is_local = mbx_cfg._key
                mbx_cfg.local = path
                if save:
                    self._save_config()

        elif mbx_cfg.local == '!CREATE' or disco_cfg.local_copy:
            config.flush_mbox_cache(self.session)
            path, wervd = config.create_local_mailstore(self.session)
            wervd.is_local = mbx_cfg._key
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
            if disco_cfg.parent_tag not in self.session.config.tags.keys():
                from mailpile.plugins.tags import Slugify
                disco_cfg.parent_tag = self._create_tag(
                    disco_cfg.parent_tag,
                    use_existing=False,
                    icon='icon-mailsource',
                    slug=Slugify(
                        self.my_config.name, tags=self.session.config.tags),
                    unique=False)
                if save:
                    self._save_config()
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

        # Make sure we have a parent tag, as that maybe useful when creating
        # tag names or the primary tag itself.
        parent = self._create_parent_tag(save=False)

        # We configure the primary_tag with a name, if it doesn't have
        # one already.
        if not mbx_cfg.primary_tag:
            mbx_cfg.primary_tag = self._create_tag_name(self._path(mbx_cfg))

        # If we have a policy for this mailbox, we really go and create
        # tags. The gap here allows the user to edit the primary_tag
        # proposal before changing the policy from 'unknown'.
        if self._policy(mbx_cfg) != 'unknown':
            try:
                mbx_cfg.primary_tag = self._create_tag(
                    mbx_cfg.primary_tag,
                    use_existing=False,
                    visible=disco_cfg.visible_tags,
                    unique=False,
                    parent=parent)
            except (ValueError, IndexError):
                self.session.ui.debug(traceback.format_exc())

        if save:
            self._save_config()

    BORING_FOLDER_RE = re.compile('(?i)^(home|mail|data|user\S*|[^[:alpha:]]+)$', re.UNICODE)
    TAGNAME_STRIP_RE = re.compile('[{}\\[\\]]', re.UNICODE)

    def _path_to_tagname(self, path):  # -> tag name
        """This converts a path to a tag name."""
        parts = self._mailbox_path_split(path)
        parts = [p for p in parts if not re.match(self.BORING_FOLDER_RE, p)]
        if not parts:
            return _('Unnamed')
        tagname = self._strip_file_extension(parts.pop(-1))
        while tagname[:1] == '.':
            tagname = tagname[1:]
        return re.sub(self.TAGNAME_STRIP_RE, '', tagname.replace('_', ' '))

    def _unique_tag_name(self, tagname):  # -> unused tag name
        """Make sure a tagname really is unused, unless we have a parent"""
        if self.my_config.discovery.parent_tag:
            return tagname
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
                    unique=False,
                    label=False,
                    visible=True,
                    slug=None,
                    icon=None,
                    parent=None):  # -> tag ID
        if tag_name_or_id in self.session.config.tags:
            # Short circuit if this is a tag ID for an existing tag
            return tag_name_or_id
        else:
            tag_name = tag_name_or_id

        tags = self.session.config.get_tags(tag_name)
        if tags and unique:
            raise ValueError('Tag name is not unique!')
        elif len(tags) == 1 and use_existing:
            tag_id = tags[0]._key
        else:
            if slug is None:
                from mailpile.plugins.tags import Slugify
                if self.my_config.name:
                    slug = Slugify('/'.join([self.my_config.name, tag_name]),
                                   tags=self.session.config.tags)
                else:
                    slug = Slugify(tag_name, tags=self.session.config.tags)
            tag_id = self.session.config.tags.append({
                'name': tag_name,
                'slug': slug,
                'type': 'mailbox',
                'parent': parent or '',
                'label': label,
                'flag_allow_add': False,
                'flag_allow_del': False,
                'icon': icon or 'icon-tag',
                'display': 'tag' if visible else 'archive',
            })
            if parent and visible:
                self.session.config.tags[parent].display = 'tag'
        return tag_id

    def interrupt_rescan(self, reason):
        self._interrupt = reason or _('Aborted')
        if self._rescanning:
            self.session.config.index.interrupt = reason

    def _process_new(self, mbx_key, mbx_cfg, mbox,
                     msg, msg_metadata_kws, msg_ts, keywords, snippet):
        # Here subclasses could use mbx_key, mbx_cfg or mbox to grab the
        # mailbox itself, in case it has metadata (like Maildir). The
        # default just looks at the Status: headers of the mail itself.
        return ProcessNew(self.session, msg, msg_metadata_kws, msg_ts,
                          keywords, snippet)

    def _msg_key_order(self, key):
        return key

    def _copy_new_messages(self, mbx_key, mbx_cfg, src,
                           stop_after=-1, scan_args=None, deadline=None):
        session, config = self.session, self.session.config
        self.event.data['copying'] = progress = {
            'running': True,
            'mailbox_id': mbx_key,
            'copied_messages': 0,
            'copied_bytes': 0,
            'deleting': False,
            'complete': False
        }
        scan_args = scan_args or {}
        policy = self._policy(mbx_cfg)
        count = 0

        def maybe_delete_from_server(loc, src):
            # Delete from source, if that's our policy.
            if policy != 'move':
                return

            downloaded = list(set(src.keys()) & set(loc.source_map.keys()))
            downloaded.sort(key=self._msg_key_order)

            should = _('Should delete %d messages') % len(downloaded)
            if 'sources' in config.sys.debug and downloaded:
                session.ui.debug(should)

            if config.prefs.allow_deletion:
                try:
                    for i, key in enumerate(downloaded):
                        progress['deleting'] = '%d/%d' % (i+1, len(downloaded))
                        src.remove(key)
                    src.flush()
                except:
                    # Just ignore errors for now, we'll try again later.
                    if 'sources' in config.sys.debug:
                        session.ui.debug(traceback.format_exc())
            else:
                progress['deleting'] = '. '.join([
                    _('Deletion is disabled'), should])

        try:
            # Lock the source mailbox while we work with it
            src.lock()

            with self._lock:
                loc = config.open_mailbox(session, mbx_key, prefer_local=True)
            if src == loc:
                return count

            # Perform housekeeping on the source_map, to make sure it does
            # not grow without bounds or misrepresent things.
            gone = []
            src_keys = set(src.keys())
            loc_keys = set(loc.keys())
            for key, val in loc.source_map.iteritems():
                if (val not in loc_keys) or (key not in src_keys):
                    gone.append(key)
            for key in gone:
                del loc.source_map[key]

            # Figure out what actually needs to be downloaded, log it
            keys = list(src_keys - set(loc.source_map.keys()))
            keys.sort(key=self._msg_key_order)
            progress.update({
                'total': len(src_keys),
                'total_local': len(loc_keys),
                'uncopied': len(keys),
                'batch_size': stop_after if (stop_after > 0) else len(keys)
            })

            # Go download!
            key_errors = []
            for key in reversed(keys):
                if self._check_interrupt(log=False, clear=False):
                    progress['interrupted'] = True
                    return count

                session.ui.mark(_('Copying message: %s') % key)
                progress['copying_src_id'] = key
                try:
                    mkws = src.get_metadata_keywords(key)
                    data = src.get_bytes(key)
                except KeyError:
                    progress['key_errors'] = key_errors
                    key_errors.append(key)
                    # Ignore, in case this is a problem with just this
                    # individual message...
                    continue

                loc_key = loc.add_from_source(key, mkws, data)
                self.event.data['counters']['copied_messages'] += 1
                del progress['copying_src_id']
                progress['copied_messages'] += 1
                progress['copied_bytes'] += len(data)
                progress['uncopied'] -= 1
                count += 1

                # This forks off a scan job to index the message
                config.index.scan_one_message(
                    session, mbx_key, loc, loc_key,
                    wait=False, msg_data=data, msg_metadata_kws=mkws,
                    **scan_args)

                stop_after -= 1
                if (stop_after == 0) or (deadline and time.time() > deadline):
                    maybe_delete_from_server(loc, src)
                    progress['stopped'] = True
                    return count
            progress['complete'] = True

        except IOError:
            # These just abort the download/read, which we're going to just
            # take in stride for now.
            if 'sources' in config.sys.debug:
                session.ui.debug(traceback.format_exc())
            progress['ioerror'] = True
        except:
            if 'sources' in config.sys.debug:
                session.ui.debug(traceback.format_exc())
            progress['raised'] = True
            raise
        finally:
            src.unlock()
            progress['running'] = False

        maybe_delete_from_server(loc, src)
        return count

    def rescan_mailbox(self, mbx_key, mbx_cfg, path, stop_after=None):
        session, config = self.session, self.session.config

        with self._lock:
            if self._rescanning:
                return -1
            self._rescanning = True

        mailboxes = min(1, len([m for m in self.my_config.mailbox.values()
                                if self._policy(m) not in ('ignore',
                                                           'unknown')]))
        try:
            ostate = self._state  # Set this in case locking fails
            with self._lock:
                new_state = 'Rescan(%s, %s)' % (mbx_key, stop_after)
                ostate, self._state = self._state, new_state

                apply_tags = mbx_cfg.apply_tags[:]

                parent = self._create_parent_tag(save=True)
                if parent:
                    tid = config.get_tag_id(parent)
                    if tid:
                        apply_tags.append(tid)

                self._create_primary_tag(mbx_cfg)
                if mbx_cfg.primary_tag:
                    tid = config.get_tag_id(mbx_cfg.primary_tag)
                    if tid:
                        apply_tags.append(tid)

            with self._lock:
                mbox = config.open_mailbox(session, mbx_key,
                                           prefer_local=False)
            def process_new(msg, msg_metadata_kws, msg_ts, keywords, snippet):
                return self._process_new(mbx_key, mbx_cfg, mbox,
                                         msg, msg_metadata_kws, msg_ts,
                                         keywords, snippet)
            scan_mailbox_args = {
                'process_new': (process_new if mbx_cfg.process_new else False),
                'apply_tags': (apply_tags or []),
                'stop_after': stop_after,
                'event': self.event
            }
            copied = count = 0

            if mbx_cfg.local or self.my_config.discovery.local_copy:
                # Note: We copy fewer messages than the batch allows for,
                # because we might have been aborted on an earlier run and
                # the rescan may need to catch up.
                self._create_local_mailbox(mbx_cfg)
                max_copy = max(min(stop_after, 5), int(0.8 * stop_after))
                self._state = '%s: %s' % (new_state, _('Copying'))
                self._log_status(_('Copying up to %d e-mails from %s'
                                   ) % (max_copy, self._mailbox_name(path)))
                copied = self._copy_new_messages(mbx_key, mbx_cfg, mbox,
                                                 stop_after=max_copy,
                                                 scan_args=scan_mailbox_args)
                count += copied

            if self._check_interrupt(clear=False):
                if 'rescan' in self.event.data:
                    self.event.data['rescan']['running'] = False
                return count

            self._state = '%s: %s' % (new_state, _('Working'))
            self._log_status(_('Updating search engine for %s'
                               ) % self._mailbox_name(path))
            # Wait for background message scans to complete...
            config.scan_worker.do(session, 'Wait', lambda: 1)

            if 'rescans' in self.event.data:
                self.event.data['rescans'][:-mailboxes] = []

            return count + config.index.scan_mailbox(session,
                                                     mbx_key,
                                                     mbx_cfg.local or path,
                                                     config.open_mailbox,
                                                     **scan_mailbox_args)
        except ValueError:
            session.ui.debug(traceback.format_exc())
            return -1
        finally:
            self._state = ostate
            self._rescanning = False

    def open_mailbox(self, mbx_id, fn):
        # This allows mail sources to override the default mailbox
        # opening mechanism.  Returning false respectfully declines.
        return None

    def is_mailbox(self, fn):
        return False

    def _summarize_auth(self):
        return sha1b64(self.my_config.auth_type, '-',
                       self.my_config.username, '-',
                       self.my_config.password)

    def run(self):
        play_nice(18)  # Reduce priority quite a lot

        with self.session.config.index_check:
            self.alive = True

        self._load_state()
        _original_session = self.session

        def sleeptime():
            if not self.my_config.enabled:
                return 24 * 3600
            elif self._last_rescan_completed or self._last_rescan_failed:
                return self.my_config.interval
            else:
                return 1

        self._loop_count = 0
        while self._loop_count == 0 or self._sleep(self._jitter(sleeptime())):
            self.event.data['enabled'] = self.my_config.enabled
            self.event.data['profile_id'] = self.my_config.profile
            if self.my_config.enabled:
                self.event.flags = Event.RUNNING
                self._loop_count += 1
            else:
                if self._loop_count > 1:
                    self._log_status(_('Disabled'), clear_errors=True)
                self._loop_count = 1
                self.close()
                continue

            self.name = self.my_config.name  # In case the config changes
            self._update_unknown_state()
            if not self.session.config.index:
                continue

            conn_err = self.event.data.get('connection', {}).get('error')
            if conn_err and conn_err[0] in ('oauth2', 'auth'):
                if ((self._loop_count % 100 != 0)
                        and self._summarize_auth() == conn_err[-1]):
                    self.session.ui.debug('Auth unchanged, doing nothing')
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
                else:
                    self._log_conn_errors()

                next_save_time = self._last_saved + self.SAVE_STATE_INTERVAL
                if self.alive and time.time() >= next_save_time:
                    self._save_state()
                    self._check_keepalive()
                elif self._last_rescan_completed:
                    self._check_keepalive()
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
            self._update_unknown_state()
        self.close()
        self._log_status(_('Shut down'), clear_errors=True)
        self._save_state()

    def _check_keepalive(self):
        if not self.my_config.keepalive:
            self.close()

    def _log_conn_errors(self):
        if 'connection' in self.event.data:
            cinfo = self.event.data['connection']
            if not cinfo.get('live'):
                err_msg = cinfo.get('error', [None, None])[1]
                if err_msg:
                    self._log_status(err_msg)

    def wake_up(self, after=0):
        self._sleeping = after

    def rescan_now(self, session=None, started_callback=None):
        if not self.my_config.enabled:
            return

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

    def quit(self, join=False):
        self.interrupt_rescan(_('Shut down'))
        self.alive = False
        self.wake_up()
        if join and self.isAlive():
            self.join()


def ProcessNew(session, msg, msg_metadata_kws, msg_ts, keywords, snippet):
    if 'dsn:has' in keywords or 'mdn:has' in keywords:
        # FIXME: This is a delivery notfication of some sort!
        #        Figure out what it is telling us...
        return False

    if ('s:maildir' in msg_metadata_kws                  # Seen=read, maildir
            or 'r:maildir' in msg_metadata_kws           # Replied, maildir
            or 'r' in msg.get('status', '').lower()      # Read, mbox
            or 'a' in msg.get('x-status', '').lower()):  # PINE, answered
        return False

    keywords.update(['%s:in' % tag._key for tag in
                     session.config.get_tags(type='unread')])
    return True


def MailSource(session, my_config):
    # FIXME: check the plugin and instanciate the right kind of mail source
    #        for this config section.
    if my_config.protocol in ('mbox', 'maildir', 'local'):
        from mailpile.mail_source.local import LocalMailSource
        return LocalMailSource(session, my_config)
    elif my_config.protocol in ('imap', 'imap_ssl', 'imap_tls'):
        from mailpile.mail_source.imap import ImapMailSource
        return ImapMailSource(session, my_config)
    elif my_config.protocol in ('pop3', 'pop3_ssl'):
        from mailpile.mail_source.pop3 import Pop3MailSource
        return Pop3MailSource(session, my_config)
    raise ValueError(_('Unknown mail source protocol: %s'
                       ) % my_config.protocol)
