import datetime
import os
import os.path
import re
import traceback
from gettext import gettext as _

from mailpile.plugins import PluginManager
from mailpile.commands import Command
from mailpile.crypto.state import *
from mailpile.eventlog import Event
from mailpile.plugins.tags import Tag
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName, Email
from mailpile.mailutils import NotEditableError
from mailpile.mailutils import NoFromAddressError, PrepareMessage
from mailpile.smtp_client import SendMail
from mailpile.search import MailIndex
from mailpile.urlmap import UrlMap
from mailpile.util import *

from mailpile.plugins.search import Search, SearchResults, View


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
            if isinstance(ephemeral_mid, int):
                # Not actually ephemeral, just return a normal Email
                return Email(self._idx(), ephemeral_mid)

            etype, mid = ephemeral_mid.split(':')
            etype = etype.lower()

            if etype in ('forward', 'forward-att'):
                refs = [Email(self._idx(), int(mid, 36))]
                e = Forward.CreateForward(self._idx(), self.session, refs,
                                          with_atts=('att' in etype))[0]
                self._track_action('fwded', refs)

            elif etype in ('reply', 'reply-all'):
                refs = [Email(self._idx(), int(mid, 36))]
                e = Reply.CreateReply(self._idx(), self.session, refs,
                                      reply_all=('all' in etype))[0]
                self._track_action('replied', refs)

            else:
                e = Compose.CreateMessage(self._idx(), self.session)[0]

            self._tag_blank([e])
            self.session.ui.debug('Actualized: %s' % e.msg_mid())

            return Email(self._idx(), e.msg_idx_pos)

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
    }

    UPDATE_HEADERS = ('Subject', 'From', 'To', 'Cc', 'Bcc', 'Encryption')

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
                up = []
                etree = e and e.get_message_tree() or {}
                defaults = etree.get('editing_strings', {})
                for hdr in self.UPDATE_HEADERS:
                    if hdr.lower() in self.data:
                        data = ', '.join(self.data[hdr.lower()])
                    else:
                        data = defaults.get(hdr.lower(), '')
                    up.append('%s: %s' % (hdr, data))
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

    def _return_search_results(self, emails,
                               expand=None, new=[], sent=[], ephemeral=False):
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
        return session.displayed

    def _edit_messages(self, emails, new=True, tag=True, ephemeral=False):
        session, idx = self.session, self._idx()
        if (not ephemeral and
                (session.ui.edit_messages(session, emails) or not new)):
            if tag:
                self._tag_blank(emails, untag=True)
                self._tag_drafts(emails)
            self.message = _('%d message(s) edited') % len(emails)
        else:
            self.message = _('%d message(s) created') % len(emails)
        session.ui.mark(self.message)
        idx.save_changes()
        return self._return_search_results(emails,
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

    # FIXME: This command should raise an error if the message being
    #        displayed is not editable.

    def _side_effects(self, emails):
        session, idx = self.session, self._idx()
        try:
            if not emails:
                session.ui.mark(_('No messages!'))
            elif session.ui.edit_messages(session, emails):
                self._tag_blank(emails, untag=True)
                self._tag_drafts(emails)
                idx.save_changes()
                self.message = _('%d message(s) edited') % len(emails)
            else:
                self.message = _('%d message(s) unchanged') % len(emails)
            session.ui.mark(self.message)
        except:
            # FIXME: Shutup
            import traceback
            traceback.print_exc()
        return None


class Compose(CompositionCommand):
    """Create a new blank e-mail for editing"""
    SYNOPSIS = ('C', 'compose', 'message/compose', "[ephemeral]")
    ORDER = ('Composing', 0)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = CompositionCommand.UPDATE_STRING_DATA

    @classmethod
    def CreateMessage(cls, idx, session, ephemeral=False):
        if not ephemeral:
            local_id, lmbox = session.config.open_local_mailbox(session)
        else:
            local_id, lmbox = -1, None
            ephemeral = ['new:mail']
        return (Email.Create(idx, local_id, lmbox,
                             save=(not ephemeral),
                             ephemeral_mid=ephemeral and ephemeral[0]),
                ephemeral)

    def command(self):
        if 'mid' in self.data:
            return self._error(_('Please use update for editing messages'))

        session, idx = self.session, self._idx()
        ephemeral = (self.args and "ephemeral" in self.args)

        email, ephemeral = self.CreateMessage(idx, session,
                                              ephemeral=ephemeral)
        email_updates = self._get_email_updates(idx,
                                                emails=[email],
                                                create=True)
        update_string = email_updates and email_updates[0][1]
        if update_string:
            email.update_from_string(session, update_string)

        if not ephemeral:
            self._tag_blank([email])
        return self._edit_messages([email], ephemeral=ephemeral, new=True)


class RelativeCompose(Compose):
    _ATT_MIMETYPES = ('application/pgp-signature', )
    _TEXT_PARTTYPES = ('text', 'quote', 'pgpsignedtext', 'pgpsecuretext',
                       'pgpverifiedtext')


class Reply(RelativeCompose):
    """Create reply(-all) drafts to one or more messages"""
    SYNOPSIS = ('r', 'reply', 'message/reply', '[all|ephemeral] <messages>')
    ORDER = ('Composing', 3)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID',
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
    def CreateReply(cls, idx, session, refs,
                    reply_all=False, ephemeral=False):
        trees = [m.evaluate_pgp(m.get_message_tree(), decrypt=True)
                 for m in refs]

        ref_ids = [t['headers_lc'].get('message-id') for t in trees]
        ref_subjs = [t['headers_lc'].get('subject') for t in trees]
        msg_to = [cls._add_gpg_key(idx, session,
            t['headers_lc'].get('reply-to', t['headers_lc']['from']))
            for t in trees]

        msg_cc_raw = []
        if reply_all:
            msg_cc_raw += [t['headers_lc'].get('to', '') for t in trees]
            msg_cc_raw += [t['headers_lc'].get('cc', '') for t in trees]
        msg_cc = []
        for hdr in msg_cc_raw:
            for addr in [a.strip() for a in hdr.split(',')]:
                if addr:
                    msg_cc.append(cls._add_gpg_key(idx, session, a))

        msg_bodies = []
        for t in trees:
            # FIXME: Templates/settings for how we quote replies?
            text = ((_('%s wrote:') % t['headers_lc']['from']) + '\n' +
                    ''.join([p['data'] for p in t['text_parts']
                             if p['type'] in cls._TEXT_PARTTYPES]))
            msg_bodies.append('\n\n' + text.replace('\n', '\n> '))

        if not ephemeral:
            local_id, lmbox = session.config.open_local_mailbox(session)
        else:
            local_id, lmbox = -1, None
            if reply_all:
                ephemeral = ['reply-all:%s' % refs[0].msg_mid()]
            else:
                ephemeral = ['reply:%s' % refs[0].msg_mid()]

        return (Email.Create(idx, local_id, lmbox,
                             msg_text='\n\n'.join(msg_bodies),
                             msg_subject=('Re: %s' % ref_subjs[-1]),
                             msg_to=msg_to,
                             msg_cc=[r for r in msg_cc if r],
                             msg_references=[i for i in ref_ids if i],
                             save=(not ephemeral),
                             ephemeral_mid=ephemeral and ephemeral[0]),
                ephemeral)

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        reply_all = False
        ephemeral = False
        args = list(self.args)
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
                email, ephemeral = self.CreateReply(idx, session, refs,
                                                    reply_all=reply_all,
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
    }
    HTTP_POST_VARS = {}

    @classmethod
    def CreateForward(cls, idx, session, refs,
                      with_atts=False, ephemeral=False):
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
            if msg_atts:
                ephemeral = ['forward-att:%s' % refs[0].msg_mid()]
            else:
                ephemeral = ['forward:%s' % refs[0].msg_mid()]

        email = Email.Create(idx, local_id, lmbox,
                             msg_text='\n\n'.join(msg_bodies),
                             msg_subject=('Fwd: %s' % ref_subjs[-1]),
                             save=(not ephemeral),
                             ephemeral_mid=ephemeral and ephemeral[0])

        if msg_atts:
            msg = email.get_msg()
            for att in msg_atts:
                msg.attach(att)
            email.update_from_msg(session, msg)

        return email, ephemeral

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        with_atts = False
        ephemeral = False
        args = list(self.args)
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
            email, ephemeral = self.CreateReply(idx, session, refs,
                                                with_atts=with_atts,
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
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
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
            while os.path.exists(args[-1]):
                files.append(args.pop(-1))

        if not files:
            return self._error(_('No files found'))

        if not emails:
            emails = [self._actualize_ephemeral(i) for i in
                      self._choose_messages(args, allow_ephemeral=True)]
        if not emails:
            return self._error(_('No messages selected'))

        updated = []
        for email in emails:
            subject = email.get_msg_info(MailIndex.MSG_SUBJECT)
            try:
                email.add_attachments(session, files, filedata=filedata)
                updated.append(email)
            except NotEditableError:
                session.ui.error(_('Read-only message: %s') % subject)
            except:
                session.ui.error(_('Error attaching to %s') % subject)
                self._ignore_exception()

        self.message = _('Attached %s to %d messages'
                         ) % (', '.join(files), len(updated))
        session.ui.notify(self.message)
        return self._return_search_results(updated, expand=updated)


class Sendit(CompositionCommand):
    """Mail/bounce a message (to someone)"""
    SYNOPSIS = (None, 'bounce', 'message/send', '<messages> [<emails>]')
    ORDER = ('Composing', 5)
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
        'to': 'recipients'
    }

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

        if not emails:
            args.extend(['=%s' % mid for mid in self.data.get('mid', [])])
            mids = self._choose_messages(args)
            emails = [Email(idx, i) for i in mids]

        # Process one at a time so we don't eat too much memory
        sent = []
        missing_keys = []
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
                events = list(config.event_log.incomplete(source=self,
                                                          data_mid=msg_mid,
                                                          data_sid=msg_sid))
                if not events:
                    events.append(config.event_log.log(
                        source=self,
                        flags=Event.RUNNING,
                        message=_('Sending message'),
                        data={'mid': msg_mid, 'sid': msg_sid}))

                SendMail(session, [PrepareMessage(config,
                                                  email.get_msg(pgpmime=False),
                                                  rcpts=(bounce_to or None),
                                                  events=events)])
                for ev in events:
                    ev.flags = Event.COMPLETE
                    config.event_log.log_event(ev)
                sent.append(email)
            except KeyLookupError, kle:
                # This is fatal, we don't retry
                message = _('Missing keys %s') % kle.missing
                for ev in events:
                    ev.flags = Event.COMPLETE
                    ev.message = message
                    config.event_log.log_event(ev)
                session.ui.warning(message)
                missing_keys.extend(kle.missing)
                self._ignore_exception()
            except:
                # We want to try that again!
                message = _('Failed to send %s') % email
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
        if sent:
            self._tag_sent(sent)
            self._tag_outbox(sent, untag=True)
            self._tag_drafts(sent, untag=True)
            self._tag_blank(sent, untag=True)
            for email in sent:
                idx.index_email(self.session, email)

            return self._return_search_results(sent, sent=sent)
        else:
            return self._error(_('Nothing was sent'))


class Update(CompositionCommand):
    """Update message from a file or HTTP upload."""
    SYNOPSIS = ('u', 'update', 'message/update', '<messages> <<filename>')
    ORDER = ('Composing', 1)
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
                    return False

            for email, update_string in email_updates:
                email.update_from_string(session, update_string, final=outbox)

            emails = [e for e, u in email_updates]
            session.ui.notify(_('%d message(s) updated') % len(email_updates))

            self._tag_blank(emails, untag=True)
            self._tag_drafts(emails, untag=outbox)
            self._tag_outbox(emails, untag=(not outbox))

            if outbox:
                return self._return_search_results(emails, sent=emails)
            else:
                return self._edit_messages(emails, new=False, tag=False)
        except KeyLookupError, kle:
            return self._error(_('Missing encryption keys'),
                               info={'missing_keys': kle.missing})


class UnThread(CompositionCommand):
    """Remove a message from a thread."""
    SYNOPSIS = (None, 'unthread', 'message/unthread', None)
    HTTP_POST_VARS = {'mid': 'message-id'}

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        # Message IDs can come from post data
        args = self.args
        for mid in self.data.get('mid', []):
            args.append('=%s' % mid)
        emails = [Email(idx, mid) for mid in self._choose_messages(args)]

        if emails:
            for email in emails:
                idx.unthread_message(email.msg_mid())
            return self._return_search_results(emails)
        else:
            return self._error(_('Nothing to do!'))


class UpdateAndSendit(Update):
    """Update message from an HTTP upload and move to outbox."""
    SYNOPSIS = ('m', 'mail', 'message/update/send', None)

    def command(self, create=True, outbox=True):
        return Update.command(self, create=create, outbox=outbox)


class EmptyOutbox(Command):
    """Try to empty the outbox."""
    SYNOPSIS = (None, 'sendmail', None, None)

    @classmethod
    def sendmail(cls, session):
        cfg, idx = session.config, session.config.index
        messages = []
        for tag in cfg.get_tags(type='outbox'):
            search = ['in:%s' % tag._key]
            for msg_idx_pos in idx.search(session, search,
                                          order='flat-index').as_set():
                messages.append('=%s' % b36(msg_idx_pos))
        if messages:
            return Sendit(session, arg=messages).run()
        else:
            return True

    def command(self):
        return self.sendmail(self.session)


_plugins.register_config_variables('prefs', {
    'empty_outbox_interval': [_('Delay between attempts to send mail'),
                              int, 90]
})
_plugins.register_slow_periodic_job('sendmail',
                                    'prefs.empty_outbox_interval',
                                    EmptyOutbox.sendmail)
_plugins.register_commands(Compose, Reply, Forward,  # Create
                           Draft, Update, Attach,    # Manipulate
                           UnThread,                 # ...
                           Sendit, UpdateAndSendit,  # Send
                           EmptyOutbox)              # ...
