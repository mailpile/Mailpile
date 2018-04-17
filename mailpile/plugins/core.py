# These are the Mailpile core commands, the public "API" we expose for
# searching, tagging and editing e-mail.
#
# FIXME: This should probably be broken into smaller modules
#
import datetime
import json
import os
import random
import re
import socket
import subprocess
import sys
import traceback
import thread
import threading
import time
import webbrowser

import mailpile.util
import mailpile.postinglist
import mailpile.security as security
from mailpile.commands import *
from mailpile.config.validators import WebRootCheck
from mailpile.crypto.gpgi import GnuPG
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import IsMailbox
from mailpile.mailutils.emails import ClearParseCache, Email
from mailpile.postinglist import GlobalPostingList
from mailpile.plugins import PluginManager
from mailpile.safe_popen import MakePopenUnsafe, MakePopenSafe
from mailpile.search import MailIndex
from mailpile.util import *
from mailpile.vcard import AddressInfo
from mailpile.vfs import vfs, FilePath

_plugins = PluginManager(builtin=__file__)


class Load(Command):
    """Load or reload the metadata index"""
    SYNOPSIS = (None, 'load', None, None)
    ORDER = ('Internals', 1)
    CONFIG_REQUIRED = False
    IS_INTERACTIVE = True

    def command(self, reset=True, wait=True, wait_all=False, quiet=False):
        try:
            if self._idx(reset=reset,
                         wait=wait,
                         wait_all=wait_all,
                         quiet=quiet):
                return self._success(_('Loaded metadata index'))
            else:
                return self._error(_('Failed to load metadata index'))
        except IOError:
            return self._error(_('Failed to decrypt configuration, '
                                 'please log in!'))


class Rescan(Command):
    """Add new messages to index"""
    SYNOPSIS = (None, 'rescan', 'rescan',
                '[full|vcards|vcards:<src>|sources|mailboxes|both|mailbox:<id>|<msgs>]')
    ORDER = ('Internals', 2)
    LOG_PROGRESS = True

    HTTP_CALLABLE = ('POST',)
    HTTP_POST_VARS = {
        'which': '[full|vcards|vcards:<src>|both|mailboxes|sources|<msgs>]'
    }

    def command(self, slowly=False, cron=False):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)
        if 'which' in self.data:
            args.extend(self.data['which'])

        # Abort if we are out of disk space
        full_path = config.need_more_disk_space()
        if full_path:
            return self._error(_('Insufficient free space in %s'
                                 ) % full_path)

        # Pretend we're idle, to make rescan go fast fast.
        if not slowly:
            mailpile.util.LAST_USER_ACTIVITY = 0

        # Cron always runs the rescan command, no matter what else
        if cron:
            self._run_rescan_command(session)

        if args and args[0].lower().startswith('vcards'):
            return self._success(_('Rescanned vCards'),
                                 result=self._rescan_vcards(session, args[0]))
        elif args and (args[0].lower() in ('both', 'mailboxes', 'sources',
                                           'editable') or
                       args[0].lower().startswith('mailbox:')):
            which = args[0].lower()
            return self._success(_('Rescanned mailboxes'),
                                 result=self._rescan_mailboxes(session,
                                                               which=which))
        elif args and args[0].lower() == 'full':
            config.flush_mbox_cache(session, wait=True)
            args.pop(0)

        # Clear the cache first, in case the user is flailing about
        ClearParseCache(full=True)

        msg_idxs = self._choose_messages(args)
        if msg_idxs:
            for msg_idx_pos in msg_idxs:
                e = Email(idx, msg_idx_pos)
                try:
                    session.ui.mark('Re-indexing %s' % e.msg_mid())
                    idx.index_email(self.session, e)
                except KeyboardInterrupt:
                    raise
                except:
                    self._ignore_exception()
                    session.ui.warning(_('Failed to reindex: %s'
                                         ) % e.msg_mid())

            self.event.data["messages"] = len(msg_idxs)
            self.session.config.event_log.log_event(self.event)
            self._background_save(index=True)

            return self._success(_('Indexed %d messages') % len(msg_idxs),
                                 result={'messages': len(msg_idxs)})

        else:
            # FIXME: Need a lock here?
            if 'rescan' in config._running:
                return self._success(_('Rescan already in progress'))
            config._running['rescan'] = True
            try:
                results = {}
                results.update(self._rescan_vcards(session, 'vcards'))
                if not cron:
                    results.update(self._rescan_mailboxes(session,
                                                          which='sources'))

                self.event.data.update(results)
                self.session.config.event_log.log_event(self.event)
                if 'aborted' in results:
                    raise KeyboardInterrupt()
                return self._success(_('Rescanned vCards and mailboxes'),
                                     result=results)
            except (KeyboardInterrupt), e:
                return self._error(_('User aborted'), info=results)
            finally:
                del config._running['rescan']

    def _rescan_vcards(self, session, which):
        from mailpile.plugins import PluginManager
        config = session.config
        imported = 0
        importer_cfgs = config.prefs.vcard.importers
        which_spec = which.split(':')
        importers = []
        try:
            session.ui.mark(_('Rescanning: %s') % 'vcards')
            for importer in PluginManager.VCARD_IMPORTERS.values():
                if (len(which_spec) > 1 and
                        which_spec[1] != importer.SHORT_NAME):
                    continue
                importers.append(importer.SHORT_NAME)
                for cfg in importer_cfgs.get(importer.SHORT_NAME, []):
                    if cfg:
                        imp = importer(session, cfg)
                        imported += imp.import_vcards(session, config.vcards)
                    if mailpile.util.QUITTING:
                        return {'vcards': imported, 'vcard_sources': importers,
                                'aborted': True}
        except KeyboardInterrupt:
            return {'vcards': imported, 'vcard_sources': importers,
                    'aborted': True}
        return {'vcards': imported, 'vcard_sources': importers}

    def _run_rescan_command(self, session, timeout=120):
        pre_command = session.config.prefs.rescan_command
        if pre_command and not mailpile.util.QUITTING:
            session.ui.mark(_('Running: %s') % pre_command)
            if not ('|' in pre_command or
                    '&' in pre_command or
                    ';' in pre_command):
                pre_command = pre_command.split()
            cmd = subprocess.Popen(pre_command,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   shell=not isinstance(pre_command, list))
            countdown = [timeout]
            def eat(fmt, fd):
                for line in fd:
                    session.ui.notify(fmt % line.strip())
                    countdown[0] = timeout
            for t in [
                threading.Thread(target=eat, args=['E: %s', cmd.stderr]),
                threading.Thread(target=eat, args=['O: %s', cmd.stdout])
            ]:
                t.daemon = True
                t.start()
            try:
                while countdown[0] > 0:
                    countdown[0] -= 1
                    if cmd.poll() is not None:
                        rv = cmd.wait()
                        if rv != 0:
                            session.ui.notify(_('Rescan command returned %d')
                                              % rv)
                        return
                    elif mailpile.util.QUITTING:
                        return
                    time.sleep(1)
            finally:
                if cmd.poll() is None:
                    session.ui.notify(_('Aborting rescan command'))
                    cmd.terminate()
                    time.sleep(0.2)
                    if cmd.poll() is None:
                        cmd.kill()
# NOTE: For some reason we were using the un-safe Popen before, not sure
#       if that matters. Leaving this commented out for now for reference.
#
#            try:
#                MakePopenUnsafe()
#                subprocess.check_call(pre_command, shell=True)
#            finally:
#                MakePopenSafe()

    def _rescan_mailboxes(self, session, which='mailboxes'):
        import mailpile.mail_source
        config = session.config
        idx = self._idx()
        msg_count = 0
        mbox_count = 0
        rv = True
        try:
            session.ui.mark(_('Rescanning: %s') % which)

            self._run_rescan_command(session)
            if which.startswith('mailbox:'):
                only = which.split(':')[1]
                which = 'mailboxes'
            else:
                only = None

            msg_count = 1
            if which in ('both', 'mailboxes', 'editable'):
                if which == 'editable':
                    mailboxes = config.get_mailboxes(with_mail_source=True)
                else:
                    mailboxes = config.get_mailboxes(with_mail_source=False)

                for fid, fpath, sc in mailboxes:
                    if mailpile.util.QUITTING:
                        break
                    if fpath == '/dev/null':
                        continue
                    if only and (only != fpath) and (only != fid):
                        continue
                    try:
                        session.ui.mark(_('Rescanning: %s %s')
                                        % (fid, fpath))
                        if which == 'editable':
                            count = idx.scan_mailbox(session, fid, fpath,
                                                     config.open_mailbox,
                                                     process_new=False,
                                                     editable=True,
                                                     event=self.event)
                        else:
                            count = idx.scan_mailbox(session, fid, fpath,
                                                     config.open_mailbox,
                                                     event=self.event)
                    except ValueError:
                        self._ignore_exception()
                        count = -1
                    if count < 0:
                        session.ui.warning(_('Failed to rescan: %s') %
                                           FilePath(fpath).display())
                    elif count > 0:
                        msg_count += count
                        mbox_count += 1
                    session.ui.mark('\n')

            if which in ('both', 'sources'):
                ocount = msg_count - 1
                while ocount != msg_count:
                    ocount = msg_count
                    src_ids = config.sources.keys()
                    src_ids.sort(key=lambda k: random.randint(0, 100))
                    for src_id in src_ids:
                        try:
                            src = config.get_mail_source(src_id, start=True)
                            if mailpile.util.QUITTING:
                                ocount = msg_count
                                break
                            session.ui.mark(_('Rescanning: %s') % (src, ))
                            count = src.rescan_now(session)
                        except ValueError:
                            count = 0
                        if count > 0:
                            msg_count += count
                            mbox_count += 1
                        session.ui.mark('\n')
                    if not session.ui.interactive:
                        break

            msg_count -= 1
            session.ui.mark(_('Nothing changed'))
        except (KeyboardInterrupt, subprocess.CalledProcessError), e:
            return {'aborted': True,
                    'messages': msg_count,
                    'mailboxes': mbox_count}
        finally:
            if msg_count:
                session.ui.mark('\n')
                if msg_count < 500:
                    self._background_save(index=True)
                else:
                    self._background_save(index_full=True)
        return {'messages': msg_count,
                'mailboxes': mbox_count}


class Optimize(Command):
    """Optimize the keyword search index"""
    SYNOPSIS = (None, 'optimize', None, '[harder]')
    ORDER = ('Internals', 3)

    def command(self, slowly=False):
        try:
            if not slowly:
                mailpile.util.LAST_USER_ACTIVITY = 0
            self._idx().save(self.session)
            GlobalPostingList.Optimize(self.session, self._idx(),
                                       force=('harder' in self.args))
            return self._success(_('Optimized search engine'))
        except KeyboardInterrupt:
            return self._error(_('Aborted'))


class DeleteMessages(Command):
    """Delete one or more messages."""
    SYNOPSIS = (None, 'delete', 'message/delete', '[--keep] <messages>')
    ORDER = ('Searching', 99)
    IS_USER_ACTIVITY = True

    def command(self, slowly=False):
        idx = self._idx()

        args = list(self.args)
        keep = 0
        while '--keep' in args:
            args.remove('--keep')
            keep += 1

        deleted, failed, mailboxes = [], [], []
        for msg_idx in self._choose_messages(args):
            e = Email(idx, msg_idx)
            del_ok, mboxes = e.delete_message(self.session,
                                              flush=False, keep=keep)
            mailboxes.extend(mboxes)
            if del_ok:
                deleted.append(msg_idx)
            else:
                failed.append(msg_idx)

        # This will actually delete from mboxes, etc.
        for m in set(mailboxes):
            with m:
                m.flush()

        # FIXME: Trigger a background rescan of affected mailboxes, as
        #        the flush() above may have broken our pointers.

        result = {'deleted': deleted}
        if failed:
            result['failed'] = failed
            return self._error(_('Could not delete all messages'),
                               result=result)
        return self._success(_('Deleted %d messages') % len(deleted),
                             result=result)


class BrowseOrLaunch(Command):
    """Launch browser and exit, if already running"""
    SYNOPSIS = (None, 'browse_or_launch', None, None)
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    RAISES = (KeyboardInterrupt,)

    @classmethod
    def Browse(cls, sspec):
        http_url = ('http://%s:%s%s/' % sspec
                    ).replace('//0.0.0.0:', '//localhost:')
        try:
            MakePopenUnsafe()
            webbrowser.open(http_url)
            return http_url
        except:
            pass
        finally:
            MakePopenSafe()
        return False

    def command(self):
        config = self.session.config

        if config.http_worker:
            sspec = config.http_worker.sspec
        else:
            sspec = (config.sys.http_host, config.sys.http_port,
                     config.sys.http_path or '')

        try:
            socket.create_connection(sspec[:2])
            self.Browse(sspec)
            os._exit(127)
        except IOError:
            pass

        return self._success(_('Launching Mailpile'), result=True)


class RunWWW(Command):
    """Just run the web server"""
    SYNOPSIS = (None, 'www', None, '[<host:port/path>]')
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False

    def command(self):
        config = self.session.config
        ospec = (config.sys.http_host, config.sys.http_port,
                 config.sys.http_path)

        if self.args:
            host, portpath = self.args[0].split('://')[-1].split(':', 1)
            port, path = (portpath+'/').split('/', 1)
            port = int(port)
            sspec = (host, port, WebRootCheck(path))
        else:
            sspec = ospec

        if self.session.config.http_worker:
            self.session.config.http_worker.quit(join=True)
            self.session.config.http_worker = None

        self.session.config.prepare_workers(self.session,
                                            httpd_spec=tuple(sspec),
                                            daemons=True)
        if config.http_worker:
            sspec = config.http_worker.httpd.sspec
            http_url = 'http://%s:%s%s/' % sspec
            if sspec != ospec:
                (config.sys.http_host, config.sys.http_port,
                 config.sys.http_path) = sspec
                self._background_save(config=True)
                return self._success(_('Moved the web server to %s'
                                       ) % http_url)
            else:
                return self._success(_('Started the web server on %s'
                                       ) % http_url)
        else:
            return self._error(_('Failed to start the web server'))


class Cleanup(Command):
    """Perform cleanup actions (runs before shutdown)"""
    SYNOPSIS = (None, 'cleanup', None, "")
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    SPLIT_ARG = False
    TASKS = []

    @classmethod
    def AddTask(cls, task, last=False, first=False):
        safe_assert(not (first and last))
        if (first or last) and not cls.TASKS:
            cls.TASKS = [lambda: True]
        if first:
            cls.TASKS.insert(0, task)
        elif last:
            cls.TASKS.append(task)
        else:
            cls.TASKS.insert(len(cls.TASKS) - 1, task)

    def command(self):
        while self.TASKS:
            try:
                self.TASKS.pop(0)()
            except:
                traceback.print_exc()
                pass
        return self._success(_('Performed shutdown tasks'))


class WritePID(Command):
    """Write the PID to a file"""
    SYNOPSIS = (None, 'pidfile', None, "</path/to/pidfile>")
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    SPLIT_ARG = False

    def command(self):
        filename = self.args[0]
        with vfs.open(filename, 'w') as fd:
            fd.write('%d' % os.getpid())
            Cleanup.AddTask(lambda: os.unlink(filename), last=True)
        return self._success(_('Wrote PID to %s') % self.args)


class RenderPage(Command):
    """Does nothing, for use by semi-static jinja2 pages"""
    SYNOPSIS = (None, None, 'page', None)
    ORDER = ('Internals', 6)
    CONFIG_REQUIRED = False
    SPLIT_ARG = False
    HTTP_STRICT_VARS = False
    IS_USER_ACTIVITY = True

    def template_path(self, ttype, template_id=None, **kwargs):
        if not template_id:
            template_id = '%s/%s' % (self.SYNOPSIS[2],
                                     self.args and self.args[0] or '')
        return Command.template_path(self, ttype, template_id=template_id,
                                     **kwargs)

    def command(self):
        return self._success(_('Rendered the page'), result={
            'path': (self.args and self.args[0] or ''),
            'data': self.data
        })


class ProgramStatus(Command):
    """Display list of running threads, locks and outstanding events."""
    SYNOPSIS = (None, 'ps', 'ps', None)
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False
    LOG_NOTHING = True

    class CommandResult(Command.CommandResult):
        def as_text(self):
            now = time.time()

            sessions = self.result.get('sessions')
            if sessions:
                sessions = '\n'.join(sorted(['  %s/%s = %s (%ds)'
                                             % (us['sessionid'],
                                                us['userdata'],
                                                us['userinfo'],
                                                now - us['timestamp'])
                                             for us in sessions]))
            else:
                sessions = '  ' + _('Nothing Found')

            ievents = self.result.get('ievents')
            cevents = self.result.get('cevents')
            if cevents:
                cevents = '\n'.join(['  %s' % (e.as_text(compact=True),)
                                     for e in cevents])
            else:
                cevents = '  ' + _('Nothing Found')

            ievents = self.result.get('ievents')
            if ievents:
                ievents = '\n'.join([' %s' % (e.as_text(compact=True),)
                                     for e in ievents])
            else:
                ievents = '  ' + _('Nothing Found')

            threads = self.result.get('threads')
            if threads:
                threads = '\n'.join(sorted([('  ' + str(t)) for t in threads]))
            else:
                threads = _('Nothing Found')

            locks = self.result.get('locks')
            if locks:
                locks = '\n'.join(sorted([('  %s.%s is %slocked'
                                           ) % (l[0], l[1],
                                                '' if l[2] else 'un')
                                          for l in locks]))
            else:
                locks = _('Nothing Found')

            return ('Recent events:\n%s\n\n'
                    'Events in progress:\n%s\n\n'
                    'Live sessions:\n%s\n\n'
                    'Postinglist timers:\n%s\n\n'
                    'Threads: (bg delay %.3fs, live=%s, httpd=%s)\n%s\n\n'
                    'Locks:\n%s'
                    ) % (cevents, ievents, sessions,
                         self.result['pl_timers'],
                         self.result['delay'],
                         self.result['live'],
                         self.result['httpd'],
                         threads, locks)

    def command(self, args=None):
        import mailpile.auth
        import mailpile.mail_source
        import mailpile.plugins.compose
        import mailpile.plugins.contacts

        config = self.session.config

        try:
            idx = config.index
            locks = [
                ('config.index', '_lock', idx._lock._is_owned()),
                ('config.index', '_save_lock', idx._save_lock._is_owned())
            ]
        except AttributeError:
            locks = []
        if config.vcards:
            locks.extend([
                ('config.vcards', '_lock', config.vcards._lock._is_owned()),
            ])
        locks.extend([
            ('config', '_lock', config._lock._is_owned()),
            ('mailpile.postinglist', 'GLOBAL_POSTING_LOCK',
             mailpile.postinglist.GLOBAL_POSTING_LOCK._is_owned()),
            ('mailpile.postinglist', 'GLOBAL_OPTIMIZE_LOCK',
             mailpile.plugins.compose.GLOBAL_EDITING_LOCK._is_owned()),
            ('mailpile.plugins.compose', 'GLOBAL_EDITING_LOCK',
             mailpile.plugins.contacts.GLOBAL_VCARD_LOCK._is_owned()),
            ('mailpile.plugins.contacts', 'GLOBAL_VCARD_LOCK',
             mailpile.postinglist.GLOBAL_OPTIMIZE_LOCK.locked()),
            ('mailpile.postinglist', 'GLOBAL_GPL_LOCK',
             mailpile.postinglist.GLOBAL_GPL_LOCK._is_owned()),
        ])

        threads = threading.enumerate()
        for thread in threads:
            try:
                if hasattr(thread, 'lock'):
                    locks.append([thread, 'lock', thread.lock])
                if hasattr(thread, '_lock'):
                    locks.append([thread, '_lock', thread._lock])
                if locks and hasattr(locks[-1][-1], 'locked'):
                    locks[-1][-1] = locks[-1][-1].locked()
                elif locks and hasattr(locks[-1][-1], '_is_owned'):
                    locks[-1][-1] = locks[-1][-1]._is_owned()
            except AttributeError:
                pass

        import mailpile.auth
        import mailpile.httpd
        result = {
            'sessions': [{'sessionid': k,
                          'timestamp': v.ts,
                          'userdata': v.data,
                          'userinfo': v.auth} for k, v in
                         mailpile.auth.SESSION_CACHE.iteritems()],
            'pl_timers': mailpile.postinglist.TIMERS,
            'delay': play_nice_with_threads(sleep=False),
            'live': mailpile.util.LIVE_USER_ACTIVITIES,
            'httpd': mailpile.httpd.LIVE_HTTP_REQUESTS,
            'threads': threads,
            'locks': sorted(locks)
        }
        if config.event_log:
            result.update({
                'cevents': list(config.event_log.events(flag='c'))[-10:],
                'ievents': config.event_log.incomplete(),
            })

        return self._success(_("Listed events, threads, and locks"),
                             result=result)


class CronStatus(Command):
    """Manually edit or display the background job schedule"""
    SYNOPSIS = (None, 'cron', None,
                "[<job> <--trigger|--interval <n>|--postpone <hours>>]")
    ORDER = ('Internals', 4)
    IS_USER_ACTIVITY = False

    class CommandResult(Command.CommandResult):
        def as_text(self):
            def _t(dt):
                return '%4.4d-%2.2d-%2.2d %2.2d:%2.2d' % (
                    dt.year, dt.month, dt.day, dt.hour, dt.minute)

            fmt = ' %-23s %8s %-16s %-16s %s'
            lines = [
                'Background CRON last ran at %s.' % _t(
                    datetime.datetime.fromtimestamp(self.result['last_run'])),
                'Current schedule:',
                '',
                fmt % ('JOB', 'INTERVAL', 'LAST RUN', 'NEXT RUN', 'STATUS')]

            for job_name, interval, func, last, status in self.result['jobs']:
                lines.append(fmt % (
                    job_name,
                    interval,
                    (_t(datetime.datetime.fromtimestamp(last))
                     if (status != 'new') else ''),
                    _t(datetime.datetime.fromtimestamp(last + interval)),
                    status))

            return '\n'.join(lines)

    def command(self, args=None):
        config = self.session.config
        args = args if (args is not None) else list(self.args)
        now = int(time.time())

        if args:
            job = args.pop(0)
        while args:
            op = args.pop(0).lower().replace('-', '')
            if op == 'interval':
                interval = int(args.pop(0))
                config.cron_worker.schedule[job][1] = interval
            elif op == 'trigger':
                interval = config.cron_worker.schedule[job][1]
                config.cron_worker.schedule[job][3] = now - interval
            elif op == 'postpone':
                hours = float(args.pop(0))
                config.cron_worker.schedule[job][3] += int(hours * 3600)
            else:
                raise NotImplementedError('Unknown op: %s' % op)

        return self._success(
            _("Displayed CRON schedule"),
            result={
                'last_run': config.cron_worker.last_run,
                'jobs': config.cron_worker.schedule.values()})


class HealthCheck(Command):
    """Check and report app health"""
    SYNOPSIS = (None, 'health', None, "")
    ORDER = ('Internals', 4)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False

    # We cache our health event, so it can be updated by the class methods.
    health_event = None

    def _create_event(self):
        if HealthCheck.health_event is not None:
            self.event = HealthCheck.health_event
        else:
            Command._create_event(self)
            self.event.data['starttime'] = int(time.time())
            self.event.data['problems'] = {}
            self.event.data['healthy'] = True
            HealthCheck.health_event = self.event

    @classmethod
    def _disk_check(cls, session, config):
        if config.need_more_disk_space():
            return _('Insufficient free disk space') + '.'
        return False

    @classmethod
    def _readonly_check(cls, session, config):
        from mailpile.security import _lockdown_basic
        if _lockdown_basic(config):
            return _('Your Mailpile is read-only!')
        return False

    @classmethod
    def check(cls, session, config):
        # Check all the things! The order here matters, more critical things
        # should be reported last as they will determine the final message.
        if not cls.health_event:
            return False

        messages = []
        problems = cls.health_event.data['problems']

        was_healthy = cls.health_event.data['healthy']
        old_problems = ' '.join(sorted(problems.keys()))

        now_healthy = True
        for crit, name, check in ((True, 'disk', cls._disk_check),
                                  (True, 'readonly', cls._readonly_check)):
             message = check(session, config)
             if message:
                 problems[name] = message
                 messages.append(message)
                 if crit:
                     now_healthy = False
             elif name in problems:
                 del problems[name]

        cls.health_event.data['healthy'] = now_healthy
        if messages:
            cls.health_event.message = ' '.join(messages[-2:])
            cls.health_event.flags = cls.health_event.RUNNING
        else:
            cls.health_event.message = _('We are healthy!')
            cls.health_event.flags = cls.health_event.COMPLETE

        # Only record changes to the event log
        new_problems = ' '.join(sorted(problems.keys()))
        if old_problems != new_problems and config.event_log:
            config.event_log.log_event(cls.health_event)

        return True

    def command(self, args=None):
        self.check(self.session, self.session.config)
        return self._success(self.event.message, result=self.event)


class GpgCommand(Command):
    """Interact with GPG directly"""
    SYNOPSIS = (None, 'gpg', None, "<GPG arguments ...>")
    ORDER = ('Internals', 4)
    IS_USER_ACTIVITY = True

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                return '%s\n\n%s' % (
                    (self.result['stdout'] or _('(no output)')).strip(),
                    self.message)
            return '%s' % self.message

    def command(self, args=None):
        args = list((args is None) and self.args or args or [])
        binary, rv = self._gnupg().gpgbinary, '(unknown)'
        with self.session.ui.term:
            try:
                self.session.ui.block()
                if (self.session.ui.interactive and
                        self.session.ui.render_mode == 'text'):
                    rv = os.system(' '.join([binary] + args))
                    stdout = None
                else:
                    sp = subprocess.Popen(
                        [binary] + ['--batch', '--no-tty'] + args,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        stdin=subprocess.PIPE)
                    (stdout, stderr) = sp.communicate(input='')
                    rv = sp.wait()
                from mailpile.plugins.vcard_gnupg import PGPKeysImportAsVCards
                PGPKeysImportAsVCards(self.session).run()
            except:
                self.session.ui.unblock()

        return self._success(_("That was fun!") + ' ' +
                             _("%s returned: %s") % (binary, rv),
                             result={'binary': binary,
                                     'stdout': stdout,
                                     'returned': rv})


class ListDir(Command):
    """Display working directory listing"""
    SYNOPSIS = (None, 'ls', 'browse', "[-a] [-d] [</path/*.foo> ...]")
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_BROWSE_FILESYSTEM

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result and self.result['entries']:
                lines = []
                for i in self.result['entries']:
                    sz = i.get('bytes')
                    dn = i['display_name']
                    dp = '' if (i['display_path'].endswith(dn)
                                ) else i['display_path']
                    dn += '/' if i.get('flag_directory') else ''
                    lines.append(('%12.12s %s%-20s %s'
                                  ) % ('' if (sz is None) else sz,
                                       '>' if i.get('flag_mailsource') else
                                       '*' if i.get('flag_mailbox') else ' ',
                                       dn, dp))
                return '\n'.join(lines)
            else:
                return _('Nothing Found')

    def command(self, args=None):
        args = list((args is None) and self.args or args or [])
        flags = [f for f in args if f[:1] == '-']
        args = [a for a in args if a[:1] != '-']

        if '_method' in self.data:
            args = ['/' + '/'.join(args)]

        if not args:
            args = ['.']

        def lsf(f):
            info = {'path': f}
            try:
                info = vfs.getinfo(f, self.session.config)
                info['icon'] = ''
                for k in info.get('flags', []):
                    info['flag_%s' % unicode(k).lower().replace('.', '_')
                         ] = True
            except (OSError, IOError, UnicodeDecodeError):
                info['flag_error'] = True
            return info
        def ls(p):
            return [lsf(vfs.path_join(p, f)) for f in vfs.listdir(p)
                    if '-a' in flags or f.raw_fp[:1] != '.']

        file_list = []
        errors = 0
        for path in args:
            if (security.forbid_command(self, security.CC_ACCESS_FILESYSTEM)
                    and (path != '/')
                    and (not path.endswith('$'))
                    and ('$/' not in path)):
                continue
            try:
                path = os.path.expanduser(path.encode('utf-8'))
                if vfs.isdir(path) and '*' not in path:
                    file_list.extend(ls(path))
                else:
                    for p in vfs.glob(path):
                        if vfs.isdir(p) and '-d' not in flags:
                            file_list.extend(ls(p))
                        else:
                            file_list.append(lsf(p))
            except (socket.error, socket.gaierror), e:
                return self._error(_('Network error: %s') % e)
            except (OSError, IOError, UnicodeDecodeError), e:
                errors += 1

        if errors and not file_list:
            traceback.print_exc()
            return self._error(_('Failed to list: %s') % e)

        id_src_map = self.session.config.find_mboxids_and_sources_by_path(
            *[unicode(f['path']) for f in file_list])
        for info in file_list:
            path = unicode(info['path'])
            mid_src = id_src_map.get(path)
            if mid_src:
                mid, src = mid_src
                if src:
                    info['source'] = src._key
                if src and src.mailbox[mid] and src.mailbox[mid].primary_tag:
                    tid = src.mailbox[mid].primary_tag
                    if tid in self.session.config.tags:
                        info['tag'] = self.session.config.tags[tid].slug
                        info['icon'] = self.session.config.tags[tid].icon
            elif info.get('flag_mailsource'):
                if path.startswith('/src:'):
                    info['source'] = path[5:]

        file_list.sort(key=lambda i: i['display_path'].lower())
        return self._success(_('Listed %d files or directories'
                               ) % len(file_list),
                             result={
            'path': args[0] if (len(args) == 1) else args,
            'name': vfs.display_name(args[0], self.session.config),
            'entries': file_list
        })


class ChangeDir(ListDir):
    """Change working directory"""
    SYNOPSIS = (None, 'cd', None, "<.../new/path/...>")
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_ACCESS_FILESYSTEM

    def command(self, args=None):
        try:
            args = list((args is None) and self.args or args or [])
            os.chdir(os.path.expanduser(args.pop(0).encode('utf-8')))
            return ListDir.command(self, args=['.'])
        except (OSError, IOError, UnicodeEncodeError), e:
            return self._error(_('Failed to change directories: %s') % e)


class CatFile(Command):
    """Dump the contents of a file, decrypting if necessary"""
    SYNOPSIS = (None, 'cat', None, "</path/to/file> [>/path/to/output]")
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_ACCESS_FILESYSTEM

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if isinstance(self.result, list):
                return ''.join(self.result)
            else:
                return ''

    def command(self, args=None):
        lines = []
        files = list(args or self.args)
        target = tfd = None
        if files and files[-1] and files[-1][:1] == '>':
            target = files.pop(-1)[1:]
            if vfs.exists(target):
                return self._error(_('That file already exists: %s'
                                     ) % target)
            tfd = vfs.open(target, 'wb')
            cb = lambda ll: [tfd.write(l) for l in ll]
        else:
            cb = lambda ll: lines.extend((l.decode('utf-8') for l in ll))

        for fn in files:
            with vfs.open(fn, 'r') as fd:
                def errors(where):
                    self.session.ui.error('Decrypt failed at %d' % where)
                decrypt_and_parse_lines(fd, cb, self.session.config,
                                        newlines=True, decode=None,
                                        gpgi=self._gnupg(),
                                        _raise=False, error_cb=errors)

        if tfd:
            tfd.close()
            return self._success(_('Dumped to %s: %s'
                                   ) % (target, ', '.join(files)))
        else:
            return self._success(_('Dumped: %s') % ', '.join(files),
                                   result=lines)


##[ Configuration commands ]###################################################


class ListLanguages(Command):
    """List available languages"""
    SYNOPSIS = (None, 'languages', 'settings/languages', '')
    ORDER = ('Config', 1)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False
    HTTP_CALLABLE = ('GET', )

    def command(self):
        from mailpile.i18n import ListTranslations
        langs = ListTranslations(self.session.config)
        return self._success(_('Listed available translations'),
                             result=sorted([(l, langs[l]) for l in langs]))


class ConfigSet(Command):
    """Change a setting"""
    SYNOPSIS = ('S', 'set', 'settings/set',
                '[--force] <section.variable> <value>')
    ORDER = ('Config', 1)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False

    SPLIT_ARG = False

    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_STRICT_VARS = False
    HTTP_POST_VARS = {
        '_section': 'common section, create if needed',
        'section.variable': 'value|json-string'
    }

    def command(self):
        from mailpile.httpd import BLOCK_HTTPD_LOCK, Idle_HTTPD

        config = self.session.config
        args = list(self.args)
        arg = ' '.join(args)
        ops = []
        on_cli = (self.data.get('_method', 'CLI') == 'CLI')
        force = False

        if arg.startswith('--force '):
            if not on_cli:
                raise ValueError('The --force flag only works on the CLI')
            force = True
            arg = arg[8:]

        if not force:
            fb = security.forbid_command(self, security.CC_CHANGE_CONFIG)
            if fb:
                return self._error(fb)

        if not config.loaded_config:
            self.session.ui.warning(_('WARNING: Any changes will '
                                      'be overwritten on login'))

        section = self.data.get('_section', [''])[0]
        if section:
            # Make sure section exists
            ops.append((section, '!CREATE_SECTION'))

        for var in self.data.keys():
            if (var in ('_section', '_method', 'context', 'csrf')
                   or var.startswith('ui_')):
                continue
            sep = '/' if ('/' in (section+var)) else '.'
            svar = (section+sep+var) if section else var
            parts = svar.split(sep)
            if parts[0] in config.rules:
                if svar.endswith('[]'):
                    ops.append((svar[:-2], json.dumps(self.data[var])))
                else:
                    ops.append((svar, self.data[var][0]))
            else:
                raise ValueError(_('Invalid section or variable: %s') % var)

        if args:
            if '=' in arg:
                # Backwards compatiblity with the old 'var = value' syntax.
                var, value = [s.strip() for s in arg.split('=', 1)]
                var = var.replace(': ', '.').replace(':', '.').replace(' ', '')
            else:
                var, value = arg.split(' ', 1)
            ops.append((var, value))

        # Access controls...
        if not force:
            for path, value in ops:
                fb = security.forbid_config_change(config, path)
                if fb:
                    return self._error(fb)
                elif path == 'master_key' and config.master_key:
                    return self._error(_('I refuse to change the master key!'))

        # We don't have transactions really, but making sure the HTTPD
        # is idle (aside from this request) will definitely help.
        with BLOCK_HTTPD_LOCK, Idle_HTTPD():
            updated = {}
            for path, value in ops:
                if not force:
                    if path == 'master_key' and config.master_key:
                        raise ValueError('Need --force to change master key.')
                    if path == 'sys.http_no_auth':
                        raise ValueError('Need --force to change auth policy.')

                value = value.strip()
                if value == '{None}':
                    value = None
                elif value == '{Blank}':
                    value = ''
                elif value == '{False}':
                    value = False
                elif value == '{True}':
                    value = True
                elif value[:1] in ('{', '[') and value[-1:] in ( ']', '}'):
                    value = json.loads(value)
                try:
                    try:
                        cfg, var = config.walk(path.strip(), parent=1)
                        if value == '!CREATE_SECTION':
                            if var not in cfg:
                                cfg[var] = {}
                        else:
                            cfg[var] = value
                            updated[path] = value
                    except IndexError:
                        cfg, v1, v2 = config.walk(path.strip(), parent=2)
                        cfg[v1] = {v2: value}
                except TypeError:
                    raise ValueError('Could not set variable: %s' % path)

        if config.loaded_config:
            self._background_save(config=True)

        return self._success(_('Updated your settings'), result=updated)


class ConfigAdd(Command):
    """Add a new value to a list (or ordered dict) setting"""
    SYNOPSIS = (None, 'append', 'settings/add', '<section.variable> <value>')
    ORDER = ('Config', 1)
    SPLIT_ARG = False
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_STRICT_VARS = False
    HTTP_POST_VARS = {
        'section.variable': 'value|json-string',
    }
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_CHANGE_CONFIG

    def command(self):
        from mailpile.httpd import BLOCK_HTTPD_LOCK, Idle_HTTPD
        config = self.session.config
        args = list(self.args)
        ops = []

        for var in self.data.keys():
            parts = ('.' in var) and var.split('.') or var.split('/')
            if parts[0] in config.rules:
                ops.append((var, self.data[var][0]))

        if args:
            arg = ' '.join(args)
            if '=' in arg:
                # Backwards compatible with the old 'var = value' syntax.
                var, value = [s.strip() for s in arg.split('=', 1)]
                var = var.replace(': ', '.').replace(':', '.').replace(' ', '')
            else:
                var, value = arg.split(' ', 1)
            ops.append((var, value))

        # Access controls...
        for path, value in ops:
            fb = security.forbid_config_change(config, path)
            if fb:
                return self._error(fb)
            elif path == 'master_key' and config.master_key:
                return self._error(_('I refuse to change the master key!'))

        # We don't have transactions really, but making sure the HTTPD
        # is idle (aside from this request) will definitely help.
        with BLOCK_HTTPD_LOCK, Idle_HTTPD():
            updated = {}
            for path, value in ops:
                value = value.strip()
                if value.startswith('{') or value.startswith('['):
                    value = json.loads(value)
                cfg, var = config.walk(path.strip(), parent=1)
                cfg[var].append(value)
                updated[path] = value

        if updated:
            self._background_save(config=True)

        return self._success(_('Updated your settings'), result=updated)


class ConfigUnset(Command):
    """Reset one or more settings to their defaults"""
    SYNOPSIS = ('U', 'unset', 'settings/unset', '<var>')
    ORDER = ('Config', 2)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
        'var': 'section.variables'
    }
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_CHANGE_CONFIG

    def command(self):
        from mailpile.httpd import BLOCK_HTTPD_LOCK, Idle_HTTPD
        session, config = self.session, self.session.config

        def unset(cfg, key):
            if isinstance(cfg[key], dict):
                if '_any' in cfg[key].rules:
                    for skey in cfg[key].keys():
                        del cfg[key][skey]
                else:
                    for skey in cfg[key].keys():
                        unset(cfg[key], skey)
            elif isinstance(cfg[key], list):
                cfg[key] = []
            else:
                del cfg[key]

        # Access controls...
        vlist = list(self.args) + (self.data.get('var', None) or [])
        # Access controls...
        for v in vlist:
            fb = security.forbid_config_change(config, v)
            if fb:
                return self._error(fb)
            elif v == 'master_key' and config.master_key:
                return self._error(_('I refuse to change the master key!'))

        # We don't have transactions really, but making sure the HTTPD
        # is idle (aside from this request) will definitely help.
        with BLOCK_HTTPD_LOCK, Idle_HTTPD():
            updated = []
            for v in vlist:
                cfg, vn = config.walk(v, parent=True)
                unset(cfg, vn)
                updated.append(v)

        if updated:
            self._background_save(config=True)

        return self._success(_('Reset to default values'), result=updated)


class ConfigPrint(Command):
    """Print one or more settings"""
    SYNOPSIS = ('P', 'print', 'settings', '[-short|-secrets|-flat] <var>')
    ORDER = ('Config', 3)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False

    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'var': 'section.variable',
        'short': 'Set True to omit unchanged values (defaults)',
        'secrets': 'Set True to show passwords and other secrets'
    }
    HTTP_POST_VARS = {
        'user': 'Authenticate as user',
        'pass': 'Authenticate with password'
    }

    def _maybe_all(self, list_all, data, key_types, recurse, sanitize):
        if isinstance(data, (dict, list)) and list_all:
            rv = {}
            for key in data.all_keys():
                if [t for t in data.key_types(key) if t not in key_types]:
                    # Silently omit things that are considered sensitive
                    continue
                rv[key] = data[key]
                if hasattr(rv[key], 'all_keys'):
                    if recurse:
                        rv[key] = self._maybe_all(True, rv[key], key_types,
                                                  recurse, sanitize)
                    else:
                        if 'name' in rv[key]:
                            rv[key] = '{ ..(%s).. }' % rv[key]['name']
                        elif 'description' in rv[key]:
                            rv[key] = '{ ..(%s).. }' % rv[key]['description']
                        elif 'host' in rv[key]:
                            rv[key] = '{ ..(%s).. }' % rv[key]['host']
                        else:
                            rv[key] = '{ ... }'
                elif sanitize and key.lower()[:4] in ('pass', 'secr'):
                    rv[key] = '(SUPPRESSED)'
            return rv
        return data

    def command(self):
        session, config = self.session, self.session.config
        result = {}
        invalid = []

        args = list(self.args)
        recurse = not self.data.get('flat', ['-flat' in args])[0]
        list_all = not self.data.get('short', ['-short' in args])[0]
        sanitize = not self.data.get('secrets', ['-secrets' in args])[0]

        if security.forbid_command(self, security.CC_LIST_PRIVATE_DATA):
            sanitize = True

        # FIXME: Shouldn't we suppress critical variables as well?
        key_types = ['public', 'critical']
        access_denied = False

        if self.data.get('_method') == 'POST':
            if 'pass' in self.data:
                from mailpile.auth import CheckPassword
                password = self.data['pass'][0]
                auth_user = CheckPassword(config,
                                          self.data.get('user', [None])[0],
                                          password)
                if auth_user == 'DEFAULT':
                    key_types += ['key']
                result['_auth_user'] = auth_user
                result['_auth_pass'] = password

        for key in (args + self.data.get('var', [])):
            if key in ('-short', '-flat', '-secrets'):
                continue
            try:
                data = config.walk(key, key_types=key_types)
                result[key] = self._maybe_all(list_all, data, key_types,
                                              recurse, sanitize)
            except AccessError:
                access_denied = True
                invalid.append(key)
            except KeyError:
                invalid.append(key)

        if invalid:
            return self._error(_('Invalid keys'),
                               result=result, info={
                                   'keys': invalid,
                                   'key_types': key_types,
                                   'access_denied': access_denied
                               })
        else:
            return self._success(_('Displayed settings'), result=result)


class ConfigureMailboxes(Command):
    """
    Add one or more mailboxes.

    If not account is specified, the mailbox is only assigned an ID for use
    in the metadata index.

    If an account is specified, the mailbox will be assigned to that account
    and configured for automatic indexing.
    """
    SYNOPSIS = ('A', 'add', 'settings/mailbox',
                '[+<tag>] [--<option>] [account@email] <path/to/mailbox>')
    ORDER = ('Config', 4)
    IS_USER_ACTIVITY = True
    HTTP_CALLABLE = ('GET', 'POST', 'UPDATE')
    HTTP_QUERY_VARS = {
        'path': 'Path to mailbox',
        'profile': 'Profile/account ID or e-mail',
        'recurse': 'y/n: search subdirectories?',
        'apply_tags': 'Mailbox tags',
        'guess_tags': 'Guess mailbox tags',
        'auto_index': 'Account e-mail or ID',
        'local_copy': 'Make local copy of mail'
    }
    COMMAND_SECURITY = security.CC_CHANGE_CONFIG

    MAX_PATHS = 50000

    def _truthy(self, var, default='n'):
        return truthy(self.data.get(var, [default])[0])

    def command(self):
        from mailpile.httpd import BLOCK_HTTPD_LOCK, Idle_HTTPD

        session, config = self.session, self.session.config
        paths = list(self.args)

        # Which tags do we want to apply?
        apply_tags = self.data.get('apply_tags', [])
        atis = [i for i, p in enumerate(paths)
                if p.startswith('+')]
        for ati in atis:
            at = paths.pop(ati)[1:].split(',')
            apply_tags += [config.get_tag_id(a) for a in at]

        # Parse arguments from the web
        paths += self.data.get('path', [])
        account_id = self.data.get('profile', [None])[0]
        recurse = self._truthy('recurse', default='n')

        if self.data.get('_method', 'CLI') == 'POST':
            auto_index = self._truthy('auto_index', default='n')
            local_copy = self._truthy('local_copy', default='n')
            guess_tags = self._truthy('guess_tags', default='n')
        else:
            auto_index = True
            local_copy = None
            guess_tags = None

        # Recursion or other options requested on CLI?
        if self.data.get('_method', 'CLI') == 'CLI':
            while paths and '--recurse' in paths:
                recurse = paths.pop(paths.index('--recurse'))
            while paths and '--local_copy' in paths:
                local_copy = paths.pop(paths.index('--local_copy'))
            while paths and '--guess_tags' in paths:
                guess_tags = paths.pop(paths.index('--guess_tags'))
            while paths and '--no_guess_tags' in paths:
                guess_tags = not paths.pop(paths.index('--guess_tags'))
            while paths and '--no_auto_index' in paths:
                auto_index = not paths.pop(paths.index('--no_auto_index'))

        # Are we linking these mailboxes to a particular account?
        if (not account_id and
                paths and '@' in paths[0] and paths[0][:1] != '/'):
            account_id = paths.pop(0)
        account = account_id and config.vcards.get_vcard(account_id)
        if account_id and (not account or account.kind != 'profile'):
            return self._error(_('Account not found: %s') % account_id)

        # Turn raw paths into FilePath objects
        paths = [FilePath(p) for p in paths]
        # Strip leading slashes of src: paths
        paths = [FilePath(p.raw_fp[1:]) if p.raw_fp.startswith('/src:') else p
                 for p in paths]
        opaths = paths[:]

        # Get a list of existing mailboxes...
        existing = {}
        existing.update(dict((FilePath(p).encoded(), (FilePath(p), _id, src))
                             for _id, p, src in
                             config.get_mailboxes(mail_source_locals=False)))
        existing.update(dict((FilePath(p).encoded(), (FilePath(p), _id, src))
                             for _id, p, src in
                             config.get_mailboxes(mail_source_locals=True)))

        # Figure out which mailboxes the user is asking us to add...
        adding = []
        configure = []
        has_source = False
        try:
            while paths:
                fn = paths.pop(0)
                fn_display = fn.display()
                einfo = existing.get(fn.encoded())
                if fn.raw_fp.startswith("src:"):
                    if einfo:
                        configure.append((fn, einfo))
                    else:
                        adding.append(fn)
                    has_source = True
                elif einfo:
                    if einfo[2]:
                        has_source = True
                    configure.append((fn, einfo))
                    if not account:
                        session.ui.warning('Already in the pile: %s'
                                           % fn_display)
                else:
                    if IsMailbox(fn.raw_fp, config):
                        adding.append(fn)
                        added = True
                        blacklist = ('.', '..', 'new', 'cur', 'tmp')
                    else:
                        added = False
                        blacklist = ('.', '..')

                    if recurse and vfs.exists(fn) and vfs.isdir(fn):
                        session.ui.mark('Scanning %s for mailboxes' % fn_display)
                        try:
                            for f in [f for f in vfs.listdir(fn)
                                      if not f.raw_fp in blacklist]:
                                paths.append(vfs.path_join(fn, f))
                                if len(paths) > self.MAX_PATHS:
                                    return self._error(_('Too many files'))
                        except OSError:
                            if fn in opaths:
                                return self._error(_('Failed to read: %s'
                                                     ) % fn_display)
                    elif fn in opaths and not added:
                        return self._error(_('Not a mailbox: %s') % fn_display)

        except KeyboardInterrupt:
            return self._error(_('User aborted'))

        if local_copy is None:
            local_copy = has_source  # No source; probably already local

        if self.data.get('_method', 'CLI') == 'GET':
            if not apply_tags and len(opaths) == 1:
                apply_tags = list(config.guess_tags(opaths[0].raw_fp))
            return self._success(_('Add and configure mailboxes'), result={
                'paths': opaths,
                'profile': account_id,
                'apply_tags': apply_tags,
                'auto_index': auto_index,
                'local_copy': local_copy,
                'recurse': recurse,
                'has_source': has_source,
                'adding': adding,
                'configure': configure
            })

        added = {}
        configured = {}
        # We don't have transactions really, but making sure the HTTPD
        # is idle (aside from this request) will definitely help.
        with BLOCK_HTTPD_LOCK, Idle_HTTPD():
            for arg in adding:
                mbox_id = config.sys.mailbox.append(arg)
                added[mbox_id] = arg
                if account or arg.raw_fp.startswith('src:'):
                    configure.append((arg, (arg, mbox_id, None)))

            def _get_source(path, einfo):
                if einfo and einfo[2]:
                    return einfo[2]
                raw_path = path.raw_fp
                if raw_path.split(':')[0] == 'src':
                    src_id = raw_path.split(':')[1].split('/')[0]
                    return config.sources[src_id]
                return account.get_source_by_proto('local', create=True)

            for path, einfo in configure:
                mbox_id = einfo[1]
                source_cfg = _get_source(path, einfo)
                source_obj = config.get_mail_source(source_cfg._key)
                policy = 'read' if auto_index else 'ignore'
                source_obj.take_over_mailbox(mbox_id,
                                             policy=policy,
                                             create_local=local_copy,
                                             guess_tags=guess_tags,
                                             apply_tags=apply_tags,
                                             save=False)
                configured[mbox_id] = path

        if added or configured:
            self._background_save(config=True)
            return self._success(_('Configured %d mailboxes'
                                   ) % max(len(added), len(configured)),
                                 result={'added': added,
                                         'configured': configured})
        else:
            return self._success(_('Nothing was added'))


###############################################################################

class Output(Command):
    """Choose format for command results."""
    SYNOPSIS = (None, 'output', None, '[json|text|html|<template>.html|...]')
    ORDER = ('Internals', 7)
    CONFIG_REQUIRED = False
    HTTP_STRICT_VARS = False
    HTTP_AUTH_REQUIRED = False
    IS_USER_ACTIVITY = False
    LOG_NOTHING = True

    def etag_data(self):
        return self.get_render_mode()

    def max_age(self):
        return 364 * 24 * 3600  # A long time!

    def get_render_mode(self):
        return self.args and self.args[0] or self.session.ui.render_mode

    def command(self):
        m = self.session.ui.render_mode = self.get_render_mode()
        return self._success(_('Set output mode to: %s') % m,
                             result={'output': m})


class Pipe(Command):
    """Pipe a command to a shell command, file or e-mail"""
    SYNOPSIS = (None, 'pipe', None,
                "[e@mail.com|command|>filename] -- [<cmd> [args ... ]]")
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_ACCESS_FILESYSTEM

    def command(self):
        if '--' in self.args:
            dashdash = self.args.index('--')
            target = self.args[0:dashdash]
            command, args = self.args[dashdash+1], self.args[dashdash+2:]
        else:
            target, command, args = [self.args[0]], self.args[1], self.args[2:]

        output = ''
        result = None
        old_ui = self.session.ui
        try:
            from mailpile.ui import CapturingUserInteraction as CUI
            self.session.ui = capture = CUI(self.session.config)
            capture.render_mode = old_ui.render_mode
            result = Action(self.session, command, ' '.join(args))
            capture.display_result(result)
            output = capture.captured
        finally:
            self.session.ui = old_ui

        if target[0].startswith('>'):
            t = ' '.join(target)
            if t[0] == '>':
                t = t[1:]
            with vfs.open(t.strip(), 'w') as fd:
                fd.write(output.encode('utf-8'))

        elif '@' in target[0]:
            from mailpile.plugins.compose import Compose
            body = 'Result as %s:\n%s' % (capture.render_mode, output)
            if capture.render_mode != 'json' and output[0] not in ('{', '['):
                body += '\n\nResult as JSON:\n%s' % result.as_json()
            composer = Compose(self.session, data={
                'to': target,
                'subject': ['Mailpile: %s %s' % (command, ' '.join(args))],
                'body': [body]
            })
            return self._success('Mailing output to %s' % ', '.join(target),
                                 result=composer.run())
        else:
            try:
                self.session.ui.block()
                MakePopenUnsafe()
                kid = subprocess.Popen(target, shell=True, stdin=PIPE)
                rv = kid.communicate(input=output.encode('utf-8'))
            finally:
                self.session.ui.unblock()
                MakePopenSafe()
                kid.wait()
            if kid.returncode != 0:
                return self._error('Error piping to %s' % (target, ),
                                   info={'stderr': rv[1], 'stdout': rv[0]})

        return self._success('Wrote %d bytes to %s'
                             % (len(output), ' '.join(target)))


class Quit(Command):
    """Exit Mailpile, normal shutdown"""
    SYNOPSIS = ("q", "quit", "quitquitquit", '[restart]')
    ABOUT = ("Quit mailpile")
    ORDER = ("Internals", 2)
    CONFIG_REQUIRED = False
    RAISES = (KeyboardInterrupt,)
    HTTP_CALLABLE = ('POST',)
    HTTP_POST_VARS = {
        'restart': 'Set to restart instead of shutting down'
    }
    COMMAND_SECURITY = security.CC_QUIT

    def command(self):
        if 'restart' in self.args or self.data.get('restart', [False])[0]:
            mailpile.util.QUITTING = 'restart'
        else:
            mailpile.util.QUITTING = mailpile.util.QUITTING or True

        from mailpile.plugins.gui import UpdateGUIState
        UpdateGUIState()

        self._background_save(index=True, config='!FORCE', wait=True)
        if self.session.config.http_worker:
            self.session.config.http_worker.quit()

        thread.interrupt_main()
        return self._success(_('Shutting down...'))


class IdleQuit(Command):
    """Shut down Mailpile if it has been idle for a while"""
    SYNOPSIS = (None, "idlequit", None, "[<timeout>]")
    ORDER = ("Internals", 2)
    CONFIG_REQUIRED = False

    def check(self):
        idle = time.time() - max(self.started, mailpile.util.LAST_USER_ACTIVITY)
        if idle > self.timeout:
            Quit(self.session, 'quit').run()

    def command(self):
        config = self.session.config
        self.timeout = int(self.args[0]) if self.args else 600
        self.started = time.time()
        config.cron_worker.add_task('idlequit', self.timeout / 5, self.check)
        return self._success(
            _('Will shut down if idle for over %s seconds') % self.timeout,
            {'timeout': self.timeout})


class TrustingQQQ(Command):
    """Allow anybody to quit the app"""
    SYNOPSIS = (None, "trustingqqq", None, None)
    COMMAND_SECURITY = security.CC_QUIT

    def command(self):
        # FIXME: This is a hack to allow Windows deployments to shut
        #        down cleanly. Eventually this will take an argument
        #        specifying a random token that the launcher chooses.

        Quit.HTTP_AUTH_REQUIRED = False
        return self._success('OK, anybody can quit!')


class Abort(Command):
    """Force exit Mailpile (kills threads)"""
    SYNOPSIS = (None, "quit/abort", "abortabortabort", None)
    ABOUT = ("Quit mailpile")
    ORDER = ("Internals", 2)
    CONFIG_REQUIRED = False
    HTTP_QUERY_VARS = {
        'no_save': 'Do not try to save state'
    }
    COMMAND_SECURITY = security.CC_QUIT

    def command(self):
        mailpile.util.QUITTING = mailpile.util.QUITTING or True
        if 'no_save' not in self.data:
            self._background_save(index=True, config=True, wait=True,
                                  wait_callback=lambda: os._exit(1))
        else:
            os._exit(1)

        return self._success(_('Shutting down...'))


class Help(Command):
    """Print help on Mailpile or individual commands."""
    SYNOPSIS = ('h', 'help', 'help', '[<command-group>]')
    ABOUT = ('This is Mailpile!')
    ORDER = ('Config', 9)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = True

    class CommandResult(Command.CommandResult):

        def splash_as_text(self):
            text = [
                self.result['splash']
            ]
            if os.getenv('DISPLAY'):
                # Launching the web browser often prints junk, move past it.
                text[:0] = ['=' * 77]

            if self.result['http_url']:
                text.append(_('The Web interface address is: %s'
                              ) % self.result['http_url'])
            else:
                text.append(_('The Web interface is disabled,'
                              ' type `www` to turn it on.'))

            text.append('')
            b = '   * '
            if self.result['interactive']:
                text.append(b + _('Type `help` for instructions or `quit` '
                                  'to quit.'))
                text.append(b + _('Long running operations can be aborted '
                                  'by pressing: <CTRL-C>'))
            if self.result['login_cmd'] and self.result['interactive']:
                text.append(b + _('You can log in using the `%s` command.'
                                  ) % self.result['login_cmd'])
            if self.result['in_browser']:
                text.append(b + _('Check your web browser!'))

            return '\n'.join(text)

        def variables_as_text(self):
            text = []
            for group in self.result['variables']:
                text.append('%s (%s.*)' % (group['name'], group['category']))
                for var in group['variables']:
                    sep = ('=' in var['type']) and ': ' or ' = '
                    text.append(('  %-35s %s'
                                 ) % (('%s%s<%s>'
                                       ) % (var['var'], sep,
                                            var['type'].replace('=', '> = <')),
                                      var['desc']))
                text.append('')
            return '\n'.join(text)

        def commands_as_text(self):
            text = [_('Commands:')]
            last_rank = None
            cmds = self.result['commands']
            width = self.result.get('width', 8)
            ckeys = cmds.keys()
            ckeys.sort(key=lambda k: (cmds[k][3], cmds[k][0]))
            arg_width = min(50, max(14, self.session.ui.term.max_width()-70))
            for c in ckeys:
                cmd, args, explanation, rank = cmds[c]
                if not rank or not cmd:
                    continue
                if last_rank and int(rank / 10) != last_rank:
                    text.append('')
                last_rank = int(rank / 10)
                if c[0] == '_':
                    c = '  '
                else:
                    c = '%s|' % c[0]
                fmt = '  %%s%%-%d.%ds' % (width, width)
                if explanation:
                    if len(args or '') <= arg_width:
                        fmt += ' %%-%d.%ds %%s' % (arg_width, arg_width)
                    else:
                        pad = len(c) + width + 3 + arg_width
                        fmt += ' %%s\n%s %%s' % (' ' * pad)
                else:
                    explanation = ''
                    fmt += ' %s %s '
                text.append(fmt % (c, cmd.replace('=', ''),
                                   args and ('%s' % (args, )) or '',
                                   (explanation.splitlines() or [''])[0]))
            if self.result.get('tags'):
                text.extend([
                    '',
                    _('Tags:  (use a tag as a command to display tagged '
                      'messages)'),
                    '',
                    self.result['tags'].as_text()
                ])
            return '\n'.join(text)

        def as_text(self):
            if not self.result:
                return _('Error')
            return ''.join([
                ('splash' in self.result) and self.splash_as_text() or '',
                (('variables' in self.result) and self.variables_as_text()
                 or ''),
                ('commands' in self.result) and self.commands_as_text() or '',
            ])

    def command(self):
        config = self.session.config
        self.session.ui.reset_marks(quiet=True)
        if self.args:
            command = self.args[0]
            for cls in COMMANDS:
                name = cls.SYNOPSIS[1] or cls.SYNOPSIS[2]
                width = len(name or '')
                if name and command in cls.SYNOPSIS[1:3]:
                    order = 1
                    cmd_list = {'_main': (name, cls.SYNOPSIS[3],
                                          cls.__doc__, order)}
                    subs = [c for c in COMMANDS
                            if (c.SYNOPSIS[1] or c.SYNOPSIS[2] or ''
                                ).startswith(name + '/')]
                    for scls in sorted(subs):
                        sc, scmd, surl, ssynopsis = scls.SYNOPSIS[:4]
                        order += 1
                        cmd_list['_%s' % scmd] = (scmd, ssynopsis,
                                                  scls.__doc__, order)
                        width = max(len(scmd or surl), width)
                    return self._success(_('Displayed help'), result={
                        'pre': cls.__doc__,
                        'commands': cmd_list,
                        'width': width
                    })
            return self._error(_('Unknown command'))

        else:
            cmd_list = {}
            count = 0
            for grp in COMMAND_GROUPS:
                count += 10
                for cls in COMMANDS:
                    if cls.CONFIG_REQUIRED and not config.loaded_config:
                        continue
                    c, name, url, synopsis = cls.SYNOPSIS[:4]
                    if cls.ORDER[0] == grp and '/' not in (name or ''):
                        cmd_list[c or '_%s' % name] = (name, synopsis,
                                                       cls.__doc__,
                                                       count + cls.ORDER[1])
            if config.loaded_config:
                tags = GetCommand('tags')(self.session).run(display="priority")
            else:
                tags = {}
            try:
                index = self._idx()
            except IOError:
                index = None
            return self._success(_('Displayed help'), result={
                'commands': cmd_list,
                'tags': tags,
                'index': index
            })

    def _starting(self):
        pass

    def _finishing(self, rv, *args, **kwargs):
        return self.CommandResult(self, self.session, self.name,
                                  self.__doc__, rv,
                                  self.status, self.message)


class HelpVars(Help):
    """Print help on Mailpile variables"""
    SYNOPSIS = (None, 'help/variables', 'help/variables', None)
    ABOUT = ('The available mailpile variables')
    ORDER = ('Config', 9)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = True

    def command(self):
        config = self.session.config.rules
        result = []
        categories = ["sys", "prefs"]
        for cat in categories:
            variables = []
            what = config[cat]
            if isinstance(what[2], dict):
                for ii, i in what[2].iteritems():
                    stype = (
                        _('(subsection)') if isinstance(i[1], dict) else
                        '|'.join(i[1]) if isinstance(i[1], (list, tuple)) else
                         str(i[1]))
                    if '<type' in stype:
                        stype = stype.replace('<type ', '')[1:-2]
                    variables.append({
                        'var': ii,
                        'type': stype,
                        'desc': i[0]
                    })
            variables.sort(key=lambda k: k['var'])
            result.append({
                'category': cat,
                'name': config[cat][0],
                'variables': variables
            })
        result.sort(key=lambda k: config[k['category']][0])
        return self._success(_('Displayed variables'),
                             result={'variables': result})


class HelpSplash(Help):
    """Print Mailpile splash screen"""
    SYNOPSIS = (None, 'help/splash', 'help/splash', None)
    ORDER = ('Config', 9)
    CONFIG_REQUIRED = False

    def command(self, interactive=True):
        from mailpile.auth import Authenticate
        http_worker = self.session.config.http_worker

        in_browser = False
        if http_worker:
            http_url = 'http://%s:%s%s/' % http_worker.httpd.sspec
            if ((sys.platform[:3] in ('dar', 'win') or os.getenv('DISPLAY'))
                    and self.session.config.prefs.open_in_browser):
                if BrowseOrLaunch.Browse(http_worker.httpd.sspec):
                    in_browser = True
                    time.sleep(2)
        else:
            http_url = ''

        return self._success(_('Displayed welcome message'), result={
            'splash': self.ABOUT,
            'http_url': http_url,
            'in_browser': in_browser,
            'login_cmd': (Authenticate.SYNOPSIS[1]
                          if not self.session.config.loaded_config else ''),
            'interactive': interactive
        })



_plugins.register_commands(
    Load, Optimize, Rescan, DeleteMessages,
    BrowseOrLaunch, RunWWW, ProgramStatus, CronStatus, HealthCheck,
    GpgCommand, ListDir, ChangeDir, CatFile, WritePID, Cleanup,
    ConfigPrint, ConfigSet, ConfigAdd, ConfigUnset, ConfigureMailboxes,
    ListLanguages, RenderPage, Output, Pipe,
    Help, HelpVars, HelpSplash, Quit, IdleQuit, TrustingQQQ, Abort
)
