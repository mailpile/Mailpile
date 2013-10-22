import datetime
import re
import time

import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import Email, ExtractEmails, MBX_ID_LEN
from mailpile.search import MailIndex
from mailpile.urlmap import UrlMap
from mailpile.util import *


class SearchResults(dict):
  def _explain_msg_summary(self, info):
    msg_ts = long(info[6], 36)
    days_ago = (time.time() - msg_ts) / (24*3600)
    msg_date = datetime.datetime.fromtimestamp(msg_ts)
    date = msg_date.strftime("%Y-%m-%d")
    urlmap = UrlMap(self.session)
    expl = {
      'mid': info[0],
      'id': info[1],
      'from': info[2],
      'from_email': ', '.join(ExtractEmails(info[2])),
      'to': info[3],
      'subject': info[4],
      'snippet': info[5],
      'timestamp': msg_ts,
      'shorttime': msg_date.strftime("%H:%M"),
      'date': date,
      'tag_ids': info[7],
      'url': urlmap.url_thread(info[0])
    }
    if info[8]:
      expl['editing_url'] = urlmap.url_edit(info[0])
    return expl

  def _prune_msg_tree(self, tree, context=True, parts=False, editable=False):
    pruned = {}
    prune = ['headers_lc', 'summary', 'tags', 'conversation', 'attachments']
    if not editable:
      prune.append('editing_string')
    for k in tree:
      if k not in prune:
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

  _NAME_TITLES = ('the', 'mr', 'ms', 'mrs', 'sir', 'dr', 'lord')

  def _name(self, sender, short=True, full_email=False):
    words = re.sub('["<>]', '', sender).split()
    nomail = [w for w in words if not '@' in w]
    if nomail:
      if short:
        if len(nomail) > 1 and nomail[0].lower() in self._NAME_TITLES:
          return nomail[1]
        return nomail[0]
      return ' '.join(nomail)
    elif words:
      if not full_email:
        return words[0].split('@', 1)[0]
      return words[0]
    return '(nobody)'

  def _names(self, senders):
    if len(senders) > 1:
      names = {}
      for sender in senders:
        sname = self._name(sender)
        names[sname] = names.get(sname, 0) + 1
      namelist = names.keys()
      namelist.sort(key=lambda n: -names[n])
      return ', '.join(namelist)
    if len(senders) < 1:
      return '(no sender)'
    if senders:
      return self._name(senders[0], short=False)
    return ''

  def _compact(self, namelist, maxlen):
    l = len(namelist)
    while l > maxlen:
      namelist = re.sub(', *[^, \.]+, *', ',,', namelist, 1)
      if l == len(namelist): break
      l = len(namelist)
    namelist = re.sub(',,,+, *', ' .. ', namelist, 1)
    return namelist

  def __init__(self, session, idx,
               results=None, start=0, end=None, num=None, expand=None):
    dict.__init__(self)
    self.session = session
    self.expand = expand
    self.idx = idx

    self['search_terms'] = terms = [t.decode('utf-8')
                                    for t in session.searched]
    if 'tags' in idx.config:
      self['search_tags'] = [idx.config.get_tag(t.split(':')[1], {})
                             for t in terms if t.startswith('in:')]

    results = results or session.results
    if not results:
      self._set_values([], 0, 0, 0)
      return

    num = num or session.config.get('num_results', 20)
    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    rv = []
    count = 0
    expand_ids = [e.msg_idx_pos for e in (expand or [])]
    for idx_pos in results[start:start+num]:
      count += 1
      msg_info = idx.get_msg_at_idx_pos(idx_pos)
      result = self._explain_msg_summary([
        msg_info[MailIndex.MSG_MID],
        msg_info[MailIndex.MSG_ID],
        msg_info[MailIndex.MSG_FROM],
        idx.expand_to_list(msg_info),
        msg_info[MailIndex.MSG_SUBJECT],
        msg_info[MailIndex.MSG_SNIPPET],
        msg_info[MailIndex.MSG_DATE],
        msg_info[MailIndex.MSG_TAGS].split(','),
        session.config.is_editable_message(msg_info)
      ])
      # FIXME: This is nice, but doing it in _explain_msg_summary
      #        would be nicer.
      result['tags'] = []
      if 'tags' in idx.config:
        searched = [t.get('slug') for t in self['search_tags']]
        for t in sorted(idx.get_tags(msg_info=msg_info)):
          tag = idx.config.get_tag(t)
          if tag:
            result['tags'].append(dict_merge(tag, {
              'searched': (tag['slug'] in searched)
            }))

      if not expand:
        conv = idx.get_conversation(msg_info)
      else:
        conv = [msg_info]
      conv_from = [c[MailIndex.MSG_FROM] for c in conv]

      result['short_from'] = self._compact(self._names(conv_from), 25)
      result['conv_count'] = len(conv)
      result['conv_mids'] = [c[MailIndex.MSG_MID] for c in conv]
      # FIXME: conv_people should look stuff in our contact list
      result['conv_people'] = people = [{
        'email': (ExtractEmails(p) or [''])[0],
        'name': self._name(p, short=False),
      } for p in list(set(conv_from))]
      people.sort(key=lambda i: i['name']+i['email'])

      if expand and idx_pos in expand_ids:
        exp_email = expand[expand_ids.index(idx_pos)]
        result['message'] = self._message_details([exp_email])[0]
      rv.append(result)

    self._set_values(rv, start, count, len(results))

  def _set_values(self, messages, start, count, total):
    self['messages'] = messages
    self['start'] = start+1
    self['count'] = count
    self['end'] = start+count
    self['total'] = total

  def __nonzero__(self):
    return True

  def next_set(self):
    return SearchResults(self.session, self.idx,
                         start=self['start'] - 1 + self['count'])
  def previous_set(self):
    return SearchResults(self.session, self.idx,
                         end=self['start'] - 1)

  def as_text(self):
    clen = max(3, len('%d' % len(self.session.results)))
    cfmt = '%%%d.%ds' % (clen, clen)
    text = []
    count = self['start']
    expand_ids = [e.msg_idx_pos for e in (self.expand or [])]
    for m in self['messages']:
      if 'message' in m:
        exp_email = self.expand[expand_ids.index(int(m['mid'], 36))]
        text.append(exp_email.get_editing_string(exp_email.get_message_tree()))
      else:
        tag_names = [t['name'] for t in m['tags'] if not t['searched']]
        msg_tags = tag_names and (' <' + '<'.join(tag_names)) or ''
        sfmt = '%%-%d.%ds%%s' % (46-(clen+len(msg_tags)),46-(clen+len(msg_tags)))
        text.append((cfmt+' %s %-20.20s '+sfmt
                     ) % (count, m['date'], m['short_from'], m['subject'],
                          msg_tags))
      count += 1
    if not count:
      text = ['(No messages found)']
    return '\n'.join(text)+'\n'


##[ Commands ]################################################################

class Search(Command):
  """Search your mail!"""
  SYNOPSIS = ('s', 'search', 'search', '[@<start>] <terms>')
  ORDER = ('Searching', 0)
  HTTP_CALLABLE = ('GET', )
  HTTP_QUERY_VARS = {
     'q': 'search terms',
     'order': 'sort order',
     'start': 'start position',
     'end': 'end position'
  }

  class CommandResult(Command.CommandResult):
    def __init__(self, *args, **kwargs):
      self.fixed_up = False
      return Command.CommandResult.__init__(self, *args, **kwargs)
    def _fixup(self):
      if self.fixed_up:
        return self
      self.fixed_up = True
      return self
    def as_text(self):
      if self.result:
        return self.result.as_text()
      else:
        return 'No results'
    def as_html(self, *args, **kwargs):
      return Command.CommandResult.as_html(self._fixup(), *args, **kwargs)
    def as_dict(self, *args, **kwargs):
      return Command.CommandResult.as_dict(self._fixup(), *args, **kwargs)

  def _do_search(self, search=None):
    session, idx = self.session, self._idx()
    session.searched = search or []
    args = self.args[:]

    for q in self.data.get('q', []):
      args.extend(q.split())

    for order in self.data.get('order', []):
      session.order = order

    num = int(session.config.get('num_results', 20))
    d_start = int(self.data.get('start', [0])[0])
    d_end = int(self.data.get('end', [0])[0])
    if d_start and d_end:
      args[:0] = ['@%s' % d_start]
      num = d_end - d_start + 1
    elif d_start:
      args[:0] = ['@%s' % d_start]
    elif d_end:
      args[:0] = ['@%s' % (d_end - num + 1)]

    if args and args[0].startswith('@'):
      spoint = args.pop(0)[1:]
      try:
        start = int(spoint)-1
      except ValueError:
        raise UsageError('Weird starting point: %s' % spoint)
    else:
      start = 0

    # FIXME: Is this dumb?
    for arg in args:
      if ':' in arg or (arg and arg[0] in ('-', '+')):
        session.searched.append(arg.lower())
      else:
        session.searched.extend(re.findall(WORD_REGEXP, arg.lower()))

    session.results = list(idx.search(session, session.searched))
    idx.sort_results(session, session.results, how=session.order)
    return session, idx, start, num

  def command(self, search=None):
    session, idx, start, num = self._do_search(search=search)
    session.displayed = SearchResults(session, idx, start=start, num=num)
    return session.displayed


class Next(Search):
  """Display next page of results"""
  SYNOPSIS = ('n', 'next', None, None)
  ORDER = ('Searching', 1)
  HTTP_CALLABLE = ( )

  def command(self):
    session = self.session
    session.displayed = session.displayed.next_set()
    return session.displayed


class Previous(Search):
  """Display previous page of results"""
  SYNOPSIS = ('p', 'previous', None, None)
  ORDER = ('Searching', 2)
  HTTP_CALLABLE = ( )

  def command(self):
    session = self.session
    session.displayed = session.displayed.previous_set()
    return session.displayed


class Order(Search):
  """Sort by: date, from, subject, random or index"""
  SYNOPSIS = ('o', 'order', None, '<how>')
  ORDER = ('Searching', 3)
  HTTP_CALLABLE = ( )

  def command(self):
    session, idx = self.session, self._idx()
    session.order = self.args and self.args[0] or None
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = SearchResults(session, idx)
    return session.displayed


class View(Search):
  """View one or more messages"""
  SYNOPSIS = ('v', 'view', 'message', '[raw] <message>')
  ORDER = ('Searching', 4)
  HTTP_QUERY_VARS = {
    'mid': 'metadata-ID'
  }

  class RawResult(dict):
    def _decode(self):
      try:
        return self['data'].decode('utf-8')
      except UnicodeDecodeError:
        try:
          return self['data'].decode('iso-8859-1')
        except:
          return '(MAILPILE FAILED TO DECODE MESSAGE)'
    def as_text(self, *args, **kwargs):
      return self._decode()
    def as_html(self, *args, **kwargs):
      return '<pre>%s</pre>' % escape_html(self._decode())

  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    results = []
    if self.args and self.args[0].lower() == 'raw':
      raw = self.args.pop(0)
    else:
      raw = False
    emails = [Email(idx, mid) for mid in self._choose_messages(self.args)]
    idx.apply_filters(session, '@read', msg_idxs=[e.msg_idx_pos for e in emails])
    for email in emails:
      if raw:
        results.append(self.RawResult({'data': email.get_file().read()}))
      else:
        conv = [int(c[0], 36)
                for c in idx.get_conversation(msg_idx=email.msg_idx_pos)]
        if email.msg_idx_pos not in conv:
          conv.append(email.msg_idx_pos)
        conv.reverse()
        results.append(SearchResults(session, idx,
                                     results=conv, num=len(conv),
                                     expand=[email]))
    if len(results) == 1:
      return results[0]
    else:
      return results


class Extract(Command):
  """Extract attachment(s) to file(s)"""
  SYNOPSIS = ('e', 'extract', 'message/download', '<att> <message> [><fn>]')
  ORDER = ('Searching', 5)

  class CommandResult(Command.CommandResult):
    def __init__(self, *args, **kwargs):
      self.fixed_up = False
      return Command.CommandResult.__init__(self, *args, **kwargs)
    def _fixup(self):
      if self.fixed_up:
        return self
      for result in (self.result or []):
        if 'data' in result:
          result['data'] = result['data'].encode('base64').replace('\n', '')
      self.fixed_up = True
      return self
    def as_html(self, *args, **kwargs):
      return Command.CommandResult.as_html(self._fixup(), *args, **kwargs)
    def as_dict(self, *args, **kwargs):
      return Command.CommandResult.as_dict(self._fixup(), *args, **kwargs)

  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()

    if self.args[0] in ('inline', 'inline-preview', 'preview', 'download'):
      mode = self.args.pop(0)
    else:
      mode = 'download'
    cid = self.args.pop(0)
    if len(self.args) > 0 and self.args[-1].startswith('>'):
      name_fmt = self.args.pop(-1)[1:]
    else:
      name_fmt = None

    emails = [Email(idx, i) for i in self._choose_messages(self.args)]
    results = []
    for email in emails:
      fn, info = email.extract_attachment(session, cid,
                                          name_fmt=name_fmt,
                                          mode=mode)
      if info:
        info['idx'] = email.msg_idx_pos
        if fn:
          info['created_file'] = fn
        results.append(info)
    return results


mailpile.plugins.register_commands(Extract, Next, Order, Previous,
                                   Search, View)


##[ Search terms ]############################################################

def mailbox_search(config, idx, term, hits):
    word = term.split(':', 1)[1].lower()
    try:
        mailbox_id = b36(int(word, 36))
    except ValueError:
        mailbox_id = None

    mailboxes = [m for m in config.sys.mailbox.keys()
                         if word in config.sys.mailbox[m].lower() or
                            mailbox_id == m]
    rt = []
    for mbox_id in mailboxes:
       mbox_id = (('0' * MBX_ID_LEN) + mbox_id)[-MBX_ID_LEN:]
       rt.extend(hits('%s:mailbox' % mbox_id))
    return rt


mailpile.plugins.register_search_term('mailbox', mailbox_search)
