import datetime
import json
import re
import time
import unicodedata

import mailpile.security as security
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils import Email, FormatMbxId, AddressHeaderParser
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName
from mailpile.plugins import PluginManager
from mailpile.search import MailIndex
from mailpile.urlmap import UrlMap
from mailpile.util import *
from mailpile.ui import SuppressHtmlOutput
from mailpile.vfs import vfs, FilePath
from mailpile.vcard import AddressInfo


_plugins = PluginManager(builtin=__file__)


##[ Shared basic Search Result class]#########################################

class SearchResults(dict):

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
            if l == len(namelist):
                break
            l = len(namelist)
        namelist = re.sub(',,,+, *', ' .. ', namelist, 1)
        return namelist

    TAG_TYPE_FLAG_MAP = {
        'trash': 'trash',
        'spam': 'spam',
        'ham': 'ham',
        'drafts': 'draft',
        'blank': 'draft',
        'sent': 'from_me',
        'unread': 'unread',
        'outbox': 'from_me',
        'replied': 'replied',
        'fwded': 'forwarded'
    }

    def _metadata(self, msg_info):
        msg_mid = msg_info[MailIndex.MSG_MID]
        if '-' in msg_mid:
            # Ephemeral...
            msg_idx = None
        else:
            msg_idx = int(msg_mid, 36)
            cache = self.idx.CACHE.get(msg_idx, {})
            if 'metadata' in cache:
                return cache['metadata']

        nz = lambda l: [v for v in l if v]
        msg_ts = long(msg_info[MailIndex.MSG_DATE], 36)
        msg_date = datetime.datetime.fromtimestamp(msg_ts)

        fe, fn = ExtractEmailAndName(msg_info[MailIndex.MSG_FROM])
        f_info = self._address(e=fe, n=fn)
        f_info['aid'] = (self._msg_addresses(msg_info, no_to=True, no_cc=True)
                         or [''])[0]
        thread_mid = parent_mid = msg_info[MailIndex.MSG_THREAD_MID]
        if '/' in thread_mid:
            thread_mid, parent_mid = thread_mid.split('/')
        expl = {
            'mid': msg_mid,
            'id': msg_info[MailIndex.MSG_ID],
            'timestamp': msg_ts,
            'from': f_info,
            'to_aids': self._msg_addresses(msg_info, no_from=True, no_cc=True),
            'cc_aids': self._msg_addresses(msg_info, no_from=True, no_to=True),
            'msg_kb': int(msg_info[MailIndex.MSG_KB], 36),
            'tag_tids': sorted(self._msg_tags(msg_info)),
            'thread_mid': thread_mid,
            'parent_mid': parent_mid,
            'subject': msg_info[MailIndex.MSG_SUBJECT],
            'body': MailIndex.get_body(msg_info),
            'flags': {
            },
            'crypto': {
            }
        }

        # Ephemeral messages do not have URLs
        if '-' in msg_info[MailIndex.MSG_MID]:
            expl['flags'].update({
                'ephemeral': True,
                'draft': True,
            })
        else:
            expl['urls'] = {
                'thread': self.urlmap.url_thread(msg_info[MailIndex.MSG_MID]),
                'source': self.urlmap.url_source(msg_info[MailIndex.MSG_MID]),
            }

        # Support rich snippets
        if expl['body']['snippet'].startswith('{'):
            try:
                expl['body'] = json.loads(expl['body']['snippet'])
            except ValueError:
                pass

        # Misc flags
        sender_vcard = self.idx.config.vcards.get_vcard(fe.lower())
        if sender_vcard:
            if sender_vcard.kind == 'profile':
                expl['flags']['from_me'] = True
        tag_types = [self.idx.config.get_tag(t).type for t in expl['tag_tids']]
        for t in self.TAG_TYPE_FLAG_MAP:
            if t in tag_types:
                expl['flags'][self.TAG_TYPE_FLAG_MAP[t]] = True

        # Check tags for signs of encryption or signatures
        tag_slugs = [self.idx.config.get_tag(t).slug for t in expl['tag_tids']]
        for t in tag_slugs:
            if t.startswith('mp_sig'):
                expl['crypto']['signature'] = t[7:]
            elif t.startswith('mp_enc'):
                expl['crypto']['encryption'] = t[7:]

        # Extra behavior for editable messages
        if 'draft' in expl['flags']:
            if 'ephemeral' in expl['flags']:
                pass
            elif self.idx.config.is_editable_message(msg_info):
                expl['urls']['editing'] = self.urlmap.url_edit(expl['mid'])
            else:
                del expl['flags']['draft']

        if msg_idx is not None:
            cache['metadata'] = expl
            self.idx.CACHE[msg_idx] = cache
        return expl

    def _msg_addresses(self, msg_info=None, addresses=[],
                       no_from=False, no_to=False, no_cc=False):
        cids = set()

        for ai in addresses:
            eid = self.idx.EMAIL_IDS.get(ai.address.lower())
            cids.add(b36(self.idx._add_email(ai.address, name=ai.fn, eid=eid)))

        if msg_info:
            if not no_to:
                to = [t for t in msg_info[MailIndex.MSG_TO].split(',') if t]
                cids |= set(to)
            if not no_cc:
                cc = [t for t in msg_info[MailIndex.MSG_CC].split(',') if t]
                cids |= set(cc)
            if not no_from:
                fe, fn = ExtractEmailAndName(msg_info[MailIndex.MSG_FROM])
                if fe:
                    eid = self.idx.EMAIL_IDS.get(fe.lower())
                    cids.add(b36(self.idx._add_email(fe, name=fn, eid=eid)))

        return sorted(list(cids))

    def _address(self, cid=None, e=None, n=None):
        if cid and not (e and n):
            e, n = ExtractEmailAndName(self.idx.EMAILS[int(cid, 36)])
        vcard = self.session.config.vcards.get_vcard(e)
        if vcard and '@' in n:
            n = vcard.fn
        return AddressInfo(e, n, vcard=vcard)

    def _msg_tags(self, msg_info):
        tids = [t for t in msg_info[MailIndex.MSG_TAGS].split(',')
                if t and t in self.session.config.tags]
        return tids

    def _tag(self, tid, attributes={}):
        return dict_merge(self.session.config.get_tag_info(tid), attributes)

    _BAR = u'\u2502'
    _FORK = u'\u251c'
    _FIRST = u'\u256d'
    _LAST = u'\u2570'
    _BLANK = u' '
    _DASH = u'\u2500'
    _TEE = u'\u252c'

    def _thread(self, thread_mid):
        thr_info = self.idx.get_conversation(msg_idx=int(thread_mid, 36))
        thr_info.sort(key=lambda i: long(i[self.idx.MSG_DATE], 36))
        if not thr_info:
            return []

        # Map messages to parents
        par_map = {}
        for info in thr_info:
            parent = (info[self.idx.MSG_THREAD_MID].split('/') + [None])[1]
            par_map[info[self.idx.MSG_MID]] = (parent, info)

        # Reverse the mapping
        thr_map = {}
        first_mid = thr_info[0][self.idx.MSG_MID]
        for msg_mid, (par_mid, m_info) in par_map.iteritems():
            if par_mid is None:
                # If we have no parent, pretend the first message in the
                # thread is the parent.
                par_mid = first_mid
            if par_mid != msg_mid:
                thr_map[par_mid] = (thr_map.get(par_mid, []) + [msg_mid])
            else:
                thr_map[par_mid] = thr_map.get(par_mid, [])

        # Render threads in thread order, including ascii art
        thread = []
        seen = set()
        def by_date(p):
            if p not in par_map:
                return 0;
            return int(par_map[p][1][self.idx.MSG_DATE], 36)
        def render(prefix, mid, first=False):
            kids = thr_map.get(mid, [])
            if mid not in seen:
                # This guarantees that if we somehow end up with a loop, we
                # just skip over the repeated message and make progress.
                seen.add(mid)
                thread.append([mid,
                               prefix + ((self._FIRST if first else self._TEE)
                                         if kids else ''),
                               kids])
                if prefix.endswith(self._LAST):
                    prefix = prefix[:-len(self._BAR)] + self._BLANK
                elif prefix:
                    prefix = prefix[:-len(self._BAR)] + self._BAR

            if kids:
                # This delete also prevents us from repeating ourselves.
                del thr_map[mid]
                kids.sort(key=by_date)
                for i, kmid in enumerate(kids):
                    if prefix.endswith(self._BLANK):
                        if thread[-1][1].endswith(self._TEE):
                            thread[-1][1] = thread[-1][1][:-len(self._TEE)]
                            thread[-1][1] = thread[-1][1][:-len(self._LAST)]
                            thread[-1][1] += self._FORK
                            prefix = prefix[:-len(self._BLANK)]
                    if i < len(kids) - 1:
                        render(prefix + self._FORK, kmid)
                    else:
                        if prefix.endswith(self._BLANK):
                            if thread[-1][1].endswith(self._LAST):
                                thread[-1][1] = thread[-1][1][:-len(self._LAST)]
                                prefix = prefix[:-len(self._BLANK)]
                        render(prefix + self._LAST, kmid)
        thr_keys = thr_map.keys()
        thr_keys.sort(key=by_date)
        first = True
        for par_mid in thr_keys:
            if par_mid in thr_map:
                render('', par_mid, first=first)
                first = False

        return thread

    WANT_MSG_TREE = ('attachments', 'html_parts', 'text_parts', 'header_list',
                     'editing_strings', 'crypto')
    PRUNE_MSG_TREE = ('headers', )  # Added by editing_strings

    def _prune_msg_tree(self, tree):
        for k in tree.keys():
            if k not in self.WANT_MSG_TREE or k in self.PRUNE_MSG_TREE:
                del tree[k]
        for att in tree.get('attachments', []):
            if 'part' in att:
                del att['part']
        return tree

    def _message(self, email):
        tree = email.get_message_tree(want=(email.WANT_MSG_TREE_PGP +
                                            self.WANT_MSG_TREE))
        email.evaluate_pgp(tree, decrypt=True)

        editing_strings = tree.get('editing_strings')
        if editing_strings:
            for key in ('from', 'to', 'cc', 'bcc'):
                if key in editing_strings:
                    cids = self._msg_addresses(
                        addresses=AddressHeaderParser(
                            unicode_data=editing_strings[key]))
                    editing_strings['%s_aids' % key] = cids
                    for cid in cids:
                        if cid not in self['data']['addresses']:
                            self['data']['addresses'
                                         ][cid] = self._address(cid=cid)

        return self._prune_msg_tree(tree)

    def __init__(self, session, idx,
                 results=None, start=0, end=None, num=None,
                 emails=None, view_pairs=None, people=None,
                 suppress_data=False, full_threads=True):
        dict.__init__(self)
        self.session = session
        self.people = people
        self.emails = emails or []
        self.view_pairs = view_pairs or {}
        self.idx = idx
        self.urlmap = UrlMap(self.session)

        results = self.results = results or session.results or []

        num = num or session.config.prefs.num_results
        if end:
            start = end - num
        if start > len(results):
            start = len(results)
        if start < 0:
            start = 0

        try:
            threads = [b36(r) for r in results[start:start + num]]
        except TypeError:
            results = threads = []
            start = end = 0

        self.session.ui.mark(_('Parsing metadata for %d results '
                               '(full_threads=%s)') % (len(threads),
                                                       full_threads))

        self.update({
            'summary': _('Search: %s') % ' '.join(session.searched),
            'stats': {
                'count': len(threads),
                'start': start + 1,
                'end': start + min(num, len(results)-start),
                'total': len(results),
            },
            'search_terms': session.searched,
            'address_ids': [],
            'message_ids': [],
            'view_pairs': view_pairs,
            'thread_ids': threads,
        })
        if 'tags' in self.session.config:
            search_tags = [idx.config.get_tag(t.split(':')[1], {})
                           for t in session.searched
                           if t.startswith('in:') or t.startswith('tag:')]
            search_tag_ids = [t._key for t in search_tags if t]
            self.update({
                'search_tag_ids': search_tag_ids,
            })
            if search_tag_ids:
                self['summary'] = ' & '.join([t.name for t
                                              in search_tags if t])
        else:
            search_tag_ids = []

        if suppress_data or (not results and not emails):
            return

        self.update({
            'data': {
                'addresses': {},
                'metadata': {},
                'messages': {},
                'threads': {}
            }
        })
        if 'tags' in self.session.config:
            th = self['data']['tags'] = {}
            for tid in search_tag_ids:
                if tid not in th:
                    th[tid] = self._tag(tid, {'searched': True})

        idxs = results[start:start + num]

        for e in emails or []:
            self.add_email(e, idxs)

        done_idxs = set()
        while idxs:
            idxs = list(set(idxs) - done_idxs)
            for idx_pos in idxs:
                done_idxs.add(idx_pos)
                msg_info = idx.get_msg_at_idx_pos(idx_pos)
                self.add_msg_info(b36(idx_pos), msg_info,
                                  full_threads=full_threads, idxs=idxs)

        if emails and len(emails) == 1:
            self['summary'] = emails[0].get_msg_info(MailIndex.MSG_SUBJECT)

    def add_msg_info(self, mid, msg_info, full_threads=False, idxs=None):
        # Populate data.metadata
        self['data']['metadata'][mid] = self._metadata(msg_info)

        # Populate data.thread
        thread_mid = parent_mid = msg_info[MailIndex.MSG_THREAD_MID]
        if '/' in thread_mid:
            thread_mid, parent_mid = thread_mid.split('/')
        if thread_mid not in self['data']['threads']:
            thread = self._thread(thread_mid)
            self['data']['threads'][thread_mid] = thread
            if full_threads and idxs:
                idxs.extend([int(t, 36) for t, bar, kids in thread
                             if t not in self['data']['metadata']])

        # Populate data.person
        for cid in self._msg_addresses(msg_info):
            if cid not in self['data']['addresses']:
                self['data']['addresses'][cid] = self._address(cid=cid)

        # Populate data.tag
        if 'tags' in self.session.config:
            for tid in self._msg_tags(msg_info):
                if tid not in self['data']['tags']:
                    self['data']['tags'][tid] = self._tag(tid,
                                                          {"searched": False})

    def add_email(self, e, idxs):
        if e not in self.emails:
            self.emails.append(e)
        mid = e.msg_mid()
        if mid not in self['data']['messages']:
            self['data']['messages'][mid] = self._message(e)
        if mid not in self['message_ids']:
            self['message_ids'].append(mid)
        # This happens last, as the parsing above may have side-effects
        # which matter once we get this far.
        self.add_msg_info(mid, e.get_msg_info(uncached=True),
                          full_threads=True, idxs=idxs)

    def __nonzero__(self):
        return True

    def next_set(self):
        stats = self['stats']
        return SearchResults(self.session, self.idx,
                             start=stats['start'] - 1 + stats['count'])

    def previous_set(self):
        stats = self['stats']
        return SearchResults(self.session, self.idx,
                             end=stats['start'] - 1)

    def _fix_width(self, text, width):
        chars = []
        for c in unicode(text):
            cwidth = 2 if (unicodedata.east_asian_width(c) in 'WF') else 1
            if cwidth <= width:
                chars.append(c)
                width -= cwidth
            else:
                break
        if width:
            chars += [' ' * width]
        return ''.join(chars)

    def as_text(self):
        from mailpile.www.jinjaextensions import MailpileCommand as JE
        clen = max(3, len('%d' % len(self.session.results)))
        cfmt = '%%%d.%ds' % (clen, clen)

        term_width = self.session.ui.term.max_width()
        fs_width = int((22 + 53) * (term_width / 79.0))
        f_width = min(32, int(0.30 * fs_width))
        s_width = fs_width - f_width

        text = []
        count = self['stats']['start']
        expand_ids = [e.msg_idx_pos for e in self.emails]
        addresses = self.get('data', {}).get('addresses', {})

        for mid in self['thread_ids']:
            m = self['data']['metadata'][mid]
            tags = [self['data']['tags'].get(t) for t in m['tag_tids']]
            tags = [t for t in tags if t]
            tag_names = [t['name'] for t in tags
                         if not t.get('searched', False)
                         and t.get('label', True)
                         and t.get('display', '') != 'invisible']
            tag_new = [t for t in tags if t.get('type') == 'unread']
            tag_names.sort()
            msg_meta = tag_names and ('  (' + '('.join(tag_names)) or ''

            # FIXME: this is a bit ugly, but useful for development
            es = ['', '']
            for t in [t['slug'] for t in tags]:
                if t.startswith('mp_enc') and 'none' not in t:
                    es[1] = 'E'
                if t.startswith('mp_sig') and 'none' not in t:
                    es[0] = 'S'
            es = ''.join([e for e in es if e])
            if es:
                msg_meta = (msg_meta or '  ') + ('[%s]' % es)
            elif msg_meta:
                msg_meta += ')'
            else:
                msg_meta += '  '
            msg_meta += elapsed_datetime(m['timestamp'])

            from_info = (m['from'].get('fn') or m['from'].get('email')
                         or '(anonymous)')
            if from_info[:1] in ('<', '"', '\''):
                from_info = from_info[1:]
                if from_info[-1:] in ('>', '"', '\''):
                    from_info = from_info[:-1]
            if '@' in from_info and len(from_info) > 18:
                e, d = from_info.split('@', 1)
                if d in ('gmail.com', 'yahoo.com', 'hotmail.com'):
                    from_info = '%s@%s..' % (e, d[0])
                else:
                    from_info = '%s..@%s' % (e[0], d)

            if not expand_ids:
                def gg(pos):
                    return (pos < 10) and pos or '>'
                thr_mid = m['thread_mid']
                thread = [ti[0] for ti in self['data']['threads'][thr_mid]]
                if m['mid'] not in thread:
                    thread.append(m['mid'])
                pos = thread.index(m['mid']) + 1
                if pos > 1:
                    from_info = '%s>%s' % (gg(pos-1), from_info)
                else:
                    from_info = '  ' + from_info
                if pos < len(thread):
                    from_info = '%s>%s' % (from_info[:20], gg(len(thread)-pos))

            subject = re.sub('^(\\[[^\\]]{6})[^\\]]{3,}\\]\\s*', '\\1..] ',
                             JE._nice_subject(m))
            subject_width = max(1, s_width - (clen + len(msg_meta)))
            subject = self._fix_width(subject, subject_width)
            from_info = self._fix_width(from_info, f_width)

            #sfmt = '%%s%%s' % (subject_width, subject_width)
            #ffmt = ' %%s%%s' % (f_width, f_width)
            tfmt = cfmt + ' %s%s%s%s'
            text.append(tfmt % (count, from_info, tag_new and '*' or ' ',
                                subject, msg_meta))

            if mid in self['data'].get('messages', {}):
                exp_email = self.emails[expand_ids.index(int(mid, 36))]
                msg_tree = exp_email.get_message_tree()
                text.append('-' * term_width)
                text.append(exp_email.get_editing_string(msg_tree,
                    attachment_headers=False).strip())
                if msg_tree['attachments']:
                    text.append('\nAttachments:')
                    for a in msg_tree['attachments']:
                        text.append('%5.5s %s' % ('#%s' % a['count'],
                                                  a['filename']))
                text.append('-' * term_width)

            count += 1
        if not count:
            text = ['(No messages found)']
        return '\n'.join(text) + '\n'
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
        'view': 'MID/MID pairs to expand in place',
        'context': 'refine or redisplay an older search'
    }
    IS_USER_ACTIVITY = True
    COMMAND_CACHE_TTL = 900
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
                elif hasattr(self.result, 'as_text'):
                    return self.result.as_text()
                return _('Unprintable results')
            else:
                return _('No results')

        def as_html(self, *args, **kwargs):
            return Command.CommandResult.as_html(self._fixup(),
                                                 *args, **kwargs)

        def as_dict(self, *args, **kwargs):
            return Command.CommandResult.as_dict(self._fixup(),
                                                 *args, **kwargs)

    def __init__(self, *args, **kwargs):
        Command.__init__(self, *args, **kwargs)
        self._email_views = []
        self._email_view_pairs = {}
        self._emails = []

    def state_as_query_args(self):
        try:
            return self._search_state
        except (AttributeError, NameError):
            return Command.state_as_query_args(self)

    def _starting(self):
        Command._starting(self)
        session, idx = self.session, self._idx()
        self._search_args = args = []

        self._email_views = self.data.get('view', [])
        self._email_view_pairs = dict((m.split('/')[0], m.split('/')[-1])
                                      for m in self._email_views)
        self._emails = []

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
        self._default_position = True
        while args and args[0].startswith('@'):
            spoint = args.pop(0)[1:]
            try:
                start = int(spoint) - 1
                self._default_position = False
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
            'view': self._email_views,
            'end': [str(start + num)] if (num != def_num) else []
        }
        if self.context:
            self._search_state['context'] = [self.context]

    def _email_view_side_effects(self, emails):
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
                        if not arg.startswith('vfs:'):
                            arg = arg.lower()
                        prefix = ''
                        session.searched.append(arg)
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

        self._emails = []
        pivot_pos = any_pos = len(session.results)
        for pmid, emid in list(self._email_view_pairs.iteritems()):
            try:
                emid_idx = int(emid, 36)
                for info in idx.get_conversation(msg_idx=emid_idx):
                    cmid = info[idx.MSG_MID]
                    self._email_view_pairs[cmid] = emid
                    # Calculate visibility...
                    try:
                        cpos = session.results.index(int(cmid, 36))
                    except ValueError:
                        cpos = -1
                    if cpos >= 0:
                        any_pos = min(any_pos, cpos)
                    if (cpos > self._start and
                            cpos < self._start + self._num + 1):
                        pivot_pos = min(cpos, pivot_pos)
                self._emails.append(Email(idx, emid_idx))
            except ValueError:
                self._email_view_pairs = {}

        # Adjust the visible window of results if we are expanding an
        # individual message, to guarantee visibility.
        if pivot_pos < len(session.results):
            self._start = max(0, pivot_pos - max(self._num // 5, 2))
        elif any_pos < len(session.results):
            self._start = max(0, any_pos - max(self._num // 5, 2))

        if self._emails:
            self._email_view_side_effects(self._emails)

        return session, idx

    def cache_id(self, *args, **kwargs):
        if self._emails:
            return ''
        return Command.cache_id(self, *args, **kwargs)

    def cache_requirements(self, result):
        msgs = self.session.results[self._start:self._start + self._num]
        def fix_term(term):
            # Terms are reversed in the search engine...
            if term[:1] in ['-', '+']:
                term = term[1:]
            if term[:4] == 'vfs:':
                raise ValueError('VFS searches are not cached')
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
                                          emails=self._emails,
                                          view_pairs=self._email_view_pairs,
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
        # A compatibility stub only
        return self._email_view_side_effects(emails)

    def state_as_query_args(self):
        return Command.state_as_query_args(self)

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        results = []
        args = list(self.args)
        args.extend(['=%s' % mid.replace('=', '')
                     for mid in self.data.get('mid', [])])
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

                # Get conversation
                conv = idx.get_conversation(msg_idx=email.msg_idx_pos)

                # Sort our results by date...
                def sort_conv_key(info):
                    return -int(info[idx.MSG_DATE], 36)
                conv.sort(key=sort_conv_key)

                # Convert to index positions only
                conv = [int(info[idx.MSG_MID], 36) for info in conv]

                session.results = conv
                results.append(SearchResults(session, idx,
                                             emails=[email],
                                             num=len(conv)))
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
            forbid = security.forbid_command(self,
                                             security.CC_ACCESS_FILESYSTEM)
            if forbid:
                return self._error(forbid)
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

    mailboxes = []
    for m in config.sys.mailbox.keys():
        fn = FilePath(config.sys.mailbox[m]).display().lower()
        if (mbox_id == m) or word in fn:
            mailboxes.append(m)

    rt = []
    for mbox_id in mailboxes:
        mbox_id = FormatMbxId(mbox_id)
        rt.extend(hits('%s:mailbox' % mbox_id))

    return rt


_plugins.register_search_term('mailbox', mailbox_search)
