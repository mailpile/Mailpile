#!/usr/bin/python
#
# Basic user-interface stuff
#
import datetime, re, sys

from mailpile.util import *


class NullUI(object):

  WIDTH = 80
  interactive = False
  buffering = False

  def __init__(self):
    self.buffered = []

  def print_key(self, key, config): pass
  def reset_marks(self, quiet=False): pass
  def mark(self, progress): pass

  def flush(self):
    while len(self.buffered) > 0:
      self.buffered.pop(0)()

  def block(self):
    self.buffering = True

  def unblock(self):
    self.flush()
    self.buffering = False

  def say(self, text='', newline='\n', fd=sys.stdout):
    def sayit():
      fd.write(text.encode('utf-8')+newline)
      fd.flush()
    self.buffered.append(sayit)
    if not self.buffering: self.flush()

  def notify(self, message):
    self.say('%s%s' % (message, ' ' * (self.WIDTH-1-len(message))))
  def warning(self, message):
    self.say('Warning: %s%s' % (message, ' ' * (self.WIDTH-11-len(message))))
  def error(self, message):
    self.say('Error: %s%s' % (message, ' ' * (self.WIDTH-9-len(message))))

  def print_intro(self, help=False, http_worker=None):
    if http_worker:
      http_status = 'on: http://%s:%s/' % http_worker.httpd.sspec
    else:
      http_status = 'disabled.'
    self.say('\n'.join([ABOUT,
                        'The web interface is %s' % http_status,
                        '',
                        'For instructions type `help`, press <CTRL-D> to quit.',
                        '']))

  def print_help(self, commands, tags=None, index=None):
    self.say('Commands:')
    last_rank = None
    cmds = commands.keys()
    cmds.sort(key=lambda k: commands[k][3])
    for c in cmds:
      cmd, args, explanation, rank = commands[c]
      if not rank: continue

      if last_rank and int(rank/10) != last_rank: self.say()
      last_rank = int(rank/10)

      self.say('    %s|%-8.8s %-15.15s %s' % (c[0], cmd.replace('=', ''),
                                              args and ('<%s>' % args) or '',
                                              explanation))
    if tags and index:
      self.say('\nTags:  (use a tag as a command to display tagged messages)',
               '\n  ')
      tkeys = tags.keys()
      tkeys.sort(key=lambda k: tags[k])
      wrap = int(self.WIDTH / 23)
      for i in range(0, len(tkeys)):
        tid = tkeys[i]
        self.say(('%5.5s %-18.18s'
                  ) % ('%s' % (int(index.STATS.get(tid, [0, 0])[1]) or ''),
                       tags[tid]),
                 newline=(i%wrap)==(wrap-1) and '\n  ' or '')
    self.say('\n')

  def print_filters(self, config):
    w = int(self.WIDTH * 23/80)
    ffmt = ' %%3.3s %%-%d.%ds %%-%d.%ds %%s' % (w, w, w-2, w-2)
    self.say(ffmt % ('ID', ' Tags', 'Terms', ''))
    for fid, terms, tags, comment in config.get_filters():
      self.say(ffmt % (fid,
        ' '.join(['%s%s' % (t[0], config['tag'][t[1:]]) for t in tags.split()]),
                       (terms == '*') and '(all new mail)' or terms or '(none)',
                       comment or '(none)'))

  def display_messages(self, emails, raw=False, sep='', fd=sys.stdout):
    for email in emails:
      self.say(sep, fd=fd)
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
        for hdr in ('Date', 'To', 'From', 'Subject'):
          self.say('%s: %s' % (hdr, email.get(hdr, '(unknown)')), fd=fd)
        self.say('\n%s' % email.get_body_text(), fd=fd)


class TextUI(NullUI):
  def __init__(self):
    NullUI.__init__(self)
    self.times = []

  def print_key(self, key, config):
    if ':' in key:
      key, subkey = key.split(':', 1)
    else:
      subkey = None

    if key in config:
      if key in config.INTS:
        self.say('%s = %s (int)' % (key, config.get(key)))
      else:
        val = config.get(key)
        if subkey:
          if subkey in val:
            self.say('%s:%s = %s' % (key, subkey, val[subkey]))
          else:
            self.say('%s:%s is unset' % (key, subkey))
        else:
          self.say('%s = %s' % (key, config.get(key)))
    else:
      self.say('%s is unset' % key)

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

  def name(self, sender):
    words = re.sub('["<>]', '', sender).split()
    nomail = [w for w in words if not '@' in w]
    if nomail: return ' '.join(nomail)
    return ' '.join(words)

  def names(self, senders):
    if len(senders) > 3:
      return re.sub('["<>]', '', ','.join([x.split()[0] for x in senders]))
    return ','.join([self.name(s) for s in senders])

  def compact(self, namelist, maxlen):
    l = len(namelist)
    while l > maxlen:
      namelist = re.sub(',[^, \.]+,', ',,', namelist, 1)
      if l == len(namelist): break
      l = len(namelist)
    namelist = re.sub(',,,+,', ' .. ', namelist, 1)
    return namelist

  def display_results(self, idx, results, terms,
                            start=0, end=None, num=None):
    if not results: return (0, 0)

    num = num or 20
    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    clen = max(3, len('%d' % len(results)))
    cfmt = '%%%d.%ds' % (clen, clen)

    count = 0
    for mid in results[start:start+num]:
      count += 1
      try:
        msg_info = idx.get_msg_by_idx(mid)
        msg_subj = msg_info[idx.MSG_SUBJECT]

        msg_from = [msg_info[idx.MSG_FROM]]
        msg_from.extend([r[idx.MSG_FROM] for r in idx.get_replies(msg_info)])

        msg_date = [msg_info[idx.MSG_DATE]]
        msg_date.extend([r[idx.MSG_DATE] for r in idx.get_replies(msg_info)])
        msg_date = datetime.date.fromtimestamp(max([
                                                int(d, 36) for d in msg_date]))

        msg_tags = '<'.join(sorted([re.sub("^.*/", "", idx.config['tag'].get(t, t))
                                    for t in idx.get_tags(msg_info=msg_info)]))
        msg_tags = msg_tags and (' <%s' % msg_tags) or '  '

        sfmt = '%%-%d.%ds%%s' % (41-(clen+len(msg_tags)),41-(clen+len(msg_tags)))
        self.say((cfmt+' %4.4d-%2.2d-%2.2d %-25.25s '+sfmt
                  ) % (start + count,
                       msg_date.year, msg_date.month, msg_date.day,
                       self.compact(self.names(msg_from), 25),
                       msg_subj, msg_tags))
      except (IndexError, ValueError):
        self.say('-- (not in index: %s)' % mid)
    self.mark(('Listed %d-%d of %d results'
               ) % (start+1, start+count, len(results)))
    return (start, count)

  def display_messages(self, emails, raw=False, sep='', fd=None):
    if not fd and self.interactive:
      viewer = subprocess.Popen(['less'], stdin=subprocess.PIPE)
      fd = viewer.stdin
    else:
      fd = sys.stdout
      viewer = None
    try:
      NullUI.display_messages(self, emails, raw=raw, sep=('_' * self.WIDTH), fd=fd)
    except IOError, e:
      pass
    if viewer:
      fd.close()
      viewer.wait()


class HtmlUI(TextUI):

  WIDTH = 110

  def __init__(self):
    TextUI.__init__(self)
    self.buffered_html = []

  def say(self, text='', newline='\n', fd=None):
    if text.startswith('\r') and self.buffered_html:
      self.buffered_html[-1] = ('text', (text+newline).replace('\r', ''))
    else:
      self.buffered_html.append(('text', text+newline))

  def fmt(self, l):
    return l[1].replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')

  def render_html(self):
    html = ''.join([l[1] for l in self.buffered_html if l[0] == 'html'])
    html += '<br /><pre>%s</pre>' % ''.join([self.fmt(l)
                                             for l in self.buffered_html
                                             if l[0] != 'html'])
    self.buffered_html = []
    return html

  def display_results(self, idx, results, terms,
                            start=0, end=None, num=None):
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

    self.buffered_html.append(('html', '<table class="results">\n'))
    for mid in results[start:start+num]:
      count += 1
      try:
        msg_info = idx.get_msg_by_idx(mid)
        msg_subj = msg_info[idx.MSG_SUBJECT] or '(no subject)'

        msg_from = [msg_info[idx.MSG_FROM]]
        msg_from.extend([r[idx.MSG_FROM] for r in idx.get_replies(msg_info)])
        msg_from = msg_from or ['(no sender)']

        msg_date = [msg_info[idx.MSG_DATE]]
        msg_date.extend([r[idx.MSG_DATE] for r in idx.get_replies(msg_info)])
        msg_date = datetime.date.fromtimestamp(max([
                                                int(d, 36) for d in msg_date]))

        msg_tags = sorted([idx.config['tag'].get(t,t)
                           for t in idx.get_tags(msg_info=msg_info)
                           if 'tag:%s' % t not in terms])
        tag_classes = ['t_%s' % t.replace('/', '_') for t in msg_tags]
        msg_tags = ['<a href="/%s/">%s</a>' % (t, re.sub("^.*/", "", t))
                    for t in msg_tags]

        self.buffered_html.append(('html', (' <tr class="result %s %s">'
          '<td class="checkbox"><input type="checkbox" name="msg_%s" /></td>'
          '<td class="from"><a href="/=%s/%s/">%s</a></td>'
          '<td class="subject"><a href="/=%s/%s/">%s</a></td>'
          '<td class="tags">%s</td>'
          '<td class="date"><a href="?q=date:%4.4d-%d-%d">%4.4d-%2.2d-%2.2d</a></td>'
        '</tr>\n') % (
          (count % 2) and 'odd' or 'even', ' '.join(tag_classes).lower(),
          msg_info[idx.MSG_IDX],
          msg_info[idx.MSG_IDX], msg_info[idx.MSG_ID],
          self.compact(self.names(msg_from), 25),
          msg_info[idx.MSG_IDX], msg_info[idx.MSG_ID],
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


class Session(object):

  main = False
  interactive = False

  ui = NullUI()
  order = None

  def __init__(self, config):
    self.config = config
    self.wait_lock = threading.Condition()
    self.results = []
    self.searched = []
    self.displayed = (0, 0)
    self.task_results = []

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
    if not self.interactive: sys.exit(1)

