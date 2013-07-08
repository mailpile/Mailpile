import datetime
import re

import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import Email
from mailpile.search import MailIndex
from mailpile.util import *


class SearchResults(dict):
  def _explain_msg_summary(self, info):
    msg_ts = long(info[4], 36)
    msg_date = datetime.date.fromtimestamp(msg_ts)
    return {
      'idx': info[0],
      'id': info[1],
      'from': info[2],
      'subject': info[3],
      'timestamp': msg_ts,
      'date': '%4.4d-%2.2d-%2.2d' % (msg_date.year, msg_date.month, msg_date.day),
      'tag_ids': info[5],
      'url': '/=%s/%s/' % (info[0], info[1])
    }

  def _prune_msg_tree(self, tree, context=True, parts=False):
    pruned = {}
    for k in tree:
      if k not in ('headers_lc', 'summary', 'tags', 'conversation',
                   'attachments'):
        pruned[k] = tree[k]
    pruned['tag_ids'] = tree['tags']
    pruned['summary'] = self._explain_msg_summary(tree['summary'])
    if context:
      pruned['conversation'] = [self._explain_msg_summary(c)
                                for c in tree['conversation']]
    pruned['attachments'] = attachments = []
    for a in tree.get('attachments', []):
      att = {}
      att.update(a)
      if not parts:
        del att['part']
      attachments.append(att)
    return pruned

  def _message_details(self, emails, context=True):
    results = []
    for email in emails:
      tree = email.get_message_tree()
      email.evaluate_pgp(tree, decrypt=True)
      results.append(self._prune_msg_tree(tree, context=context))
    return results

  def __init__(self, session, idx,
               results=None, start=0, end=None, num=None, expand=None):
    dict.__init__(self)
    self.session = session
    self.idx = idx

    results = results or session.results
    if not results:
      self._set_values([], 0, 0, 0)
      return

    terms = session.searched
    num = num or session.config.get('num_results', 20)
    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    rv = []
    count = 0
    expand_ids = [e.msg_idx for e in (expand or [])]
    for mid in results[start:start+num]:
      count += 1
      msg_info = idx.get_msg_by_idx(mid)
      result = self._explain_msg_summary([
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
        exp_ids = [expand[expand_ids.index(mid)]]
        result['message'] = self._message_details(exp_ids)[0]
      rv.append(result)

    self._set_values(rv, start, count, len(results))

  def _set_values(self, messages, start, count, total):
    self['messages'] = messages
    self['start'] = start+1
    self['count'] = count
    self['end'] = start+count
    self['total'] = total

  def next_set(self):
    return SearchResults(self.session, self.idx,
                         start=self['start'] - 1 + self['count'])
  def previous_set(self):
    return SearchResults(self.session, self.idx,
                         end=self['start'] - 1)

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
      if 'message' in m:
        text.append('%s' % m['message'])
      else:
        msg_tags = m['tags'] and (' <' + '<'.join(m['tags'])) or ''
        sfmt = '%%-%d.%ds%%s' % (41-(clen+len(msg_tags)),41-(clen+len(msg_tags)))
        text.append((cfmt+' %s %-25.25s '+sfmt
                     ) % (count, m['date'],
                    self._compact(self._names([m['from'] or '(no sender)']), 25),
                          m['subject'], msg_tags))
      count += 1
    return '\n'.join(text)+'\n'


##[ Commands ]################################################################

class Search(Command):
  """Search your mail!"""
  ORDER = ('Searching', 0)
  TEMPLATE_ID = 'search'
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
  class CommandResult(Command.CommandResult):
    def as_text(self):
      return ('\n%s\n' % ('=' * self.session.ui.MAX_WIDTH)
              ).join([r.as_text() for r in self.result])

  class RawResult(dict):
    def as_text(self):
      try:
        return self['data'].decode('utf-8')
      except UnicodeDecodeError:
        try:
          return self['data'].decode('iso-8859-1')
        except:
          return '(MAILPILE FAILED TO DECODE MESSAGE)'

  SYNOPSIS = '<[raw] m1 ...>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    results = []
    if self.args and self.args[0].lower() == 'raw':
      raw = self.args.pop(0)
    else:
      raw = False
    emails = [Email(idx, i) for i in self._choose_messages(self.args)]
    idx.apply_filters(session, '@read', msg_idxs=[e.msg_idx for e in emails])
    for email in emails:
      if raw:
        results.append(self.RawResult({'data': email.get_file().read()}))
      else:
        conv = [int(c[0], 36) for c in email.get_message_tree()['conversation']]
        results.append(SearchResults(session, idx,
                                     results=conv, num=len(conv),
                                     expand=[email]))
    return results


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


mailpile.plugins.register_command('d:', 'delete=',  Delete)
mailpile.plugins.register_command('s:', 'search=',  Search)
mailpile.plugins.register_command('n:', 'next=',    Next)
mailpile.plugins.register_command('e:', 'extract=', Extract)
mailpile.plugins.register_command('n',  'next',     Next)
mailpile.plugins.register_command('o:', 'order',    Order)
mailpile.plugins.register_command('p',  'previous', Previous)
mailpile.plugins.register_command('v:', 'view',     View)

