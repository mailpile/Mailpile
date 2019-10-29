# The basic Mailpile command framework.
#
# TODO: Merge with plugins/ the division is obsolete and artificial.
#
import json
import os
import re
import shlex
import traceback
import time

import mailpile.util
import mailpile.security as security
from mailpile.crypto.gpgi import GnuPG
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *
from mailpile.vfs import vfs


# Commands starting with _ don't get single-letter shortcodes...
COMMANDS = []
COMMAND_GROUPS = ['Internals', 'Config', 'Searching', 'Tagging', 'Composing']


class Command(object):
    """Generic command object all others inherit from"""
    SYNOPSIS = (None,     # CLI shortcode, e.g. A:
                None,     # CLI shortname, e.g. add
                None,     # API endpoint, e.g. sys/addmailbox
                None)     # Positional argument list
    SYNOPSIS_ARGS = None  # New-style positional argument list
    API_VERSION = None
    UI_CONTEXT = None
    IS_USER_ACTIVITY = False
    IS_HANGING_ACTIVITY = False
    IS_INTERACTIVE = False
    CONFIG_REQUIRED = True

    COMMAND_CACHE_TTL = 0   # < 1 = Not cached
    CHANGES_SESSION_CONTEXT = False

    FAILURE = 'Failed: %(name)s %(args)s'
    ORDER = (None, 0)
    SPLIT_ARG = True  # Uses shlex by default
    RAISES = (UsageError, UrlRedirectException)
    WITH_CONTEXT = ()
    COMMAND_SECURITY = None

    # Event logging settings
    LOG_NOTHING = False
    LOG_ARGUMENTS = True
    LOG_PROGRESS = False
    LOG_STARTING = '%(name)s: Starting'
    LOG_FINISHED = '%(name)s: %(message)s'

    # HTTP settings (note: security!)
    HTTP_CALLABLE = ('GET', )
    HTTP_POST_VARS = {}
    HTTP_QUERY_VARS = {}
    HTTP_BANNED_VARS = {}
    HTTP_STRICT_VARS = True
    HTTP_AUTH_REQUIRED = True

    class CommandResult:
        def __init__(self, command_obj, session,
                     command_name, doc, result, status, message,
                     template_id=None, kwargs={}, error_info={}):
            self.session = session
            self.command_obj = command_obj
            self.command_name = command_name
            self.kwargs = {}
            self.kwargs.update(kwargs)
            self.template_id = template_id
            self.doc = doc
            self.result = result
            self.status = status
            self.error_info = {}
            self.error_info.update(error_info)
            self.message = message
            self.rendered = {}
            self.renderers = {
                'json': self.as_json,
                'html': self.as_html,
                'text': self.as_text,
                'css': self.as_css,
                'csv': self.as_csv,
                'rss': self.as_rss,
                'xml': self.as_xml,
                'txt': self.as_txt,
                'js': self.as_js
            }

        def __nonzero__(self):
            return (self.result and True or False)

        def as_(self, what, *args, **kwargs):
            if args or kwargs:
                # Args render things un-cacheable.
                return self.renderers.get(what)(*args, **kwargs)

            if what not in self.rendered:
                self.rendered[what] = self.renderers.get(what, self.as_text)()
            return self.rendered[what]

        def as_text(self):
            if isinstance(self.result, bool):
                happy = '%s: %s' % (self.result and _('OK') or _('Failed'),
                                    self.message or self.doc)
                if not self.result and self.error_info:
                    return '%s\n%s' % (happy,
                        json.dumps(self.error_info, indent=4,
                                   default=mailpile.util.json_helper))
                else:
                    return happy
            elif isinstance(self.result, (dict, list, tuple)):
                return json.dumps(self.result, indent=4, sort_keys=True,
                    default=mailpile.util.json_helper)
            else:
                return unicode(self.result)

        __str__ = lambda self: self.as_text()

        __unicode__ = lambda self: self.as_text()

        def as_dict(self):
            from mailpile.urlmap import UrlMap
            um = UrlMap(self.session)
            rv = {
                'command': self.command_name,
                'state': {
                    'command_url': um.ui_url(self.command_obj),
                    'context_url': um.context_url(self.command_obj),
                    'query_args': self.command_obj.state_as_query_args(),
                    'cache_id': self.command_obj.cache_id(),
                    'context': self.command_obj.context or ''
                },
                'status': self.status,
                'message': self.message,
                'result': self.result,
                'event_id': self.command_obj.event.event_id,
                'elapsed': '%.3f' % self.session.ui.time_elapsed,
            }
            csrf_token = self.session.ui.html_variables.get('csrf_token')
            if csrf_token:
                rv['state']['csrf_token'] = csrf_token
            if self.error_info:
                rv['error'] = self.error_info
            for ui_key in [k for k in self.command_obj.data.keys()
                           if k.startswith('ui_')]:
                rv[ui_key] = self.command_obj.data[ui_key][0]
            ev = self.command_obj.event
            if ev and ev.data.get('password_needed'):
                rv['password_needed'] = ev.private_data['password_needed']
            return rv

        def as_csv(self, template=None, result=None):
            result = self.result if (result is None) else result
            if (isinstance(result, (list, tuple)) and
                    (not result or isinstance(result[0], (list, tuple)))):
                import csv, StringIO
                output = StringIO.StringIO()
                writer = csv.writer(output, dialect='excel')
                for row in result:
                    writer.writerow([unicode(r).encode('utf-8') for r in row])
                return output.getvalue().decode('utf-8')
            else:
                return ''

        def as_json(self):
            return self.session.ui.render_json(self.as_dict())

        def as_html(self, template=None):
            return self.as_template('html', template)

        def as_js(self, template=None):
            return self.as_template('js', template)

        def as_css(self, template=None):
            return self.as_template('css', template)

        def as_rss(self, template=None):
            return self.as_template('rss', template)

        def as_xml(self, template=None):
            return self.as_template('xml', template)

        def as_txt(self, template=None):
            return self.as_template('txt', template)

        def as_template(self, ttype,
                        mode=None, wrap_in_json=False, template=None):
            cache_id = ''.join(('j' if wrap_in_json else '', ttype,
                                '/' if template else '', template or '',
                                ':', mode or 'full'))
            if cache_id in self.rendered:
                return self.rendered[cache_id]
            tpath = self.command_obj.template_path(
                ttype, template_id=self.template_id, template=template)

            data = self.as_dict()
            data['title'] = self.message
            data['render_mode'] = mode or 'full'
            data['render_template'] = template or 'index'

            rendering = self.session.ui.render_web(self.session.config,
                                                   [tpath], data)
            if wrap_in_json:
                data['result'] = rendering
                self.rendered[cache_id] = self.session.ui.render_json(data)
            else:
                self.rendered[cache_id] = rendering

            return self.rendered[cache_id]

    def __init__(self, session, name=None, arg=None, data=None, async=False):
        self.session = session
        self.context = None
        self.name = self.SYNOPSIS[1] or self.SYNOPSIS[2] or name
        self.data = data or {}
        self.status = 'unknown'
        self.message = name
        self.error_info = {}
        self.result = None
        self.run_async = async
        if type(arg) in (type(list()), type(tuple())):
            self.args = tuple(arg)
        elif arg:
            if self.SPLIT_ARG is True:
                try:
                    self.args = tuple([a.decode('utf-8') for a in
                                       shlex.split(arg.encode('utf-8'))])
                except (ValueError, UnicodeEncodeError, UnicodeDecodeError):
                    raise UsageError(_('Failed to parse arguments'))
            else:
                self.args = (arg, )
        else:
            self.args = tuple([])
        if 'arg' in self.data:
            self.args = tuple(list(self.args) + self.data['arg'])
        self._create_event()

    def state_as_query_args(self):
        args = {}
        if self.args:
            args['arg'] = self._sloppy_copy(self.args)
        args.update(self._sloppy_copy(self.data))
        return args

    def cache_id(self, sqa=None):
        if self.COMMAND_CACHE_TTL < 1:
            return ''
        from mailpile.urlmap import UrlMap
        args = sorted(list((sqa or self.state_as_query_args()).iteritems()))
        args += '/%d' % self.session.ui.term.max_width
        # The replace() stuff makes these usable as CSS class IDs
        return ('%s-%s' % (UrlMap(self.session).ui_url(self),
                           md5_hex(str(args))
                           )).replace('/', '-').replace('.', '-')

    def cache_requirements(self, result):
        raise NotImplementedError('Cachable commands should override this, '
                                  'returning a set() of requirements.')

    def cache_result(self, result):
        if self.COMMAND_CACHE_TTL > 0:
            try:
                cache_id = self.cache_id()
                if cache_id:
                    self.session.config.command_cache.cache_result(
                        cache_id,
                        time.time() + self.COMMAND_CACHE_TTL,
                        self.cache_requirements(result),
                        self,
                        result)
                    self.session.ui.mark(_('Cached result as %s') % cache_id)
            except (ValueError, KeyError, TypeError, AttributeError):
                self._ignore_exception()

    def template_path(self, ttype, template_id=None, template=None):
        path_parts = (template_id or self.SYNOPSIS[2] or 'command').split('/')
        if template in (None, ttype, 'as.' + ttype):
            path_parts.append('index')
        else:
            # Security: The template request may come from the URL, so we
            #           sanitize it very aggressively before heading off
            #           to the filesystem.
            clean_tpl = CleanText(template.replace('.%s' % ttype, ''),
                                  banned=(CleanText.FS +
                                          CleanText.WHITESPACE))
            path_parts.append(clean_tpl.clean)
        path_parts[-1] += '.' + ttype
        return os.path.join(*path_parts)

    def _gnupg(self, **kwargs):
        return GnuPG(self.session.config, event=self.event, **kwargs)

    def _config(self):
        session, config = self.session, self.session.config
        if not config.loaded_config:
            config.load(session)
            parent = session
            config.prepare_workers(session, daemons=self.IS_INTERACTIVE)
        if self.IS_INTERACTIVE and not config.daemons_started():
            config.prepare_workers(session, daemons=True)
        return config

    def _idx(self, reset=False, wait=True, wait_all=True, quiet=False):
        session, config = self.session, self._config()

        if not reset and config.index:
            return config.index

        def __do_load2():
            config.vcards.load_vcards(session)
            if not wait_all:
                session.ui.report_marks(quiet=quiet)

        def __do_load1():
            with config.interruptable_wait_for_lock():
                if reset:
                    config.index = None
                    session.results = []
                    session.searched = []
                    session.displayed = None
                idx = config.get_index(session)
                if wait_all:
                    __do_load2()
                if not wait:
                    session.ui.report_marks(quiet=quiet)
                return idx

        if wait:
            rv = __do_load1()
            session.ui.reset_marks(quiet=quiet)
        else:
            config.save_worker.add_task(session, 'Load', __do_load1)
            rv = None

        if not wait_all:
            config.save_worker.add_task(session, 'Load2', __do_load2)

        return rv

    def _background_save(self,
                         everything=False, config=False,
                         index=False, index_full=False,
                         wait=False, wait_callback=None):
        session, cfg = self.session, self.session.config
        aut = cfg.save_worker.add_unique_task
        if everything or config:
            aut(session,
                'Save config',
                lambda: cfg.save(session, force=(config == '!FORCE')),
                first=True)
        if cfg.index:
            cfg.flush_mbox_cache(session, clear=False, wait=wait)
            if index_full:
                aut(session, 'Save index',
                    lambda: self._idx().save(session),
                    first=True)
            elif everything or index:
                aut(session, 'Save index changes',
                    lambda: self._idx().save_changes(session),
                    first=True)
        if wait:
            wait_callback = wait_callback or (lambda: True)
            cfg.save_worker.do(session, 'Waiting', wait_callback)

    def _choose_messages(self, words, allow_ephemeral=False):
        msg_ids = set()
        all_words = []
        for word in words:
            all_words.extend(word.split(','))
        for what in all_words:
            if what.lower() == 'these':
                if self.session.displayed:
                    b = self.session.displayed['stats']['start'] - 1
                    c = self.session.displayed['stats']['count']
                    msg_ids |= set(self.session.results[b:b + c])
                else:
                    self.session.ui.warning(_('No results to choose from!'))
            elif what.lower() in ('all', '!all', '=!all'):
                if self.session.results:
                    msg_ids |= set(self.session.results)
                else:
                    self.session.ui.warning(_('No results to choose from!'))
            elif what.startswith('='):
                try:
                    msg_id = int(what.replace('=', ''), 36)
                    if msg_id >= 0 and msg_id < len(self._idx().INDEX):
                        msg_ids.add(msg_id)
                    else:
                        self.session.ui.warning((_('No such ID: %s')
                                                 ) % (what[1:], ))
                except ValueError:
                    if allow_ephemeral and '-' in what:
                        msg_ids.add(what[1:])
                    else:
                        self.session.ui.warning(_('What message is %s?'
                                                  ) % (what, ))
            elif '-' in what:
                try:
                    b, e = what.split('-')
                    msg_ids |= set(self.session.results[int(b) - 1:int(e)])
                except (ValueError, KeyError, IndexError, TypeError):
                    self.session.ui.warning(_('What message is %s?'
                                              ) % (what, ))
            else:
                try:
                    msg_ids.add(self.session.results[int(what) - 1])
                except (ValueError, KeyError, IndexError, TypeError):
                    self.session.ui.warning(_('What message is %s?'
                                              ) % (what, ))
        return msg_ids

    def _error(self, message, info=None, result=None):
        self.status = 'error'
        self.message = message

        ui_message = _('%s error: %s') % (self.name, message)
        if info:
            self.error_info.update(info)
            details = ' '.join(['%s=%s' % (k, info[k]) for k in info])
            ui_message += ' (%s)' % details
        self.session.ui.mark(self.name)
        self.session.ui.error(ui_message)

        if result:
            return self.view(result)
        else:
            return False

    def _success(self, message, result=True):
        self.status = 'success'
        self.message = message

        ui_message = '%s: %s' % (self.name, message)
        self.session.ui.mark(ui_message)

        return self.view(result)

    def _read_file_or_data(self, fn):
        if fn in self.data:
            return self.data[fn]
        else:
            return vfs.open(fn, 'rb').read()

    def _ignore_exception(self):
        self.session.ui.debug(traceback.format_exc())

    def _serialize(self, name, function):
        return function()

    def _background(self, name, function):
        session, config = self.session, self.session.config
        return config.scan_worker.add_task(session, name, function)

    def _update_event_state(self, state, log=False):
        self.event.flags = state
        self.event.data['elapsed'] = int(1000 * (time.time()-self._start_time))

        if (log or self.LOG_PROGRESS) and not self.LOG_NOTHING:
            self.event.data['ui'] = str(self.session.ui.__class__.__name__)
            self.event.data['output'] = self.session.ui.render_mode
            if self.session.config.event_log:
                self.session.config.event_log.log_event(self.event)

    def _starting(self):
        self._start_time = time.time()
        self._update_event_state(Event.RUNNING)
        if self.name:
            self.session.ui.start_command(self.name, self.args, self.data)

    def _fmt_msg(self, message):
        return message % {'name': self.name,
                          'status': self.status or '',
                          'message': self.message or ''}

    def _sloppy_copy(self, data, name=None):
        if name and (name[:4] in ('pass', 'csrf') or
                     'password' in name or
                     'passphrase' in name):
            data = '(SUPPRESSED)'
        def copy_value(v):
            try:
                unicode(v).encode('utf-8')
                return unicode(v)[:1024]
            except (UnicodeEncodeError, UnicodeDecodeError):
                return '(BINARY DATA)'
        if isinstance(data, (list, tuple)):
            return [self._sloppy_copy(i, name=name) for i in data]
        elif isinstance(data, dict):
            return dict((k, self._sloppy_copy(v, name=k))
                        for k, v in data.iteritems())
        else:
            return copy_value(data)

    def _create_event(self):
        private_data = {}
        if self.LOG_ARGUMENTS:
            if self.data:
                private_data['data'] = self._sloppy_copy(self.data)
            if self.args:
                private_data['args'] = self._sloppy_copy(self.args)

        self.event = self._make_command_event(private_data)

    def _make_command_event(self, private_data):
        return Event(source=self,
                     message=self._fmt_msg(self.LOG_STARTING),
                     flags=Event.INCOMPLETE,
                     data={},
                     private_data=private_data)

    def _finishing(self, rv, just_cleanup=False):
        if just_cleanup:
            self._update_finished_event()
            return rv

        if not self.context:
            self.context = self.session.get_context(
                update=self.CHANGES_SESSION_CONTEXT)

        self.session.ui.mark(_('Generating result'))
        result = self.CommandResult(self, self.session, self.name,
                                    self.__doc__,
                                    rv, self.status, self.message,
                                    error_info=self.error_info)
        self.cache_result(result)

        if not self.run_async:
            self._update_finished_event()
        self.session.last_event_id = self.event.event_id
        return result

    def _update_finished_event(self):
        # Update the event!
        if self.message:
            self.event.message = self.message
        if self.error_info:
            self.event.private_data['error_info'] = self.error_info
        self.event.message = self._fmt_msg(self.LOG_FINISHED)
        self._update_event_state(Event.COMPLETE, log=True)

        self.session.ui.mark(self.event.message)
        self.session.ui.report_marks(
            details=('timing' in self.session.config.sys.debug))
        if self.name:
            self.session.ui.finish_command(self.name)

    def _run_sync(self, enable_cache, *args, **kwargs):
        try:
            thread_context_push(command=self,
                                event=self.event,
                                session=self.session)
            self._starting()
            self._run_args = args
            self._run_kwargs = kwargs

            if (self.COMMAND_CACHE_TTL > 0 and
                   'http' not in self.session.config.sys.debug and
                   enable_cache):
                cid = self.cache_id()
                try:
                    rv = self.session.config.command_cache.get_result(cid)
                    rv.session.ui = self.session.ui
                    if self.CHANGES_SESSION_CONTEXT:
                        self.session.copy(rv.session)
                    self.session.ui.mark(_('Using pre-cached result object %s') % cid)
                    self._finishing(True, just_cleanup=True)
                    return rv
                except:
                    pass

            def command(self, *args, **kwargs):
                if self.CONFIG_REQUIRED:
                    if not self.session.config.loaded_config:
                        return self._error(_('Please log in'))
                    if mailpile.util.QUITTING:
                        return self._error(_('Shutting down'))
                return self.command(*args, **kwargs)

            return self._finishing(command(self, *args, **kwargs))
        except self.RAISES:
            self.status = 'success'
            self._finishing(True, just_cleanup=True)
            raise
        except:
            self._ignore_exception()
            self._error(self.FAILURE % {'name': self.name,
                                        'args': ' '.join(self.args)})
            return self._finishing(False)
        finally:
            thread_context_pop()

    def _run(self, *args, **kwargs):
        if self.run_async:
            def streetcar():
                try:
                    with MultiContext(self.WITH_CONTEXT):
                        rv = self._run_sync(True, *args, **kwargs).as_dict()
                        self.event.private_data.update(rv)
                        self._update_finished_event()
                except:
                    traceback.print_exc()

            self._starting()
            self._update_event_state(self.event.RUNNING, log=True)
            result = Command.CommandResult(self, self.session, self.name,
                                           self.__doc__,
                                           {"resultid": self.event.event_id},
                                           "success",
                                           "Running in background")

            self.session.config.scan_worker.add_task(self.session, self.name,
                                                     streetcar, first=True)
            return result

        else:
            return self._run_sync(True, *args, **kwargs)

    def _maybe_trigger_cache_refresh(self):
        if self.data.get('_method') == 'POST':
            def refresher():
                self.session.config.command_cache.refresh(
                    event_log=self.session.config.event_log)
            self.session.config.scan_worker.add_unique_task(
                self.session, 'post-refresh', refresher, first=True)

    def record_user_activity(self):
        mailpile.util.LAST_USER_ACTIVITY = time.time()

    def run(self, *args, **kwargs):
        if self.COMMAND_SECURITY is not None:
            forbidden = security.forbid_command(self)
            if forbidden:
                return self._error(forbidden)

        with MultiContext(self.WITH_CONTEXT):
            if self.IS_USER_ACTIVITY:
                try:
                    self.record_user_activity()
                    mailpile.util.LIVE_USER_ACTIVITIES += 1
                    rv = self._run(*args, **kwargs)
                    self._maybe_trigger_cache_refresh()
                    return rv
                finally:
                    mailpile.util.LIVE_USER_ACTIVITIES -= 1
            else:
                rv = self._run(*args, **kwargs)
                self._maybe_trigger_cache_refresh()
                return rv

    def refresh(self):
        self._create_event()
        return self._run_sync(False, *self._run_args, **self._run_kwargs)

    def command(self):
        return None

    def etag_data(self):
        return []

    def max_age(self):
        return 0

    @classmethod
    def view(cls, result):
        return result


def GetCommand(name):
    match = [c for c in COMMANDS if name in c.SYNOPSIS[:3]]
    if len(match) == 1:
        return match[0]
    return None


def Action(session, opt, arg, data=None):
    session.ui.reset_marks(quiet=True)
    config = session.config

    if not opt:
        return Help(session, 'help').run()

    # Use the COMMANDS dict by default.
    command = GetCommand(opt)
    if command:
        return command(session, opt, arg, data=data).run()

    # Tags are commands
    if config.loaded_config:
        lopt = opt.lower()

        found = None
        for tag in config.tags.values():
            if lopt == tag.slug.lower():
                found = tag
                break
        if not found:
            for tag in config.tags.values():
                if lopt == tag.name.lower():
                    found = tag
                    break
        if not found:
            for tag in config.tags.values():
                if lopt == _(tag.name).lower():
                    found = tag
                    break

        if found:
            a = 'in:%s%s%s' % (found.slug, ' ' if arg else '', arg)
            return GetCommand('search')(session, opt,
                                        arg=a, data=data).run()

    # OK, give up!
    raise UsageError(_('Unknown command: %s') % opt)
