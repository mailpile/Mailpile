import mailpile.plugins
import mailpile.config
from mailpile.commands import Command
from mailpile.urlmap import UrlMap
from mailpile.util import *

from mailpile.plugins.search import Search


##[ Configuration ]###########################################################

mailpile.plugins.register_config_section('tags', ["Tags", {
    'name': ['Tag name', 'str', ''],
    'slug': ['URL slug', 'slashslug', ''],

    # Statistics
    'stats': ['Tag stats', False, {
        'read': ['Read message count', int, 0],
        'unread': ['Unread message count', int, 0],
        'all': ['Number of messages tagged with this tag', int, 0],
    }],

    # Functional attributes
    'type': ['Tag type', ['tag', 'group', 'attribute', 'unread', 'drafts',
                          # TODO: 'folder', 'shadow',
                          'trash', 'spam', 'ham'], 'tag'],
    'flag_hides': ['Hide tagged messages from searches?', bool, False],
    'flag_editable': ['Mark tagged messages as editable?', bool, False],

    # Tag display attributes for /in/tag or searching in:tag
    'template': ['Default tag display template', 'str', 'index'],
    'search_terms': ['Terms to search for', 'str', 'in:%(slug)s'],
    'search_order': ['Default search order', 'str', ''],

    # Tag display attributes for search results/lists/UI placement
    'icon': ['URL to default tag icon', 'url', ''],
    'label': ['Display as label in results', bool, True],
    'label_color': ['Color to use in label', 'str', ''],
    'display': ['Display context in UI', ['priority', 'tag', 'subtag',
                                          'archive', 'invisible'], 'tag'],
    'display_order': ['Order in lists', float, 0],
    'parent': ['ID of parent tag, if any', str, ''],

    # Outdated crap
    'hides_flag': ['DEPRECATED', 'ignore', None],
    'write_flag': ['DEPRECATED', 'ignore', None],
}, {}])

mailpile.plugins.register_config_section('filters', ["Filters", {
    'tags': ['Tag/untag actions', 'str', ''],
    'terms': ['Search terms', 'str', ''],
    'comment': ['Human readable description', 'str', ''],
}, {}])

mailpile.plugins.register_config_variables('sys', {
    'writable_tags': ['DEPRECATED', 'str', []],
    'invisible_tags': ['DEPRECATED', 'str', []],
})


def GetFilters(cfg, filter_on=None):
    filters = cfg.filters.keys()
    filters.sort(key=lambda k: int(k, 36))
    flist = []
    for fid in filters:
        terms = cfg.filters[fid].get('terms', '')
        if filter_on is not None and terms != filter_on:
            continue
        flist.append((fid, terms, cfg.filters[fid].get('tags', ''),
                                  cfg.filters[fid].get('comments', '')))
    return flist


def MoveFilter(cfg, filter_id, filter_new_id):
    def swap(f1, f2):
        tmp = cfg.filters[f1]
        cfg.filters[f1] = cfg.filters[f2]
        cfg.filters[f2] = tmp
    ffrm = int(filter_id, 36)
    fto = int(filter_new_id, 36)
    if ffrm > fto:
        for fid in reversed(range(fto, ffrm)):
            swap(b36(fid + 1), b36(fid))
    elif ffrm < fto:
        for fid in range(ffrm, fto):
            swap(b36(fid), b36(fid + 1))


def GetTags(cfg, tn=None, default=None, **kwargs):
    results = []
    if tn is not None:
        # Hack, allow the tn= to be any of: TID, name or slug.
        tn = tn.lower()
        try:
            if tn in cfg.tags:
                results.append([cfg.tags[tn]._key])
        except (KeyError, IndexError, AttributeError):
            pass
        if not results:
            tv = cfg.tags.values()
            tags = ([t._key for t in tv if t.slug.lower() == tn] or
                    [t._key for t in tv if t.name.lower() == tn])
            results.append(tags)

    if kwargs:
        tv = cfg.tags.values()
        for kw in kwargs:
            want = unicode(kwargs[kw]).lower()
            results.append([t._key for t in tv
                            if (want == '*' or
                                unicode(t[kw]).lower() == want)])

    if (tn or kwargs) and not results:
        return default
    else:
        tags = set(cfg.tags.keys())
        for r in results:
            tags &= set(r)
        tags = [cfg.tags[t] for t in tags]
        if 'display' in kwargs:
            tags.sort(key=lambda k: (k.get('display_order', 0), k.slug))
        else:
            tags.sort(key=lambda k: k.slug)
        return tags


def GetTag(cfg, tn, default=None):
    return (GetTags(cfg, tn, default=None) or [default])[0]


def GetTagID(cfg, tn):
    tags = GetTags(cfg, tn=tn, default=[None])
    return tags and (len(tags) == 1) and tags[0]._key or None


# FIXME: Is this bad form or awesome?  This is used in a few places by
#        commands.py and search.py, but might be a hint that the plugin
#        architecture needs a little more polishing.
mailpile.config.ConfigManager.get_tag = GetTag
mailpile.config.ConfigManager.get_tags = GetTags
mailpile.config.ConfigManager.get_tag_id = GetTagID
mailpile.config.ConfigManager.get_filters = GetFilters
mailpile.config.ConfigManager.filter_move = MoveFilter


##[ Commands ]################################################################

class TagCommand(Command):
    def slugify(self, tag_name):
        return CleanText(tag_name.lower().replace(' ', '-'),
                         banned=CleanText.NONDNS.replace('/', '')
                         ).clean.lower()

    def finish(self, stats=True, save=True):
        idx = self._idx()
        if save:
            # Background save makes things feel fast!
            def background():
                if stats:
                    idx.update_tag_stats(self.session, self.session.config)
                idx.save_changes()
                self.session.config.save()
            self._background('Save index', background)
        elif stats:
            idx.update_tag_stats(self.session, self.session.config)


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

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['msg_ids']:
                return 'Nothing happened'
            what = []
            if self.result['tagged']:
                what.append('Tagged ' +
                            ', '.join([k['name'] for k
                                       in self.result['tagged']]))
            if self.result['untagged']:
                what.append('Untagged ' +
                            ', '.join([k['name'] for k
                                       in self.result['untagged']]))
            return '%s (%d messages)' % (', '.join(what),
                                         len(self.result['msg_ids']))

    def command(self, save=True):
        idx = self._idx()

        if 'mid' in self.data:
            msg_ids = [int(m.replace('=', ''), 36) for m in self.data['mid']]
            ops = (['+%s' % t for t in self.data.get('add', []) if t] +
                   ['-%s' % t for t in self.data.get('del', []) if t])
        else:
            words = self.args[:]
            ops = []
            while words and words[0][0] in ('-', '+'):
                ops.append(words.pop(0))
            msg_ids = self._choose_messages(words)

        rv = {'msg_ids': [], 'tagged': [], 'untagged': []}
        rv['msg_ids'] = [b36(i) for i in msg_ids]
        for op in ops:
            tag = self.session.config.get_tag(op[1:])
            if tag:
                tag_id = tag._key
                if op[0] == '-':
                    idx.remove_tag(self.session, tag_id, msg_idxs=msg_ids,
                       conversation=('flat' not in (self.session.order or '')))
                    rv['untagged'].append(tag)
                else:
                    idx.add_tag(self.session, tag_id, msg_idxs=msg_ids,
                       conversation=('flat' not in (self.session.order or '')))
                    rv['tagged'].append(tag)
            else:
                self.session.ui.warning('Unknown tag: %s' % op)

        self.finish(save=save, stats=True)
        return rv


class AddTag(TagCommand):
    """Create a new tag"""
    SYNOPSIS = (None, 'tag/add', 'tag/add', '<tag>')
    ORDER = ('Tagging', 0)
    SPLIT_ARG = False
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
            'name': 'tag name',
            'slug': 'tag slug',
    }

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['added']:
                return 'Nothing happened'
            return ('Added tags: ' +
                    ', '.join([k['name'] for k in self.result['added']]))

    def command(self):
        config = self.session.config

        slugs = self.data.get('slug', [])
        names = self.data.get('name', [])
        if slugs and len(names) != len(slugs):
            return self._error('Name/slug pairs do not match')
        elif names and not slugs:
            slugs = [self.slugify(n) for n in names]
        slugs.extend([self.slugify(s) for s in self.args])
        names.extend(self.args)

        for slug in slugs:
            if slug != self.slugify(slug):
                return self._error('Invalid tag slug: %s' % slug)

        for tag in config.tags.values():
            if tag.slug in slugs:
                return self._error('Tag already exists: %s/%s' % (tag.slug,
                                                                  tag.name))

        tags = [{'name': n, 'slug': s} for (n, s) in zip(names, slugs)]
        if tags:
            config.tags.extend(tags)
            self.finish(save=True, stats=False)

        return {'added': tags}


class ListTags(TagCommand):
    """List tags"""
    SYNOPSIS = (None, 'tag/list', 'tag/list', '[<wanted>|!<wanted>] [...]')
    ORDER = ('Tagging', 0)
    HTTP_STRICT_VARS = False
    HIDE_TAG_METADATA = ('type', 'flag_editable', 'flag_hides',
                         'search_terms', 'search_order', 'template')

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            tags = self.result['tags']
            wrap = int(78 / 23)  # FIXME: Magic number
            text = []
            for i in range(0, len(tags)):
                text.append(('%s%5.5s %-18.18s'
                             ) % ((i % wrap) == 0 and '  ' or '',
                                  '%s' % (tags[i]['stats']['new'] or ''),
                                  tags[i]['name'])
                            + ((i % wrap) == (wrap - 1) and '\n' or ''))
            return ''.join(text) + '\n'

    def command(self):
        result, idx = [], self._idx()

        args = []
        search = {}
        for arg in self.args:
            if '=' in arg:
                kw, val = arg.split('=', 1)
                search[kw.strip()] = val.strip()
            else:
                args.append(arg)
        for kw in self.data:
            if kw in self.session.config.tags.rules:
                search[kw] = self.data[kw]

        wanted = [t.lower() for t in args if not t.startswith('!')]
        unwanted = [t[1:].lower() for t in args if t.startswith('!')]
        wanted.extend([t.lower() for t in self.data.get('only', [])])
        unwanted.extend([t.lower() for t in self.data.get('not', [])])

        for tag in self.session.config.get_tags(**search):
            if wanted and tag.slug.lower() not in wanted:
                continue
            if unwanted and tag.slug.lower() in unwanted:
                continue
            tid = tag._key
            info = {
                'tid': tid,
                'url': UrlMap(self.session).url_tag(tid),
            }
            for k in tag.all_keys():
                if k not in self.HIDE_TAG_METADATA:
                    info[k] = tag[k]
            info['stats'] = {
                'all': int(idx.STATS.get(tid, [0, 0])[0]),
                'new': int(idx.STATS.get(tid, [0, 0])[1]),
                'not': len(idx.INDEX) - int(idx.STATS.get(tid, [0, 0])[0])
            }
            subtags = self.session.config.get_tags(parent=tid)
            if subtags and '_recursing' not in self.data:
                info['subtags'] = ListTags(self.session,
                                           arg=[t.slug for t in subtags],
                                           data={'_recursing': 1}
                                           ).run().result['tags']
            result.append(info)
        return {
            'search': search,
            'wanted': wanted,
            'unwanted': unwanted,
            'tags': result
        }


class DeleteTag(TagCommand):
    """Delete a tag"""
    SYNOPSIS = (None, 'tag/delete', 'tag/delete', '<tag>')
    ORDER = ('Tagging', 0)
    HTTP_CALLABLE = ('POST', 'DELETE')

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['removed']:
                return 'Nothing happened'
            return ('Removed tags: ' +
                    ', '.join([k['name'] for k in self.result['removed']]))

    def command(self):
        session, config = self.session, self.session.config
        clean_session = mailpile.ui.Session(config)
        clean_session.ui = session.ui
        result = []
        for tag_name in self.args:
            tag = config.get_tag(tag_name)
            if tag:
                tag_id = tag._key
                # FIXME: Refuse to delete tag if in use by filters
                rv = (Search(clean_session, arg=['tag:%s' % tag_id]).run() and
                      Tag(clean_session, arg=['-%s' % tag_id, 'all']).run())
                if rv:
                    del config.tags[tag_id]
                    result.append({'name': tag.name, 'tid': tag_id})
                else:
                    raise Exception('That failed: %s' % rv)
            else:
                self._error('No such tag %s' % tag_name)
        if result:
            self.finish(save=True, stats=False)
        return {'removed': result}


class FilterCommand(Command):
    def finish(self):
        def save_filter():
            self.session.config.save()
            if self.session.config.index:
                self.session.config.index.save_changes()
            return True
        self._serialize('Save filter', save_filter)


class Filter(FilterCommand):
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
            filter_id = None

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
            tids.append(tag[0] + config.get_tag_id(tag[1:]))

        if not args:
            args = ['Filter for %s' % ' '.join(tags)]

        if auto_tag and 'notag' not in flags:
            if not Tag(session, arg=tags + ['all']).run(save=False):
                raise UsageError()

        filter_dict = {
            'comment': ' '.join(self.args),
            'terms': ' '.join(terms),
            'tags': ' '.join(tids)
        }
        if filter_id:
                config.filters[filter_id] = filter_dict
        else:
                config.filters.append(filter_dict)

        self.finish()
        return True


class DeleteFilter(FilterCommand):
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
            self.finish()
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
                                    r['fid'], r['terms'],
                                    r['human_tags'], r['comment']
                                ) for r in self.result])

    def command(self, want_fid=None):
        results = []
        for (fid, trms, tags, cmnt
             ) in self.session.config.get_filters(filter_on=None):
            if want_fid and fid != want_fid:
                continue

            human_tags = []
            for tterm in tags.split():
                tagname = self.session.config.tags.get(tterm[1:],
                                                      {}).get('slug', '(None)')
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


mailpile.plugins.register_commands(Tag, AddTag, DeleteTag, ListTags,
                                   Filter, DeleteFilter,
                                   MoveFilter, ListFilters)
