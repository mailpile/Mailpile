# These are the Mailpile commands, the public "API" we expose for searching,
# tagging and editing e-mail.
#
import copy
import datetime
import json
import os
import os.path
import re
import traceback
import time
from gettext import gettext as _

import mailpile.util
import mailpile.ui
from mailpile.eventlog import Event
from mailpile.mailboxes import IsMailbox
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName, Email
from mailpile.postinglist import GlobalPostingList
from mailpile.search import MailIndex
from mailpile.util import *
from mailpile.vcard import AddressInfo


class Command:
    """Generic command object all others inherit from"""
    SYNOPSIS = (None,    # CLI shortcode, e.g. A:
                None,    # CLI shortname, e.g. add
                None,    # API endpoint, e.g. sys/addmailbox
                None)    # Positional argument list
    SYNOPSIS_ARGS = None # New-style positional argument list
    API_VERSION = None
    UI_CONTEXT = None

    FAILURE = 'Failed: %(name)s %(args)s'
    ORDER = (None, 0)
    SERIALIZE = False
    SPLIT_ARG = 10000  # A big number!
    RAISES = (UsageError, UrlRedirectException)

    # Event logging settings
    LOG_NOTHING = False
    LOG_PROGRESS = False
    LOG_STARTING = '%(name)s: Starting'
    LOG_FINISHED = '%(name)s: %(message)s'

    # HTTP settings (note: security!)
    HTTP_CALLABLE = ('GET', )
    HTTP_POST_VARS = {}
    HTTP_QUERY_VARS = {}
    HTTP_BANNED_VARS = {}
    HTTP_STRICT_VARS = True

    class CommandResult:
        def __init__(self, command_obj, session,
                     command_name, doc, result, status, message,
                     template_id=None, kwargs={}, error_info={}):
            self.session = session
            self.command_obj = command_obj
            self.command_name = command_name
            self.kwargs = {}
            self.kwargs.update(kwargs)
            self.template_id = template_id
            self.doc = doc
            self.result = result
            self.status = status
            self.error_info = {}
            self.error_info.update(error_info)
            self.message = message

        def __nonzero__(self):
            return (self.result and True or False)

        def as_text(self):
            if isinstance(self.result, bool):
                happy = '%s: %s' % (self.result and _('OK') or _('Failed'),
                                    self.message or self.doc)
                if not self.result and self.error_info:
                    return '%s\n%s' % (happy, json.dumps(self.error_info,
                                                         indent=4))
                else:
                    return happy
            elif isinstance(self.result, (dict, list, tuple)):
                return json.dumps(self.result, indent=4, sort_keys=True)
            else:
                return unicode(self.result)

        __str__ = lambda self: self.as_text()

        __unicode__ = lambda self: self.as_text()

        def as_dict(self):
            from mailpile.urlmap import UrlMap
            rv = {
                'command': self.command_name,
                'state': {
                    'command_url': UrlMap.ui_url(self.command_obj),
                    'context_url': UrlMap.context_url(self.command_obj),
                    'query_args': self.command_obj.state_as_query_args()
                },
                'status': self.status,
                'message': self.message,
                'result': self.result,
                'elapsed': '%.3f' % self.session.ui.time_elapsed,
            }
            if self.error_info:
                rv['error'] = self.error_info
            for ui_key in [k for k in self.kwargs.keys()
                           if k.startswith('ui_')]:
                rv[ui_key] = self.kwargs[ui_key]
            return rv

        def as_json(self):
            return self.session.ui.render_json(self.as_dict())

        def as_html(self, template=None):
            return self.as_template('html', template)

        def as_js(self, template=None):
            return self.as_template('js', template)

        def as_css(self, template=None):
            return self.as_template('css', template)

        def as_rss(self, template=None):
            return self.as_template('rss', template)

        def as_xml(self, template=None):
            return self.as_template('xml', template)

        def as_txt(self, template=None):
            return self.as_template('txt', template)

        def as_template(self, etype, template=None):
            tpath = self.command_obj.template_path(etype,
                template_id=self.template_id, template=template)

            data = self.as_dict()
            data['title'] = self.message
            data['render_mode'] = 'full'
            def render():
                return self.session.ui.render_web(
                    self.session.config, [tpath], data)

            for e in ('jhtml', 'jjs', 'jcss', 'jxml', 'jrss'):
                if self.session.ui.render_mode.endswith(e):
                    data['render_mode'] = 'content'
                    data['result'] = render()
                    return self.session.ui.render_json(data)

            return render()

    def __init__(self, session, name=None, arg=None, data=None):
        self.session = session
        self.serialize = self.SERIALIZE
        self.name = self.SYNOPSIS[1] or self.SYNOPSIS[2] or name
        self.data = data or {}
        self.status = 'unknown'
        self.message = name
        self.error_info = {}
        self.result = None
        if type(arg) in (type(list()), type(tuple())):
            self.args = tuple(arg)
        elif arg:
            if self.SPLIT_ARG:
                self.args = tuple(arg.split(' ', self.SPLIT_ARG))
            else:
                self.args = (arg, )
        else:
            self.args = tuple([])
        if 'arg' in self.data:
            self.args = tuple(list(self.args) + self.data['arg'])
        self._create_event()

    def state_as_query_args(self):
        args = {}
        if self.args:
            args['arg'] = self.args
        args.update(self.data)
        return args

    def template_path(self, etype, template_id=None, template=None):
        path_parts = (template_id or self.SYNOPSIS[2] or 'command').split('/')
        if len(path_parts) == 1:
            path_parts.append('index')
        if template not in (None, etype, 'as.' + etype):
            # Security: The template request may come from the URL, so we
            #           sanitize it very aggressively before heading off
            #           to the filesystem.
            clean_tpl = CleanText(template.replace('.%s' % etype, ''),
                                  banned=(CleanText.FS +
                                          CleanText.WHITESPACE))
            path_parts[-1] += '-%s' % clean_tpl
        path_parts[-1] += '.' + etype
        return os.path.join(*path_parts)

    def _idx(self, reset=False, wait=True, wait_all=True, quiet=False):
        session, config = self.session, self.session.config
        if not reset and config.index:
            return config.index

        def __do_load2():
            config.vcards.load_vcards(session)
            if not wait_all:
                session.ui.report_marks(quiet=quiet)

        def __do_load1():
            if reset:
                config.index = None
                session.results = []
                session.searched = []
                session.displayed = {'start': 1, 'count': 0}
            idx = config.get_index(session)
            if wait_all:
                __do_load2()
            if not wait:
                session.ui.report_marks(quiet=quiet)
            return idx

        if wait:
            rv = config.slow_worker.do(session, 'Load', __do_load1)
            session.ui.reset_marks(quiet=quiet)
        else:
            config.slow_worker.add_task(session, 'Load', __do_load1)
            rv = None

        if not wait_all:
            config.slow_worker.add_task(session, 'Load2', __do_load2)

        return rv

    def _choose_messages(self, words, allow_ephemeral=False):
        msg_ids = set()
        all_words = []
        for word in words:
            all_words.extend(word.split(','))
        for what in all_words:
            if what.lower() == 'these':
                b = self.session.displayed['stats']['start'] - 1
                c = self.session.displayed['stats']['count']
                msg_ids |= set(self.session.results[b:b + c])
            elif what.lower() == 'all':
                msg_ids |= set(self.session.results)
            elif what.startswith('='):
                try:
                    msg_id = int(what[1:], 36)
                    if msg_id >= 0 and msg_id < len(self._idx().INDEX):
                        msg_ids.add(msg_id)
                    else:
                        self.session.ui.warning((_('No such ID: %s')
                                                 ) % (what[1:], ))
                except ValueError:
                    if allow_ephemeral and '-' in what:
                        msg_ids.add(what[1:])
                    else:
                        self.session.ui.warning(_('What message is %s?'
                                                  ) % (what, ))
            elif '-' in what:
                try:
                    b, e = what.split('-')
                    msg_ids |= set(self.session.results[int(b) - 1:int(e)])
                except:
                    self.session.ui.warning(_('What message is %s?'
                                              ) % (what, ))
            else:
                try:
                    msg_ids.add(self.session.results[int(what) - 1])
                except:
                    self.session.ui.warning(_('What message is %s?'
                                              ) % (what, ))
        return msg_ids

    def _error(self, message, info=None):
        self.status = 'error'
        self.message = message

        ui_message = _('%s error: %s') % (self.name, message)
        if info:
            self.error_info.update(info)
            details = ' '.join(['%s=%s' % (k, info[k]) for k in info])
            ui_message += ' (%s)' % details
        self.session.ui.mark(self.name)
        self.session.ui.error(ui_message)

        return False

    def _success(self, message, result=True):
        self.status = 'success'
        self.message = message

        ui_message = _('%s: %s') % (self.name, message)
        self.session.ui.mark(ui_message)

        return self.view(result)

    def _read_file_or_data(self, fn):
        if fn in self.data:
            return self.data[fn]
        else:
            return open(fn, 'rb').read()

    def _ignore_exception(self):
        self.session.ui.debug(traceback.format_exc())

    def _serialize(self, name, function):
        session, config = self.session, self.session.config
        return config.slow_worker.do(session, name, function)

    def _background(self, name, function):
        session, config = self.session, self.session.config
        return config.slow_worker.add_task(session, name, function)

    def _update_event_state(self, state, log=False):
        self.event.flags = state
        self.event.data['elapsed'] = int(1000 * (time.time()-self._start_time))

        if (log or self.LOG_PROGRESS) and not self.LOG_NOTHING:
            ui = str(self.session.ui.__class__).replace('mailpile.', '.')
            self.event.data['ui'] = ui
            self.event.data['output'] = self.session.ui.render_mode
            self.session.config.event_log.log_event(self.event)

    def _starting(self):
        self._start_time = time.time()
        self._update_event_state(Event.RUNNING)
        if self.name:
            self.session.ui.start_command(self.name, self.args, self.data)

    def _fmt_msg(self, message):
        return message % {'name': self.name,
                          'status': self.status or '',
                          'message': self.message or ''}

    def _create_event(self):
        private_data = {}
        if self.data:
            private_data['data'] = copy.copy(self.data)
        if self.args:
            private_data['args'] = copy.copy(self.args)

        self.event = Event(source=self,
                           message=self._fmt_msg(self.LOG_STARTING),
                           data={},
                           private_data=private_data)

    def _finishing(self, command, rv):
        # FIXME: Remove this when stuff is up to date
        if self.status == 'unknown':
            self.session.ui.warning('FIXME: %s should use self._success'
                                    ' etc. (issue #383)' % self.__class__)
            self.status = 'success'

        self.session.ui.mark(_('Generating result'))
        result = self.CommandResult(self, self.session, self.name,
                                    command.__doc__ or self.__doc__,
                                    rv, self.status, self.message,
                                    error_info=self.error_info)

        # Update the event!
        if self.message:
            self.event.message = self.message
        if self.error_info:
            self.event.private_data['error_info'] = self.error_info
        self.event.message = self._fmt_msg(self.LOG_FINISHED)
        self._update_event_state(Event.COMPLETE, log=True)

        self.session.ui.mark(self.event.message)
        self.session.ui.report_marks(
            details=('timing' in self.session.config.sys.debug))
        if self.name:
            self.session.ui.finish_command(self.name)
        return result

    def _run(self, *args, **kwargs):
        def command(self, *args, **kwargs):
            return self.command(*args, **kwargs)
        try:
            self._starting()
            return self._finishing(command, command(self, *args, **kwargs))
        except self.RAISES:
            raise
        except:
            self._ignore_exception()
            self._error(self.FAILURE % {'name': self.name,
                                        'args': ' '.join(self.args)})
            return self._finishing(command, False)

    def run(self, *args, **kwargs):
        if self.serialize:
            # Some functions we always run in the slow worker, to make sure
            # they don't get run in parallel with other things.
            return self._serialize(self.serialize,
                                   lambda: self._run(*args, **kwargs))
        else:
            return self._run(*args, **kwargs)

    def command(self):
        return None

    @classmethod
    def view(cls, result):
        return result


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
        'outbox': 'from_me',
        'replied': 'replied',
        'fwded': 'forwarded'
    }

    def _metadata(self, msg_info):
        import mailpile.urlmap
        nz = lambda l: [v for v in l if v]
        msg_ts = long(msg_info[MailIndex.MSG_DATE], 36)
        msg_date = datetime.datetime.fromtimestamp(msg_ts)

        fe, fn = ExtractEmailAndName(msg_info[MailIndex.MSG_FROM])
        f_info = self._address(e=fe, n=fn)
        f_info['aid'] = (self._msg_addresses(msg_info, no_to=True, no_cc=True)
                         or [''])[0]
        expl = {
            'mid': msg_info[MailIndex.MSG_MID],
            'id': msg_info[MailIndex.MSG_ID],
            'timestamp': msg_ts,
            'from': f_info,
            'to_aids': self._msg_addresses(msg_info, no_from=True, no_cc=True),
            'cc_aids': self._msg_addresses(msg_info, no_from=True, no_to=True),
            'msg_kb': int(msg_info[MailIndex.MSG_KB], 36),
            'tag_tids': self._msg_tags(msg_info),
            'thread_mid': msg_info[MailIndex.MSG_THREAD_MID],
            'subject': msg_info[MailIndex.MSG_SUBJECT],
            'body': MailIndex.get_body(msg_info),
            'flags': {
            },
            'crypto': {
            }
        }

        # Ephemeral messages do not have URLs
        if '-' not in msg_info[MailIndex.MSG_MID]:
            expl['urls'] = {
                'thread': self.urlmap.url_thread(msg_info[MailIndex.MSG_MID]),
                'source': self.urlmap.url_source(msg_info[MailIndex.MSG_MID]),
            }
        else:
            expl['flags']['ephemeral'] = True

        # Support rich snippets
        if expl['body']['snippet'].startswith('{'):
            try:
                expl['body'] = json.loads(expl['body']['snippet'])
            except ValueError:
                pass

        # Misc flags
        if [e for e in self.idx.config.profiles if (e.email.lower()
                                                    == fe.lower())]:
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
            if self.idx.config.is_editable_message(msg_info):
                expl['urls']['editing'] = self.urlmap.url_edit(expl['mid'])
            else:
                del expl['flags']['draft']

        return expl

    def _msg_addresses(self, msg_info,
                       no_from=False, no_to=False, no_cc=False):
        if no_to:
            cids = set()
        else:
            to = [t for t in msg_info[MailIndex.MSG_TO].split(',') if t]
            cids = set(to)
        if not no_cc:
            cc = [t for t in msg_info[MailIndex.MSG_CC].split(',') if t]
            cids |= set(cc)
        if not no_from:
            fe, fn = ExtractEmailAndName(msg_info[MailIndex.MSG_FROM])
            if fe:
                try:
                    cids.add(b36(self.idx.EMAIL_IDS[fe.lower()]))
                except KeyError:
                    cids.add(b36(self.idx._add_email(fe, name=fn)))
        return sorted(list(cids))

    def _address(self, cid=None, e=None, n=None):
        if cid and not (e and n):
            e, n = ExtractEmailAndName(self.idx.EMAILS[int(cid, 36)])
        vcard = self.session.config.vcards.get_vcard(e)
        return AddressInfo(e, n, vcard=vcard)

    def _msg_tags(self, msg_info):
        tids = [t for t in msg_info[MailIndex.MSG_TAGS].split(',')
                if t and t in self.session.config.tags]
        return tids

    def _tag(self, tid, attributes={}):
        return dict_merge(self.session.config.get_tag_info(tid), attributes)

    def _thread(self, thread_mid):
        msg_info = self.idx.get_msg_at_idx_pos(int(thread_mid, 36))
        thread = [i for i in msg_info[MailIndex.MSG_REPLIES].split(',') if i]

        # FIXME: This is a hack, the indexer should just keep things
        #        in the right order on rescan. Fixing threading is a bigger
        #        problem though, so we do this for now.
        def thread_sort_key(idx):
            info = self.idx.get_msg_at_idx_pos(int(thread_mid, 36))
            return int(info[self.idx.MSG_DATE], 36)
        thread.sort(key=thread_sort_key)

        return thread

    WANT_MSG_TREE = ('attachments', 'html_parts', 'text_parts', 'header_list',
                     'editing_strings', 'crypto')
    PRUNE_MSG_TREE = ('headers', )  # Added by editing_strings

    def _prune_msg_tree(self, tree):
        for k in tree.keys():
            if k not in self.WANT_MSG_TREE or k in self.PRUNE_MSG_TREE:
                del tree[k]
        return tree

    def _message(self, email):
        tree = email.get_message_tree(want=(email.WANT_MSG_TREE_PGP +
                                            self.WANT_MSG_TREE))
        email.evaluate_pgp(tree, decrypt=True)
        return self._prune_msg_tree(tree)

    def __init__(self, session, idx,
                 results=None, start=0, end=None, num=None,
                 emails=None, people=None,
                 suppress_data=False, full_threads=True):
        dict.__init__(self)
        self.session = session
        self.people = people
        self.emails = emails
        self.idx = idx
        self.urlmap = mailpile.urlmap.UrlMap(self.session)

        results = self.results = results or session.results or []

        num = num or session.config.prefs.num_results
        if end:
            start = end - num
        if start > len(results):
            start = len(results)
        if start < 0:
            start = 0

        self.session.ui.mark(_('Parsing metadata for %d results '
                               '(full_threads=%s)') % (num, full_threads))

        try:
            threads = [b36(r) for r in results[start:start + num]]
        except TypeError:
            results = threads = []
            start = end = 0

        self.update({
            'summary': _('Search: %s') % ' '.join(session.searched),
            'stats': {
                'count': len(threads),
                'start': start + 1,
                'end': start + num,
                'total': len(results),
            },
            'search_terms': session.searched,
            'address_ids': [],
            'message_ids': [],
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
        while idxs:
            idx_pos = idxs.pop(0)
            msg_info = idx.get_msg_at_idx_pos(idx_pos)
            self.add_msg_info(b36(idx_pos), msg_info,
                              full_threads=full_threads, idxs=idxs)

        if emails and len(emails) == 1:
            self['summary'] = emails[0].get_msg_info(MailIndex.MSG_SUBJECT)

        for e in emails or []:
            self.add_email(e)

    def add_msg_info(self, mid, msg_info, full_threads=False, idxs=None):
        # Populate data.metadata
        self['data']['metadata'][mid] = self._metadata(msg_info)

        # Populate data.thread
        thread_mid = msg_info[self.idx.MSG_THREAD_MID]
        if thread_mid not in self['data']['threads']:
            thread = self._thread(thread_mid)
            self['data']['threads'][thread_mid] = thread
            if full_threads and idxs:
                idxs.extend([int(t, 36) for t in thread
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

    def add_email(self, e):
        if e not in self.emails:
            self.emails.append(e)
        mid = e.msg_mid()
        self.add_msg_info(mid, e.get_msg_info())
        if mid not in self['data']['messages']:
            self['data']['messages'][mid] = self._message(e)
        if mid not in self['message_ids']:
            self['message_ids'].append(mid)

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

    def as_text(self):
        from mailpile.jinjaextensions import MailpileCommand as JE
        clen = max(3, len('%d' % len(self.session.results)))
        cfmt = '%%%d.%ds' % (clen, clen)
        text = []
        count = self['stats']['start']
        expand_ids = [e.msg_idx_pos for e in (self.emails or [])]
        addresses = self.get('data', {}).get('addresses', {})
        for mid in self['thread_ids']:
            m = self['data']['metadata'][mid]
            tags = [self['data']['tags'][t] for t in m['tag_tids']]
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
                thread = [m['thread_mid']]
                thread += self['data']['threads'][m['thread_mid']]
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
                             JE._nice_subject(m['subject']))

            sfmt = '%%-%d.%ds%%s' % (53 - (clen + len(msg_meta)),
                                     53 - (clen + len(msg_meta)))
            text.append((cfmt + ' %-22.22s %s' + sfmt
                         ) % (count, from_info, tag_new and '*' or ' ',
                              subject, msg_meta))

            if mid in self['data'].get('messages', {}):
                exp_email = self.emails[expand_ids.index(int(mid, 36))]
                msg_tree = exp_email.get_message_tree()
                text.append('-' * 79)
                text.append(exp_email.get_editing_string(msg_tree))
                text.append('-' * 79)

            count += 1
        if not count:
            text = ['(No messages found)']
        return '\n'.join(text) + '\n'


##[ Internals ]###############################################################

class Load(Command):
    """Load or reload the metadata index"""
    SYNOPSIS = (None, 'load', None, None)
    ORDER = ('Internals', 1)

    def command(self, reset=True, wait=True, wait_all=False, quiet=False):
        if self._idx(reset=reset,
                     wait=wait,
                     wait_all=wait_all,
                     quiet=quiet):
            return self._success(_('Loaded metadata index'))
        else:
            return self._error(_('Failed to loaded metadata index'))


class Rescan(Command):
    """Add new messages to index"""
    SYNOPSIS = (None, 'rescan', None, '[all|vcards|mailboxes|<msgs>]')
    ORDER = ('Internals', 2)
    SERIALIZE = 'Rescan'
    LOG_PROGRESS = True

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)

        if config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))

        delay = play_nice_with_threads()
        if delay > 0:
            session.ui.notify((
                _('Note: periodic delay is %ss, run from shell to '
                  'speed up: mp --rescan=...')
            ) % delay)

        if args and args[0].lower() == 'vcards':
            return self._rescan_vcards(session, config)
        elif args and args[0].lower() == 'mailboxes':
            return self._rescan_mailboxes(session, config)
        elif args and args[0].lower() == 'all':
            args.pop(0)

        msg_idxs = self._choose_messages(args)
        if msg_idxs:
            for msg_idx_pos in msg_idxs:
                e = Email(idx, msg_idx_pos)
                try:
                    session.ui.mark('Re-indexing %s' % e.msg_mid())
                    idx.index_email(self.session, e)
                except KeyboardInterrupt:
                    raise
                except:
                    self._ignore_exception()
                    session.ui.warning(_('Failed to reindex: %s'
                                         ) % e.msg_mid())
            return self._success(_('Indexed %d messages') % len(msg_idxs),
                                 result={'messages': len(msg_idxs)})

        else:
            # FIXME: Need a lock here?
            if 'rescan' in config._running:
                return self._success(_('Rescan already in progress'))
            config._running['rescan'] = True
            try:
                results = {}
                results.update(self._rescan_vcards(session, config))
                results.update(self._rescan_mailboxes(session, config))
                if 'aborted' in results:
                    raise KeyboardInterrupt()
                return self._success(_('Rescanned vcards and mailboxes'),
                                     result=results)
            except (KeyboardInterrupt), e:
                return self._error(_('User aborted'), info=results)
            finally:
                del config._running['rescan']

    def _rescan_vcards(self, session, config):
        from mailpile.plugins import PluginManager
        imported = 0
        importer_cfgs = config.prefs.vcard.importers
        for importer in PluginManager.VCARD_IMPORTERS.values():
            for cfg in importer_cfgs.get(importer.SHORT_NAME, []):
                if cfg:
                    imp = importer(session, cfg)
                    imported += imp.import_vcards(session, config.vcards)
        return {'vcards': imported}

    def _rescan_mailboxes(self, session, config):
        idx = self._idx()
        msg_count = 0
        mbox_count = 0
        rv = True
        try:
            pre_command = config.prefs.rescan_command
            if pre_command:
                session.ui.mark(_('Running: %s') % pre_command)
                subprocess.check_call(pre_command, shell=True)
            msg_count = 1
            for fid, fpath in config.get_mailboxes():
                if fpath == '/dev/null':
                    continue
                if mailpile.util.QUITTING:
                    break
                try:
                    count = idx.scan_mailbox(session, fid, fpath,
                                             config.open_mailbox)
                except ValueError:
                    session.ui.warning(_('Failed to rescan: %s') % fpath)
                    count = 0

                if count:
                    msg_count += count
                    mbox_count += 1
                config.clear_mbox_cache()
                session.ui.mark('\n')
            msg_count -= 1
            if msg_count:
                if not mailpile.util.QUITTING:
                    idx.cache_sort_orders(session)
                if not mailpile.util.QUITTING:
                    GlobalPostingList.Optimize(session, idx, quick=True)
            else:
                session.ui.mark(_('Nothing changed'))
        except (KeyboardInterrupt, subprocess.CalledProcessError), e:
            return {'aborted': True,
                    'messages': msg_count,
                    'mailboxes': mbox_count}
        finally:
            if msg_count:
                session.ui.mark('\n')
                if msg_count < 500:
                    idx.save_changes(session)
                else:
                    idx.save(session)
        return {'messages': msg_count,
                'mailboxes': mbox_count}


class Optimize(Command):
    """Optimize the keyword search index"""
    SYNOPSIS = (None, 'optimize', None, '[harder]')
    ORDER = ('Internals', 3)
    SERIALIZE = 'Optimize'

    def command(self):
        try:
            self._idx().save(self.session)
            GlobalPostingList.Optimize(self.session, self._idx(),
                                       force=('harder' in self.args))
            return self._success(_('Optimized search engine'))
        except KeyboardInterrupt:
            return self._error(_('Aborted'))


class RunWWW(Command):
    """Just run the web server"""
    SYNOPSIS = (None, 'www', None, None)
    ORDER = ('Internals', 5)

    def command(self):
        self.session.config.prepare_workers(self.session, daemons=True)
        while not mailpile.util.QUITTING:
            time.sleep(1)
        return self_success(_('Started the web server'))


class WritePID(Command):
    """Write the PID to a file"""
    SYNOPSIS = (None, 'pidfile', None, "</path/to/pidfile>")
    ORDER = ('Internals', 5)
    SPLIT_ARG = False

    def command(self):
        with open(self.args[0], 'w') as fd:
            fd.write('%d' % os.getpid())
        return self._success(_('Wrote PID to %s') % self.args)


class RenderPage(Command):
    """Does nothing, for use by semi-static jinja2 pages"""
    SYNOPSIS = (None, None, 'page', None)
    ORDER = ('Internals', 6)
    SPLIT_ARG = False
    HTTP_STRICT_VARS = False

    class CommandResult(Command.CommandResult):
        def __init__(self, *args, **kwargs):
            Command.CommandResult.__init__(self, *args, **kwargs)
            if self.result and 'path' in self.result:
                self.template_id = 'page/' + self.result['path'] + '/index'

    def command(self):
        return self._success(_('Rendered the page'), result={
            'path': (self.args and self.args[0] or ''),
            'data': self.data
        })


##[ Configuration commands ]###################################################

class ConfigSet(Command):
    """Change a setting"""
    SYNOPSIS = ('S', 'set', 'settings/set', '<section.variable> <value>')
    ORDER = ('Config', 1)
    SPLIT_ARG = False
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_STRICT_VARS = False
    HTTP_POST_VARS = {
        'section.variable': 'value|json-string',
    }

    def command(self):
        config = self.session.config
        args = list(self.args)
        ops = []

        if config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))

        for var in self.data.keys():
            parts = ('.' in var) and var.split('.') or var.split('/')
            if parts[0] in config.rules:
                ops.append((var, self.data[var][0]))

        if self.args:
            arg = ' '.join(self.args)
            if '=' in arg:
                # Backwards compatiblity with the old 'var = value' syntax.
                var, value = [s.strip() for s in arg.split('=', 1)]
                var = var.replace(': ', '.').replace(':', '.').replace(' ', '')
            else:
                var, value = arg.split(' ', 1)
            ops.append((var, value))

        updated = {}
        for path, value in ops:
            value = value.strip()
            if value.startswith('{') or value.startswith('['):
                value = json.loads(value)
            try:
                cfg, var = config.walk(path.strip(), parent=1)
                cfg[var] = value
                updated[path] = value
            except IndexError:
                cfg, v1, v2 = config.walk(path.strip(), parent=2)
                cfg[v1] = {v2: value}

        self._serialize('Save config', lambda: config.save())
        return self._success(_('Updated your settings'), result=updated)


class ConfigAdd(Command):
    """Add a new value to a list (or ordered dict) setting"""
    SYNOPSIS = (None, 'append', 'settings/add', '<section.variable> <value>')
    ORDER = ('Config', 1)
    SPLIT_ARG = False
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_STRICT_VARS = False
    HTTP_POST_VARS = {
        'section.variable': 'value|json-string',
    }

    def command(self):
        config = self.session.config
        ops = []

        if config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))

        for var in self.data.keys():
            parts = ('.' in var) and var.split('.') or var.split('/')
            if parts[0] in config.rules:
                ops.append((var, self.data[var][0]))

        if self.args:
            arg = ' '.join(self.args)
            if '=' in arg:
                # Backwards compatible with the old 'var = value' syntax.
                var, value = [s.strip() for s in arg.split('=', 1)]
                var = var.replace(': ', '.').replace(':', '.').replace(' ', '')
            else:
                var, value = arg.split(' ', 1)
            ops.append((var, value))

        updated = {}
        for path, value in ops:
            value = value.strip()
            if value.startswith('{') or value.startswith('['):
                value = json.loads(value)
            cfg, var = config.walk(path.strip(), parent=1)
            cfg[var].append(value)
            updated[path] = value

        self._serialize('Save config', lambda: config.save())
        return self._success(_('Updated your settings'), result=updated)


class ConfigUnset(Command):
    """Reset one or more settings to their defaults"""
    SYNOPSIS = ('U', 'unset', 'settings/unset', '<var>')
    ORDER = ('Config', 2)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
        'var': 'section.variables'
    }

    def command(self):
        session, config = self.session, self.session.config

        if config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))

        updated = []
        vlist = list(self.args) + (self.data.get('var', None) or [])
        for v in vlist:
            cfg, vn = config.walk(v, parent=True)
            if vn in cfg:
                del cfg[vn]
                updated.append(v)

        self._serialize('Save config', lambda: config.save())
        return self._success(_('Reset to default values'), result=updated)


class ConfigPrint(Command):
    """Print one or more settings"""
    SYNOPSIS = ('P', 'print', 'settings', '<var>')
    ORDER = ('Config', 3)
    HTTP_QUERY_VARS = {
        'var': 'section.variable'
    }

    def command(self):
        session, config = self.session, self.session.config
        result = {}
        invalid = []
        # FIXME: Are there privacy implications here somewhere?
        for key in (self.args + tuple(self.data.get('var', []))):
            try:
                result[key] = config.walk(key)
            except KeyError:
                invalid.append(key)
        if invalid:
            return self._error(_('Invalid keys'), info={'keys': invalid})
        else:
            return self._success(_('Displayed settings'), result=result)


class AddMailboxes(Command):
    """Add one or more mailboxes"""
    SYNOPSIS = ('A', 'add', None, '<path/to/mailbox>')
    ORDER = ('Config', 4)
    SPLIT_ARG = False
    HTTP_CALLABLE = ('POST', 'UPDATE')

    MAX_PATHS = 50000

    def command(self):
        session, config = self.session, self.session.config
        adding = []
        existing = config.sys.mailbox
        paths = list(self.args)

        if config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))

        try:
            while paths:
                raw_fn = paths.pop(0)
                fn = os.path.normpath(os.path.expanduser(raw_fn))
                fn = os.path.abspath(fn)
                if raw_fn in existing or fn in existing:
                    session.ui.warning('Already in the pile: %s' % raw_fn)
                elif raw_fn.startswith("imap://"):
                    adding.append(raw_fn)
                elif os.path.exists(fn):
                    if IsMailbox(fn):
                        adding.append(fn)
                    elif os.path.isdir(fn):
                        session.ui.mark('Scanning %s for mailboxes' % fn)
                        try:
                            for f in [f for f in os.listdir(fn)
                                      if not f.startswith('.')]:
                                paths.append(os.path.join(fn, f))
                                if len(paths) > self.MAX_PATHS:
                                    return self._error(_('Too many files'))
                        except OSError:
                            if raw_fn in self.args:
                                return self._error(_('Failed to read: %s'
                                                     ) % raw_fn)
                    elif raw_fn in self.args:
                        return self._error(_('Not a mailbox: %s') % raw_fn)
                elif raw_fn in self.args:
                    return self._error(_('No such file or directory: %s'
                                         ) % raw_fn)
        except KeyboardInterrupt:
            return self._error(_('User aborted'))

        added = {}
        for arg in adding:
            added[config.sys.mailbox.append(arg)] = arg
        if added:
            self._serialize('Save config', lambda: config.save())
            return self._success(_('Added %d mailboxes') % len(added),
                                 result={'added': added})
        else:
            return self._success(_('Nothing was added'))


###############################################################################

class Output(Command):
    """Choose format for command results."""
    SYNOPSIS = (None, 'output', None, '[json|text|html|<template>.html|...]')
    ORDER = ('Internals', 7)
    HTTP_STRICT_VARS = False
    LOG_NOTHING = True

    def get_render_mode(self):
        return self.args and self.args[0] or 'text'

    def command(self):
        m = self.session.ui.render_mode = self.get_render_mode()
        return self._success(_('Set output mode to: %s') % m,
                             result={'output': m})


class Help(Command):
    """Print help on Mailpile or individual commands."""
    SYNOPSIS = ('h', 'help', 'help', '[<command-group>]')
    ABOUT = ('This is Mailpile!')
    ORDER = ('Config', 9)

    class CommandResult(Command.CommandResult):

        def splash_as_text(self):
            if self.result['http_url']:
                web_interface = _('The Web interface address is: %s'
                                  ) % self.result['http_url']
            else:
                web_interface = _('The Web interface is disabled.')
            return '\n'.join([
                self.result['splash'],
                web_interface,
                '',
                _('Type `help` for instructions or press <Ctrl-d> to quit.'),
                ''
            ])

        def variables_as_text(self):
            text = []
            for group in self.result['variables']:
                text.append(group['name'])
                for var in group['variables']:
                    sep = ('=' in var['type']) and ': ' or ' = '
                    text.append(('  %-35s %s'
                                 ) % (('%s%s<%s>'
                                       ) % (var['var'], sep,
                                            var['type'].replace('=', '> = <')),
                                      var['desc']))
                text.append('')
            return '\n'.join(text)

        def commands_as_text(self):
            text = [_('Commands:')]
            last_rank = None
            cmds = self.result['commands']
            width = self.result.get('width', 8)
            ckeys = cmds.keys()
            ckeys.sort(key=lambda k: cmds[k][3])
            for c in ckeys:
                cmd, args, explanation, rank = cmds[c]
                if not rank or not cmd:
                    continue
                if last_rank and int(rank / 10) != last_rank:
                    text.append('')
                last_rank = int(rank / 10)
                if c[0] == '_':
                    c = '  '
                else:
                    c = '%s|' % c[0]
                fmt = '  %%s%%-%d.%ds' % (width, width)
                if explanation:
                    if len(args or '') <= 15:
                        fmt += ' %-15.15s %s'
                    else:
                        fmt += ' %%s\n%s %%s' % (' ' * (len(c) + width + 18))
                else:
                    explanation = ''
                    fmt += ' %s %s '
                text.append(fmt % (c, cmd.replace('=', ''),
                                   args and ('%s' % (args, )) or '',
                                   (explanation.splitlines() or [''])[0]))
            if 'tags' in self.result:
                text.extend([
                    '',
                    _('Tags:  (use a tag as a command to display tagged '
                      'messages)'),
                    '',
                    self.result['tags'].as_text()
                ])
            return '\n'.join(text)

        def as_text(self):
            if not self.result:
                return _('Error')
            return ''.join([
                ('splash' in self.result) and self.splash_as_text() or '',
                (('variables' in self.result) and self.variables_as_text()
                 or ''),
                ('commands' in self.result) and self.commands_as_text() or '',
            ])

    def command(self):
        self.session.ui.reset_marks(quiet=True)
        if self.args:
            command = self.args[0]
            for cls in COMMANDS:
                name = cls.SYNOPSIS[1] or cls.SYNOPSIS[2]
                width = len(name)
                if name and name == command:
                    order = 1
                    cmd_list = {'_main': (name, cls.SYNOPSIS[3],
                                          cls.__doc__, order)}
                    subs = [c for c in COMMANDS
                            if (c.SYNOPSIS[1] or c.SYNOPSIS[2]
                                ).startswith(name + '/')]
                    for scls in sorted(subs):
                        sc, scmd, surl, ssynopsis = scls.SYNOPSIS[:4]
                        order += 1
                        cmd_list['_%s' % scmd] = (scmd, ssynopsis,
                                                  scls.__doc__, order)
                        width = max(len(scmd or surl), width)
                    return self._success(_('Displayed help'), result={
                        'pre': cls.__doc__,
                        'commands': cmd_list,
                        'width': width
                    })
            return self._error(_('Unknown command'))

        else:
            cmd_list = {}
            count = 0
            for grp in COMMAND_GROUPS:
                count += 10
                for cls in COMMANDS:
                    c, name, url, synopsis = cls.SYNOPSIS[:4]
                    if cls.ORDER[0] == grp and '/' not in (name or ''):
                        cmd_list[c or '_%s' % name] = (name, synopsis,
                                                       cls.__doc__,
                                                       count + cls.ORDER[1])
            return self._success(_('Displayed help'), result={
                'commands': cmd_list,
                'tags': GetCommand('tag/list')(self.session).run(),
                'index': self._idx()
            })

    def _starting(self):
        pass

    def _finishing(self, command, rv):
        return self.CommandResult(self, self.session, self.name,
                                  command.__doc__ or self.__doc__, rv,
                                  self.status, self.message)


class HelpVars(Help):
    """Print help on Mailpile variables"""
    SYNOPSIS = (None, 'help/variables', 'help/variables', None)
    ABOUT = ('The available mailpile variables')
    ORDER = ('Config', 9)

    def command(self):
        config = self.session.config.rules
        result = []
        categories = ["sys", "prefs", "profiles"]
        for cat in categories:
            variables = []
            what = config[cat]
            if isinstance(what[2], dict):
                for ii, i in what[2].iteritems():
                    variables.append({
                        'var': ii,
                        'type': str(i[1]),
                        'desc': i[0]
                    })
            variables.sort(key=lambda k: k['var'])
            result.append({
                'category': cat,
                'name': config[cat][0],
                'variables': variables
            })
        result.sort(key=lambda k: config[k['category']][0])
        return self._success(_('Displayed variables'),
                             result={'variables': result})


class HelpSplash(Help):
    """Print Mailpile splash screen"""
    SYNOPSIS = (None, 'help/splash', 'help/splash', None)
    ORDER = ('Config', 9)

    def command(self):
        http_worker = self.session.config.http_worker
        if http_worker:
            http_url = 'http://%s:%s/' % http_worker.httpd.sspec
        else:
            http_url = ''
        return self._success(_('Displayed welcome message'), result={
            'splash': self.ABOUT,
            'http_url': http_url,
        })


def GetCommand(name):
    match = [c for c in COMMANDS if name in c.SYNOPSIS[:3]]
    if len(match) == 1:
        return match[0]
    return None


def Action(session, opt, arg, data=None):
    session.ui.reset_marks(quiet=True)
    config = session.config

    if not opt:
        return Help(session, 'help').run()

    # Use the COMMANDS dict by default.
    command = GetCommand(opt)
    if command:
        return command(session, opt, arg, data=data).run()

    # Tags are commands
    tag = config.get_tag(opt)
    if tag:
        return GetCommand('search')(session, opt, arg=arg, data=data
                                    ).run(search=['in:%s' % tag._key])

    # OK, give up!
    raise UsageError(_('Unknown command: %s') % opt)


# Commands starting with _ don't get single-letter shortcodes...
COMMANDS = [
    Optimize, Rescan, RunWWW, WritePID, RenderPage,
    ConfigPrint, ConfigSet, ConfigAdd, ConfigUnset, AddMailboxes,
    Output, Help, HelpVars, HelpSplash
]
COMMAND_GROUPS = ['Internals', 'Config', 'Searching', 'Tagging', 'Composing']
