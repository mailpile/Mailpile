import datetime
import os
import os.path
import re
import traceback
from gettext import gettext as _

import mailpile.plugins
from mailpile.commands import Command
from mailpile.plugins.tags import Tag
from mailpile.mailutils import ExtractEmails, Email, PrepareMail, SendMail
from mailpile.search import MailIndex
from mailpile.urlmap import UrlMap
from mailpile.util import *

from mailpile.plugins.search import Search, SearchResults, View


class EditableSearchResults(SearchResults):
    def __init__(self, session, idx, new, sent, **kwargs):
        SearchResults.__init__(self, session, idx, **kwargs)
        self.new_messages = new
        self.sent_messages = sent
        if new:
            self['created'] = [m.msg_mid() for m in new]
        if sent:
            self['sent'] = [m.msg_mid() for m in new]


class CompositionCommand(Search):
    HTTP_QUERY_VARS = { }
    HTTP_POST_VARS = { }
    UPDATE_STRING_DATA = {
        'mid': 'metadata-ID',
        'subject': '..',
        'from': '..',
        'to': '..',
        'cc': '..',
        'bcc': '..',
        'body': '..',
    }

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

    UPDATE_HEADERS = ('Subject', 'From', 'To', 'Cc', 'Bcc')

    def _get_email_updates(self, idx, emails=None):
        # Split the argument list into files and message IDs
        files = [f[1:].strip() for f in self.args if f.startswith('<')]
        args = [a for a in self.args if not a.startswith('<')]

        # Message IDs can come from post data
        for mid in self.data.get('mid', []):
            args.append('=%s' % mid)
        emails = emails or [Email(idx, mid)
                            for mid in self._choose_messages(args)]

        update_header_set = (set(self.data.keys()) &
                             set([k.lower() for k in self.UPDATE_HEADERS]))
        updates, fofs = [], 0
        for e in (emails or (create and [None]) or []):
            # If we don't have a file, check for posted data
            if len(files) not in (0, 1, len(emails)):
                return (self._error('Cannot update from multiple files'), None)
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
                updates.append((e, '\n'.join(up + ['',
                    '\n'.join(self.data.get('body', defaults.get('body', '')))
                ])))
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

    def _return_search_results(self, emails, expand=None, new=[], sent=[]):
        session, idx = self.session, self._idx()
        session.results = [e.msg_idx_pos for e in emails]
        session.displayed = EditableSearchResults(session, idx, new, sent,
                                                  results=session.results,
                                                  num=len(emails),
                                                  emails=expand)
        return session.displayed

    def _edit_messages(self, emails, new=True):
        session, idx = self.session, self._idx()
        session.ui.edit_messages(emails)
        if new:
            session.ui.mark('%d message(s) created as drafts' % len(emails))
        else:
            session.ui.mark('%d message(s) edited' % len(emails))
        idx.save()
        return self._return_search_results(emails,
                                           expand=emails,
                                           new=(new and emails))


class Draft(View):
    """Edit an existing draft"""
    SYNOPSIS = ('D', 'draft', 'message/draft', '[<messages>]')
    ORDER = ('Composing', 0)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID'
    }

    # FIXME: This command should raise an error if the message being
    #        displayed is not editable.


class Compose(CompositionCommand):
    """Create a new blank e-mail for editing"""
    SYNOPSIS = ('C', 'compose', 'message/compose', None)
    ORDER = ('Composing', 0)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = CompositionCommand.UPDATE_STRING_DATA

    def command(self):
        if 'mid' in self.data:
            return self._error('Please use update for editing messages')

        session, idx = self.session, self._idx()
        local_id, lmbox = session.config.open_local_mailbox(session)
        emails = [Email.Create(idx, local_id, lmbox)]

        self._tag_blank(emails)
        for email in emails:
            email_updates = self._get_email_updates(idx, [email])
            update_string = email_updates and email_updates[0][1]
            if update_string:
                email.update_from_string(update_string)

        return self._edit_messages(emails, new=True)


class RelativeCompose(Compose):
    _ATT_MIMETYPES = ('application/pgp-signature', )
    _TEXT_PARTTYPES = ('text', 'quote', 'pgpsignedtext', 'pgpsecuretext',
                       'pgpverifiedtext')


class Reply(RelativeCompose):
    """Create reply(-all) drafts to one or more messages"""
    SYNOPSIS = ('r', 'reply', 'message/reply', '[all] <messages>')
    ORDER = ('Composing', 3)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID',
    }
    HTTP_POST_VARS = {}

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        if self.args and self.args[0].lower() == 'all':
            reply_all = self.args.pop(0) or True
        else:
            reply_all = False

        refs = [Email(idx, i) for i in self._choose_messages(self.args)]
        if refs:
            trees = [m.evaluate_pgp(m.get_message_tree(), decrypt=True)
                     for m in refs]
            ref_ids = [t['headers_lc'].get('message-id') for t in trees]
            ref_subjs = [t['headers_lc'].get('subject') for t in trees]
            msg_to = [t['headers_lc'].get('reply-to', t['headers_lc']['from'])
                      for t in trees]
            msg_cc = []
            if reply_all:
                msg_cc += [t['headers_lc'].get('to', '') for t in trees]
                msg_cc += [t['headers_lc'].get('cc', '') for t in trees]
            msg_bodies = []
            for t in trees:
                # FIXME: Templates/settings for how we quote replies?
                text = (('%s wrote:\n' % t['headers_lc']['from']) +
                         ''.join([p['data'] for p in t['text_parts']
                                  if p['type'] in self._TEXT_PARTTYPES]))
                msg_bodies.append(text.replace('\n', '\n> '))

            local_id, lmbox = config.open_local_mailbox(session)
            try:
                email = Email.Create(idx, local_id, lmbox,
                                     msg_text='\n\n'.join(msg_bodies),
                                     msg_subject=('Re: %s' % ref_subjs[-1]),
                                     msg_to=msg_to,
                                     msg_cc=[r for r in msg_cc if r],
                                     msg_references=[i for i in ref_ids if i])
                self._tag_blank([email])

            except NoFromAddressError:
                return self._error('You must configure a From address first.')

            # Behavior tracking
            if 'tags' in config:
                for tag in config.get_tags(type='replied'):
                    idx.add_tag(session, tag._key,
                                msg_idxs=[m.msg_idx_pos for m in refs])

            return self._edit_messages([email])
        else:
            return self._error('No message found')


class Forward(RelativeCompose):
    """Create forwarding drafts of one or more messages"""
    SYNOPSIS = ('f', 'forward', 'message/forward', '[att] <messages>')
    ORDER = ('Composing', 4)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID',
    }
    HTTP_POST_VARS = {}

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        if self.args and self.args[0].lower().startswith('att'):
            with_atts = self.args.pop(0) or True
        else:
            with_atts = False

        refs = [Email(idx, i) for i in self._choose_messages(self.args)]
        if refs:
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
                                 if p['type'] in self._TEXT_PARTTYPES])
                msg_bodies.append(text)
                if with_atts:
                    for att in t['attachments']:
                        if att['mimetype'] not in self._ATT_MIMETYPES:
                            msg_atts.append(att['part'])

            local_id, lmbox = config.open_local_mailbox(session)
            email = Email.Create(idx, local_id, lmbox,
                                 msg_text='\n\n'.join(msg_bodies),
                                 msg_subject=('Fwd: %s' % ref_subjs[-1]))
            if msg_atts:
                msg = email.get_msg()
                for att in msg_atts:
                    msg.attach(att)
                email.update_from_msg(msg)

            # Behavior tracking
            if 'tags' in config:
                for tag in config.get_tags(type='replied'):
                    idx.add_tag(session, tag._key,
                                msg_idxs=[m.msg_idx_pos for m in refs])

            self._tag_blank([email])
            return self._edit_messages([email])
        else:
            return self._error('No message found')


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

        files = []
        filedata = {}
        if 'file-data' in self.data:
            count = 0
            for fd in self.data['file-data']:
                fn = (hasattr(fd, 'filename') and fd.filename
                                               or 'attach-%d.dat' % count)
                filedata[fn] = fd
                files.append(fn)
                count += 1
        else:
            while os.path.exists(self.args[-1]):
                files.append(self.args.pop(-1))

        if not files:
            return self._error('No files found')

        if not emails:
            emails = [Email(idx, i) for i in self._choose_messages(self.args)]
        if not emails:
            return self._error('No messages selected')

        updated = []
        for email in emails:
            subject = email.get_msg_info(MailIndex.MSG_SUBJECT)
            try:
                email.add_attachments(files, filedata=filedata)
                updated.append(email)
            except NotEditableError:
                session.ui.error('Read-only message: %s' % subject)
            except:
                session.ui.error('Error attaching to %s' % subject)
                self._ignore_exception()

        session.ui.notify(('Attached %s to %d messages'
                           ) % (', '.join(files), len(updated)))
        return self._return_search_results(updated, expand=updated)


class Sendit(CompositionCommand):
    """Mail/bounce a message (to someone)"""
    SYNOPSIS = ('m', 'mail', 'message/send', '<messages> [<emails>]')
    ORDER = ('Composing', 5)
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
        'to': 'recipients'
    }

    def command(self, emails=None):
        session, config, idx = self.session, self.session.config, self._idx()

        bounce_to = []
        while self.args and '@' in self.args[-1]:
            bounce_to.append(self.args.pop(-1))
        for rcpt in (self.data.get('to', []) +
                     self.data.get('cc', []) +
                     self.data.get('bcc', [])):
            bounce_to.extend(ExtractEmails(rcpt))

        args = self.args[:]
        if not emails:
            args.extend(['=%s' % mid for mid in self.data.get('mid', [])])
            mids = self._choose_messages(args)
            emails = [Email(idx, i) for i in mids]

        # Process one at a time so we don't eat too much memory
        sent = []
        for email in emails:
            try:
                msg_mid = email.get_msg_info(idx.MSG_MID)
                SendMail(session, [PrepareMail(email,
                                               rcpts=(bounce_to or None))])
                sent.append(email)
            except:
                session.ui.error('Failed to send %s' % email)
                self._ignore_exception()

        if 'compose' in config.sys.debug:
            sys.stderr.write(('compose/Sendit: Send %s to %s (sent: %s)\n'
                              ) % (len(emails),
                                   bounce_to or '(header folks)', sent))

        if sent:
            self._tag_sent(sent)
            self._tag_outbox(sent, untag=True)
            self._tag_drafts(sent, untag=True)
            self._tag_blank(sent, untag=True)
            for email in sent:
                idx.index_email(self.session, email)

            return self._return_search_results(sent, sent=sent)
        else:
            return self._error('Nothing was sent')


class Update(CompositionCommand):
    """Update message from a file or HTTP upload."""
    SYNOPSIS = ('u', 'update', 'message/update', '<messages> <<filename>')
    ORDER = ('Composing', 1)
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_POST_VARS = dict_merge(CompositionCommand.UPDATE_STRING_DATA,
                                Attach.HTTP_POST_VARS)

    def command(self, create=True, outbox=False):
        session, config, idx = self.session, self.session.config, self._idx()
        email_updates = self._get_email_updates(idx)

        if email_updates:
            for email, update_string in email_updates:
                email.update_from_string(update_string)

            if (self.data.get('file-data') or [''])[0]:
                if not Attach(session, data=self.data).command(emails=emails):
                    return False

            emails = [e for e, u in email_updates]
            session.ui.notify('%d message(s) updated' % len(email_updates))

            self._tag_blank(emails, untag=True)
            self._tag_drafts(emails, untag=outbox)
            self._tag_outbox(emails, untag=(not outbox))

            if outbox:
                return self._return_search_results(emails, sent=emails)
            else:
                return self._edit_messages(emails, new=False)
        else:
            return self._error('Nothing to do!')


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
            return self._error('Nothing to do!')


class UpdateAndSendit(Update):
    """Update message from an HTTP upload and move to outbox."""
    SYNOPSIS = (None, None, 'message/update/send', None)

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


mailpile.plugins.register_config_variables('prefs', {
    'empty_outbox_interval': [_('Delay between attempts to send mail'),
                              int, 90]
})
mailpile.plugins.register_slow_periodic_job('sendmail',
                                            'prefs.empty_outbox_interval',
                                            EmptyOutbox.sendmail)
mailpile.plugins.register_commands(Compose, Reply, Forward, # Create
                                   Draft, Update, Attach,   # Manipulate
                                   UnThread,                # ...
                                   Sendit, UpdateAndSendit, # Send
                                   EmptyOutbox)             # ...
