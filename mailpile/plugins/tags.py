import mailpile.config
import mailpile.security as security
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.urlmap import UrlMap
from mailpile.util import *

from mailpile.plugins.search import Search


_plugins = PluginManager(builtin=__file__)


##[ Configuration ]###########################################################


FILTER_TYPES = ('user',      # These are the default, user-created filters
                'incoming',  # These filters are only applied to new messages
                'system',    # Mailpile core internal filters
                'plugin')    # Filters created by plugins

_plugins.register_config_section('tags', ["Tags", {
    'name': ['Tag name', 'str', ''],
    'slug': ['URL slug', 'slashslug', ''],

    # Functional attributes
    'type': ['Tag type', [
        'tag', 'group', 'attribute', 'unread', 'inbox', 'search',
        # Maybe TODO: 'folder', 'shadow',
        'profile', 'mailbox',                         # Accounts, Mailboxes
        'drafts', 'blank', 'outbox', 'sent',          # composing and sending
        'replied', 'fwded', 'tagged', 'read', 'ham',  # behavior tracking tags
        'trash', 'spam'                               # junk mail tags
    ], 'tag'],
    'flag_hides': ['Hide tagged messages from searches?', 'bool', False],
    'flag_editable': ['Mark tagged messages as editable?', 'bool', False],
    'flag_msg_only': ['Never apply to entire conversations', 'bool', False],

    # Tag display attributes for /in/tag or searching in:tag
    'template': ['Default tag display template', 'str', 'index'],
    'search_terms': ['Terms to search for on /in/tag/', 'str', 'in:%(slug)s'],
    'search_order': ['Default search order for /in/tag/', 'str', ''],
    'magic_terms': ['Extra terms to search for', 'str', ''],

    # Tag display attributes for search results/lists/UI placement
    'icon': ['URL to default tag icon', 'str', 'icon-tag'],
    'label': ['Display as label in results', 'bool', True],
    'label_color': ['Color to use in label', 'str', '#4D4D4D'],
    'display': ['Display context in UI', ['priority', 'tag', 'subtag',
                                          'archive', 'invisible'], 'tag'],
    'display_order': ['Order in lists', 'float', 0],
    'parent': ['ID of parent tag, if any', 'str', '']
}, {}])

_plugins.register_config_section('filters', ["Filters", {
    'tags': ['Tag/untag actions', 'str', ''],
    'terms': ['Search terms', 'str', ''],
    'comment': ['Human readable description', 'str', ''],
    'type': ['Filter type', FILTER_TYPES, FILTER_TYPES[0]],
    'primary_tag': ['Tag dedicated to this filter', 'str', ''],
}, {}])


def GetFilters(cfg, filter_on=None, types=FILTER_TYPES[:1]):
    filters = cfg.filters.keys()
    filters.sort(key=lambda k: int(k, 36))
    flist = []
    tset = set(types)
    for fid in filters:
        terms = cfg.filters[fid].get('terms', '')
        ftype = cfg.filters[fid]['type']
        if not (set([ftype, 'any', 'all', None]) & tset):
            continue
        if filter_on is not None and terms != filter_on:
            continue
        flist.append((fid, terms,
                      cfg.filters[fid].get('tags', ''),
                      cfg.filters[fid].get('comment', ''),
                      ftype))
    return flist


def FilterMove(cfg, filter_id, filter_new_id):
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


def FilterDelete(cfg, *filter_ids):
    filter_ids = list(filter_ids)
    filter_ids.sort(key=lambda fid: int(fid, 36))
    filters = cfg.filters
    for fid in reversed(filter_ids):
        lastid = b36(len(filters)-1).lower()
        if fid <= lastid:
            if lastid != fid:
                cfg.filter_move(fid, lastid)
            del filters[lastid]


def GetTags(cfg, tn=None, default=None, **kwargs):
    results = []
    if tn is not None:
        #
        # Hack, allow the tn= to be any of: TID, name or slug.
        #
        # However, the most precise style of match wins - so TID lookups
        # will never get confused by slugs, and slug lookups will never
        # get confused by names.
        #
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
        return tags


def GetTag(cfg, tn, default=None):
    return (GetTags(cfg, tn, default=None) or [default])[0]


def GetTagID(cfg, tn):
    tags = GetTags(cfg, tn=tn, default=[None])
    return tags and (len(tags) == 1) and tags[0]._key or None


def Slugify(tag_name, tags=None):
    slug = CleanText(tag_name.lower().replace(' ', '-'),
                     banned=CleanText.NONDNS.replace('/', '')
                     ).clean.lower()
    n = 1
    while tags and slug in [t.slug for t in tags.values()]:
        n += 1
        slug = Slugify('%s-%s' % (tag_name, n))
    return slug


def GetTagInfo(cfg, tn, stats=False, unread=None, exclude=None, subtags=None):
    tag = GetTag(cfg, tn)
    tid = tag._key
    info = {
        'tid': tid,
        'url': UrlMap(config=cfg).url_tag(tid),
    }
    for k in tag.all_keys():
        if k in ('display_order', ):
            if str(tag[k]) == 'nan':
                tag[k] = 0.01 * len(info)
        info[k] = tag[k]
    if subtags:
        info['subtag_ids'] = [t._key for t in subtags]
    exclude = exclude or set()
    if stats and (unread is not None):
        messages = (cfg.index.TAGS.get(tid, set()) - exclude)
        stats_all = len(messages)
        info['name'] = _(info['name'])
        info['stats'] = {
            'all': stats_all,
            'new': len(messages & unread),
            'not': len(cfg.index.INDEX) - stats_all
        }
        if subtags:
            for subtag in subtags:
                messages |= cfg.index.TAGS.get(subtag._key, set())
            info['stats'].update({
                'sum_all': len(messages),
                'sum_new': len(messages & unread),
            })

    return info


# FIXME: Is this bad form or awesome?  This is used in a few places by
#        commands.py and search.py, but might be a hint that the plugin
#        architecture needs a little more polishing.
mailpile.config.ConfigManager.get_tag = GetTag
mailpile.config.ConfigManager.get_tags = GetTags
mailpile.config.ConfigManager.get_tag_id = GetTagID
mailpile.config.ConfigManager.get_tag_info = GetTagInfo
mailpile.config.ConfigManager.get_filters = GetFilters
mailpile.config.ConfigManager.filter_move = FilterMove
mailpile.config.ConfigManager.filter_delete = FilterDelete


##[ Commands ]################################################################

class TagCommand(Command):
    def _reorder_all_tags(self):
        taglist = [(t.display, t.display_order, t.slug, t._key)
                   for t in self.session.config.tags.values()]
        taglist.sort()
        order = 1
        for td, tdo, ts, tid in taglist:
            self.session.config.tags[tid].display_order = order
            order += 1

    def finish(self, save=True):
        if save:
            self._background_save(config=True, index=True)
        return True


class Tag(TagCommand):
    """Add or remove tags on a set of messages"""
    SYNOPSIS = (None, 'tag', 'tag', '[--conversations|--messages] '
                                    '<[+|-]tags> <msgs>')
    ORDER = ('Tagging', 0)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
        'mid': 'message-ids',
        'add': 'tags',
        'del': 'tags',
        'conversations': '[yes|no|auto]',
        'context': 'search context, for tagging relative results'
    }
    COMMAND_SECURITY = security.CC_TAG_EMAIL

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['msg_ids']:
                return 'Nothing happened'
            what = []
            if self.result['tagged']:
                what.append('Tagged ' +
                            ', '.join([k['name'] for k, ids
                                       in self.result['tagged']]))
            if self.result['untagged']:
                what.append('Untagged ' +
                            ', '.join([k['name'] for k, ids
                                       in self.result['untagged']]))
            count = len(self.result['msg_ids'])
            whats = ', '.join(what)
            convs = (_n('%d conversation', '%d conversation', count)
                     if self.result.get('conversations') else
                     _n('%d message', '%d messages', count)) % count
            return '%s (%s)' % (whats, convs)

    def _get_ops_and_msgids(self, words):
        # If we are asked to both add and remove a tag, we do neither as
        # that is nonsense without knowing the order of the operations.
        deling = set(self.data.get('del', []))
        adding = set(self.data.get('add', []))
        ops = (['-%s' % t for t in (deling-adding) if t] +
               ['+%s' % t for t in (adding-deling) if t])
        conversations = {'yes': True, 'no': False, 'auto': None
                         }[self.data.get('conversations',
                                         ['auto'])[0].lower()]
        if 'mid' in self.data:
            words = ['=%s' % m for m in self.data['mid']]
        else:
            while words and words[0][:1] in ('-', '+'):
                op = words.pop(0)
                if op in ('--conversations', '--messages'):
                    conversations = True if (op[:3] == '--c') else False
                else:
                    ops.append(op)
        msg_ids = self._choose_messages(words)
        return ops, msg_ids, conversations

    def _do_tagging(self, ops, msg_ids, conversations, save=True, auto=False):
        idx = self._idx()
        rv = {
            'conversations': False,
            'msg_ids': [b36(i) for i in msg_ids],
            'tagged': [],
            'untagged': []
        }

        for op in ops:
            tag = self.session.config.get_tag(op[1:])
            if tag:
                # FIXME: This should depend on more factors!
                #    - Tags should have metadata about default scope
                if conversations is None:
                    conversation = ('flat' not in (self.session.order or ''))
                    if (tag.flag_msg_only or
                            tag.flag_editable or
                            tag.type == 'attribute'):
                        conversation = False
                else:
                    conversation = conversations
                if conversation:
                    rv['conversations'] = True

                tag_id = tag._key
                tag = tag.copy()
                tag["tid"] = tag_id
                if op[0] == '-':
                    removed = idx.remove_tag(self.session, tag_id,
                                             msg_idxs=msg_ids,
                                             conversation=conversation)
                    rv['untagged'].append((tag, sorted([b36(i)
                                                        for i in removed])))
                else:
                    added = idx.add_tag(self.session, tag_id,
                                        msg_idxs=msg_ids,
                                        conversation=conversation)
                    rv['tagged'].append((tag, sorted([b36(i)
                                                      for i in added])))
                # Record behavior
                if len(msg_ids) < 15:
                    for t in self.session.config.get_tags(type='tagged'):
                        idx.add_tag(self.session, t._key, msg_idxs=msg_ids)
            else:
                self.session.ui.warning('Unknown tag: %s' % op)

        if rv['conversations']:
            undo_msg = _n('Untag %d conversation',
                          'Untag %d conversations',
                          len(msg_ids)) % len(msg_ids)
            done_msg = _n('Tagged %d conversation',
                          'Tagged %d conversations',
                          len(msg_ids)) % len(msg_ids)
        else:
            undo_msg = _n('Untag %d message',
                          'Untag %d messages', len(msg_ids)) % len(msg_ids)
            done_msg = _n('Tagged %d message',
                          'Tagged %d messages', len(msg_ids)) % len(msg_ids)

        self.event.data['undo'] = undo_msg
        self.event.private_data['undo'] = {
            'tagged': [[t['tid'], mids] for t, mids in rv['tagged']],
            'untagged': [[t['tid'], mids] for t, mids in rv['untagged']],
        }

        self.finish(save=save)
        return self._success(done_msg, rv)

    @classmethod
    def Undo(cls, undo, event):
        idx = undo._idx()
        rv = {
            'tagged': [],
            'untagged': []
        }
        for tid, msg_mids in event.private_data['undo']['tagged']:
            removed = idx.remove_tag(undo.session, tid,
                                     msg_idxs=[int(i, 36) for i in msg_mids],
                                     conversation=False)
            rv['untagged'].append((tid, sorted([b36(i) for i in removed])))

        for tid, msg_mids in event.private_data['undo']['untagged']:
            added = idx.add_tag(undo.session, tid,
                                msg_idxs=[int(i, 36) for i in msg_mids],
                                conversation=False)
            rv['tagged'].append((tid, sorted([b36(i) for i in added])))
        return undo._success(_('Undid tagging operation'), rv)

    def command(self, **kwargs):
        return self._do_tagging(*self._get_ops_and_msgids(list(self.args)),
                                **kwargs)


class TagLater(Tag):
    """Schedule a tag operation to happen later."""
    SYNOPSIS = (None, 'tag/later', 'tag/later', '<seconds> <[+|-]tags> <msgs>')

    def command(self, **kwargs):
        args = list(self.args)
        seconds = args.pop(0)
        ops, msg_ids, conversations = self._get_ops_and_msgids(args)
        # FIXME: Schedule event!
        return self._success(_('Scheduled %d messages for future tagging')
                             % len(msg_ids), {
            'msg_ids': [b36(i) for i in msg_ids],
            'seconds': seconds
        })


class TagTemporarily(Tag):
    """Temporarily add or remove tags."""
    SYNOPSIS = (None, 'tag/tmp', 'tag/tmp', '<seconds> <[+|-]tags> <msgs>')

    def command(self, **kwargs):
        args = list(self.args)
        seconds = args.pop(0)
        rv = self._do_tagging(*self._get_ops_and_msgids(args), **kwargs)
        # FIXME: Schedule undo event!
        return rv


class AddTag(TagCommand):
    """Create a new tag"""
    SYNOPSIS = (None, 'tags/add', 'tags/add', '<tag>')
    ORDER = ('Tagging', 0)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = {
        'name': 'tag name',
        'slug': 'tag slug',
        # Optional initial attributes of tags
        'icon': 'icon-tag',
        'label': 'display as label in search results, or not',
        'label_color': 'the color of the label',
        'display': 'tag display type',
        'template': 'tag template type',
        'search_terms': 'default search associated with this tag',
        'magic_terms': 'magic search terms associated with this tag',
        'parent': 'parent tag ID',
    }
    COMMAND_SECURITY = security.CC_CHANGE_TAGS

    OPTIONAL_VARS = ['icon', 'label', 'label_color', 'display', 'template',
                     'search_terms', 'parent']

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['added']:
                return 'Nothing happened'
            return ('Added tags: ' +
                    ', '.join([k['name'] for k in self.result['added']]))

    def command(self, save=True):
        config = self.session.config

        if self.data.get('_method', 'not-http').upper() == 'GET':
            return self._success(_('Add tags here!'), {
                'form': self.HTTP_POST_VARS,
                'rules': self.session.config.tags.rules['_any'][1]
            })

        # Check arguments/POST data, and make sure we have matching numbers
        # of names and slugs for the tags we're about to create.
        slugs = self.data.get('slug', [])
        names = self.data.get('name', [])
        if slugs and len(names) != len(slugs):
            return self._error('Name/slug pairs do not match')
        elif names and not slugs:
            slugs = [Slugify(n, config.tags) for n in names]
        # This adds CLI-style arguments to the list
        slugs.extend([Slugify(s, config.tags) for s in self.args])
        names.extend(self.args)

        # Check Slug is valid
        for slug in slugs:
            if slug != Slugify(slug, config.tags):
                return self._error('Invalid tag slug: %s' % slug)

        # Check Tag is unique
        for tag in config.tags.values():
            if tag.slug in slugs:
                return self._error('Tag already exists: %s/%s' % (tag.slug,
                                                                  tag.name))

        tags = [{'name': n, 'slug': s} for (n, s) in zip(names, slugs)]
        for v in self.OPTIONAL_VARS:
            for i in range(0, len(tags)):
                vlist = self.data.get(v, [])
                if len(vlist) > i and vlist[i]:
                    tags[i][v] = vlist[i]
        if tags:
            # Add Tag to config
            config.tags.extend(tags)
            if save:
                self._reorder_all_tags()
            self.finish(save=save)

        # Get full Tag objects of added tags to return
        results = []
        for tag in tags:
            results.append(GetTagInfo(self.session.config, tag['slug']))

        # Return success
        return self._success(_('Added %d tags') % len(results),
                             {'added': results})


class ListTags(TagCommand):
    """List tags"""
    SYNOPSIS = (None, 'tags', 'tags', '[<wanted>|!<wanted>] [...]')
    ORDER = ('Tagging', 0)
    HTTP_STRICT_VARS = False
    COMMAND_CACHE_TTL = 3600
    LOG_NOTHING = True  # Avoid gunking up the event log with Boring Stuff

    def cache_requirements(self, result):
        if result:
            return set([u'!config'] +
                       [u'%s:in' % ti['slug'] for ti in result.result['tags']])
        else:
            return set([u'!config'])

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            tags = self.result['tags']
            wrap = int(min(23*5, (self.session.ui.term.max_width()-1)) / 23)
            text = []
            for i in range(0, len(tags)):
                stats = tags[i]['stats']
                text.append(('%s%5.5s %-18.18s'
                             ) % ((i % wrap) == 0 and '  ' or '',
                                  '%s' % (stats.get('sum_new', stats['new'])
                                          or ''),
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

        unread_messages = set()
        for tag in self.session.config.get_tags(type='unread'):
            unread_messages |= idx.TAGS.get(tag._key, set())

        excluded_messages = set()
        for tag in self.session.config.get_tags(flag_hides=True):
            excluded_messages |= idx.TAGS.get(tag._key, set())

        mode = search.get('mode', 'default')
        if 'mode' in search:
            del search['mode']

        for tag in self.session.config.get_tags(**search):
            if wanted and tag.slug.lower() not in wanted:
                continue
            if unwanted and tag.slug.lower() in unwanted:
                continue
            if mode == 'tree' and tag.parent and not wanted:
                continue

            # Hide invisible tags by default, any search terms at all will
            # disable this behavior
            if (not wanted and not unwanted and not search
                    and tag.display == 'invisible'):
                continue

            recursion = self.data.get('_recursion', 0)
            tid = tag._key

            # List subtags...
            if recursion == 0:
                subtags = self.session.config.get_tags(parent=tid)
                subtags.sort(key=lambda k: k.get('slug', 'zzzz'))
            else:
                subtags = None

            # Get tag info (how depends on whether this is a hiding tag)
            if tag.flag_hides:
                info = GetTagInfo(self.session.config, tid, stats=True,
                                  unread=unread_messages,
                                  subtags=subtags)
            else:
                info = GetTagInfo(self.session.config, tid, stats=True,
                                  unread=unread_messages,
                                  exclude=excluded_messages,
                                  subtags=subtags)

            # This expands out the full tree
            if subtags and recursion == 0:
                if mode in ('both', 'tree') or (wanted and mode != 'flat'):
                    info['subtags'] = ListTags(self.session,
                                               arg=[t.slug for t in subtags],
                                               data={'_recursion': 1}
                                               ).run().result['tags']

            result.append(info)
        result.sort(key=lambda k: (float(k.get('display_order', 0)),
                                         k.get('slug', 'zzz')))
        return self._success(_('Listed %d tags') % len(result), {
            'search': search,
            'wanted': wanted,
            'unwanted': unwanted,
            'tags': result
        })


class DeleteTag(TagCommand):
    """Delete a tag"""
    SYNOPSIS = (None, 'tags/delete', 'tags/delete', '<tag>')
    ORDER = ('Tagging', 0)
    HTTP_CALLABLE = ('POST', 'DELETE')
    HTTP_POST_VARS = {
        "tag" : "tag(s) to delete"
    }
    COMMAND_SECURITY = security.CC_CHANGE_TAGS

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

        tag_names = []
        if self.args:
            tag_names = list(self.args)
        elif self.data.get('tag', []):
            tag_names = self.data.get('tag', [])

        for tag_name in tag_names:

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
            self._reorder_all_tags()
            self.finish(save=True)
        return self._success(_('Deleted %d tags') % len(result),
                             {'removed': result})


class FilterCommand(Command):
    def finish(self, save=True):
        self._background_save(config=True, index=True)
        return True


class Filter(FilterCommand):
    """Add auto-tag rule for current search or terms"""
    SYNOPSIS = (None, 'filter', 'filter', '[new|read] [notag|maketag] [=<mid>] '
                                          '[<terms>] [+<tag>] [-<tag>] '
                                          '[<comment>]')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
        'comment': '...',
        'terms': '...',
        'add-tag': 'tag,tag,tag,... or !CREATE',
        'del-tag': 'tag,tag,tag,... ',
        'mark-read': 'yes or no',
        'skip-inbox': 'yes or no',
        'never-spam': 'yes or no',
        'create-tag': 'yes or no',
        'tag-icon': 'icon',
        'tag-color': 'color',
        'replace': 'filter ID'
    }
    COMMAND_SECURITY = security.CC_CHANGE_FILTERS

    def _truthy(self, var):
        return (self.data.get(var, ['n'])[0][:1].lower()
                in ('y', 't', 'o', '1'))

    def command(self, save=True):
        session, config = self.session, self.session.config
        args = list(self.args)

        flags = []
        while args and args[0] in ('add', 'set', 'new', 'read',
                                   'notag', 'maketag'):
            flags.append(args.pop(0))
        if self._truthy('create-tag'):
            flags.append('maketag')

        if args and args[0][:1] == '=':
            filter_id = args.pop(0)[1:]
        else:
            filter_id = self.data.get('replace', [None])[0] or None

        if args and args[0][:1] == '@':
            filter_type = args.pop(0)[1:]
        else:
            filter_type = FILTER_TYPES[0]

        # Convert HTTP variable tag ops...
        for tag in self.data.get('add-tag', []):
            args.append('+%s' % tag)
        for tag in self.data.get('del-tag', []):
            args.append('-%s' % tag)
        if self._truthy('mark-read'):
            args.append('-new')
        if self._truthy('skip-inbox'):
            args.append('-inbox')
        if self._truthy('never-spam'):
            args.append('-spam')

        auto_tag = False
        if 'read' in flags:
            terms = ['@read']
        elif 'new' in flags:
            terms = ['*']
        elif self.data.get('terms', [''])[0]:
            terms = self.data['terms'][0].strip().split()
            auto_tag = True
        elif args and args[0][:1] not in ('-', '+'):
            terms = []
            while args and args[0][0] not in ('-', '+'):
                terms.append(args.pop(0))
        else:
            terms = session.searched
            auto_tag = True

        tag_ops = []
        while args and args[0][0] in ('-', '+'):
            tag_ops.append(args.pop(0))

        comment = self.data.get('comment', [None])[0] or ' '.join(args)

        if filter_id:
            primary_tag = config.filters[filter_id].primary_tag or None
        else:
            primary_tag = None

        if primary_tag is None and 'maketag' in flags:
            if not comment:
                raise UsageError(_('Need tag name'))
            result = AddTag(session, arg=[comment]).run(save=False).result
            primary_tag = result['added'][0]['tid']

        if not terms or (len(tag_ops) < 1):
            raise UsageError(_('Need flags and search terms or a hook'))

        tags, tids = [], []
        for tag in tag_ops:
            if tag[1:] == '!PRIMARY':
                tid = primary_tag
                tag = tag[0] + tid
            else:
                tid = config.get_tag_id(tag[1:])
            if tid is not None:
                tags.append(tag)
                tids.append(tag[0] + tid)
            else:
                raise UsageError(_('No such tag: %s') % tag)

        if not args:
            args = ['Filter for %s' % ' '.join(tags)]

        if auto_tag and 'notag' not in flags:
            if not Tag(session, arg=tags + ['all']).run(save=False):
                raise UsageError()

        filter_dict = {
            'primary_tag': primary_tag,
            'comment': comment,
            'terms': ' '.join(terms),
            'tags': ' '.join(tids),
            'type': filter_type
        }
        if filter_id:
            config.filters[filter_id] = filter_dict
        else:
            filter_id = config.filters.append(filter_dict)

        if 'maketag' in flags and primary_tag and primary_tag in config.tags:
            tag_icon = self.data.get('tag-icon', [None])[0]
            tag_color = self.data.get('tag-color', [None])[0]
            if tag_icon:
                config.tags[primary_tag].icon = tag_icon
            if tag_color:
                config.tags[primary_tag].label_color = tag_color
            config.tags[primary_tag].name = comment
            config.tags[primary_tag].slug = 'saved-search-%s' % filter_id

        self.finish(save=save)

        filter_dict['id'] = filter_id
        return self._success(_('Added new filter'), result=filter_dict)


class DeleteFilter(FilterCommand):
    """Delete an auto-tagging rule"""
    SYNOPSIS = (None, 'filter/delete', None, '<filter-id>')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('POST', 'DELETE')
    COMMAND_SECURITY = security.CC_CHANGE_FILTERS

    def command(self):
        session, config = self.session, self.session.config
        if len(self.args) < 1:
            raise UsageError('Delete what?')

        args = list(self.args)
        args.sort(key=lambda fid: int(fid, 36))

        filter_keys = config.get('filters', {}).keys()
        removed = 0
        for fid in reversed(args):
            if fid in filter_keys:
                self.session.config.filter_delete(fid)
                removed += 1
            else:
                session.ui.warning('Failed to remove %s' % fid)
        if removed:
            self.finish()

        return self._success(_('Removed %d filter(s)') % removed)


class ListFilters(Command):
    """List (all) auto-tagging rules"""
    SYNOPSIS = (None, 'filter/list', 'filter/list', '[<search>|=<id>|@<type>]')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'search': 'Text to search for',
        'id': 'Filter ID',
        'type': 'Filter type'
    }

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result is False:
                return unicode(self.result)
            return '\n'.join([('%3.3s %-10s %-18s %-18s %s'
                               ) % (r['fid'], r['type'],
                                    r['terms'], r['human_tags'], r['comment'])
                              for r in self.result])

    def command(self, want_fid=None):
        results = []
        for (fid, trms, tags, cmnt, ftype
             ) in self.session.config.get_filters(filter_on=None,
                                                  types=['all']):
            if want_fid and fid != want_fid:
                continue

            human_tags = []
            for tterm in tags.split():
                tagname = self.session.config.tags.get(
                    tterm[1:], {}).get('slug', '(None)')
                human_tags.append('%s%s' % (tterm[0], tagname))

            skip = False
            args = list(self.args)
            args.extend([t for t in self.data.get('search', [])])
            args.extend(['='+t for t in self.data.get('id', [])])
            args.extend(['@'+t for t in self.data.get('type', [])])
            if args and not want_fid:
                for term in args:
                    term = term.lower()
                    if term.startswith('='):
                        if (term[1:] != fid):
                            skip = True
                    elif term.startswith('@'):
                        if (term[1:] != ftype):
                            skip = True
                    elif ((term not in ' '.join(human_tags).lower())
                            and (term not in trms.lower())
                            and (term not in cmnt.lower())):
                        skip = True
            if skip:
                continue

            results.append({
                'fid': fid,
                'terms': trms,
                'tags': tags,
                'human_tags': ' '.join(human_tags),
                'comment': cmnt,
                'type': ftype
            })
        return results


class MoveFilter(ListFilters):
    """Move an auto-tagging rule"""
    SYNOPSIS = (None, 'filter/move', None, '<filter-id> <position>')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('POST', 'UPDATE')
    COMMAND_SECURITY = security.CC_CHANGE_FILTERS

    def command(self):
        self.session.config.filter_move(self.args[0], self.args[1])
        self._background_save(config=True)
        return ListFilters.command(self, want_fid=self.args[1])


_plugins.register_commands(Tag, TagLater, TagTemporarily,
                           AddTag, DeleteTag, ListTags,
                           Filter, DeleteFilter,
                           MoveFilter, ListFilters)
