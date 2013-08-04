#!/usr/bin/env python2.7
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
import cgi
import datetime
import os
import random
import re
import sys
import traceback
import json

from lxml.html.clean import autolink_html
import jsontemplate

import mailpile.commands
from mailpile.util import *
from mailpile.search import MailIndex


class SuppressHtmlOutput(Exception):
  pass


def _html_escape(data):
  return cgi.escape(unicode(data))

JSONTEMPLATE_ARGS = {
  'undefined_str': '',
  'more_formatters': {
    'html': _html_escape
  },
  'default_formatter': 'html'
}



def default_dict(*args):
  d = defaultdict(str)
  for arg in args:
    d.update(arg)
  return d


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
    self.time_elapsed = 0.0
    self.last_display = [self.LOG_PROGRESS, 0]
    self.render_mode = 'text'
    self.html_variables = {
      'title': 'Mailpile',
      'name': 'Bradley Manning',
      'csrf': '',
      'even_odd': 'odd',
      'mailpile_size': 0
    }

  # Logging
  def _display_log(self, text, level=LOG_URGENT):
    pad = ''
    if self.last_display[0] in (self.LOG_PROGRESS, ):
      pad = ' ' * max(0, min(self.MAX_WIDTH, self.MAX_WIDTH-len(text)))
      sys.stderr.write('\r')
    elif self.last_display[0] not in (self.LOG_RESULT, ):
      sys.stderr.write('\n')
    sys.stderr.write('%s%s' % (text.encode('utf-8'), pad))
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
    return json.dumps(data, indent=1)
  def _html_template(self, config, tpl_names, elems=None):
    for tpl_name in tpl_names:
      try:
        fn = '%s.html' % tpl_name
        return config.open_file('html_template', fn)[1].read().decode('utf-8')
      except (IOError, OSError, AttributeError):
        pass
    if elems:
      return ('<div class="%s">\n  ' % tpl_names[0].replace('/', '_') +
              '\n  '.join(['<span class="%s">{%s}</span>' % (e,e)
                           for e in elems]) +
              '\n</div>')
    else:
      return '{data}'
  def render_html(self, cfg, tpl_names, data):
    """Render data as HTML"""
    return jsontemplate.expand(self._html_template(cfg, tpl_names,
                                                   elems=data.keys()), data,
                               **JSONTEMPLATE_ARGS)
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
    page = self._html_template(config, ['html/page'],
                               elems=['results', 'logged'])
    quiet = Session(config)
    quiet.ui = SilentInteraction()
    while page.startswith('{# set'):
      load, page = page.split('\n', 1)
      _set, vname, _eq, mode, cmd = load.strip()[3:-2].split(None, 4)
      cmd, arg = (' ' in cmd) and cmd.split(' ', 1) or (cmd, '')
      quiet.ui.render_mode = mode
      result = mailpile.commands.Action(quiet, cmd, arg)
      self.html_variables[vname] = quiet.ui.display_result(result)

    return jsontemplate.expand(page, default_dict(self.html_variables, {
      'results': '\n'.join(['<div class="result">%s</div>' % r
                            for r in self.results]),
      'logged': '\n'.join(['<p class="ll_%s">%s</p>' % l
                           for l in self.logged])
    }), **JSONTEMPLATE_ARGS)
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



class xxBaseUI(object):

  WIDTH = 80
  MAX_BUFFER_LEN = 150
  interactive = False
  buffering = False

  def __init__(self):
    self.buffered = []

  def print_key(self, key, config): pass
  def reset_marks(self, quiet=False): pass
  def mark(self, progress): pass

  def clear(self):
    self.buffered = []

  def flush(self):
    try:
      while len(self.buffered) > 0:
        self.buffered.pop(0)()
    except IndexError:
      pass

  def block(self):
    self.buffering = True

  def unblock(self):
    self.flush()
    self.buffering = False

  def start_command(self, cmd, args, kwargs):
    self.clear()
    self.mark('%s(%s)' % (cmd, ', '.join((args or []) + ['%s' % kwargs])))

  def finish_command(self):
    self.reset_marks()

  def say(self, text='', newline='\n', fd=sys.stdout):
    if not fd:
      fd = sys.stdout
    def sayit():
      fd.write(text.encode('utf-8')+newline)
      fd.flush()
    self.buffered.append(sayit)
    while len(self.buffered) > self.MAX_BUFFER_LEN:
      self.buffered[0:(self.MAX_BUFFER_LEN/10)] = []
    if not self.buffering:
      self.flush()

  def notify(self, message):
    self.say('%s%s' % (message, ' ' * (self.WIDTH-1-len(message))))
  def warning(self, message):
    self.say('Warning: %s%s' % (message, ' ' * (self.WIDTH-11-len(message))))
  def error(self, message):
    self.say('Error: %s%s' % (message, ' ' * (self.WIDTH-9-len(message))))

  def print_filters(self, config):
    w = int(self.WIDTH * 23/80)
    ffmt = ' %%3.3s %%-%d.%ds %%-%d.%ds %%s' % (w, w, w-2, w-2)
    self.say(ffmt % ('ID', ' Tags', 'Terms', ''))
    for fid, terms, tags, comment in config.get_filters(filter_on=None):
      self.say(ffmt % (
        fid,
        ' '.join(['%s%s' % (t[0], config['tag'].get(t[1:], t[1:]))
                  for t in tags.split()]),
        ((terms == '*') and '(all new mail)' or
         (terms == '@read') and '(read mail)' or terms or '(none)'),
        comment or '(none)'
      ))

  def display_messages(self, emails,
                       raw=False, sep='', fd=sys.stdout, context=True):
    for email in emails:
      if raw:
        self.display_message(email, None, raw=True, sep=sep, fd=fd)
      else:
        tree = email.get_message_tree()
        if context:
          try:
            try:
              conversation = [int(m[0], 36) for m in tree['conversation']
                                                  if m[0] is not None]
            except TypeError:
              self.warning('Bad conversation: %s' % tree['conversation'])
              conversation = [email.msg_idx]
            self.display_results(email.index,  conversation, [],
                                 expand=[email], fd=fd)
          except TypeError:
            self.warning('No conversation, bad ID: %s' % email.msg_idx)
            self.warning(traceback.format_exc())
        else:
          email.evaluate_pgp(tree, decrypt=True)
          self.display_message(email, tree, raw=raw, sep=sep, fd=fd)

  def _name(self, sender):
    words = re.sub('["<>]', '', sender).split()
    nomail = [w for w in words if not '@' in w]
    if nomail: return ' '.join(nomail)
    return ' '.join(words)

  def _names(self, senders):
    if len(senders) > 1:
      return re.sub('["<>]', '', ', '.join([x.split()[0] for x in senders]))
    return ', '.join([self._name(s) for s in senders])

  def _compact(self, namelist, maxlen):
    l = len(namelist)
    while l > maxlen:
      namelist = re.sub(', *[^, \.]+, *', ',,', namelist, 1)
      if l == len(namelist): break
      l = len(namelist)
    namelist = re.sub(',,,+, *', ' .. ', namelist, 1)
    return namelist

  def display_message(self, email, tree, raw=False, sep='', fd=None):
    if raw:
      self.say(sep, fd=fd)
      for line in email.get_file().readlines():
        try:
          line = line.decode('utf-8')
        except UnicodeDecodeError:
          try:
            line = line.decode('iso-8859-1')
          except:
            line = '(MAILPILE DECODING FAILED)\n'
        self.say(line, newline='', fd=fd)
    else:
      self.say(sep, fd=fd)
      for hdr in ('From', 'Subject', 'Date', 'To', 'Cc'):
        value = email.get(hdr, '')
        if value:
          self.say('%s: %s' % (hdr, value), fd=fd)
      self.say('', fd=fd)
      for part in tree['text_parts']:
        if part['type'] == 'quote':
          self.say('[quoted text]', fd=fd)
        else:
          self.say('%s' % part['data'], fd=fd, newline='')
      if tree['attachments']:
        self.say('', fd=fd)
        for att in tree['attachments']:
          desc = '%(count)s: %(filename)s (%(mimetype)s, %(length)s bytes)' % att
          self.say(' [Attachment #%s]' % desc, fd=fd)
      self.say('', fd=fd)

  def edit_messages(self, emails):
    self.say('Sorry, this UI cannot edit messages.')

  def display_gpg_keys(self, data):
    self.say('%s' % data)


class xxTextUI(xxBaseUI):
  def __init__(self):
    xxBaseUI.__init__(self)
    self.times = []

  def reset_marks(self, quiet=False):
    t = self.times
    self.times = []
    if t:
      if not quiet:
        result = 'Elapsed: %.3fs (%s)' % (t[-1][0] - t[0][0], t[-1][1])
        self.say('%s%s' % (result, ' ' * (self.WIDTH-1-len(result))))
      return t[-1][0] - t[0][0]
    else:
      return 0

  def mark(self, progress):
    self.say('  %s%s\r' % (progress, ' ' * (self.WIDTH-3-len(progress))),
             newline='', fd=sys.stderr)
    self.times.append((time.time(), progress))

  def display_vcard(self, vcard, compact=False):
    if compact:
      self.say('%s' % vcard)
    else:
      self.say('%s' % vcard.as_vCard())

  def display_results(self, idx, results, terms,
                            start=0, end=None, num=None, expand=None,
                            fd=None):
    if not results: return (0, 0)

    num = num or 20
    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    clen = max(3, len('%d' % len(results)))
    cfmt = '%%%d.%ds' % (clen, clen)

    count = 0
    expand_ids = [e.msg_idx for e in (expand or [])]
    for mid in results[start:start+num]:
      count += 1
      if expand and mid in expand_ids:
        self.display_messages([expand[expand_ids.index(mid)]],
                              context=False, fd=fd);
      else:
        try:
          msg_info = idx.get_msg_by_idx(mid)
          msg_subj = msg_info[idx.MSG_SUBJECT]

          if expand:
            msg_from = [msg_info[idx.MSG_FROM]]
            msg_date = [msg_info[idx.MSG_DATE]]
          else:
            conversation = idx.get_conversation(msg_info)
            msg_from = [r[idx.MSG_FROM] for r in conversation]
            msg_date = [r[idx.MSG_DATE] for r in conversation]

          msg_from = msg_from or ['(no sender)']
          msg_date = datetime.date.fromtimestamp(max([
                                                 int(d, 36) for d in msg_date]))

          msg_tags = '<'.join(sorted([re.sub("^.*/", "", idx.config['tag'].get(t, t))
                                       for t in idx.get_tags(msg_info=msg_info)]))
          msg_tags = msg_tags and (' <%s' % msg_tags) or '  '

          sfmt = '%%-%d.%ds%%s' % (41-(clen+len(msg_tags)),41-(clen+len(msg_tags)))
          self.say((cfmt+' %4.4d-%2.2d-%2.2d %-25.25s '+sfmt
                    ) % (start + count,
                         msg_date.year, msg_date.month, msg_date.day,
                         self._compact(self._names(msg_from), 25),
                         msg_subj, msg_tags),
                    fd=fd)
        except (IndexError, ValueError):
          self.say('-- (not in index: %s)' % mid)
    self.mark(('Listed %d-%d of %d results'
               ) % (start+1, start+count, len(results)))
    return (start, count)

  def display_messages(self, emails, raw=False, sep=None, fd=None, context=True):
    viewer = None
    if not fd:
      if self.interactive:
        viewer = subprocess.Popen(['less'], stdin=subprocess.PIPE)
        fd = viewer.stdin
      else:
        fd = sys.stdout
    try:
      xx.BaseUI.display_messages(self, emails,
                                 raw=raw,
                                sep=(sep is None and ('_' * self.WIDTH) or sep),
                              fd=fd, context=context)
    except IOError, e:
      pass
    if viewer:
      fd.close()
      viewer.wait()

  def edit_messages(self, emails):
    for email in emails:
      try:
        if email.is_editable():
          es = email.get_editing_string().encode('utf-8')

          tf = tempfile.NamedTemporaryFile(suffix='.txt')
          tf.write(es)
          tf.flush()
          rv = subprocess.call(['edit', tf.name])
          tf.seek(0, 0)
          ns = tf.read()
          tf.close()

          if es != ns:
            email.update_from_string(ns)
            self.say('Message saved.  Use the "mail" command to send it.')
          else:
            self.warning('Message unchanged.')
        else:
          self.error('That message cannot be edited.')
      except:
        self.warning('Editing failed!')
        self.warning(traceback.format_exc())


class RawHttpResponder:

  def __init__(self, request, attributes={}):
    self.request = request
    #
    # FIXME: Security risks here, untrusted content may find its way into
    #        our raw HTTP headers etc.
    #
    mimetype = attributes.get('mimetype', 'application/octet-stream')
    filename = attributes.get('filename', 'attachment.dat').replace('"', '')
    length = attributes['length']
    request.send_http_response(200, 'OK')
    request.send_standard_headers(header_list=[
      ('Content-Length', length),
      ('Content-Disposition', 'attachment; filename="%s"' % filename)
    ], mimetype=mimetype)

  def write(self, data):
    self.request.wfile.write(data)

  def close(self):
    raise SuppressHtmlOutput()


class xxHttpUI(xxBaseUI):
  def __init__(self, request):
    xxBaseUI.__init__(self)

  def set_postdata(self, postdata):
    self.post_data = postdata

  def set_querydata(self, querydata):
    self.query_data = querydata

  def open_for_data(self, name_fmt=None, attributes={}):
    return 'HTTP Client', RawHttpResponder(self.request, attributes)


class xxJsonUI(xxHttpUI):
  def __init__(self, request):
    xxHttpUI.__init__(self, request)
    self.request = request
    self.clear()

  def clear(self):
    self.status_code = 200
    self.buffered_results = []
    self.buffered_loglines = []
    self.buffered_json = {
      "command": '',
      "loglines": self.buffered_loglines,
      "results": self.buffered_results
    }

  def say(self, text=[], newline=None, fd=None):
    # Just suppress the progress indicator chitter chatter
    if not text.endswith('\r'):
      self.buffered_loglines.append(text.rstrip())

  def error(self, message):
    self.status_code = 500
    return xxHttpUI.error(self, message)

  def explain_msg_summary(self, info):
    return {
      'idx': info[0],
      'id': info[1],
      'from': info[2],
      'subject': info[3],
      'date': long(info[4], 36),
      'tag_ids': info[5],
      'url': '/=%s/%s/' % (info[0], info[1])
    }

  def display_gpg_keys(self, data):
    self.buffered_json['results'] = self.buffered_results = data

  def display_results(self, idx, results, terms,
                            start=0, end=0, num=0, expand=None,
                            fd=None):
    if not results:
      return (0, 0)

    num = num or 50
    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    count = 0
    for mid in results[start:start+num]:
      count += 1
      msg_info = idx.get_msg_by_idx(mid)
      result = self.explain_msg_summary([
        msg_info[MailIndex.MSG_IDX],
        msg_info[MailIndex.MSG_ID],
        msg_info[MailIndex.MSG_FROM],
        msg_info[MailIndex.MSG_SUBJECT],
        msg_info[MailIndex.MSG_DATE],
        msg_info[MailIndex.MSG_TAGS].split(','),
      ])
      result['tags'] = sorted([idx.config['tag'].get(t,t)
                               for t in idx.get_tags(msg_info=msg_info)
                                     if 'tag:%s' % t not in terms])
      self.buffered_results.append(result)

    return (start, count)

  def display_messages(self, emails,
                       raw=False, sep='', fd=sys.stdout, context=True):
    for email in emails:
      # This doesn't do e-mail contexts...
      tree = email.get_message_tree()
      email.evaluate_pgp(tree, decrypt=True)
      self.display_message(email, tree, raw=raw, sep=sep, fd=fd)

  def prune_message_tree(self, tree):
    pruned = {}
    for k in tree:
      if k not in ('headers_lc', 'summary', 'conversation', 'tags',
                   'attachments'):
        pruned[k] = tree[k]
    pruned['tag_ids'] = tree['tags']
    pruned['summary'] = self.explain_msg_summary(tree['summary'])
    pruned['conversation'] = [self.explain_msg_summary(c)
                              for c in tree['conversation']]
    pruned['attachments'] = attachments = []
    for a in tree.get('attachments', []):
      att = {}
      att.update(a)
      del att['part']
      attachments.append(att)
    return pruned

  def display_message(self, email, tree, raw=False, sep='', fd=None):
    if raw:
      for line in email.get_file().readlines():
        try:
          line = line.decode('utf-8')
        except UnicodeDecodeError:
          try:
            line = line.decode('iso-8859-1')
          except:
            line = '(MAILPILE DECODING FAILED)\n'
        self.say(line, newline='', fd=fd)
    else:
      self.buffered_results.append(self.prune_message_tree(tree))

  def render_data(self, session, request_url, request_path):
    message = json.dumps(self.buffered_json, indent=1)
    return message, 'application/json'

  def render(self, session, request_url, request_path):
    message, mimetype = self.render_data(session, request_url, request_path)
    self.request.send_http_response(self.status_code,
                                  (self.status_code == 200) and "OK" or 'Error')
    self.request.send_header('Content-Length', len(message or ''))
    self.request.send_standard_headers(mimetype=mimetype, cachectrl='no-cache')
    self.request.wfile.write(message)
    self.request.log_request(self.status_code, message and len(message) or '-')


class xxXmlUI(xxJsonUI):

  ROOT_NAME = 'xml'
  ROOT_ATTRS = {'testing': True}
  EXPLAIN_XML = True
  BARE_LISTS = False

  def esc(self, d):
    d = unicode(d)
    d = d.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')
    return d.encode('utf-8')

  def render_xml_data(self, data, name='', attrs={}, indent=''):
    attrtext = ''
    if type(data) == type(dict()):
      data = self.render_xml_dict(data, indent=indent)+indent
      dtype = 'dict'
    elif type(data) == type(list()):
      data = self.render_xml_list(data, name=name, indent=indent)+indent
      dtype = 'list'
      if self.BARE_LISTS:
        return data
    elif type(data) == type(set()):
      data = self.render_xml_list(list(data), name=name, indent=indent)+indent
      dtype = 'set'
      if self.BARE_LISTS:
        return data
    else:
      data = self.esc(data)
      dtype = None
      if '\n' in data:
        attrtext += ' xml:space="preserve"'

    if self.EXPLAIN_XML:
      attrtext += dtype and (' type="%s"' % dtype) or ''
    for attr in attrs:
      attrtext += ' %s="%s"' % (attr, self.esc(attrs[attr]))

    if data.strip():
      return '%s<%s%s>%s</%s>' % (indent, name, attrtext, data, name)
    else:
      return '%s<%s%s/>' % (indent, name, attrtext)

  def render_xml_list(self, lst, name='items', indent=''):
    xml = ['']
    if name.endswith('s'):
      nh = name[:-1]
    else:
      nh = 'item'
    for item in lst:
      xml.append(self.render_xml_data(item, name=nh, indent=indent+' '))
    return '\n'.join(xml)+'\n'

  def render_xml_dict(self, dct, name='dict', indent=''):
    xml = ['']
    for name in dct.keys():
      xml.append(self.render_xml_data(dct[name], name=name, indent=indent+' '))
    return '\n'.join(xml)+'\n'

  def render_data(self, session, request_url, request_path):
    message = ('<?xml version="1.0"?>\n' +
               self.render_xml_data(self.buffered_json,
                                    name=self.ROOT_NAME,
                                    attrs=self.ROOT_ATTRS))
    return message, 'text/xml'


class xxRssUI(xxXmlUI):

  ROOT_NAME = 'rss'
  ROOT_ATTRS = {'version': '2.0'}
  EXPLAIN_XML = False
  BARE_LISTS = True

  def clear(self):
    xxXmlUI.clear(self)
    self.buffered_json = {
      "channel": {'items': self.buffered_results}
    }

  def explain_msg_summary(self, info):
    summary = xxXmlUI.explain_msg_summary(self, info)
    return {
      '_id': summary['id'],
      'title': summary['subject'],
      'link': summary['url'],
      'pubDate': summary['date']
    }

  def prune_message_tree(self, tree):
    r = {}
    r['items'] = [self.explain_msg_summary(c) for c in tree['conversation']]
    for item in r['items']:
      if item['_id'] == tree['id']:
        item['description'] = 'FIXME: Insert text body here, w/o quotes?'
    return r

  def render_data(self, session, request_url, request_path):
    # Reparent conversation list for single message
    if (len(self.buffered_results) > 0
    and 'items' in self.buffered_results[0]):
      self.buffered_results = self.buffered_results[0]['items']
      self.buffered_json['channel']['items'] = self.buffered_results

    # Make URLs absolute
    for item in self.buffered_results:
      item['link'] = '%s%s' % (request_url, item['link'])

    # Cleanup...
    for r in self.buffered_results:
      if 'tags' in r: del r['tags']
      if '_id' in r: del r['_id']

    # FIXME: Add channel info to buffered_json before rendering.

    return (xxXmlUI.render_data(self, session, request_url, request_path)[0],
            'application/rss+xml')


class xxHtmlUI(xxHttpUI):
  WIDTH = 110

  def __init__(self, request):
    xxHttpUI.__init__(self, request)
    self.buffered_html = []
    self.request = request

  def clear(self):
    self.buffered_html = []

  def say(self, text='', newline='\n', fd=None):
    # Just suppress the progress indicator chitter chatter
    if not text.endswith('\r'):
      self.buffered_html.append(('text', text+newline))

  def fmt(self, l):
    return l[1].replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')

  def transform_text(self):
    text = [self.fmt(l) for l in self.buffered_html if l[0] != 'html']
    self.buffered_html = [l for l in self.buffered_html if l[0] == 'html']
    self.buffered_html.append(('html', '<pre id="loglines">%s</pre>' % ''.join(text)))

  def render(self, session, request_url, path):
    config = session.config
    index = config.get_index(session)
    sidebar = ['<ul class="tag_list">']
    tids = config.get('tag', {}).keys()
    special = ['new', 'inbox', 'sent', 'drafts', 'spam', 'trash']
    def tord(k):
      tname = config['tag'][k]
      if tname.lower() in special:
        return '00000-%s-%s' % (special.index(tname.lower()), tname)
      return tname
    tids.sort(key=tord)
    for tid in tids:
      checked = ('tag:%s' % tid) in session.searched and ' checked' or ''
      checked1 = checked and ' checked="checked"' or ''
      tag_name = config.get('tag', {}).get(tid)
      tag_new = index.STATS.get(tid, [0,0])[1]
      sidebar.append((' <li id="tag_%s" class="%s">'
                      '<input type="checkbox" name="tag_%s"%s />'
                      ' <a href="/%s/">%s</a>'
                      ' <span class="tag_new %s">(<b>%s</b>)</span>'
                      '</li>') % (tid, checked, tid, checked1,
                                  tag_name, tag_name,
                                  tag_new and 'some' or 'none', tag_new))
    sidebar.append('</ul>')
    lastqpath = (path != '/' and path[1] not in ('=', '_') and path[:-1]
                 or '')
    variables = {
      'url': request_url,
      'lastq': self.post_data.get('lq', self.query_data.get('q',
                                  [lastqpath]))[0].strip().decode('utf-8'),
      'csrf': self.request.csrf(),
      'path': path
    }

    # FIXME: This title is dumb
    title = 'The biggest pile of mail EVAR!'

    self.request.send_full_response(self.render_page(config, variables,
                                                    title=title,
                                                   body=self.render_html(),
                                                  sidebar='\n'.join(sidebar)),
                                    suppress_body=False)

  def render_page(self, config, variables, body='', title='', sidebar=''):
    tpl = config.get('path', {}).get(self.request.http_host(), 'html_template')
    def r(part):
      return config.open_file(tpl, 'html/%s.html' % part)[1].read() % variables
    return ''.join([
      r('head'), '<title>', title, '</title>',
      r('body'), body,
      r('sidebar'), sidebar,
      r('tail')
    ])


  def render_html(self):
    self.transform_text()
    html = ''.join([l[1] for l in self.buffered_html])
    self.buffered_html = []
    return html

  def display_results(self, idx, results, terms,
                            start=0, end=None, num=None,
                            expand=None, fd=None):
    if not results: return (0, 0)

    num = num or 50
    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    count = 0
    nav = []
    if start > 0:
      bstart = max(1, start-num+1)
      nav.append(('<a href="/?q=/search%s %s">&lt;&lt; page back</a>'
                  ) % (bstart > 1 and (' @%d' % bstart) or '', ' '.join(terms)))
    else:
      nav.append('first page')
    nav.append('(about %d results)' % len(results))
    if start+num < len(results):
      nav.append(('<a href="/?q=/search @%d %s">next page &gt;&gt;</a>'
                  ) % (start+num+1, ' '.join(terms)))
    else:
      nav.append('last page')
    self.buffered_html.append(('html', ('<p id="rnavtop" class="rnav">%s &nbsp;'
                                        ' </p>\n') % ' '.join(nav)))

    self.buffered_html.append(('html', '<table class="results" id="results">\n'))
    expand_ids = [e.msg_idx for e in (expand or [])]
    for mid in results[start:start+num]:
      count += 1
      try:
        msg_info = idx.get_msg_by_idx(mid)

        all_msg_tags = [idx.config['tag'].get(t,t)
                        for t in idx.get_tags(msg_info=msg_info)]
        msg_tags = sorted([t for t in all_msg_tags
                           if 'tag:%s' % t not in terms])
        tag_classes = ['t_%s' % t.replace('/', '_') for t in msg_tags]
        msg_tags = ['<a href="/%s/">%s</a>' % (t, re.sub("^.*/", "", t))
                    for t in msg_tags]

        if expand and mid in expand_ids:
          self.buffered_html.append(('html', (' <tr class="result message %s">'
            '<td valign=top class="checkbox"><input type="checkbox" name="msg_%s" /></td>'
            '<td valign=top class="message" colspan=2>\n'
          ) % (
            (count % 2) and 'odd' or 'even',
            msg_info[idx.MSG_IDX],
          )))
          self.display_messages([expand[expand_ids.index(mid)]],
                                context=False, fd=fd, sep='');
          self.transform_text()

          msg_date = datetime.date.fromtimestamp(int(msg_info[idx.MSG_DATE], 36))
          self.buffered_html.append(('html', (
            '</td>'
            '<td valign=top class="tags">%s</td>'
            '<td valign=top class="date"><a href="?q=date:%4.4d-%d-%d">%4.4d-%2.2d-%2.2d</a></td>'
          '</tr>\n') % (
            ', '.join(msg_tags),
            msg_date.year, msg_date.month, msg_date.day,
            msg_date.year, msg_date.month, msg_date.day
          )))
        else:
          msg_subj = msg_info[idx.MSG_SUBJECT] or '(no subject)'

          if expand:
            msg_from = [msg_info[idx.MSG_FROM]]
            msg_date = [msg_info[idx.MSG_DATE]]
          else:
            conversation = idx.get_conversation(msg_info)
            msg_from = [r[idx.MSG_FROM] for r in conversation]
            msg_date = [r[idx.MSG_DATE] for r in conversation]

          msg_from = msg_from or ['(no sender)']
          msg_date = datetime.date.fromtimestamp(max([
                                                 int(d, 36) for d in msg_date]))

          edit = ('Drafts' in all_msg_tags) and 'edit.html' or ''
          self.buffered_html.append(('html', (' <tr class="result %s %s">'
            '<td class="checkbox"><input type="checkbox" name="msg_%s" /></td>'
            '<td class="from"><a href="/=%s/%s/%s">%s</a></td>'
            '<td class="subject"><a href="/=%s/%s/%s">%s</a></td>'
            '<td class="tags">%s</td>'
            '<td class="date"><a href="?q=date:%4.4d-%d-%d">%4.4d-%2.2d-%2.2d</a></td>'
          '</tr>\n') % (
            (count % 2) and 'odd' or 'even', ' '.join(tag_classes).lower(),
            msg_info[idx.MSG_IDX],
            msg_info[idx.MSG_IDX], msg_info[idx.MSG_ID], edit,
            self._compact(self._names(msg_from), 30),
            msg_info[idx.MSG_IDX], msg_info[idx.MSG_ID], edit,
            msg_subj,
            ', '.join(msg_tags),
            msg_date.year, msg_date.month, msg_date.day,
            msg_date.year, msg_date.month, msg_date.day,
          )))
      except (IndexError, ValueError):
        pass
    self.buffered_html.append(('html', '</table>\n'))
    self.buffered_html.append(('html', ('<p id="rnavbot" class="rnav">%s &nbsp;'
                                        ' </p>\n') % ' '.join(nav)))
    self.mark(('Listed %d-%d of %d results'
               ) % (start+1, start+count, len(results)))
    return (start, count)

  def display_message(self, email, tree, raw=False, sep='', fd=None):
    if raw:
      for line in email.get_file().readlines():
        try:
          line = line.decode('utf-8')
        except UnicodeDecodeError:
          try:
            line = line.decode('iso-8859-1')
          except:
            line = '(MAILPILE DECODING FAILED)\n'
        self.say(line, newline='', fd=fd)
    else:
      self.buffered_html.append(('html', '<div class=headers>'))
      for hdr in ('From', 'Subject', 'To', 'Cc'):
        value = email.get(hdr, '')
        if value:
          html = '<b>%s:</b> %s<br>' % (hdr, escape_html(value))
          self.buffered_html.append(('html', html))
      self.buffered_html.append(('html', '</div><br>'))

      if tree['text_parts']:
        self.buffered_html.append(('html', '<div class="message plain">'))
        last = '<bogus>'
        for part in tree['text_parts']:
          if part['data'] != last:
            self.buffered_html.append(self.fmt_part(part))
            last = part['data']
      else:
        self.buffered_html.append(('html', '<div class="message html">'))
        last = '<bogus>'
        for part in tree['html_parts']:
          if part['data'] != last:
            self.buffered_html.append(('html', autolink_html(part['data'])))
            last = part['data']
      if tree['attachments']:
        self.buffered_html.append(('html', '</div><div class="attachments"><ul>'))
        for att in tree['attachments']:
          desc = ('<a href="./att:%(count)s">Attachment: %(filename)s</a> '
                  '(%(mimetype)s, %(length)s bytes)') % att
          self.buffered_html.append(('html', '<li>%s</li>' % desc))
        self.buffered_html.append(('html', '</ul>'))
      self.buffered_html.append(('html', '</div>'))

  def fmt_part(self, part):
    what = [part['type'], escape_html(part['data'])]
    if what[0] == 'pgpbeginsigned':
      what[1] = ('<input type="submit" name="gpg_recvkey"'
                 ' value="Get PGP key and Verify">' + what[1])
    if what[0] in ('pgpsignature', 'pgpbeginsigned'):
      key_id = re.search('key ID ([0-9A-Fa-f]+)', what[1])
      if key_id:
        what[1] += ('<input type="hidden" name="gpg_key_id" value="0x%s">'
                    ) % key_id.group(1)

    return ('html', autolink_html('<p class="%s">%s</p>' % tuple(what)))

  def edit_messages(self, emails):
    for email in emails:
      if email.is_editable():
        es = email.get_editing_string()
        save_id = len(self.buffered_html)
        self.buffered_html.append(('html',
                                   '<div class=editing>'
                            '<input type=hidden name="save_%d_msg" value="%s">'
                              '<textarea name="@save_%d_data" cols=72 rows=20>'
                                   '' % (save_id, email.msg_mid(), save_id)))
        self.buffered_html.append(('html', escape_html(es)))
        self.buffered_html.append(('html', '</textarea><br>'
                                '<input type=submit name="save_%d" value=Save>'
                                '<input type=submit name="mail_%d" value=Send>'
                                           '</div>' % (save_id, save_id)))
      else:
        self.error('That message cannot be edited.')

  def display_vcard(self, vcard, compact=False):
    if compact:
      self.say('%s' % vcard)
    else:
      self.buffered_html.append(('html',
                        '<pre>%s</pre>' % escape_html(vcard.as_vCard())))


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

