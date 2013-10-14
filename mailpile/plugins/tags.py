import mailpile.plugins
from mailpile.commands import Command
from mailpile.urlmap import UrlMap
from mailpile.util import *

from mailpile.plugins.search import Search


##[ Configuration ]###########################################################

mailpile.plugins.register_config_section('tags', ["Tags", {
    'name': ['Tag name', 'str', ''],
    'slug': ['URL slug', 'slug', ''],
}, []])

mailpile.plugins.register_config_variables('sys', {
    'writable_tags': ['Tags used to mark writable messages', 'b36', []]
})



##[ Commands ]################################################################

class TagCommand(Command):

  class CommandResult(Command.CommandResult):
    def _tags_as_text(self):
      tags = self.result['tags']
      wrap = int(78/23) # FIXME: Magic number
      text = []
      for i in range(0, len(tags)):
        text.append(('%s%5.5s %-18.18s'
                     ) % ((i%wrap) == 0 and '  ' or '',
                     '%s' % (tags[i]['new'] or ''),
                     tags[i]['name'])
                   + ((i%wrap)==(wrap-1) and '\n' or ''))
      return ''.join(text)+'\n'
    def _added_as_text(self):
      return ('Added tags: '
             +', '.join([k['name'] for k in self.result['added']]))
    def _removed_as_text(self):
      return ('Removed tags: '
             +', '.join([k['name'] for k in self.result['removed']]))
    def _tagging_as_text(self):
      what = []
      if self.result['tagged']:
        what.append('Tagged ' +
                    ', '.join([k['name'] for k in self.result['tagged']]))
      if self.result['untagged']:
        what.append('Untagged ' +
                    ', '.join([k['name'] for k in self.result['untagged']]))
      return '%s (%d messages)' % (', '.join(what), len(self.result['msg_ids']))
    def as_text(self):
      if not self.result:
        return 'Failed'
      return ''.join([
        ('added' in self.result) and self._added_as_text() or '',
        ('removed' in self.result) and self._removed_as_text() or '',
        ('tags' in self.result) and self._tags_as_text() or '',
        ('msg_ids' in self.result) and self._tagging_as_text() or '',
      ])


class Tag(TagCommand):
  """Add or remove tags on a set of messages"""
  SYNOPSIS = (None, 'tag', 'tag', '<[+|-]tags> <msgs>')
  ORDER = ('Tagging', 0)
  HTTP_CALLABLE = ('POST', )
  HTTP_POST_VARS = {
    'mid': 'message-ids',
    'add': 'tags',
    'del': 'tags'
  }

  def command(self, save=True):
    idx = self._idx()

    if 'mid' in self.data:
      msg_ids = [int(m.replace('=', ''), 36) for m in self.data['mid']]
      ops = (['+%s' % t for t in self.data.get('add', [])] +
             ['-%s' % t for t in self.data.get('del', [])])
    else:
      words = self.args[:]
      ops = []
      while words and words[0][0] in ('-', '+'):
        ops.append(words.pop(0))
      msg_ids = self._choose_messages(words)

    rv = {'msg_ids': [], 'tagged': [], 'untagged': []}
    rv['msg_ids'] = [b36(i) for i in msg_ids]
    for op in ops:
      tag_id = self.session.config.get_tag_id(op[1:])
      if op[0] == '-':
        idx.remove_tag(self.session, tag_id, msg_idxs=msg_ids, conversation=True)
        rv['untagged'].append({'name': op[1:], 'tid': tag_id})
      else:
        idx.add_tag(self.session, tag_id, msg_idxs=msg_ids, conversation=True)
        rv['tagged'].append({'name': op[1:], 'tid': tag_id})

    if save:
      # Background save makes things feel fast!
      def background():
        idx.update_tag_stats(self.session, self.session.config)
        idx.save_changes()
      self._background('Save index', background)
    else:
      idx.update_tag_stats(self.session, self.session.config)

    return rv


class AddTag(TagCommand):
  """Create a new tag"""
  SYNOPSIS = (None, 'tag/add', 'tag/add', '<tag>')
  ORDER = ('Tagging', 0)
  HTTP_CALLABLE = ('POST', )
  HTTP_POST_VARS = {
      'name': 'tag name',
      'slug': 'tag slug',
  }

  def command(self):
    config = self.session.config
    existing = [v.lower() for v in config.get('tag', {}).values()]
    creating = (self.args or []) + self.data.get('name', [])
    for tag in creating:
      if ' ' in tag:
        return self._error('Invalid tag: %s' % tag)
      if tag.lower() in existing:
        return self._error('Tag already exists: %s' % tag)
    result = []
    for tag in sorted(creating):
      if config.parse_set(self.session, 'tag:%s=%s' % (config.nid('tag'), tag)):
        result.append({'name': tag, 'tid': config.get_tag_id(tag), 'new': 0})
    if result:
      self._background('Save config', lambda: config.save())
    return {'added': result}


class ListTags(TagCommand):
  """List tags"""
  SYNOPSIS = (None, 'tag/list', 'tag/list', '[<wanted>|!<wanted>] [...]')
  ORDER = ('Tagging', 0)
  HTTP_QUERY_VARS = {
    'only': 'tags',
    'not': 'tags',
  }

  def command(self):
    result, idx = [], self._idx()

    wanted = [t.lower() for t in self.args if not t.startswith('!')]
    unwanted = [t[1:].lower() for t in self.args if t.startswith('!')]
    wanted.extend([t.lower() for t in self.data.get('only', [])])
    unwanted.extend([t.lower() for t in self.data.get('not', [])])

    for tid, tag in self.session.config.get('tag', {}).iteritems():
      if wanted and tag.lower() not in wanted: continue
      if unwanted and tag.lower() in unwanted: continue
      result.append({
        'name': tag,
        'tid': tid,
        'url': UrlMap(self.session).url_tag(tid),
        'all': int(idx.STATS.get(tid, [0, 0])[0]),
        'new': int(idx.STATS.get(tid, [0, 0])[1]),
        'not': len(idx.INDEX) - int(idx.STATS.get(tid, [0, 0])[0])
      })
    result.sort(key=lambda k: k['name'])
    return {'tags': result}


class DeleteTag(TagCommand):
  """Delete a tag"""
  SYNOPSIS = (None, 'tag/delete', 'tag/delete', '<tag>')
  ORDER = ('Tagging', 0)
  HTTP_CALLABLE = ('POST', 'DELETE')

  def command(self):
    session, config = self.session, self.session.config
    existing = [v.lower() for v in config.get('tag', {}).values()]
    clean_session = mailpile.ui.Session(config)
    clean_session.ui = session.ui
    result = []
    for tag in self.args:
      tag_id = config.get_tag_id(tag)
      if tag_id:
        # FIXME: Update filters too
        if (Search(clean_session, arg=['tag:%s' % tag]).run()
        and Tag(clean_session, arg=['-%s' % tag, 'all']).run()
        and config.parse_unset(session, 'tag:%s' % tag_id)):
          result.append({'name': tag, 'tid': tag_id})
        else:
          raise Exception('That failed, not sure why?!')
      else:
        self._error('No such tag %s' % tag)
    if result:
      config.save()
    return {'removed': result}


class Filter(Command):
  """Add auto-tag rule for current search or terms"""
  SYNOPSIS = (None, 'filter', None,
              '[new|read] [notag] [=<mid>] '
              '[<terms>] [+<tag>] [-<tag>] [<comment>]')
  ORDER = ('Tagging', 1)
  HTTP_CALLABLE = ('POST', )

  def command(self):
    args, session, config = self.args, self.session, self.session.config

    flags = []
    while args and args[0] in ('add', 'set', 'new', 'read', 'notag'):
      flags.append(args.pop(0))

    if args and args[0] and args[0][0] == '=':
      filter_id = args.pop(0)[1:]
    else:
      filter_id = config.nid('filter')

    auto_tag = False
    if 'read' in flags:
      terms = ['@read']
    elif 'new' in flags:
      terms = ['*']
    elif args[0] and args[0][0] not in ('-', '+'):
      terms = []
      while args and args[0][0] not in ('-', '+'):
        terms.append(args.pop(0))
    else:
      terms = session.searched
      auto_tag = True

    if not terms or (len(args) < 1):
      raise UsageError('Need flags and search terms or a hook')

    tags, tids = [], []
    while args and args[0][0] in ('-', '+'):
      tag = args.pop(0)
      tags.append(tag)
      tids.append(tag[0]+config.get_tag_id(tag[1:]))

    if not args:
      args = ['Filter for %s' % ' '.join(tags)]

    if auto_tag and 'notag' not in flags:
      if not Tag(session, arg=tags + ['all']).run(save=False):
        raise UsageError()

    if (config.parse_set(session, ('filter:%s=%s'
                                   ) % (filter_id, ' '.join(args)))
    and config.parse_set(session, ('filter_tags:%s=%s'
                                   ) % (filter_id, ' '.join(tids)))
    and config.parse_set(session, ('filter_terms:%s=%s'
                                   ) % (filter_id, ' '.join(terms)))):
      def save_filter():
        config.save()
        if config.index: config.index.save_changes()
        return True
      self._serialize('Save filter', save_filter)
      return True
    else:
      raise Exception('That failed, not sure why?!')


class DeleteFilter(Command):
  """Delete an auto-tagging rule"""
  SYNOPSIS = (None, 'filter/delete', None, '<filter-id>')
  ORDER = ('Tagging', 1)
  HTTP_CALLABLE = ('POST', 'DELETE')

  def command(self):
    session, config = self.session, self.session.config
    if len(self.args) < 1:
      raise UsageError('Delete what?')

    removed = 0
    filters = config.get('filter', {})
    filter_terms = config.get('filter_terms', {})
    for fid in self.args[:]:
      if fid not in filters:
        match = [f for f in filters if filter_terms[f] == fid]
        if match:
          self.args.remove(fid)
          self.args.extend(match)

    for fid in self.args:
      if (config.parse_unset(session, 'filter:%s' % fid)
      and config.parse_unset(session, 'filter_tags:%s' % fid)
      and config.parse_unset(session, 'filter_terms:%s' % fid)):
        removed += 1
      else:
        session.ui.warning('Failed to remove %s' % fid)
    if removed:
      config.save()
    return True


class ListFilters(Command):
  """List (all) auto-tagging rules"""
  SYNOPSIS = (None, 'filter/list', 'filter/list', '[<search>|=<id>]')
  ORDER = ('Tagging', 1)

  class CommandResult(Command.CommandResult):
    def as_text(self):
      if self.result is False:
        return unicode(self.result)
      return '\n'.join([' %3.3s %-20s %-25s %s' % (
                          r['fid'], r['terms'], r['human_tags'], r['comment']
                        ) for r in self.result])

  def command(self, want_fid=None):
    results = []
    for fid, trms, tags, cmnt in self.session.config.get_filters(filter_on=None):
      if want_fid and fid != want_fid:
        continue

      human_tags = []
      for tterm in tags.split():
        tagname =  self.session.config.get('tag', {}).get(tterm[1:], '(None)')
        human_tags.append('%s%s' % (tterm[0], tagname))

      skip = False
      if self.args and not want_fid:
        for term in self.args:
          term = term.lower()
          if term.startswith('='):
            if (term[1:] != fid):
              skip = True
          elif ((term not in ' '.join(human_tags).lower()) and
                (term not in trms.lower()) and
                (term not in cmnt.lower())):
            skip = True
      if skip:
        continue

      results.append({
        'fid': fid,
        'terms': trms,
        'tags': tags,
        'human_tags': ' '.join(human_tags),
        'comment': cmnt
      })
    return results


class MoveFilter(ListFilters):
  """Move an auto-tagging rule"""
  SYNOPSIS = (None, 'filter/move', None, '<filter-id> <position>')
  ORDER = ('Tagging', 1)
  HTTP_CALLABLE = ('POST', 'UPDATE')

  def command(self):
    self.session.config.filter_move(self.args[0], self.args[1])
    self.session.config.save()
    return ListFilters.command(self, want_fid=self.args[1])


mailpile.plugins.register_commands(Tag, AddTag, DeleteTag, ListTags)
mailpile.plugins.register_commands(Filter, DeleteFilter,
                                   MoveFilter, ListFilters)
