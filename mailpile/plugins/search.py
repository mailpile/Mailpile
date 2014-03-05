import datetime
import re
import time
from gettext import gettext as _

import mailpile.plugins
from mailpile.commands import Command, SearchResults
from mailpile.mailutils import Email, MBX_ID_LEN
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName
from mailpile.search import MailIndex
from mailpile.urlmap import UrlMap
from mailpile.util import *
from mailpile.ui import SuppressHtmlOutput


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
            Command.CommandResult.__init__(self, *args, **kwargs)
            self.fixed_up = False
            if isinstance(self.result, dict):
                self.message = self.result.get('summary', '')
            elif isinstance(self.result, list):
                self.message = ', '.join([r.get('summary', '') for r in self.result])

        def _fixup(self):
            if self.fixed_up:
                return self
            self.fixed_up = True
            return self

        def as_text(self):
            if self.result:
                if isinstance(self.result, (list, set)):
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

    def _do_search(self, search=None):
        session, idx = self.session, self._idx()
        session.searched = search or []
        args = self.args[:]

        for q in self.data.get('q', []):
            args.extend(q.split())

        for order in self.data.get('order', []):
            session.order = order

        num = session.config.prefs.num_results
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
                start = int(spoint) - 1
            except ValueError:
                raise UsageError(_('Weird starting point: %s') % spoint)
        else:
            start = 0

        # FIXME: Is this dumb?
        for arg in args:
            if ':' in arg or (arg and arg[0] in ('-', '+')):
                session.searched.append(arg.lower())
            else:
                session.searched.extend(re.findall(WORD_REGEXP, arg.lower()))

        session.order = session.order or session.config.prefs.default_order
        session.results = list(idx.search(session, session.searched).as_set())
        idx.sort_results(session, session.results, session.order)
        return session, idx, start, num

    def command(self, search=None):
        session, idx, start, num = self._do_search(search=search)
        session.displayed = SearchResults(session, idx, start=start, num=num)
        return session.displayed


class Next(Search):
    """Display next page of results"""
    SYNOPSIS = ('n', 'next', None, None)
    ORDER = ('Searching', 1)
    HTTP_CALLABLE = ()

    def command(self):
        session = self.session
        try:
            session.displayed = session.displayed.next_set()
        except AttributeError:
            session.ui.error(_("You must perform a search before requesting the next page."))
            return False
        return session.displayed


class Previous(Search):
    """Display previous page of results"""
    SYNOPSIS = ('p', 'previous', None, None)
    ORDER = ('Searching', 2)
    HTTP_CALLABLE = ()

    def command(self):
        session = self.session
        try:
            session.displayed = session.displayed.previous_set()
        except AttributeError:
            session.ui.error(_("You must perform a search before requesting the previous page."))
            return False
        return session.displayed


class Order(Search):
    """Sort by: date, from, subject, random or index"""
    SYNOPSIS = ('o', 'order', None, '<how>')
    ORDER = ('Searching', 3)
    HTTP_CALLABLE = ()

    def command(self):
        session, idx = self.session, self._idx()
        session.order = self.args and self.args[0] or None
        idx.sort_results(session, session.results, session.order)
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

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        results = []
        if self.args and self.args[0].lower() == 'raw':
            raw = self.args.pop(0)
        else:
            raw = False
        emails = [Email(idx, mid) for mid in self._choose_messages(self.args)]

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

                results.append(SearchResults(session, idx,
                                             results=conv, num=len(conv),
                                             emails=[email]))
        if len(results) == 1:
            return results[0]
        else:
            return results


class Extract(Command):
    """Extract attachment(s) to file(s)"""
    SYNOPSIS = ('e', 'extract', 'message/download', '<msgs> <att> [><fn>]')
    ORDER = ('Searching', 5)
    RAISES = (SuppressHtmlOutput, UrlRedirectException)

    class CommandResult(Command.CommandResult):
        def __init__(self, *args, **kwargs):
            self.fixed_up = False
            return Command.CommandResult.__init__(self, *args, **kwargs)

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

        if self.args[0] in ('inline', 'inline-preview', 'preview', 'download'):
            mode = self.args.pop(0)

        if len(self.args) > 0 and self.args[-1].startswith('>'):
            name_fmt = self.args.pop(-1)[1:]

        if self.args[0].startswith('#') or self.args[0].startswith('part:'):
            cid = self.args.pop(0)
        else:
            cid = self.args.pop(-1)

        eids = self._choose_messages(self.args)
        print 'Download %s from %s as %s/%s' % (cid, eids, mode, name_fmt)

        emails = [Email(idx, i) for i in eids]
        results = []
        for e in emails:
            fn, info = e.extract_attachment(session, cid,
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
                 if word in config.sys.mailbox[m].lower() or mailbox_id == m]
    rt = []
    for mbox_id in mailboxes:
        mbox_id = (('0' * MBX_ID_LEN) + mbox_id)[-MBX_ID_LEN:]
        rt.extend(hits('%s:mailbox' % mbox_id))
    return rt


mailpile.plugins.register_search_term('mailbox', mailbox_search)
