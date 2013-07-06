import datetime
import re

import mailpile.plugins
from mailpile.commands import Command
from mailpile.search import MailIndex
from mailpile.util import *


def explain_msg_summary(info):
  return {
    'idx': info[0],
    'id': info[1],
    'from': info[2],
    'subject': info[3],
    'date': long(info[4], 36),
    'tag_ids': info[5],
    'url': '/=%s/%s/' % (info[0], info[1])
  }

def message_details(session, idx, emails, raw=False, context=True):
  return {'FIXME': 'FIXME'}

class SearchResults(dict):
  def __init__(self, session, idx,
               results=None, start=0, end=None, expand=None):
    dict.__init__(self)
    self.session = session
    self.idx = idx

    results = results or session.results
    if not results:
      return (0, 0), []

    terms = session.searched
    num = session.config.get('num_results', 20)
    if end: start = end - num
    if start > len(session.results): start = len(session.results)
    if start < 0: start = 0

    rv = []
    count = 0
    expand_ids = [e.msg_idx for e in (expand or [])]
    for mid in session.results[start:start+num]:
      count += 1
      msg_info = idx.get_msg_by_idx(mid)
      result = explain_msg_summary([
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
      if expand and mid in expand_ids:
        result['message'] = message_details([expand[expand_ids.index(mid)]],
                                            context=False)
      rv.append(result)

    self['messages'] = rv
    self['start'] = start
    self['count'] = num

  def next_set(self):
    return SearchResults(self.session, self.idx,
                         start=self['start'] + self['count'])
  def previous_set(self):
    return SearchResults(self.session, self.idx,
                         end=self['start'])
 
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

  def as_text(self):
    clen = max(3, len('%d' % len(self.session.results)))
    cfmt = '%%%d.%ds' % (clen, clen)
    text = []
    count = self['start']
    for m in self['messages']:
      msg_date = datetime.date.fromtimestamp(m['date'])
      msg_tags = m['tags'] and (' <' + '<'.join(m['tags'])) or ''
      sfmt = '%%-%d.%ds%%s' % (41-(clen+len(msg_tags)),41-(clen+len(msg_tags)))
      text.append((cfmt+' %4.4d-%2.2d-%2.2d %-25.25s '+sfmt
                   ) % (count,
                        msg_date.year, msg_date.month, msg_date.day,
                  self._compact(self._names([m['from'] or '(no sender)']), 25),
                        m['subject'], msg_tags))
      count += 1
    return '\n'.join(text)+'\n'


##[ Commands ]################################################################

class Search(Command):
  """Search your mail!"""
  ORDER = ('Searching', 0)
  class CommandResult(Command.CommandResult):
    def as_text(self):
      return self.result.as_text()

  SYNOPSIS = '<terms ...>'
  def command(self, search=None):
    session, idx = self.session, self._idx()
    session.searched = search or []

    if self.args and self.args[0].startswith('@'):
      try:
        start = int(self.args.pop(0)[1:])-1
      except ValueError:
        raise UsageError('Weird starting point')
    else:
      start = 0

    # FIXME: Is this dumb?
    for arg in self.args:
      if ':' in arg or (arg and arg[0] in ('-', '+')):
        session.searched.append(arg.lower())
      else:
        session.searched.extend(re.findall(WORD_REGEXP, arg.lower()))

    session.results = list(idx.search(session, session.searched))
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = SearchResults(session, idx, start=start)
    return session.displayed

class Next(Search):
  """Display next page of results"""
  ORDER = ('Searching', 1)
  def command(self):
    session = self.session
    session.displayed = session.displayed.next_set()
    return session.displayed

class Previous(Search):
  """Display previous page of results"""
  ORDER = ('Searching', 2)
  def command(self):
    session = self.session
    session.displayed = session.displayed.previous_set()
    return session.displayed

class Order(Search):
  """Sort by: date, from, subject, random or index"""
  ORDER = ('Searching', 3)
  SYNOPSIS = '<terms ...>'
  def command(self):
    session, idx = self.session, self._idx()
    session.order = self.args and self.args[0] or None
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = SearchResults(session, idx)
    return session.displayed


class View(Command):
  """View one or more messages"""
  ORDER = ('Searching', 4)
  SYNOPSIS = '<[raw] m1 ...>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    if self.args and self.args[0].lower() == 'raw':
      raw = self.args.pop(0)
    else:
      raw = False
    emails = [Email(idx, i) for i in self._choose_messages(self.args)]
    if emails:
      idx.apply_filters(session, '@read', msg_idxs=[e.msg_idx for e in emails])
      session.ui.clear()
      session.ui.display_messages(emails, raw=raw)
    return True


class Extract(Command):
  """Extract attachment(s) to file(s)"""
  ORDER = ('Searching', 5)
  SYNOPSIS = '<att msg [>fn]>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    cid = self.args.pop(0)
    if len(self.args) > 0 and self.args[-1].startswith('>'):
      name_fmt = self.args.pop(-1)[1:]
    else:
      name_fmt = None
    emails = [Email(idx, i) for i in self._choose_messages(self.args)]
    for email in emails:
      email.extract_attachment(session, cid, name_fmt=name_fmt)
    return True


class Delete(Command):
  """Delete a message from the index"""
  ORDER = ('Searching', 6)
  SYNOPSIS = '<msg>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    raise Exception('Unimplemented')


mailpile.plugins.register_command('s:', 'search=',  Search)
mailpile.plugins.register_command('n:', 'next=',    Next) 
mailpile.plugins.register_command('e:', 'extract=', Extract)
mailpile.plugins.register_command('n',  'next',     Next)
mailpile.plugins.register_command('o:', 'order',    Order)
mailpile.plugins.register_command('p',  'previous', Previous)

