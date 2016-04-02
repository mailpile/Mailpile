import json
import os
import traceback
from gettext import gettext as _
from urllib import urlencode, URLopener

import mailpile.auth
from mailpile.commands import Command
from mailpile.conn_brokers import TcpConnectionBroker as TcpConnBroker
from mailpile.mailutils import *
from mailpile.plugins.core import Help
from mailpile.search import *
from mailpile.util import *
from mailpile.vcard import *


class Hacks(Command):
    """Various hacks ..."""
    SYNOPSIS = (None, 'hacks', None, None)
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ()

    def command(self):
        return self._success('OK', Help(self.session, arg=['hacks']).run())


class FixIndex(Hacks):
    """Do various things to try and fix broken indexes"""
    SYNOPSIS = (None, 'hacks/fixindex', None, None)
    LOG_PROGRESS = True

    def command(self):
        session, index = self.session, self._idx()

        session.ui.mark('Checking index for duplicate MSG IDs...')
        found = {}
        for i in range(0, len(index.INDEX)):
            msg_id = index.get_msg_at_idx_pos(i)[index.MSG_ID]
            if msg_id in found:
                found[msg_id].append(i)
            else:
                found[msg_id] = [i]

        session.ui.mark('Attempting to fix dups with bad location...')
        for msg_id in found:
            if len(found[msg_id]) > 1:
                good, bad = [], []
                for idx_pos in found[msg_id]:
                    msg = Email(index, idx_pos).get_msg()
                    if msg:
                        good.append(idx_pos)
                    else:
                        bad.append(idx_pos)
                if good and bad:
                    good_info = index.get_msg_at_idx_pos(good[0])
                    for bad_idx in bad:
                        bad_info = index.get_msg_at_idx_pos(bad_idx)
                        bad_info[index.MSG_PTRS] = good_info[index.MSG_PTRS]
                        index.set_msg_at_idx_pos(bad_idx, bad_info)

        return self._success(_('Tried to fix metadata index'))


class PyCLI(Hacks):
    """Launch a Python REPL"""
    SYNOPSIS = (None, 'hacks/pycli', None, None)
    LOG_PROGRESS = True

    def command(self):
        import code
        import readline
        from mailpile import Mailpile

        variables = globals()
        variables['session'] = self.session
        variables['config'] = self.session.config
        variables['index'] = self.session.config.index
        variables['mp'] = Mailpile(session=self.session)

        self.session.config.stop_workers()
        self.session.ui.block()
        code.InteractiveConsole(locals=variables).interact("""\
This is Python inside of Mailpile inside of Python.

   - The `mp` variable is a Pythonic API to the current pile of mail.
   - The `session` variable is the current UI session.
   - The `config` variable contains the current configuration.
   - Press CTRL+D to return to the normal CLI.
""")
        self.session.ui.unblock()
        self.session.config.prepare_workers(self.session, daemons=True)

        return self._success(_('That was fun!'))


class ViewMetadata(Hacks):
    """Display the raw metadata for a message"""
    SYNOPSIS = (None, 'hacks/metadata', None, '[<message>]')

    def _explain(self, i):
        idx, cfg = self._idx(), self.session.config
        info = idx.get_msg_at_idx_pos(i)
        ptags = [cfg.get_tag(t) or t
                 for t in info[idx.MSG_TAGS].split(',') if t]
        ptags = [t.name for t in ptags if hasattr(t, 'name')]
        pptrs = ['%s -> %s' % (cfg.sys.mailbox.get(p[:MBX_ID_LEN],
                                                   p[:MBX_ID_LEN] + '?'),
                               p[MBX_ID_LEN:])
                 for p in info[idx.MSG_PTRS].split(',') if p]
        to = idx.expand_to_list(info)
        cc = idx.expand_to_list(info, idx.MSG_CC)
        return {
            'mid': info[idx.MSG_MID],
            'ptrs': info[idx.MSG_PTRS],
            'id': info[idx.MSG_ID],
            'date': info[idx.MSG_DATE],
            'from': info[idx.MSG_FROM],
            'to': info[idx.MSG_TO],
            'cc': info[idx.MSG_CC],
            'kb': info[idx.MSG_KB],
            'subject': info[idx.MSG_SUBJECT],
            'body': info[idx.MSG_BODY],
            'tags': info[idx.MSG_TAGS],
            'replies': info[idx.MSG_REPLIES],
            'thread_mid': info[idx.MSG_THREAD_MID],
            'parsed': {
                'date': friendly_datetime(long(info[idx.MSG_DATE], 36)),
                'tags': ', '.join(ptags),
                'to': to,
                'cc': cc,
                'ptrs': pptrs
            }
        }

    def command(self):
        return self._success(_('Displayed raw metadata'),
            [self._explain(i) for i in self._choose_messages(self.args)])


class ViewKeywords(Hacks):
    """Display the keywords for a message"""
    SYNOPSIS = (None, 'hacks/keywords', None, '[<message>]')

    def _explain(self, i):
        idx = self._idx()
        info = idx.get_msg_at_idx_pos(i)
        msg = Email(idx, i).get_msg()
        return sorted(list(idx.read_message(
            self.session,
            info[idx.MSG_MID], info[idx.MSG_ID], msg,
            long(info[idx.MSG_KB], 36) * 1024,
            long(info[idx.MSG_DATE], 36))[0]))

    def command(self):
        return self._success(_('Displayed message keywords'),
            [self._explain(i) for i in self._choose_messages(self.args)])


class ViewHeaderPrint(Hacks):
    """Display the HeaderPrint for a message"""
    SYNOPSIS = (None, 'hacks/headerprint', None, '[<message>]')

    def _explain(self, i):
        msg = Email(self._idx(), i).get_msg()
        return {
            'headers': HeaderPrintHeaders(msg),
            'headerprint': HeaderPrint(msg)
        }

    def command(self):
        return self._success(_('Displayed message HeaderPrint'),
            [self._explain(i) for i in self._choose_messages(self.args)])


HACKS_SESSION_ID = None

class Http(Hacks):
    """Send HTTP requests to the web server"""
    SYNOPSIS = (None, 'hacks/http', None,
                '<GET|POST> </url/> [<Q|P> <var>=<val> ...]')

#    class CommandResult(Hacks.CommandResult):
#        def as_text(self):
#            pass

    def command(self):
        args = list(self.args)
        method, url = args[0:2]

        if not url.startswith('http'):
            url = 'http://%s:%s%s' % (self.session.config.sys.http_host,
                                      self.session.config.sys.http_port,
                                      ('/' + url).replace('//', '/'))

        # FIXME: The python URLopener doesn't seem to support other verbs,
        #        which is really quite lame.
        method = method.upper()
        assert(method in ('GET', 'POST'))

        qv, pv = [], []
        if method == 'POST':
            which = pv
        else:
            which = qv
        for arg in args[2:]:
            if '=' in arg:
                which.append(tuple(arg.split('=', 1)))
            elif arg.upper()[0] == 'P':
                which = pv
            elif arg.upper()[0] == 'Q':
                which = qv

        if qv:
            qv = urlencode(qv)
            url += ('?' in url and '&' or '?') + qv

        # Log us in automagically!
        httpd = self.session.config.http_worker.httpd
        global HACKS_SESSION_ID
        if HACKS_SESSION_ID is None:
            HACKS_SESSION_ID = httpd.make_session_id(None)
        mailpile.auth.SetLoggedIn(None,
                                  user='Hacks plugin HTTP client',
                                  session_id=HACKS_SESSION_ID)
        cookie = httpd.session_cookie

        try:
            uo = URLopener()
            uo.addheader('Cookie', '%s=%s' % (cookie, HACKS_SESSION_ID))
            with TcpConnBroker().context(need=[TcpConnBroker.OUTGOING_HTTP],
                                         oneshot=True):
                if method == 'POST':
                    (fn, hdrs) = uo.retrieve(url, data=urlencode(pv))
                else:
                    (fn, hdrs) = uo.retrieve(url)
            hdrs = unicode(hdrs)
            data = open(fn, 'rb').read().strip()
            if data.startswith('{') and 'application/json' in hdrs:
                data = json.loads(data)
            return self._success('%s %s' % (method, url), result={
                'headers': hdrs.splitlines(),
                'data': data
            })
        except:
            self._ignore_exception()
            return self._error('%s %s' % (method, url))


class CheckMailbox(Hacks):
    """Sanity-check and optionally fix a mailbox"""
    SYNOPSIS = (None, 'hacks/chkmbx', None, '[-force] [-noremote] '
                                            '[-auto|-index|-clean|-dedup] '
                                            '[all|<ID>]')

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        flags = [a[1:] for a in self.args if a[:1] == '-']
        if 'auto' in flags:
            flags.extend(['clean', 'dedup', 'index'])

        mbxids = [a for a in self.args if a[:1] != '-']
        if 'all' in mbxids:
            mbxids = config.sys.mailbox.keys()

        results = {}
        errors = {}
        for mbx_id in mbxids:
            result = results[mbx_id] = {
                'messages': None,
                'finalized': [],
                'unindexed': [],
                'duplicates': [],
                'source_map': False
            }
            seen = {}
            msgids = {}
            indexed = {}
            try:
                session.ui.mark('%s: Opening mailbox' % mbx_id)
                mbx = config.open_mailbox(session, mbx_id, prefer_local=True)
                try:
                    remote = config.open_mailbox(session, mbx_id,
                                                 prefer_local=False)
                except:
                    remote = None

                def _mark_progress(what, counts):
                    counts[0] += 1
                    i, n = counts[0], counts[1] or 1  # Avoid divide by zero
                    if i > max(10, (n/25)) and 0 == i % max(1, (n//397)):
                        session.ui.mark('%s: %s: Message %d/%d (%d%%)'
                                        % (mbx_id, what, i, n, 100 * i / n))

                # We do the scan with the mailbox locked, just to be a bit
                # paranoid. Not doing this was a good way to find bugs...
                with mbx:
                    mbx.update_toc()
                    result['messages'] = len(mbx)
                    session.ui.mark('%s: Checking %d messages'
                                    % (mbx_id, len(mbx)))
                    counts = [0, len(mbx)]
                    for key in list(mbx.keys()):
                        _mark_progress('Checking', counts)
                        try:
                            message = mbx[key]  # FIXME: only need header...
                        except KeyError:
                            traceback.print_exc()
                            session.ui.notify('%s: Not found in mailbox: %s'
                                              % (mbx_id, key))
                            continue

                        enc_msgid = idx.get_msg_id(message, 'bogus')
                        msgids[key] = enc_msgid
                        if enc_msgid in seen:
                            seen[enc_msgid].add(key)
                        else:
                            seen[enc_msgid] = set([key])
                        msg_idx_pos = idx.MSGIDS.get(enc_msgid)
                        if msg_idx_pos is None:
                            session.ui.notify('%s: Not in index: %s %s'
                                              % (mbx_id, key, enc_msgid))
                            result['unindexed'].append((key, enc_msgid))
                        else:
                            msg_info = idx.get_msg_at_idx_pos(msg_idx_pos)
                            for ptr in msg_info[idx.MSG_PTRS].split(','):
                                if ptr[:MBX_ID_LEN] == mbx_id:
                                    indexed[enc_msgid] = ptr[MBX_ID_LEN:]

                        if 'x-mp-internal-readonly' in message:
                            result['finalized'].append(key)

                for msg_id, keys in seen.iteritems():
                    if len(keys) > 1:
                        result['duplicates'].append([msg_id] + list(keys))

                if hasattr(mbx, 'source_map'):
                    result['source_map'] = len(mbx.source_map)
                elif mbx.is_local:
                    try:
                        mbx.source_map = {}
                        result['source_map'] = 0
                    except AttributeError:
                        session.ui.warning('%s: Failed to add source_map'
                                           % mbx_id)

                if remote and 'noremote' not in flags:
                    if hasattr(mbx, 'source_map') and len(mbx.source_map) > 0:
                        session.ui.mark('%s: Comparing with source' % mbx_id)
                        result['source_unknown'] = []
                        result['source_missing'] = []
                        result['source_mismatch'] = []

                        mapped = mbx.source_map.values()
                        for k in mbx.iterkeys():
                            if k not in mapped:
                                result['source_unknown'].append(k)

                        counts = [0, len(mapped)]
                        for sk in mbx.source_map.iteritems():
                            _mark_progress('Comparing', counts)
                            source_id, key = sk
                            try:
                                # FIXME: Can we grab only the header?
                                src_msg = remote[source_id]
                                loc_msgid = msgids[key]
                                if idx.get_msg_id(src_msg, 'x') != loc_msgid:
                                    session.ui.notify(
                                        '%s: Source mismatch: %s %s'
                                        % (mbx_id, source_id, key))
                                    result['source_missing'].append(sk)
                            except (IndexError, KeyError):
                                session.ui.notify(
                                    '%s: Source missing: %s %s'
                                    % (mbx_id, source_id, key))
                                result['source_missing'].append(sk)

                if 'index' in flags:
                    reindex = result['unindexed'][:]
                else:
                    reindex = []

                if 'clean' in flags or 'dedup' in flags:
                    if mbx.is_local or mbx.editable or 'force' in flags:
                        result['removed'] = []
                        session.ui.mark('%s: Removing autosaved drafts'
                                        % mbx_id)
                        counts = [0, len(result['duplicates'])]
                        for dups in result['duplicates'][:]:
                            _mark_progress('Clean', counts)
                            dlist = dups[1:]
                            for k in dlist:
                                if k in result['finalized']:
                                    if indexed[msgids[k]] != k:
                                        # Make sure this gets rescanned
                                        reindex.append((k, msgids[k]))
                                    dlist.remove(k)
                                    for k in dlist:
                                        mbx.remove(k)
                                        result['removed'].append(k)
                                    result['duplicates'].remove(dups)
                                    break
                    else:
                        session.ui.warning('Use -force if you are sure you '
                                           'want to modify this mailbox.')

                if 'dedup' in flags:
                    if mbx.is_local or mbx.editable or 'force' in flags:
                        session.ui.mark('%s: Removing duplicate messages'
                                        % mbx_id)
                        if 'removed' not in result:
                            result['removed'] = []
                        counts = [0, len(result['duplicates'])]
                        for dups in result['duplicates'][:]:
                            _mark_progress('Dedup', counts)
                            dlist = dups[1:]
                            msgid = msgids[dups[1]]
                            if msgid in indexed:
                                # Remove all except the one that is already
                                # in the metadata index.
                                dlist.remove(indexed[msgid])
                            else:
                                 dlist = dups[1:-1]
                            for k in dlist:
                                mbx.remove(k)
                                result['removed'].append(k)
                            result['duplicates'].remove(dups)
                    else:
                        session.ui.warning('Use -force if you are sure you '
                                           'want to modify this mailbox.')

                if reindex:
                    session.ui.mark('%s: Indexing unindexed messages'
                                    % mbx_id)
                    result['indexed'] = []
                    counts = [0, len(reindex)]
                    for key, message_id in reindex:
                        _mark_progress('Index', counts)
                        config.index.scan_one_message(
                            session, mbx_id, mbx, key, wait=True)

            except KeyboardInterrupt:
                mbx.update_toc()
                errors[mbx_id] = ('Interrupted', '')
                break
            except:
                errors[mbx_id] = ('Failed', traceback.format_exc())

            mbx.update_toc()

        if errors:
            return self._error('Checked %d mailboxes' % len(results),
                               info=errors, result=results)
        else:
            return self._success('Checked %d mailboxes' % len(results),
                                 result=results)
