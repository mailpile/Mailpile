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
from collections import defaultdict
import datetime
import os
import random
import re
import sys
import traceback
import json

from lxml.html.clean import autolink_html
from jinja2 import Environment, PackageLoader
from jinja2 import TemplateError, TemplateSyntaxError, TemplateNotFound, TemplatesNotFound, TemplateAssertionError, UndefinedError

import mailpile.commands
from mailpile.util import *
from mailpile.search import MailIndex


class SuppressHtmlOutput(Exception):
  pass


def default_dict(*args):
  d = defaultdict(str)
  for arg in args:
    d.update(arg)
  return d


class NoColors:
  """Dummy color constants"""
  NORMAL = ''
  BOLD   = ''
  NONE   = ''
  BLACK  = ''
  RED    = ''
  YELLOW = ''
  BLUE   = ''
  FORMAT = "%s%s"
  RESET  = ''

  def color(self, text, color='', weight=''):
    return '%s%s%s' % (self.FORMAT % (color, weight), text, self.RESET)

class ANSIColors(NoColors):
  """ANSI color constants"""
  NORMAL = ''
  BOLD   = ';1'
  NONE   = '0'
  BLACK  = "30"
  RED    = "31"
  YELLOW = "33"
  BLUE   = "34"
  RESET  = "\x1B[0m"
  FORMAT = "\x1B[%s%sm"


class UserInteraction:
  """Log the progress and performance of individual operations"""
  MAX_BUFFER_LEN = 150
  MAX_WIDTH = 79

  LOG_URGENT   =  0
  LOG_RESULT   =  5
  LOG_ERROR    = 10
  LOG_NOTIFY   = 20
  LOG_WARNING  = 30
  LOG_PROGRESS = 40
  LOG_DEBUG    = 50
  LOG_ALL      = 99

  def __init__(self, log_parent=None):
    self.log_parent = log_parent
    self.log_buffer = []
    self.log_buffering = False
    self.log_level = self.LOG_ALL
    self.interactive = False
    self.time_tracking = [('Main', [])]
    self.session = None
    self.time_elapsed = 0.0
    self.last_display = [self.LOG_PROGRESS, 0]
    self.render_mode = 'text'
    self.palette = NoColors()
    self.html_variables = {
      'title': 'Mailpile',
      'name': 'Chelsea Manning',
      'csrf': '',
      'even_odd': 'odd',
      'mailpile_size': 0
    }

  def set_session(self, session):
    self.session = session

  # Logging
  def _display_log(self, text, level=LOG_URGENT):
    pad = ''
    if self.last_display[0] in (self.LOG_PROGRESS, ):
      pad = ' ' * max(0, min(self.MAX_WIDTH, self.MAX_WIDTH-len(text)))
      sys.stderr.write('\r')
    elif self.last_display[0] not in (self.LOG_RESULT, ):
      sys.stderr.write('\n')
    c, w = self.palette.NONE, self.palette.NORMAL
    if level == self.LOG_URGENT: c, w = self.palette.RED, self.palette.BOLD
    elif level == self.LOG_ERROR: c = self.palette.RED
    elif level == self.LOG_WARNING: c = self.palette.YELLOW
    elif level == self.LOG_PROGRESS: c = self.palette.BLUE
    sys.stderr.write('%s%s' % (self.palette.color(text.encode('utf-8'),
                                                  color=c, weight=w), pad))
    self.last_display = [level, len(text)]
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
    self._display_log('')
    self.log_buffering = True
  def unblock(self):
    self.log_buffering = False
    self.last_display = [self.LOG_RESULT, 0]
    self.flush_log()
  def log(self, level, message):
    if self.log_buffering:
      self.log_buffer.append((level, message))
      while len(self.log_buffer) > self.MAX_BUFFER_LEN:
        self.log_buffer[0:(self.MAX_BUFFER_LEN/10)] = []
    elif level <= self.log_level:
      self._display_log(message, level)
  def finish_command(self):
    pass
  def start_command(self):
    pass

  error = lambda self, msg: self.log(self.LOG_ERROR, msg)
  notify = lambda self, msg: self.log(self.LOG_NOTIFY, msg)
  warning = lambda self, msg: self.log(self.LOG_WARNING, msg)
  progress = lambda self, msg: self.log(self.LOG_PROGRESS, msg)
  debug = lambda self, msg: self.log(self.LOG_DEBUG, msg)

  # Progress indication and performance tracking
  times = property(lambda self: self.time_tracking[0][1])
  def mark(self, action, percent=None):
    """Note that we are about to perform an action."""
    self.progress(action)
    self.times.append((time.time(), action))
  def reset_marks(self, quiet=False):
    """This sequence of actions is complete."""
    t = self.times
    self.times = []
    if t:
      self.time_elapsed = elapsed = t[-1][0] - t[0][0]
      if not quiet:
        self.notify('Elapsed: %.3fs (%s)' % (elapsed, t[-1][1]))
      return elapsed
    else:
      return 0
  def mark_push(self, subtask):
    """We are beginnning a sub-sequence we want to track separately."""
    self.time_tracking[:0] = [(subtask, [])]
  def mark_pop(self, quiet=False):
    """Sub-task completed."""
    elapsed = self.reset_marks(quiet=quiet)
    if len(self.time_tracking) > 1:
      subtask, times = self.time_tracking.pop(0)
      self.mark('Completed %s in %.3fs' % (subtask, elapsed))
    return elapsed

  # Higher level command-related methods
  def _display_result(self, result):
    sys.stdout.write(result+'\n')
  def start_command(self, cmd, args, kwargs):
    self.flush_log()
    self.mark('%s(%s)' % (cmd, ', '.join((args or []) + ['%s' % kwargs])))
  def finish_command(self):
    self.reset_marks()
  def display_result(self, result):
    """Render command result objects to the user"""
    self._display_log('', level=self.LOG_RESULT)
    if self.render_mode == 'json':
      return self._display_result(result.as_json())
    elif self.render_mode in ('html', 'jhtml'):
      return self._display_result(result.as_html())
    elif self.render_mode == 'xml':
      return self._display_result(result.as_xml())
    elif self.render_mode == 'rss':
      return self._display_result(result.as_rss())
    else:
      return self._display_result(unicode(result))

  # Creating output files
  DEFAULT_DATA_NAME_FMT = '%(msg_idx)s.%(count)s_%(att_name)s.%(att_ext)s'
  DEFAULT_DATA_ATTRS = {
    'msg_idx': 'file',
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
    filename = self._make_data_filename(name_fmt,
                                       self._make_data_attributes(attributes))
    return filename, open(filename, 'w')

  # Rendering helpers for templating and such
  def render_json(self, data):
    """Render data as JSON"""
    from json import JSONEncoder
    class NoFailEncoder(JSONEncoder):
      def default(self, obj):
        if isinstance(obj, (list, dict, str, unicode, int, float, bool, type(None))):
            return JSONEncoder.default(self, obj)
        return "COMPLEXBLOB"

    return json.dumps(data, indent=1, cls=NoFailEncoder)

  def _html_template(self, config, tpl_names, elems=None):
    theme = config.data_directory('html_theme')
    print config.get('path', {})
    env = Environment(loader=PackageLoader('mailpile', '../%s/html/' % theme),
                      extensions=['jinja2.ext.i18n', 'jinja2.ext.with_', 'mailpile.jinjaextensions.MailpileCommand'])
    env.session = self.session
    for tpl_name in tpl_names:
      try:
        fn = '%s.html' % tpl_name
        template = env.get_template(fn)
        return template
      except (IOError, OSError, AttributeError), e:
        emsg = "<h1>Template not found: %s</h1>%s\n"
        return emsg % (fn, e)
      except (TemplateError, UndefinedError, TemplateSyntaxError, TemplateAssertionError, TemplateNotFound, TemplatesNotFound), e:
        emsg = "<h1>Template error in %s</h1>\nParsing template %s: <b>%s</b> on line %s<br/><div><xmp>%s</xmp></div>"
        return emsg % (e.name, e.filename, e.message, e.lineno, e.source)

  def render_html(self, cfg, tpl_names, data):
    """Render data as HTML"""
    template = self._html_template(cfg, tpl_names)
    alldata = default_dict(cfg)
    alldata.update(self.html_variables)
    alldata.update(data)
    print alldata
    try:
      return template.render(alldata)
    except:
      return template

  def edit_messages(self, emails):
    self.error('Sorry, this UI cannot edit messages.')


class HttpUserInteraction(UserInteraction):
  def __init__(self, request, *args, **kwargs):
    UserInteraction.__init__(self, *args, **kwargs)
    self.request = request
    self.logged = []
    self.results = []

  # Just buffer up rendered data
  def _display_log(self, text, level=UserInteraction.LOG_URGENT):
    self.logged.append((level, text))
  def _display_result(self, result):
    self.results.append(result)

  # Stream raw data to the client on open_for_data
  def open_for_data(self, name_fmt=None, attributes={}):
    return 'HTTP Client', RawHttpResponder(self.request, attributes)

  # Render to HTML/JSON/...
  def _render_jhtml_response(self, config):
    return json.dumps(default_dict(self.html_variables, {
      'results': self.results,
      'logged': self.logged,
    }))
  def _render_text_response(self, config):
    return '%s\n%s' % (
      '\n'.join([l[1] for l in self.logged]),
      ('\n%s\n' % ('=' * 79)).join(self.results)
    )
  def _render_html_response(self, config):
    if len(self.results) > 0:
      return self.results[0]

    return ""

  def render_response(self, config):
    if self.render_mode == 'json':
      return ('application/json', '[%s]' % ','.join(self.results))
    elif self.render_mode == 'jhtml':
      return ('application/json', self._render_jhtml_response(config))
    elif self.render_mode == 'html':
      return ('text/html', self._render_html_response(config))
    else:
      return ('text/plain', self._render_text_response(config))

  def edit_messages(self, emails):
    pass

  def print_filters(self, args):
    print args
    return args

class BackgroundInteraction(UserInteraction):
  # FIXME: This shouldn't be quite so silent...
  def _display_log(self, text, level=UserInteraction.LOG_URGENT):
    pass


class SilentInteraction(UserInteraction):
  def _display_log(self, text, level=UserInteraction.LOG_URGENT):
    pass
  def _display_result(self, result):
    return result
  def edit_messages(self, emails):
    pass


class BackgroundInteraction(SilentInteraction):
  # FIXME: This shouldn't be quite so silent...
  pass


class RawHttpResponder:

  def __init__(self, request, attributes={}):
    self.request = request
    #
    # FIXME: Security risks here, untrusted content may find its way into
    #        our raw HTTP headers etc.
    #
    mimetype = attributes.get('mimetype', 'application/octet-stream')
    filename = attributes.get('filename', 'attachment.dat').replace('"', '')
    disposition = attributes.get('disposition', 'attachment')
    length = attributes['length']
    request.send_http_response(200, 'OK')
    request.send_standard_headers(header_list=[
      ('Content-Length', length),
      ('Content-Disposition', '%s; filename="%s"' % (disposition, filename))
    ], mimetype=mimetype)

  def write(self, data):
    self.request.wfile.write(data)

  def close(self):
    raise SuppressHtmlOutput()


class Session(object):

  def __init__(self, config):
    self.config = config
    self.interactive = False
    self.main = False
    self.order = None
    self.wait_lock = threading.Condition()
    self.results = []
    self.searched = []
    self.displayed = (0, 0)
    self.task_results = []
    self.ui = UserInteraction()

  def report_task_completed(self, name, result):
    self.wait_lock.acquire()
    self.task_results.append((name, result))
    self.wait_lock.notify_all()
    self.wait_lock.release()

  def report_task_failed(self, name):
    self.report_task_completed(name, None)

  def wait_for_task(self, wait_for, quiet=False):
    while True:
      self.wait_lock.acquire()
      for i in range(0, len(self.task_results)):
        if self.task_results[i][0] == wait_for:
          tn, rv = self.task_results.pop(i)
          self.wait_lock.release()
          self.ui.reset_marks(quiet=quiet)
          return rv

      self.wait_lock.wait()
      self.wait_lock.release()

  def error(self, message):
    self.ui.error(message)
    if not self.interactive:
      sys.exit(1)
