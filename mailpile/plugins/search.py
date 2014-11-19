import datetime
import re
import time

from mailpile.commands import Command, SearchResults
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils import Email, FormatMbxId
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName
from mailpile.plugins import PluginManager
from mailpile.search import MailIndex
from mailpile.urlmap import UrlMap
from mailpile.util import *
from mailpile.ui import SuppressHtmlOutput


_plugins = PluginManager(builtin=__file__)


##[ Commands ]################################################################

class Search(Command):
    """Search your mail!"""
    SYNOPSIS = ('s', 'search', 'search', '[@<start>] <terms>')
    ORDER = ('Searching', 0)
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        'q': 'search terms',
        'qr': 'search refinements',
        'order': 'sort order',
        'start': 'start position',
        'end': 'end position',
        'full': 'return all metadata',
        'context': 'refine or redisplay an older search'
    }
    IS_USER_ACTIVITY = True
    COMMAND_CACHE_TTL = 3600
    CHANGES_SESSION_CONTEXT = True

    class CommandResult(Command.CommandResult):
        def __init__(self, *args, **kwargs):
            Command.CommandResult.__init__(self, *args, **kwargs)
            self.fixed_up = False
            if isinstance(self.result, dict):
                self.message = self.result.get('summary', '')
            elif isinstance(self.result, list):
                self.message = ', '.join([r.get('summary', '')
                                          for r in self.result])

        def _fixup(self):
            if self.fixed_up:
                return self
            self.fixed_up = True
            return self

        def as_text(self):
            if self.result:
                if isinstance(self.result, (bool, str, unicode, int, float)):
                    return unicode(self.result)
                elif isinstance(self.result, (list, set)):
                    return '\n'.join([r.as_text() for r in self.result])
                else:
                    return self.result.as_text()
            else:
                return _('No results')

        def as_html(self, *args, **kwargs):
            return Command.CommandResult.as_html(self._fixup(),
                                                 *args, **kwargs)

        def as_dict(self, *args, **kwargs):
            return Command.CommandResult.as_dict(self._fixup(),
                                                 *args, **kwargs)

    def state_as_query_args(self):
        try:
            return self._search_state
        except (AttributeError, NameError):
            return Command.state_as_query_args(self)

    def _starting(self):
        Command._starting(self)
        session, idx = self.session, self._idx()
        self._search_args = args = []

        self.context = self.data.get('context', [None])[0]
        if self.context:
            args += self.session.searched

        def nq(t):
            p = t[0] if (t and t[0] in '-+') else ''
            t = t[len(p):]
            if t.startswith('tag:') or t.startswith('in:'):
                try:
                    raw_tag = session.config.get_tag(t.split(':')[1])
                    if raw_tag and raw_tag.hasattr(slug):
                        t = 'in:%s' % raw_tag.slug
                except (IndexError, KeyError, TypeError):
                    pass
            return p+t


        args += [a for a in list(nq(a) for a in self.args) if a not in args]
        for q in self.data.get('q', []):
            ext = [nq(a) for a in q.split()]
            args.extend([a for a in ext if a not in args])

        # Query refinements...
        qrs = []
        for qr in self.data.get('qr', []):
            qrs.extend(nq(a) for a in qr.split())
        args.extend(qrs)

        for order in self.data.get('order', []):
            session.order = order

        num = def_num = session.config.prefs.num_results
        d_start = int(self.data.get('start', [0])[0])
        d_end = int(self.data.get('end', [0])[0])
        if d_start and d_end:
            args[:0] = ['@%s' % d_start]
            num = d_end - d_start + 1
        elif d_start:
            args[:0] = ['@%s' % d_start]
        elif d_end:
            args[:0] = ['@%s' % (d_end - num + 1)]

        start = 0
        while args and args[0].startswith('@'):
            spoint = args.pop(0)[1:]
            try:
                start = int(spoint) - 1
            except ValueError:
                raise UsageError(_('Weird starting point: %s') % spoint)

        session.order = session.order or session.config.prefs.default_order
        self._start = start
        self._num = num
        self._search_state = {
            'q': [q for q in args if q not in qrs],
            'qr': qrs,
            'order': [session.order],
            'start': [str(start + 1)] if start else [],
            'end': [str(start + num)] if (num != def_num) else []
        }
        if self.context:
            self._search_state['context'] = [self.context]

    def _do_search(self, search=None, process_args=False):
        session, idx = self.session, self._idx()

        if self.context is None or search or session.searched != self._search_args:
            session.searched = search or []
            if search is None or process_args:
                prefix = ''
                for arg in self._search_args:
                    if arg.endswith(':'):
                        prefix = arg
                    elif ':' in arg or (arg and arg[0] in ('-', '+')):
                        prefix = ''
                        session.searched.append(arg.lower())
                    elif prefix and '@' in arg:
                        session.searched.append(prefix + arg.lower())
                    else:
                        words = re.findall(WORD_REGEXP, arg.lower())
                        session.searched.extend([prefix + word
                                                 for word in words])
            if not session.searched:
                session.searched = ['all:mail']

            context = session.results if self.context else None
            session.results = list(idx.search(session, session.searched,
                                              context=context).as_set())
            if session.order:
                idx.sort_results(session, session.results, session.order)

        return session, idx

    def cache_requirements(self, result):
        msgs = self.session.results[self._start:self._start + self._num]
        def fix_term(term):
            # Terms are reversed in the search engine...
            if term[:1] in ['-', '+']:
                term = term[1:]
            term = ':'.join(reversed(term.split(':', 1)))
            return unicode(term)
        reqs = set(['!config'] +
                   [fix_term(t) for t in self.session.searched] +
                   [u'%s:msg' % i for i in msgs])
        if self.session.displayed:
            reqs |= set(u'%s:thread' % int(tmid, 36) for tmid in
                        self.session.displayed.get('thread_ids', []))
            reqs |= set(u'%s:msg' % int(tmid, 36) for tmid in
                        self.session.displayed.get('message_ids', []))
        return reqs

    def command(self):
        session, idx = self._do_search()
        full_threads = self.data.get('full', False)
        session.displayed = SearchResults(session, idx,
                                          start=self._start,
                                          num=self._num,
                                          full_threads=full_threads)
        session.ui.mark(_('Prepared %d search results (context=%s)'
                          ) % (len(session.results), self.context))
        return self._success(_('Found %d results in %.3fs'
                               ) % (len(session.results),
                                    session.ui.report_marks(quiet=True)),
                             result=session.displayed)


class Next(Search):
    """Display next page of results"""
    SYNOPSIS = ('n', 'next', None, None)
    ORDER = ('Searching', 1)
    HTTP_CALLABLE = ()
    COMMAND_CACHE_TTL = 0

    def command(self):
        session = self.session
        try:
            session.displayed = session.displayed.next_set()
        except AttributeError:
            session.ui.error(_("You must perform a search before "
                               "requesting the next page."))
            return False
        return self._success(_('Displayed next page of results.'),
                             result=session.displayed)


class Previous(Search):
    """Display previous page of results"""
    SYNOPSIS = ('p', 'previous', None, None)
    ORDER = ('Searching', 2)
    HTTP_CALLABLE = ()
    COMMAND_CACHE_TTL = 0

    def command(self):
        session = self.session
        try:
            session.displayed = session.displayed.previous_set()
        except AttributeError:
            session.ui.error(_("You must perform a search before "
                               "requesting the previous page."))
            return False
        return self._success(_('Displayed previous page of results.'),
                             result=session.displayed)


class Order(Search):
    """Sort by: date, from, subject, random or index"""
    SYNOPSIS = ('o', 'order', None, '<how>')
    ORDER = ('Searching', 3)
    HTTP_CALLABLE = ()
    COMMAND_CACHE_TTL = 0

    def command(self):
        session, idx = self.session, self._idx()
        session.order = self.args and self.args[0] or None
        idx.sort_results(session, session.results, session.order)
        session.displayed = SearchResults(session, idx)
        return self._success(_('Changed sort order to %s') % session.order,
                             result=session.displayed)


class View(Search):
    """View one or more messages"""
    SYNOPSIS = ('v', 'view', 'message', '[raw] <message>')
    ORDER = ('Searching', 4)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID'
    }
    COMMAND_CACHE_TTL = 0

    class RawResult(dict):
        def _decode(self):
            try:
                return self['source'].decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return self['source'].decode('iso-8859-1')
                except:
                    return '(MAILPILE FAILED TO DECODE MESSAGE)'

        def as_text(self, *args, **kwargs):
            return self._decode()

        def as_html(self, *args, **kwargs):
            return '<pre>%s</pre>' % escape_html(self._decode())

    def _side_effects(self, emails):
        session, config, idx = self.session, self.session.config, self._idx()
        msg_idxs = [e.msg_idx_pos for e in emails]
        if 'tags' in config:
            for tag in config.get_tags(type='unread'):
                idx.remove_tag(session, tag._key, msg_idxs=msg_idxs)
            for tag in config.get_tags(type='read'):
                idx.add_tag(session, tag._key, msg_idxs=msg_idxs)

        idx.apply_filters(session, '@read',
                          msg_idxs=[e.msg_idx_pos for e in emails])
        return None

    def state_as_query_args(self):
        return Command.state_as_query_args(self)

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        results = []
        args = list(self.args)
        if args and args[0].lower() == 'raw':
            raw = args.pop(0)
        else:
            raw = False
        emails = [Email(idx, mid) for mid in self._choose_messages(args)]

        rv = self._side_effects(emails)
        if rv is not None:
            # This is here so derived classes can do funky things.
            return rv

        for email in emails:
            if raw:
                subject = email.get_msg_info(idx.MSG_SUBJECT)
                results.append(self.RawResult({
                    'summary': _('Raw message: %s') % subject,
                    'source': email.get_file().read()
                }))
            else:
                old_result = None
                for result in results:
                    if email.msg_idx_pos in result.results:
                        old_result = result
                if old_result:
                    old_result.add_email(email)
                    continue

                conv = [int(c[0], 36) for c
                        in idx.get_conversation(msg_idx=email.msg_idx_pos)]
                if email.msg_idx_pos not in conv:
                    conv.append(email.msg_idx_pos)

                # FIXME: This is a hack. The indexer should just keep things
                #        in the right order on rescan. Fixing threading is a
                #        bigger problem though, so we do this for now.
                def sort_conv_key(msg_idx_pos):
                    info = idx.get_msg_at_idx_pos(msg_idx_pos)
                    return -int(info[idx.MSG_DATE], 36)
                conv.sort(key=sort_conv_key)

                session.results = conv
                results.append(SearchResults(session, idx, emails=[email]))
        if len(results) == 1:
            return self._success(_('Displayed a single message'),
                                 result=results[0])
        else:
            session.results = []
            return self._success(_('Displayed %d messages') % len(results),
                                 result=results)


class Extract(Command):
    """Extract attachment(s) to file(s)"""
    SYNOPSIS = ('e', 'extract', 'message/download', '<msgs> <att> [><fn>]')
    ORDER = ('Searching', 5)
    RAISES = (SuppressHtmlOutput, UrlRedirectException)
    IS_USER_ACTIVITY = True

    class CommandResult(Command.CommandResult):
        def __init__(self, *args, **kwargs):
            self.fixed_up = False
            Command.CommandResult.__init__(self, *args, **kwargs)

        def _fixup(self):
            if self.fixed_up:
                return self
            for result in (self.result or []):
                if 'data' in result:
                    result['data'] = result['data'].encode('base64'
                                                           ).replace('\n', '')
            self.fixed_up = True
            return self

        def as_html(self, *args, **kwargs):
            return Command.CommandResult.as_html(self._fixup(),
                                                 *args, **kwargs)

        def as_dict(self, *args, **kwargs):
            return Command.CommandResult.as_dict(self._fixup(),
                                                 *args, **kwargs)

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        mode = 'download'
        name_fmt = None

        args = list(self.args)
        if args[0] in ('inline', 'inline-preview', 'preview', 'download'):
            mode = args.pop(0)

        if len(args) > 0 and args[-1].startswith('>'):
            if self.session.config.sys.lockdown:
                return self._error(_('In lockdown, doing nothing.'))
            name_fmt = args.pop(-1)[1:]

        if (args[0].startswith('#') or
                args[0].startswith('part:') or
                args[0].startswith('ext:')):
            cid = args.pop(0)
        else:
            cid = args.pop(-1)

        emails = [Email(idx, i) for i in self._choose_messages(args)]
        results = []
        for e in emails:
            if cid[0] == '*':
                tree = e.get_message_tree(want=['attachments'])
                cids = [('#%s' % a['count']) for a in tree['attachments']
                        if a['filename'].lower().endswith(cid[1:].lower())]
            else:
                cids = [cid]

            for c in cids:
                fn, info = e.extract_attachment(session, c,
                                                name_fmt=name_fmt, mode=mode)
                if info:
                    info['idx'] = e.msg_idx_pos
                    if fn:
                        info['created_file'] = fn
                    results.append(info)
        return results


_plugins.register_commands(Extract, Next, Order, Previous, Search, View)


##[ Search terms ]############################################################

def mailbox_search(config, idx, term, hits):
    word = term.split(':', 1)[1].lower()
    try:
        mbox_id = FormatMbxId(b36(int(word, 36)))
    except ValueError:
        mbox_id = None

    mailboxes = [m for m in config.sys.mailbox.keys()
                 if (mbox_id == m) or word in config.sys.mailbox[m].lower()]
    rt = []
    for mbox_id in mailboxes:
        mbox_id = FormatMbxId(mbox_id)
        rt.extend(hits('%s:mailbox' % mbox_id))
    return rt


_plugins.register_search_term('mailbox', mailbox_search)
