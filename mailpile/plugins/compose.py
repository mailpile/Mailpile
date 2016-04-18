import datetime
import email.utils
import os
import os.path
import re
import traceback

import mailpile.security as security
from mailpile.commands import Command
from mailpile.crypto.state import *
from mailpile.crypto.mime import EncryptionFailureError, SignatureFailureError
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.plugins.tags import Tag
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName, Email
from mailpile.mailutils import NotEditableError, AddressHeaderParser
from mailpile.mailutils import NoFromAddressError, PrepareMessage
from mailpile.mailutils import MakeMessageID
from mailpile.search import MailIndex
from mailpile.smtp_client import SendMail
from mailpile.urlmap import UrlMap
from mailpile.util import *
from mailpile.vcard import AddressInfo

from mailpile.plugins.search import Search, SearchResults, View


GLOBAL_EDITING_LOCK = MboxRLock()

_plugins = PluginManager(builtin=__file__)


class EditableSearchResults(SearchResults):
    def __init__(self, session, idx, new, sent, **kwargs):
        SearchResults.__init__(self, session, idx, **kwargs)
        self.new_messages = new
        self.sent_messages = sent
        if new:
            self['created'] = [m.msg_mid() for m in new]
        if sent:
            self['sent'] = [m.msg_mid() for m in new]
            self['summary'] = _('Sent: %s') % self['summary']


def AddComposeMethods(cls):
    class newcls(cls):
        COMMAND_CACHE_TTL = 0
        COMMAND_SECURITY = security.CC_COMPOSE_EMAIL

        def _create_contacts(self, emails):
            try:
                from mailpile.plugins.contacts import AddContact
                AddContact(self.session,
                           arg=['=%s' % e.msg_mid() for e in emails]
                           ).run(recipients=True, quietly=True, internal=True)
            except (TypeError, ValueError, IndexError):
                self._ignore_exception()

        def _tag_emails(self, emails, tag):
            try:
                idx = self._idx()
                idx.add_tag(self.session,
                            self.session.config.get_tag_id(tag),
                            msg_idxs=[e.msg_idx_pos for e in emails],
                            conversation=False)
            except (TypeError, ValueError, IndexError):
                self._ignore_exception()

        def _untag_emails(self, emails, tag):
            try:
                idx = self._idx()
                idx.remove_tag(self.session,
                               self.session.config.get_tag_id(tag),
                               msg_idxs=[e.msg_idx_pos for e in emails],
                               conversation=False)
            except (TypeError, ValueError, IndexError):
                self._ignore_exception()

        def _tagger(self, emails, untag, **kwargs):
            tag = self.session.config.get_tags(**kwargs)
            if tag and untag:
                return self._untag_emails(emails, tag[0]._key)
            elif tag:
                return self._tag_emails(emails, tag[0]._key)

        def _tag_blank(self, emails, untag=False):
            return self._tagger(emails, untag, type='blank')

        def _tag_drafts(self, emails, untag=False):
            return self._tagger(emails, untag, type='drafts')

        def _tag_outbox(self, emails, untag=False):
            return self._tagger(emails, untag, type='outbox')

        def _tag_sent(self, emails, untag=False):
            return self._tagger(emails, untag, type='sent')

        def _track_action(self, action_type, refs):
            session, idx = self.session, self._idx()
            for tag in session.config.get_tags(type=action_type):
                idx.add_tag(session, tag._key,
                            msg_idxs=[m.msg_idx_pos for m in refs])

        def _actualize_ephemeral(self, ephemeral_mid):
            idx = self._idx()

            if isinstance(ephemeral_mid, int):
                # Not actually ephemeral, just return a normal Email
                return Email(idx, ephemeral_mid)

            msgid, mid = ephemeral_mid.rsplit('-', 1)
            etype, etarg, msgid = msgid.split('-', 2)
            if etarg not in ('all', 'att'):
                msgid = etarg + '-' + msgid
            msgid = '<%s>' % msgid.replace('_', '@')
            etype = etype.lower()

            enc_msgid = idx.encode_msg_id(msgid)
            msg_idx = idx.MSGIDS.get(enc_msgid)
            if msg_idx is not None:
                # Already actualized, just return a normal Email
                return Email(idx, msg_idx)

            if etype == 'forward':
                refs = [Email(idx, int(mid, 36))]
                e = Forward.CreateForward(idx, self.session, refs, msgid,
                                          with_atts=(etarg == 'att'))[0]
                self._track_action('fwded', refs)

            elif etype == 'reply':
                refs = [Email(idx, int(mid, 36))]
                e = Reply.CreateReply(idx, self.session, refs, msgid,
                                      reply_all=(etarg == 'all'))[0]
                self._track_action('replied', refs)

            else:
                e = Compose.CreateMessage(idx, self.session, msgid)[0]

            self._tag_blank([e])
            self.session.ui.debug('Actualized: %s' % e.msg_mid())

            return Email(idx, e.msg_idx_pos)

    return newcls


class CompositionCommand(AddComposeMethods(Search)):
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {}
    UPDATE_STRING_DATA = {
        'mid': 'metadata-ID',
        'subject': '..',
        'from': '..',
        'to': '..',
        'cc': '..',
        'bcc': '..',
        'body': '..',
        'encryption': '..',
        'attachment': '..',
        'attach-pgp-pubkey': '..',
    }

    UPDATE_HEADERS = ('Subject', 'From', 'To', 'Cc', 'Bcc', 'Encryption',
                      'Attach-PGP-Pubkey')

    def _new_msgid(self):
        msgid = (MakeMessageID()
                 .replace('.', '-')   # Dots may bother JS/CSS
                 .replace('_', '-'))  # We use _ to encode the @ later on
        return msgid

    def _get_email_updates(self, idx, create=False, noneok=False, emails=None):
        # Split the argument list into files and message IDs
        files = [f[1:].strip() for f in self.args if f.startswith('<')]
        args = [a for a in self.args if not a.startswith('<')]

        # Message IDs can come from post data
        for mid in self.data.get('mid', []):
            args.append('=%s' % mid)
        emails = emails or [self._actualize_ephemeral(mid) for mid in
                            self._choose_messages(args, allow_ephemeral=True)]

        update_header_set = (set(self.data.keys()) &
                             set([k.lower() for k in self.UPDATE_HEADERS]))
        updates, fofs = [], 0
        for e in (emails or (create and [None]) or []):
            # If we don't have a file, check for posted data
            if len(files) not in (0, 1, len(emails)):
                return (self._error(_('Cannot update from multiple files')),
                        None)
            elif len(files) == 1:
                updates.append((e, self._read_file_or_data(files[0])))
            elif files and (len(files) == len(emails)):
                updates.append((e, self._read_file_or_data(files[fofs])))
            elif update_header_set:
                # No file name, construct an update string from the POST data.
                etree = e and e.get_message_tree() or {}
                defaults = etree.get('editing_strings', {})

                up = []
                for hdr in self.UPDATE_HEADERS:
                    if hdr.lower() in self.data:
                        data = ', '.join(self.data[hdr.lower()])
                    else:
                        data = defaults.get(hdr.lower(), '')
                    up.append('%s: %s' % (hdr, data))

                # This preserves in-reply-to, references and any other
                # headers we're not usually keen on editing.
                if defaults.get('headers'):
                    up.append(defaults['headers'])

                # This weird thing converts attachment=1234:bla.txt into a
                # dict of 1234=>bla.txt values, attachment=1234 to 1234=>None.
                # .. or just keeps all attachments if nothing is specified.
                att_keep = (dict([(ai.split(':', 1) if (':' in ai)
                                   else (ai, None))
                                  for ai in self.data.get('attachment', [])])
                            if 'attachment' in self.data
                            else defaults.get('attachments', {}))
                for att_id, att_fn in defaults.get('attachments',
                                                   {}).iteritems():
                    if att_id in att_keep:
                        fn = att_keep[att_id] or att_fn
                        up.append('Attachment-%s: %s' % (att_id, fn))

                updates.append((e, '\n'.join(
                    up +
                    ['', '\n'.join(self.data.get('body',
                                                 defaults.get('body', '')))]
                )))
            elif noneok:
                updates.append((e, None))
            elif 'compose' in self.session.config.sys.debug:
                sys.stderr.write('Doing nothing with %s' % update_header_set)
            fofs += 1

        if 'compose' in self.session.config.sys.debug:
            for e, up in updates:
                sys.stderr.write(('compose/update: Update %s with:\n%s\n--\n'
                                  ) % ((e and e.msg_mid() or '(new'), up))
            if not updates:
                sys.stderr.write('compose/update: No updates!\n')

        return updates

    def _return_search_results(self, message, emails,
                               expand=None, new=[], sent=[], ephemeral=False,
                               error=None):
        session, idx = self.session, self._idx()
        if not ephemeral:
            session.results = [e.msg_idx_pos for e in emails]
        else:
            session.results = ephemeral
        session.displayed = EditableSearchResults(session, idx,
                                                  new, sent,
                                                  results=session.results,
                                                  num=len(emails),
                                                  emails=expand)
        if error:
            return self._error(message,
                               result=session.displayed,
                               info=error)
        else:
            return self._success(message, result=session.displayed)

    def _edit_messages(self, *args, **kwargs):
        try:
            return self._real_edit_messages(*args, **kwargs)
        except NotEditableError:
            return self._error(_('Message is not editable'))

    def _real_edit_messages(self, emails, new=True, tag=True, ephemeral=False):
        session, idx = self.session, self._idx()
        if (not ephemeral and
                (session.ui.edit_messages(session, emails) or not new)):
            if tag:
                self._tag_blank(emails, untag=True)
                self._tag_drafts(emails)
                self._background_save(index=True)
            self.message = _('%d message(s) edited') % len(emails)
        else:
            self.message = _('%d message(s) created') % len(emails)
        session.ui.mark(self.message)
        return self._return_search_results(self.message, emails,
                                           expand=emails,
                                           new=(new and emails),
                                           ephemeral=ephemeral)


class Draft(AddComposeMethods(View)):
    """Edit an existing draft"""
    SYNOPSIS = ('E', 'edit', 'message/draft', '[<messages>]')
    ORDER = ('Composing', 0)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID'
    }

    def _side_effects(self, emails):
        session, idx = self.session, self._idx()
        with GLOBAL_EDITING_LOCK:
            if not emails:
                session.ui.mark(_('No messages!'))
            elif session.ui.edit_messages(session, emails):
                self._tag_blank(emails, untag=True)
                self._tag_drafts(emails)
                self._background_save(index=True)
                self.message = _('%d message(s) edited') % len(emails)
            else:
                self.message = _('%d message(s) unchanged') % len(emails)
        session.ui.mark(self.message)
        return None


class Compose(CompositionCommand):
    """Create a new blank e-mail for editing"""
    SYNOPSIS = ('C', 'compose', 'message/compose', "[ephemeral]")
    ORDER = ('Composing', 0)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = dict_merge(CompositionCommand.UPDATE_STRING_DATA, {
        'cid': 'canned response metadata-ID',
    })

    @classmethod
    def _get_canned(cls, idx, cid):
        try:
            return Email(idx, int(cid, 36)
                         ).get_editing_strings().get('body', '')
        except (ValueError, IndexError, TypeError, OSError, IOError):
            traceback.print_exc()  # FIXME, ugly
            return ''

    @classmethod
    def CreateMessage(cls, idx, session, msgid, cid=None, ephemeral=False):
        if not ephemeral:
            local_id, lmbox = session.config.open_local_mailbox(session)
        else:
            local_id, lmbox = -1, None
            ephemeral = ['new-%s-mail' % msgid[1:-1].replace('@', '_')]
        profiles = session.config.vcards.find_vcards([], kinds=['profile'])
        return (Email.Create(idx, local_id, lmbox,
                             save=(not ephemeral),
                             msg_text=(cid and cls._get_canned(idx, cid)
                                       or ''),
                             msg_id=msgid,
                             ephemeral_mid=ephemeral and ephemeral[0],
                             use_default_from=(len(profiles) == 1)),
                ephemeral)

    def command(self):
        if 'mid' in self.data:
            return self._error(_('Please use update for editing messages'))

        session, idx = self.session, self._idx()
        ephemeral = (self.args and "ephemeral" in self.args)
        cid = self.data.get('cid', [None])[0]

        email, ephemeral = self.CreateMessage(idx, session, self._new_msgid(),
                                              cid=cid,
                                              ephemeral=ephemeral)
        if not ephemeral:
            self._tag_blank([email])

        email_updates = self._get_email_updates(idx,
                                                emails=[email],
                                                create=True)
        update_string = email_updates and email_updates[0][1]
        if update_string:
            email.update_from_string(session, update_string)

        return self._edit_messages([email],
                                   ephemeral=ephemeral,
                                   new=(ephemeral or not update_string))


class RelativeCompose(Compose):
    _ATT_MIMETYPES = ('application/pgp-signature', )
    _TEXT_PARTTYPES = ('text', 'quote', 'pgpsignedtext', 'pgpsecuretext',
                       'pgpverifiedtext')

    _FW_REGEXP = re.compile(r'^(fwd|fw):.*', re.IGNORECASE)
    _RE_REGEXP = re.compile(r'^(rep|re):.*', re.IGNORECASE)

    @staticmethod
    def prefix_subject(subject, prefix, prefix_regex):
        """Avoids stacking several consecutive Fw: Re: Re: Re:"""
        if subject is None:
            return prefix
        elif prefix_regex.match(subject):
            return subject
        else:
            return '%s %s' % (prefix, subject)


class Reply(RelativeCompose):
    """Create reply(-all) drafts to one or more messages"""
    SYNOPSIS = ('r', 'reply', 'message/reply', '[all|ephemeral] <messages>')
    ORDER = ('Composing', 3)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID',
        'cid': 'canned response metadata-ID',
        'reply_all': 'reply to all',
        'ephemeral': 'ephemerality',
    }
    HTTP_POST_VARS = {}

    @classmethod
    def _add_gpg_key(cls, idx, session, addr):
        fe, fn = ExtractEmailAndName(addr)
        vcard = session.config.vcards.get_vcard(fe)
        if vcard:
            keys = vcard.get_all('KEY')
            if keys:
                mime, fp = keys[0].value.split('data:')[1].split(',', 1)
                return "%s <%s#%s>" % (fn, fe, fp)
        return "%s <%s>" % (fn, fe)

    @classmethod
    def _create_from_to_cc(cls, idx, session, trees):
        config = session.config
        ahp = AddressHeaderParser()
        ref_from, ref_to, ref_cc = [], [], []
        result = {'from': '', 'to': [], 'cc': []}

        def merge_contact(ai):
            vcard = config.vcards.get_vcard(ai.address)
            if vcard:
                ai.merge_vcard(vcard)
            return ai

        # Parse the headers, so we know what we're working with. We prune
        # some of the duplicates at this stage.
        for addrs in [t['addresses'] for t in trees]:
            alist = []
            for dst, addresses in (
                    (ref_from, addrs.get('reply-to') or addrs.get('from', [])),
                    (ref_to, addrs.get('to', [])),
                    (ref_cc, addrs.get('cc', []))):
                alist += [d.address for d in dst]
                dst.extend([a for a in addresses if a.address not in alist])

        # 1st, choose a from address.
        from_ai = config.vcards.choose_from_address(
            config, ref_from, ref_to, ref_cc)  # Note: order matters!
        if from_ai:
            result['from'] = ahp.normalized(addresses=[from_ai],
                                            force_name=True)

        def addresses(addrs, exclude=[]):
            alist = [from_ai.address] if (from_ai) else []
            alist += [a.address for a in exclude]
            return [merge_contact(a) for a in addrs
                    if a.address not in alist
                    and not a.address.startswith('noreply@')
                    and '@noreply' not in a.address]

        # If only replying to messages sent from chosen from, then this is
        # a follow-up or clarification, so just use the same headers.
        if (from_ai and
               len([e for e in ref_from
                    if e and e.address == from_ai.address]) == len(ref_from)):
            if ref_to:
                result['to'] = addresses(ref_to)
            if ref_cc:
                result['cc'] = addresses(ref_cc)

        # Else, if replying to other people:
        #   - Construct To from the From lines, excluding own from
        #   - Construct Cc from the To and CC lines, except new To/From
        else:
            result['to'] = addresses(ref_from)
            result['cc'] = addresses(ref_to + ref_cc, exclude=ref_from)

        return result

    @classmethod
    def CreateReply(cls, idx, session, refs, msgid,
                    reply_all=False, cid=None, ephemeral=False):
        trees = [m.evaluate_pgp(m.get_message_tree(), decrypt=True)
                 for m in refs]

        headers = cls._create_from_to_cc(idx, session, trees)
        if not reply_all and 'cc' in headers:
            del headers['cc']

        ref_ids = [t['headers_lc'].get('message-id') for t in trees]
        ref_subjs = [t['headers_lc'].get('subject') for t in trees]
        msg_bodies = []
        for t in trees:
            # FIXME: Templates/settings for how we quote replies?
            quoted = ''.join([p['data'] for p in t['text_parts']
                              if p['type'] in cls._TEXT_PARTTYPES
                              and p['data']])
            if quoted:
                target_width = session.config.prefs.line_length
                if target_width > 40:
                    quoted = reflow_text(quoted, target_width=target_width-2)
                text = ((_('%s wrote:') % t['headers_lc']['from']) + '\n' +
                        quoted)
                msg_bodies.append('\n\n' + text.replace('\n', '\n> '))

        if not ephemeral:
            local_id, lmbox = session.config.open_local_mailbox(session)
        else:
            local_id, lmbox = -1, None
            fmt = 'reply-all-%s-%s' if reply_all else 'reply-%s-%s'
            ephemeral = [fmt % (msgid[1:-1].replace('@', '_'),
                                refs[0].msg_mid())]

        if 'cc' in headers:
            fmt = _('Composing a reply from %(from)s to %(to)s, cc %(cc)s')
        else:
            fmt = _('Composing a reply from %(from)s to %(to)s')
        session.ui.debug(fmt % headers)

        if cid:
            # FIXME: Instead, we should use placeholders in the template
            #        and insert the quoted bits in the right place (or
            #        nowhere if the template doesn't want them).
            msg_bodies[:0] = [cls._get_canned(idx, cid)]

        return (Email.Create(idx, local_id, lmbox,
                             msg_text='\n\n'.join(msg_bodies),
                             msg_subject=cls.prefix_subject(
                                 ref_subjs[-1], 'Re:', cls._RE_REGEXP),
                             msg_from=headers.get('from', None),
                             msg_to=headers.get('to', []),
                             msg_cc=headers.get('cc', []),
                             msg_references=[i for i in ref_ids if i],
                             msg_id=msgid,
                             save=(not ephemeral),
                             ephemeral_mid=ephemeral and ephemeral[0]),
                ephemeral)

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        reply_all = False
        ephemeral = False
        args = list(self.args)
        if not args:
            args = ["=%s" % x for x in self.data.get('mid', [])]
            ephemeral = truthy((self.data.get('ephemeral') or [False])[0])
            reply_all = truthy((self.data.get('reply_all') or [False])[0])
        else:
            while args:
                if args[0].lower() == 'all':
                    reply_all = args.pop(0) or True
                elif args[0].lower() == 'ephemeral':
                    ephemeral = args.pop(0) or True
                else:
                    break

        refs = [Email(idx, i) for i in self._choose_messages(args)]
        if refs:
            try:
                cid = self.data.get('cid', [None])[0]
                email, ephemeral = self.CreateReply(idx, session, refs,
                                                    self._new_msgid(),
                                                    reply_all=reply_all,
                                                    cid=cid,
                                                    ephemeral=ephemeral)
            except NoFromAddressError:
                return self._error(_('You must configure a '
                                     'From address first.'))

            if not ephemeral:
                self._track_action('replied', refs)
                self._tag_blank([email])

            return self._edit_messages([email], ephemeral=ephemeral)
        else:
            return self._error(_('No message found'))


class Forward(RelativeCompose):
    """Create forwarding drafts of one or more messages"""
    SYNOPSIS = ('f', 'forward', 'message/forward', '[att|ephemeral] <messages>')
    ORDER = ('Composing', 4)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID',
        'cid': 'canned response metadata-ID',
        'ephemeral': 'ephemerality',
        'atts': 'forward attachments'
    }
    HTTP_POST_VARS = {}

    @classmethod
    def CreateForward(cls, idx, session, refs, msgid,
                      with_atts=False, cid=None, ephemeral=False):
        trees = [m.evaluate_pgp(m.get_message_tree(), decrypt=True)
                 for m in refs]
        ref_subjs = [t['headers_lc']['subject'] for t in trees]
        msg_bodies = []
        msg_atts = []
        for t in trees:
            # FIXME: Templates/settings for how we quote forwards?
            text = '-------- Original Message --------\n'
            for h in ('Date', 'Subject', 'From', 'To'):
                v = t['headers_lc'].get(h.lower(), None)
                if v:
                    text += '%s: %s\n' % (h, v)
            text += '\n'
            text += ''.join([p['data'] for p in t['text_parts']
                             if p['type'] in cls._TEXT_PARTTYPES])
            msg_bodies.append(text)
            if with_atts:
                for att in t['attachments']:
                    if att['mimetype'] not in cls._ATT_MIMETYPES:
                        msg_atts.append(att['part'])

        if not ephemeral:
            local_id, lmbox = session.config.open_local_mailbox(session)
        else:
            local_id, lmbox = -1, None
            fmt = 'forward-att-%s-%s' if msg_atts else 'forward-%s-%s'
            ephemeral = [fmt % (msgid[1:-1].replace('@', '_'),
                                refs[0].msg_mid())]

        if cid:
            # FIXME: Instead, we should use placeholders in the template
            #        and insert the quoted bits in the right place (or
            #        nowhere if the template doesn't want them).
            msg_bodies[:0] = [cls._get_canned(idx, cid)]

        email = Email.Create(idx, local_id, lmbox,
                             msg_text='\n\n'.join(msg_bodies),
                             msg_subject=cls.prefix_subject(
                                 ref_subjs[-1], 'Fwd:', cls._FW_REGEXP),
                             msg_id=msgid,
                             msg_atts=msg_atts,
                             save=(not ephemeral),
                             ephemeral_mid=ephemeral and ephemeral[0])

        return email, ephemeral

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        with_atts = False
        ephemeral = False
        args = list(self.args)
        if not args:
            args = ["=%s" % x for x in self.data.get('mid', [])]
            ephemeral = truthy((self.data.get('ephemeral') or [False])[0])
            with_atts = truthy((self.data.get('atts') or [False])[0])
        else:
            while args:
                if args[0].lower() == 'att':
                    with_atts = args.pop(0) or True
                elif args[0].lower() == 'ephemeral':
                    ephemeral = args.pop(0) or True
                else:
                    break

        if ephemeral and with_atts:
            raise UsageError(_('Sorry, ephemeral messages cannot have '
                               'attachments at this time.'))

        refs = [Email(idx, i) for i in self._choose_messages(args)]
        if refs:
            cid = self.data.get('cid', [None])[0]
            email, ephemeral = self.CreateForward(idx, session, refs,
                                                  self._new_msgid(),
                                                  with_atts=with_atts,
                                                  cid=cid,
                                                  ephemeral=ephemeral)

            if not ephemeral:
                self._track_action('fwded', refs)
                self._tag_blank([email])

            return self._edit_messages([email], ephemeral=ephemeral)
        else:
            return self._error(_('No message found'))


class Attach(CompositionCommand):
    """Attach a file to a message"""
    SYNOPSIS = ('a', 'attach', 'message/attach', '<messages> [<path/to/file>]')
    ORDER = ('Composing', 2)
    WITH_CONTEXT = (GLOBAL_EDITING_LOCK, )
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
        'name': '(ignored)',
        'file-data': 'file data'
    }

    def command(self, emails=None):
        session, idx = self.session, self._idx()
        args = list(self.args)

        files = []
        filedata = {}
        if 'file-data' in self.data:
            count = 0
            for fd in self.data['file-data']:
                fn = (hasattr(fd, 'filename')
                      and fd.filename or 'attach-%d.dat' % count)
                filedata[fn] = fd
                files.append(fn)
                count += 1
        else:
            if args:
                fb = security.forbid_command(self,
                                             security.CC_ACCESS_FILESYSTEM)
                if fb:
                    return self._error(fb)
            while os.path.exists(args[-1]):
                files.append(args.pop(-1))

        if not files:
            return self._error(_('No files found'))

        if not emails:
            args.extend(['=%s' % mid for mid in self.data.get('mid', [])])
            emails = [self._actualize_ephemeral(i) for i in
                      self._choose_messages(args, allow_ephemeral=True)]
        if not emails:
            return self._error(_('No messages selected'))

        updated = []
        errors = []
        def err(msg):
            errors.append(msg)
            session.ui.error(msg)
        for email in emails:
            subject = email.get_msg_info(MailIndex.MSG_SUBJECT)
            try:
                email.add_attachments(session, files, filedata=filedata)
                updated.append(email)
            except KeyboardInterrupt:
                raise
            except NotEditableError:
                err(_('Read-only message: %s') % subject)
            except:
                err(_('Error attaching to %s') % subject)
                self._ignore_exception()

        if errors:
            self.message = _('Attached %s to %d messages, failed %d'
                             ) % (', '.join(files), len(updated), len(errors))
        else:
            self.message = _('Attached %s to %d messages'
                             ) % (', '.join(files), len(updated))

        session.ui.notify(self.message)
        return self._return_search_results(self.message, updated,
                                           expand=updated, error=errors)


class UnAttach(CompositionCommand):
    """Remove an attachment from a message"""
    SYNOPSIS = (None, 'unattach', 'message/unattach', '<mid> <atts>')
    ORDER = ('Composing', 2)
    WITH_CONTEXT = (GLOBAL_EDITING_LOCK, )
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
        'att': 'Attachment IDs or filename'
    }

    def command(self, emails=None):
        session, idx = self.session, self._idx()
        args = list(self.args)
        atts = []

        if '--' in args:
            atts = args[args.index('--') + 1:]
            args = args[:args.index('--')]
        elif args:
            atts = [args.pop(-1)]
        atts.extend(self.data.get('att', []))

        if not emails:
            args.extend(['=%s' % mid for mid in self.data.get('mid', [])])
            emails = [self._actualize_ephemeral(i) for i in
                      self._choose_messages(args, allow_ephemeral=True)]
        if not emails:
            return self._error(_('No messages selected'))

        updated = []
        errors = []
        def err(msg):
            errors.append(msg)
            session.ui.error(msg)

        for email in emails:
            subject = email.get_msg_info(MailIndex.MSG_SUBJECT)
            try:
                email.remove_attachments(session, *atts)
                updated.append(email)
            except KeyboardInterrupt:
                raise
            except NotEditableError:
                err(_('Read-only message: %s') % subject)
            except:
                err(_('Error removing from %s') % subject)
                self._ignore_exception()

        if errors:
            self.message = _('Removed %s from %d messages, failed %d'
                             ) % (', '.join(atts), len(updated), len(errors))
        else:
            self.message = _('Removed %s from %d messages'
                             ) % (', '.join(atts), len(updated))

        session.ui.notify(self.message)
        return self._return_search_results(self.message, updated,
                                           expand=updated, error=errors)



class Sendit(CompositionCommand):
    """Mail/bounce a message (to someone)"""
    SYNOPSIS = (None, 'bounce', 'message/send', '<messages> [<emails>]')
    ORDER = ('Composing', 5)
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
        'to': 'recipients',
        'from': 'sender e-mail'
    }

    # We set our events' source class explicitly, so subclasses don't
    # accidentally create orphaned mail tracking events.
    EVENT_SOURCE = 'mailpile.plugins.compose.Sendit'

    def command(self, emails=None):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)

        bounce_to = []
        while args and '@' in args[-1]:
            bounce_to.append(args.pop(-1))
        for rcpt in (self.data.get('to', []) +
                     self.data.get('cc', []) +
                     self.data.get('bcc', [])):
            bounce_to.extend(ExtractEmails(rcpt))

        sender = self.data.get('from', [None])[0]
        if not sender and bounce_to:
            sender = idx.config.get_profile().get('email', None)

        if not emails:
            args.extend(['=%s' % mid for mid in self.data.get('mid', [])])
            emails = [self._actualize_ephemeral(i) for i in
                      self._choose_messages(args, allow_ephemeral=True)]

        # First make sure the draft tags are all gone, so other edits either
        # fail or complete while we wait for the lock.
        with GLOBAL_EDITING_LOCK:
            self._tag_drafts(emails, untag=True)
            self._tag_blank(emails, untag=True)

        # Process one at a time so we don't eat too much memory
        sent = []
        missing_keys = []
        locked_keys = []
        for email in emails:
            events = []
            try:
                msg_mid = email.get_msg_info(idx.MSG_MID)

                # This is a unique sending-ID. This goes in the public (meant
                # for debugging help) section of the event-log, so we take
                # care to not reveal details about the message or recipients.
                msg_sid = sha1b64(email.get_msg_info(idx.MSG_ID),
                                  *sorted(bounce_to))[:8]

                # We load up any incomplete events for sending this message
                # to this set of recipients. If nothing is in flight, create
                # a new event for tracking this operation.
                events = list(config.event_log.incomplete(
                    source=self.EVENT_SOURCE,
                    data_mid=msg_mid,
                    data_sid=msg_sid))
                if not events:
                    events.append(config.event_log.log(
                        source=self.EVENT_SOURCE,
                        flags=Event.RUNNING,
                        message=_('Sending message'),
                        data={'mid': msg_mid, 'sid': msg_sid}))

                SendMail(session, msg_mid,
                         [PrepareMessage(config,
                                         email.get_msg(pgpmime=False),
                                         sender=sender,
                                         rcpts=(bounce_to or None),
                                         bounce=(True if bounce_to else False),
                                         events=events)])
                for ev in events:
                    ev.flags = Event.COMPLETE
                    config.event_log.log_event(ev)
                sent.append(email)

            # Encryption related failures are fatal, don't retry
            except (KeyLookupError,
                    EncryptionFailureError,
                    SignatureFailureError), exc:
                message = unicode(exc)
                session.ui.warning(message)
                if hasattr(exc, 'missing_keys'):
                    missing_keys.extend(exc.missing)
                if hasattr(exc, 'from_key'):
                    # FIXME: We assume signature failures happen because
                    # the key is locked. Are there any other reasons?
                    locked_keys.append(exc.from_key)
                for ev in events:
                    ev.flags = Event.COMPLETE
                    ev.message = message
                    config.event_log.log_event(ev)
                self._ignore_exception()

            # FIXME: Also fatal, when the SMTP server REJECTS the mail
            except:
                # We want to try that again!
                to = email.get_msg().get('x-mp-internal-rcpts',
                                         '').split(',')[0]
                if to:
                    message = _('Could not send mail to %s') % to
                else:
                    message = _('Could not send mail')
                for ev in events:
                    ev.flags = Event.INCOMPLETE
                    ev.message = message
                    config.event_log.log_event(ev)
                session.ui.error(message)
                self._ignore_exception()

        if 'compose' in config.sys.debug:
            sys.stderr.write(('compose/Sendit: Send %s to %s (sent: %s)\n'
                              ) % (len(emails),
                                   bounce_to or '(header folks)', sent))

        if missing_keys:
            self.error_info['missing_keys'] = missing_keys
        if locked_keys:
            self.error_info['locked_keys'] = locked_keys
        if sent:
            self._tag_sent(sent)
            self._tag_outbox(sent, untag=True)
            for email in sent:
                email.reset_caches()
                idx.index_email(self.session, email)

            return self._return_search_results(
                _('Sent %d messages') % len(sent), sent, sent=sent)
        else:
            return self._error(_('Nothing was sent'))


class Update(CompositionCommand):
    """Update message from a file or HTTP upload."""
    SYNOPSIS = (None, 'update', 'message/update', '<messages> <<filename>')
    ORDER = ('Composing', 1)
    WITH_CONTEXT = (GLOBAL_EDITING_LOCK, )
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_POST_VARS = dict_merge(CompositionCommand.UPDATE_STRING_DATA,
                                Attach.HTTP_POST_VARS)

    def command(self, create=True, outbox=False):
        session, config, idx = self.session, self.session.config, self._idx()
        email_updates = self._get_email_updates(idx,
                                                create=create,
                                                noneok=outbox)

        if not email_updates:
            return self._error(_('Nothing to do!'))
        try:
            if (self.data.get('file-data') or [''])[0]:
                if not Attach(session, data=self.data).command(emails=emails):
                    return self._error(_('Failed to attach files'))

            for email, update_string in email_updates:
                email.update_from_string(session, update_string, final=outbox)

            emails = [e for e, u in email_updates]
            message = _('%d message(s) updated') % len(email_updates)

            self._tag_blank(emails, untag=True)
            self._tag_drafts(emails, untag=outbox)
            self._tag_outbox(emails, untag=(not outbox))

            if outbox:
                self._create_contacts(emails)
                return self._return_search_results(message, emails,
                                                   sent=emails)
            else:
                return self._edit_messages(emails, new=False, tag=False)
        except KeyLookupError, kle:
            return self._error(_('Missing encryption keys'),
                               info={'missing_keys': kle.missing})
        except EncryptionFailureError, efe:
            # This should never happen, should have been prevented at key
            # lookup!
            return self._error(_('Could not encrypt message'),
                               info={'to_keys': efe.to_keys})
        except SignatureFailureError, sfe:
            # FIXME: We assume signature failures happen because
            # the key is locked. Are there any other reasons?
            return self._error(_('Could not sign message'),
                               info={'locked_keys': [sfe.from_key]})


class UpdateAndSendit(Update):
    """Update message from an HTTP upload and move to outbox."""
    SYNOPSIS = ('m', 'mail', 'message/update/send', None)

    def command(self, create=True, outbox=True):
        return Update.command(self, create=create, outbox=outbox)


class UnThread(CompositionCommand):
    """Remove a message from a thread."""
    SYNOPSIS = (None, 'unthread', 'message/unthread', None)
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_POST_VARS = {'mid': 'message-id'}

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        # Message IDs can come from post data
        args = list(self.args)
        for mid in self.data.get('mid', []):
            args.append('=%s' % mid)
        emails = [self._actualize_ephemeral(i) for i in
                  self._choose_messages(args, allow_ephemeral=True)]

        if emails:
            for email in emails:
                idx.unthread_message(email.msg_mid())
            return self._return_search_results(
                _('Unthreaded %d messages') % len(emails), emails)
        else:
            return self._error(_('Nothing to do!'))


class EmptyOutbox(Sendit):
    """Try to empty the outbox."""
    SYNOPSIS = (None, 'sendmail', None, None)
    IS_USER_ACTIVITY = False

    @classmethod
    def sendmail(cls, session):
        cls(session).run()

    def command(self):
        cfg, idx = self.session.config, self.session.config.index
        if not idx:
            return self._error(_('The index is not ready yet'))

        # Collect a list of messages from the outbox
        messages = []
        for tag in cfg.get_tags(type='outbox'):
            search = ['in:%s' % tag._key]
            for msg_idx_pos in idx.search(self.session, search,
                                          order='flat-index').as_set():
                messages.append('=%s' % b36(msg_idx_pos))

        # Messages no longer in the outbox get their events canceled...
        if cfg.event_log:
            events = cfg.event_log.incomplete(source='.plugins.compose.Sendit')
            for ev in events:
                if ('mid' in ev.data and
                        ('=%s' % ev.data['mid']) not in messages):
                    ev.flags = ev.COMPLETE
                    ev.message = _('Sending cancelled.')
                    cfg.event_log.log_event(ev)

        # Send all the mail!
        if messages:
            self.args = tuple(set(messages))
            return Sendit.command(self)
        else:
            return self._success(_('The outbox is empty'))


_plugins.register_config_variables('prefs', {
    'empty_outbox_interval': [_('Delay between attempts to send mail'),
                              int, 90]
})
_plugins.register_slow_periodic_job('sendmail',
                                    'prefs.empty_outbox_interval',
                                    EmptyOutbox.sendmail)
_plugins.register_commands(Compose, Reply, Forward,           # Create
                           Draft, Update, Attach, UnAttach,   # Manipulate
                           UnThread,                          # ...
                           Sendit, UpdateAndSendit,           # Send
                           EmptyOutbox)                       # ...
