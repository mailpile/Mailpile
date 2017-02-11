#
# This file contains the UserInteraction and Session classes.
#
# The Session encapsulates settings and command results, allowing commands
# to be chanined in an interactive environment.
#
# The UserInteraction classes log the progress and performance of individual
# operations and assist with rendering the results in various formats (text,
# HTML, JSON, etc.).
#
###############################################################################
import datetime
import getpass
import json
import os
import random
import re
import sys
import tempfile
import time
import traceback
import urllib
from collections import defaultdict
from json import JSONEncoder
from jinja2 import TemplateError, TemplateSyntaxError, TemplateNotFound
from jinja2 import TemplatesNotFound, TemplateAssertionError, UndefinedError

import mailpile.commands
import mailpile.util
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


class SuppressHtmlOutput(Exception):
    pass


def default_dict(*args):
    d = defaultdict(str)
    for arg in args:
        d.update(arg)
    return d


class NoColors:
    """Dummy color constants"""
    C_SAVE = ''
    C_RESTORE = ''

    NORMAL = ''
    BOLD = ''
    NONE = ''
    BLACK = ''
    RED = ''
    YELLOW = ''
    BLUE = ''
    MAGENTA = ''
    CYAN = ''
    FORMAT = "%s%s"
    FORMAT_READLINE = "%s%s"
    RESET = ''
    LINE_BELOW = ''

    def __init__(self):
        self.lock = UiRLock()

    def __enter__(self, *args, **kwargs):
        return self.lock.__enter__()

    def __exit__(self, *args, **kwargs):
        return self.lock.__exit__(*args, **kwargs)

    def max_width(self):
        return 79

    def color(self, text, color='', weight='', readline=False):
        return '%s%s%s' % ((self.FORMAT_READLINE if readline else self.FORMAT)
                           % (color, weight), text, self.RESET)

    def replace_line(self, text, chars=None):
        pad = ' ' * max(0, min(self.max_width(),
                               self.max_width()-(chars or len(unicode(text)))))
        return '%s%s\r' % (text, pad)

    def add_line_below(self):
        pass

    def print_below(self):
        pass

    def write(self, data):
        with self:
            sys.stderr.write(data)

    def check_max_width(self):
        pass


class ANSIColors(NoColors):
    """ANSI color constants"""
    NORMAL = ''
    BOLD = ';1'
    NONE = '0'
    BLACK = "30"
    RED = "31"
    YELLOW = "33"
    BLUE = "34"
    MAGENTA = '35'
    CYAN = '36'
    RESET = "\x1B[0m"
    FORMAT = "\x1B[%s%sm"
    FORMAT_READLINE = "\001\x1B[%s%sm\002"

    CURSOR_UP = "\x1B[1A"
    CURSOR_DN = "\x1B[1B"
    CURSOR_SAVE = "\x1B[s"
    CURSOR_RESTORE = "\x1B[u"
    CLEAR_LINE = "\x1B[2K"

    def __init__(self):
        NoColors.__init__(self)
        self.check_max_width()

    def replace_line(self, text, chars=None):
        return '%s%s%s\r%s' % (self.CURSOR_SAVE,
                               self.CLEAR_LINE, text,
                               self.CURSOR_RESTORE)

    def max_width(self):
        return self.MAX_WIDTH

    def check_max_width(self):
        try:
            import fcntl, termios, struct
            fcntl_result = fcntl.ioctl(sys.stdin.fileno(),
                                       termios.TIOCGWINSZ,
                                       struct.pack('HHHH', 0, 0, 0, 0))
            h, w, hp, wp = struct.unpack('HHHH', fcntl_result)
            self.MAX_WIDTH = (w-1)
        except:
            self.MAX_WIDTH = 79


class Completer(object):
    """Readline autocompler"""
    DELIMS = ' \t\n`~!@#$%^&*()-=+[{]}\\|;:\'",<>?'

    def __init__(self, session):
        self.session = session

    def _available_opts(self, text):
        opts = ([s.SYNOPSIS[1] for s in mailpile.commands.COMMANDS] +
                [s.SYNOPSIS[2] for s in mailpile.commands.COMMANDS] +
                [t.name.lower() for t in self.session.config.tags.values()])
        return sorted([o for o in opts if o and o.startswith(text)])

    def _autocomplete(self, text, state):
        try:
            return self._available_opts(text)[state] + ' '
        except IndexError:
            return None

    def get_completer(self):
        return lambda t, s: self._autocomplete(t, s)


class UserInteraction:
    """Log the progress and performance of individual operations"""
    MAX_BUFFER_LEN = 250
    JSON_WRAP_TYPES = ('jhtml', 'jjs', 'jtxt', 'jcss', 'jxml', 'jrss')

    LOG_URGENT = 0
    LOG_RESULT = 5
    LOG_ERROR = 10
    LOG_NOTIFY = 20
    LOG_WARNING = 30
    LOG_PROGRESS = 40
    LOG_DEBUG = 50
    LOG_ALL = 99

    LOG_PREFIX = ''


    def __init__(self, config, log_parent=None, log_prefix=None):
        self.log_buffer = []
        self.log_buffering = 0
        self.log_level = self.LOG_ALL
        self.log_prefix = log_prefix or self.LOG_PREFIX
        self.interactive = False
        self.time_tracking = [('Main', [])]
        self.time_elapsed = 0.0
        self.render_mode = 'text'
        self.term = NoColors()
        self.config = config
        self.html_variables = {
            'title': 'Mailpile',
            'name': 'Chelsea Manning',
            'csrf': '',
            'even_odd': 'odd',
            'mailpile_size': 0
        }

        # Short-circuit and avoid infinite recursion in parent logging.
        self.log_parent = log_parent
        recurse = 0
        while self.log_parent and self.log_parent.log_parent:
            self.log_parent = self.log_parent.log_parent
            recurse += 1
            if recurse > 10:
                self.log_parent = None

    # Logging

    def _fmt_log(self, text, level=LOG_URGENT):
        c, w, clip = self.term.NONE, self.term.NORMAL, 1024
        if level == self.LOG_URGENT:
            c, w = self.term.RED, self.term.BOLD
        elif level == self.LOG_ERROR:
            c = self.term.RED
        elif level == self.LOG_WARNING:
            c = self.term.YELLOW
        elif level == self.LOG_NOTIFY:
            c = self.term.CYAN
        elif level == self.LOG_DEBUG:
            c = self.term.MAGENTA
        elif level == self.LOG_PROGRESS:
            c, clip = self.term.BLUE, 78

        try:
            unicode_text = unicode(text[-clip:]).encode('utf-8', 'replace')
        except UnicodeDecodeError:
            unicode_text = 'ENCODING ERROR'

        formatted = self.term.replace_line(self.term.color(
            unicode_text, color=c, weight=w), chars=len(text[-clip:]))
        if level != self.LOG_PROGRESS:
            formatted += '\n'

        return formatted

    def _display_log(self, text, level=LOG_URGENT):
        if not text.startswith(self.log_prefix):
            text = '%slog(%s): %s' % (self.log_prefix, level, text)
        if self.log_parent is not None:
            self.log_parent.log(level, text)
        else:
            self.term.write(self._fmt_log(text, level=level))

    def _debug_log(self, text, level):
        if text and 'log' in self.config.sys.debug:
            if not text.startswith(self.log_prefix):
                text = '%slog(%s): %s' % (self.log_prefix, level, text)
            if self.log_parent is not None:
                return self.log_parent.log(level, text)
            else:
                self.term.write(self._fmt_log(text, level=level))

    def clear_log(self):
        self.log_buffer = []

    def flush_log(self):
        try:
            while len(self.log_buffer) > 0:
                level, message = self.log_buffer.pop(0)
                if level <= self.log_level:
                    self._display_log(message, level)
        except IndexError:
            pass

    def block(self):
        with self.term:
            self._display_log('')
            self.log_buffering += 1

    def unblock(self, force=False):
        with self.term:
            if self.log_buffering <= 1 or force:
                self.log_buffering = 0
                self.flush_log()
            else:
                self.log_buffering -= 1

    def log(self, level, message):
        if self.log_buffering:
            self.log_buffer.append((level, message))
            while len(self.log_buffer) > self.MAX_BUFFER_LEN:
                self.log_buffer[0:(self.MAX_BUFFER_LEN/10)] = []
        elif level <= self.log_level:
            self._display_log(message, level)

    error = lambda self, msg: self.log(self.LOG_ERROR, msg)
    notify = lambda self, msg: self.log(self.LOG_NOTIFY, msg)
    warning = lambda self, msg: self.log(self.LOG_WARNING, msg)
    progress = lambda self, msg: self.log(self.LOG_PROGRESS, msg)
    debug = lambda self, msg: self.log(self.LOG_DEBUG, msg)

    # Progress indication and performance tracking
    times = property(lambda self: self.time_tracking[-1][1])

    def mark(self, action=None, percent=None):
        """Note that we are about to perform an action."""
        if not action:
            try:
                action = self.times[-1][1]
            except IndexError:
                action = 'mark'
        self.progress(action)
        self.times.append((time.time(), action))

    def report_marks(self, quiet=False, details=False):
        t = self.times
        if t and t[0]:
            self.time_elapsed = elapsed = t[-1][0] - t[0][0]
            if not quiet:
                try:
                    self.notify(_('Elapsed: %.3fs (%s)') % (elapsed, t[-1][1]))
                    if details:
                        for i in range(0, len(self.times)-1):
                            e = t[i+1][0] - t[i][0]
                            self.debug(' -> %.3fs (%s)' % (e, t[i][1]))
                except IndexError:
                    self.notify(_('Elapsed: %.3fs') % elapsed)
            return elapsed
        return 0

    def reset_marks(self, mark=True, quiet=False, details=False):
        """This sequence of actions is complete."""
        if self.times and mark:
            self.mark()
        elapsed = self.report_marks(quiet=quiet, details=details)
        self.times[:] = []
        return elapsed

    def push_marks(self, subtask):
        """Start tracking a new sub-task."""
        self.time_tracking.append((subtask, []))

    def pop_marks(self, name=None, quiet=True):
        """Sub-task ended!"""
        elapsed = self.report_marks(quiet=quiet)
        if len(self.time_tracking) > 1:
            if not name or (self.time_tracking[-1][0] == name):
                self.time_tracking.pop(-1)
        return elapsed

    # Higher level command-related methods
    def _display_result(self, ttype, result):
        with self.term:
            sys.stdout.write(unicode(result).encode('utf-8').rstrip())
            sys.stdout.write('\n')

    def start_command(self, cmd, args, kwargs):
        self.flush_log()
        self.push_marks(cmd)
        self.mark(('%s(%s)'
                   ) % (cmd, ', '.join((args or tuple()) +
                                       ('%s' % kwargs, ))))

    def finish_command(self, cmd):
        self.pop_marks(name=cmd)

    def _parse_render_mode(self):
        # Split out the template/type and rendering mode
        if '!' in self.render_mode:
            ttype, mode = self.render_mode.split('!')
        else:
            ttype, mode = self.render_mode, None

        # Figure out whether a template has been requested, or if we
        # are using the default "as.foo" template. Assume :content if
        # people request a .jfoo, unless otherwise specified.
        if ttype.split('.')[-1].lower() in self.JSON_WRAP_TYPES:
            parts = ttype.split('.')
            parts[-1] = parts[-1][1:]
            ttype = '.'.join(parts)
            wrap_in_json = True
            mode = mode or 'content'
        else:
            wrap_in_json = False

        # Figure out which template we're really asking for...
        if '.' in ttype:
            template = ttype
            ttype = ttype.split('.')[1]
        else:
            template = 'as.' + ttype

        return ttype.lower(), mode, wrap_in_json, template

    def display_result(self, result):
        """Render command result objects to the user"""
        try:
            if self.render_mode in ('json', 'as.json'):
                return self._display_result('json', result.as_('json'))
            if self.render_mode in ('text', 'as.text'):
                return self._display_result('text', unicode(result))
            if self.render_mode in ('csv', 'as.csv'):
                return self._display_result('csv', result.as_csv())

            ttype, mode, wrap_in_json, template = self._parse_render_mode()
            rendering = result.as_template(ttype,
                                           mode=mode,
                                           wrap_in_json=wrap_in_json,
                                           template=template)

            return self._display_result(ttype, rendering)
        except (TypeError, ValueError, KeyError, IndexError,
                UnicodeDecodeError):
            traceback.print_exc()
            return '[%s]' % _('Internal Error')

    # Creating output files
    DEFAULT_DATA_NAME_FMT = '%(msg_mid)s.%(count)s_%(att_name)s.%(att_ext)s'
    DEFAULT_DATA_ATTRS = {
        'msg_mid': 'file',
        'mimetype': 'application/octet-stream',
        'att_name': 'unnamed',
        'att_ext': 'dat',
        'rand': '0000'
    }
    DEFAULT_DATA_EXTS = {
        # FIXME: Add more!
        'text/plain': 'txt',
        'text/html': 'html',
        'image/gif': 'gif',
        'image/jpeg': 'jpg',
        'image/png': 'png'
    }

    def _make_data_filename(self, name_fmt, attributes):
        return (name_fmt or self.DEFAULT_DATA_NAME_FMT) % attributes

    def _make_data_attributes(self, attributes={}):
        attrs = self.DEFAULT_DATA_ATTRS.copy()
        attrs.update(attributes)
        attrs['rand'] = '%4.4x' % random.randint(0, 0xffff)
        if attrs['att_ext'] == self.DEFAULT_DATA_ATTRS['att_ext']:
            if attrs['mimetype'] in self.DEFAULT_DATA_EXTS:
                attrs['att_ext'] = self.DEFAULT_DATA_EXTS[attrs['mimetype']]
        return attrs

    def open_for_data(self, name_fmt=None, attributes={}):
        filename = self._make_data_filename(
            name_fmt, self._make_data_attributes(attributes))
        return filename, open(filename, 'w')

    # Rendering helpers for templating and such
    def render_json(self, data):
        """Render data as JSON"""
        class NoFailEncoder(JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (list, dict, str, unicode,
                                    int, float, bool, type(None))):
                    return JSONEncoder.default(self, obj)
                else:
                    return json_helper(obj)

        return json.dumps(data, indent=1, cls=NoFailEncoder,
                                sort_keys=True, allow_nan=False)

    def _web_template(self, config, tpl_names, elems=None):
        env = config.jinja_env
        env.session = Session(config)
        env.session.ui = HttpUserInteraction(None, config, log_parent=self)
        for fn in tpl_names:
            try:
                # FIXME(Security): Here we need to sanitize the file name
                #                  very strictly in case it somehow came
                #                  from user data.
                return env.get_template(fn)
            except (IOError, OSError, AttributeError), e:
                pass
        return None

    def _render_error(self, cfg, error_info):
        emsg = "<h1>%(error)s</h1>"
        if 'http' in cfg.sys.debug:
            emsg += "<p>%(details)s</p>"
            if 'traceback' in error_info:
                emsg += "<h3>TRACEBACK:</h3><pre>%(traceback)s</pre>"
            if 'source' in error_info:
                emsg += "<h3>SOURCE:</h3><xmp>%(source)s</xmp>"
            if 'data' in error_info:
                emsg += "<h3>DATA:</h3><pre>%(data)s</pre>"
            if 'config' in error_info.get('data'):
                del error_info['data']['config']
        ei = {}
        for kw in ('error', 'details', 'traceback', 'source', 'data'):
            value = error_info.get(kw, '')
            if isinstance(value, dict):
                ei[kw] = escape_html('%.8196s' % self.render_json(value))
            else:
                ei[kw] = escape_html('%.2048s' % value).replace('\n', '<br>')
        return emsg % ei

    def render_web(self, cfg, tpl_names, data):
        """Render data as HTML"""
        alldata = default_dict(self.html_variables)
        alldata['config'] = cfg
        alldata.update(data)
        try:
            template = self._web_template(cfg, tpl_names)
            if template:
                return template.render(alldata)
            else:
                tpl_esc_names = [escape_html(tn) for tn in tpl_names]
                return self._render_error(cfg, {
                    'error': _('Template not found'),
                    'details': ' or '.join(tpl_esc_names),
                    'data': alldata
                })
        except (UndefinedError, ):
            tpl_esc_names = [escape_html(tn) for tn in tpl_names]
            return self._render_error(cfg, {
                'error': _('Template error'),
                'details': ' or '.join(tpl_esc_names),
                'traceback': traceback.format_exc(),
                'data': alldata
            })
        except (TemplateNotFound, TemplatesNotFound), e:
            tpl_esc_names = [escape_html(tn) for tn in tpl_names]
            return self._render_error(cfg, {
                'error': _('Template not found'),
                'details': 'In %s:\n%s' % (e.name, e.message),
                'data': alldata
            })
        except (TemplateError, TemplateSyntaxError,
                TemplateAssertionError,), e:
            return self._render_error(cfg, {
                'error': _('Template error'),
                'details': ('In %s (%s), line %s:\n%s'
                            % (e.name, e.filename, e.lineno, e.message)),
                'source': e.source,
                'traceback': traceback.format_exc(),
                'data': alldata
            })

    def edit_messages(self, session, emails):
        if not self.interactive:
            return False

        for e in emails:
            if not e.is_editable():
                from mailpile.mailutils import NotEditableError
                raise NotEditableError(_('Message %s is not editable')
                                       % e.msg_mid())

        sep = '%s(%8.8x%3.3x)-\n' % ('-' * 68, time.time(),
                                     random.randint(0, 0xfff))
        edit_this = ('\n'+sep).join([e.get_editing_string() for e in emails])

        tf = tempfile.NamedTemporaryFile()
        tf.write(edit_this.encode('utf-8'))
        tf.flush()
        with self.term:
            try:
                self.block()
                os.system('%s %s' % (os.getenv('VISUAL', default='vi'),
                                     tf.name))
            finally:
                self.unblock()
        tf.seek(0, 0)
        edited = tf.read().decode('utf-8')
        tf.close()

        if edited == edit_this:
            return False

        updates = [t.strip() for t in edited.split(sep)]
        if len(updates) != len(emails):
            raise ValueError(_('Number of edited messages does not match!'))
        for i in range(0, len(updates)):
            emails[i].update_from_string(session, updates[i])
        return True

    def get_password(self, prompt):
        if not (self.interactive or sys.stdout.isatty()):
            return ''
        with self.term:
            try:
                self.block()
                return getpass.getpass(prompt.encode('utf-8')).decode('utf-8')
            finally:
                self.unblock()


class HttpUserInteraction(UserInteraction):
    LOG_PREFIX = 'http/'

    def __init__(self, request, *args, **kwargs):
        UserInteraction.__init__(self, *args, **kwargs)
        self.request = request
        self.logged = []
        self.results = []

    # Just buffer up rendered data
    def _display_log(self, text, level=UserInteraction.LOG_URGENT):
        self._debug_log(text, level)
        self.logged.append((level, text))

    def _display_result(self, ttype, result):
        self.results.append((ttype, result))

    # Stream raw data to the client on open_for_data
    def open_for_data(self, name_fmt=None, attributes={}):
        return 'HTTP Client', RawHttpResponder(self.request, attributes)

    def _render_text_responses(self, config):
        if config.sys.debug:
            return '%s\n%s' % (
                '\n'.join([l[1] for l in self.logged]),
                ('\n%s\n' % ('=' * 79)).join(r for t, r in self.results)
            )
        else:
            return ('\n%s\n' % ('=' * 79)).join(r for t, r in self.results)

    def _ttype_to_mimetype(self, ttype, result):
        return ({
            'css': 'text/css',
            'csv': 'text/csv',
            'js': 'text/javascript',
            'json': 'application/json',
            'html': 'text/html',
            'rss': 'application/rss+xml',
            'text': 'text/plain',
            'txt': 'text/plain',
            'xml': 'application/xml'
        }.get(ttype.lower(), 'text/plain'), result)

    def render_response(self, config):
        ttype, mode, wrap_in_json, template = self._parse_render_mode()
        if (ttype == 'json' or wrap_in_json):
            if len(self.results) == 1:
                data = self.results[0][1]
            else:
                data = '[%s]' % ','.join(r for t, r in self.results)
            return ('application/json', data)
        else:
            if len(self.results) == 1:
                return self._ttype_to_mimetype(*self.results[0])
            if len(self.results) > 1:
                raise Exception('FIXME: Multiple results, OMG WTF')
            return ""

    def edit_messages(self, session, emails):
        return False


class BackgroundInteraction(UserInteraction):
    LOG_PREFIX = 'bg/'

    def _display_log(self, text, level=UserInteraction.LOG_URGENT):
        self._debug_log(text, level)

    def edit_messages(self, session, emails):
        return False


class SilentInteraction(UserInteraction):
    LOG_PREFIX = 'silent/'

    def _display_log(self, text, level=UserInteraction.LOG_URGENT):
        self._debug_log(text, level)

    def _display_result(self, ttype, result):
        return result

    def edit_messages(self, session, emails):
        return False


class CapturingUserInteraction(UserInteraction):
    def __init__(self, config):
        mailpile.ui.UserInteraction.__init__(self, config)
        self.captured = ''

    def _display_result(self, ttype, result):
        self.captured = unicode(result)


class RawHttpResponder:

    def __init__(self, request, attributes={}):
        self.raised = False
        self.request = request
        #
        # FIXME: Security risks here, untrusted content may find its way into
        #                our raw HTTP headers etc.
        #
        mimetype = attributes.get('mimetype', 'application/octet-stream')
        filename = attributes.get('filename', 'attachment.dat'
                                  ).replace('"', '')
        disposition = attributes.get('disposition', 'attachment')
        length = attributes.get('length')
        request.send_http_response(200, 'OK')
        headers = []
        if length is not None:
            headers.append(('Content-Length', '%s' % length))
        if disposition and filename:
            encfilename = urllib.quote(filename.encode("utf-8"))
            headers.append(('Content-Disposition',
                            '%s; filename*=UTF-8\'\'%s' % (disposition,
                                                           encfilename)))
        elif disposition:
            headers.append(('Content-Disposition', disposition))
        request.send_standard_headers(header_list=headers,
                                      mimetype=mimetype)

    def write(self, data):
        self.request.wfile.write(data)

    def close(self):
        if not self.raised:
            self.raised = True
            raise SuppressHtmlOutput()


class Session(object):

    @classmethod
    def Snapshot(cls, session, **copy_kwargs):
        return cls(session.config).copy(session, **copy_kwargs)

    def __init__(self, config):
        self.config = config

        self.main = False
        self.ui = UserInteraction(config)

        self.wait_lock = threading.Condition(UiRLock())
        self.task_results = []

        self.order = None
        self.results = []
        self.searched = []
        self.search_index = None
        self.last_event_id = None
        self.displayed = None
        self.context = None

    def set_interactive(self, val):
        self.ui.interactive = val

    interactive = property(lambda s: s.ui.interactive,
                           lambda s, v: s.set_interactive(v))

    def copy(self, session, ui=False, search=True):
        if ui is True:
            self.main = session.main
            self.ui = session.ui
        if search:
            self.order = session.order
            self.results = session.results[:]
            self.searched = session.searched[:]
            self.search_index = session.search_index
            self.displayed = session.displayed
            self.context = session.context
        return self

    def get_context(self, update=False):
        if update or not self.context:
            if self.searched and not self.search_index:
                sid = self.config.search_history.add(self.searched,
                                                     self.results,
                                                     self.order)
                self.context = 'search:%s' % sid
        return self.context

    def load_context(self, context):
        if self.context and self.context == context:
            return context
        try:
            if context.startswith('search:'):
                s, r, o = self.config.search_history.get(self, context[7:])
                self.searched, self.results, self.order = s, r, o
                self.search_index = None
                self.displayed = None
                self.context = context
                return context
            else:
                return False
        except (KeyError, ValueError):
            return False

    def report_task_completed(self, name, result):
        with self.wait_lock:
            self.task_results.append((name, result))
            self.wait_lock.notify_all()

    def report_task_failed(self, name):
        self.report_task_completed(name, None)

    def wait_for_task(self, wait_for, quiet=False):
        while not mailpile.util.QUITTING:
            with self.wait_lock:
                for i in range(0, len(self.task_results)):
                    if self.task_results[i][0] == wait_for:
                        tn, rv = self.task_results.pop(i)
                        self.ui.reset_marks(quiet=quiet)
                        return rv
                self.wait_lock.wait()

    def error(self, message):
        self.ui.error(message)
        if not self.interactive:
            sys.exit(1)
