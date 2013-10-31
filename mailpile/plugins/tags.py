import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *


##[ Commands ]################################################################

class Tag(Command):
    """Add/remove/list/edit message tags"""
    ORDER = ('Tagging', 0)
    TEMPLATE_IDS = ['tag']

    class CommandResult(Command.CommandResult):
        def _tags_as_text(self):
            tags = self.result['tags']
            wrap = int(78 / 23) # FIXME: Magic number
            text = []
            for i in range(0, len(tags)):
                text.append(('%s%5.5s %-18.18s') % ((i % wrap) == 0 and '  ' or '',
                            '%s' % (tags[i]['new'] or ''),
                            tags[i]['name'])
                       + ((i % wrap) == (wrap - 1) and '\n' or ''))
            return ''.join(text) + '\n'

        def _added_as_text(self):
            return ('Added tags: '
                + ', '.join([k['name'] for k in self.result['added']]))

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
        return ''.join([('added' in self.result) and self._added_as_text() or '',
            ('removed' in self.result) and self._added_as_text() or '',
            ('tags' in self.result) and self._tags_as_text() or '',
            ('msg_ids' in self.result) and self._tagging_as_text() or '',
                        ])

    SYNOPSIS = '<[+|-]tags msgs>'

    def command(self, save=True):
        idx = self._idx()
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
                idx.remove_tag(self.session,
                        tag_id, msg_idxs=msg_ids,
                        conversation=True)
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

    def add_tag(self):
        config = self.session.config
        existing = [v.lower() for v in config.get('tag', {}).values()]
        for tag in self.args:
            if ' ' in tag:
                return self._error('Invalid tag: %s' % tag)
            if tag.lower() in existing:
                return self._error('Tag already exists: %s' % tag)
        result = []
        for tag in sorted(self.args):
            if config.parse_set(self.session, 'tag:%s=%s' % (config.nid('tag'), tag)):
                result.append({'name': tag, 'tid': config.get_tag_id(tag), 'new': 0})
        if result:
            self._background('Save config', lambda: config.save())
        return {'added': result}

    def list_tags(self):
        result, idx = [], self._idx()
        wanted = [t.lower() for t in self.args if not t.startswith('!')]
        unwanted = [t[1:].lower() for t in self.args if t.startswith('!')]
        for tid, tag in self.session.config.get('tag', {}).iteritems():
            if wanted and tag.lower() not in wanted: continue
            if unwanted and tag.lower() in unwanted: continue
            result.append({
                'name': tag,
                'tid': tid,
                'all': int(idx.STATS.get(tid, [0, 0])[0]),
                'new': int(idx.STATS.get(tid, [0, 0])[1]),
                'not': len(idx.INDEX) - int(idx.STATS.get(tid, [0, 0])[0])
            })
        result.sort(key=lambda k: k['name'])
        return {'tags': result}

    def rm_tag(self):
        session, config = self.session, self.session.config
        existing = [v.lower() for v in config.get('tag', {}).values()] # FIXME: where does/should existing get used?
        clean_session = mailpile.ui.Session(config)
        clean_session.ui = session.ui
        result = []
        for tag in self.args:
            tag_id = config.get_tag_id(tag)
            #if tag_id: FIXME: Update filters too
            if (COMMANDS['s:'][1](clean_session, arg=['tag:%s' % tag]).run()
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

    SUBCOMMANDS = {
            'add':    (add_tag,
            '<tag>'),
            'delete': (rm_tag,
            '<tag>'),
            'list':   (list_tags,
            ''),
                    }


class Filter(Command):
    """Add/edit/delete/list auto-tagging rules"""
    ORDER = ('Tagging', 1)
    SYNOPSIS = '[new|read] [notag] [=ID] [terms] <[+|-]tags ...> [description]'

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
            tids.append(tag[0] + config.get_tag_id(tag[1:]))

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

    def rm(self):
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

    def mv(self):
        raise Exception('Unimplemented')

    def ls(self):
        results = []
        for fid, trms, tags, cmnt in self.session.config.get_filters(filter_on=None):
            results.append({
                'fid': fid,
                'terms': trms,
                'tags': tags,
                'comment': cmnt
            })
        return results

    SUBCOMMANDS = {
        'delete': (rm, '<id>'),
        'move':   (mv, '<id> <pos>'),
        'list':   (ls, ''),
    }


mailpile.plugins.register_command('t:', 'tag=',    Tag)
mailpile.plugins.register_command('F:', 'filter=', Filter)
