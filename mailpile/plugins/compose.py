import datetime
import os
import os.path
import re
import traceback

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

    def _prune_msg_tree(self, *args, **kwargs):
        kwargs['editable'] = True
        return SearchResults._prune_msg_tree(self, *args, **kwargs)


class CompositionCommand(Search):
    UPDATE_STRING_DATA = {
        'mid': 'metadata-ID',
        'subject': '..',
        'from': '..',
        'to': '..',
        'cc': '..',
        'bcc': '..',
        'body': '..',
        'send': 'Send the message?',
    }
    BLANK_TAG = 'Blank'
    DRAFT_TAG = 'Drafts'
    SENT_TAG = 'Sent'

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

    def _get_emails_and_update_string(self, idx):
        # Split the argument list into files and message IDs
        files = [f[1:].strip() for f in self.args if f.startswith('<')]
        args = [a for a in self.args if not a.startswith('<')]

        # Message IDs can come from post data
        for mid in self.data.get('mid', []):
            args.append('=%s' % mid)
        emails = [Email(idx, mid) for mid in self._choose_messages(args)]

        # If we don't have a file, check for posted data
        if len(files) > 1:
            return (self._error('Cannot update from multiple files'), None)
        elif len(files) == 1:
            update_string = self._read_file_or_data(files[0])
        elif 'from' in self.data:
            # No file name, construct an update string from the POST data.
            update_string = '\n'.join([
                '\n'.join(['%s: %s' % (s, ', '.join(self.data.get(s, [''])))
                           for s in ('subject', 'from', 'to', 'cc', 'bcc')]),
                '',
                '\n'.join(self.data.get('body', ['']))
            ])
        else:
            update_string = False

        return (emails, update_string)

    def _return_search_results(self, emails, expand=None, new=[], sent=[]):
        session, idx = self.session, self._idx()
        session.results = [e.msg_idx_pos for e in emails]
        session.displayed = EditableSearchResults(session, idx, new, sent,
                                                  results=session.results,
                                                  num=len(emails),
                                                  expand=expand)
        return [session.displayed]

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
        session, idx = self.session, self._idx()
        emails, update_string = self._get_emails_and_update_string(idx)

        if emails:
            return self._error('Please use update for editing messages')

        else:
            local_id, lmbox = session.config.open_local_mailbox(session)
            emails = [Email.Create(idx, local_id, lmbox)]
            if self.BLANK_TAG:
                self._tag_emails(emails, self.BLANK_TAG)
            if update_string:
                for email in emails:
                    email.update_from_string(update_string)
            return self._edit_messages(emails, new=True)


class Update(CompositionCommand):
    """Update message from a file or HTTP upload."""
    SYNOPSIS = ('u', 'update', 'message/update', '<messages> <<filename>')
    ORDER = ('Composing', 1)
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_POST_VARS = CompositionCommand.UPDATE_STRING_DATA

    def command(self, create=True):
        session, config, idx = self.session, self.session.config, self._idx()
        emails, update_string = self._get_emails_and_update_string(idx)

        if emails and update_string:
            print 'HMM: %s / %s' % (self.data, emails)
            for email in emails:
                email.update_from_string(update_string)
            session.ui.notify('%d message(s) updated' % len(emails))
            if self.BLANK_TAG:
                self._untag_emails(emails, self.BLANK_TAG)
            if self.DRAFT_TAG:
                self._tag_emails(emails, self.DRAFT_TAG)
            return self._edit_messages(emails, new=False)

        else:
            return self._error('Nothing to do!')


class Attach(CompositionCommand):
    """Attach a file to a message"""
    SYNOPSIS = ('a', 'attach', 'message/attach', '<messages> [<path/to/file>]')
    ORDER = ('Composing', 2)
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
        'data': 'file data',
        'name': 'file name'
    }

    def command(self):
        session, idx = self.session, self._idx()

        files = []
        while os.path.exists(self.args[-1]):
            files.append(self.args.pop(-1))
        if not files:
            return self._error('No files found')

        emails = [Email(idx, i) for i in self._choose_messages(self.args)]
        if not emails:
            return self._error('No messages selected')

        # FIXME: Using "say" here is rather lame.
        updated = []
        for email in emails:
            subject = email.get_msg_info(MailIndex.MSG_SUBJECT)
            try:
                email.add_attachments(files)
                updated.append(email)
            except NotEditableError:
                session.ui.error('Read-only message: %s' % subject)
            except:
                session.ui.error('Error attaching to %s' % subject)
                self._ignore_exception()

        session.ui.notify(('Attached %s to %d messages'
                           ) % (', '.join(files), len(updated)))
        return self._return_search_results(updated, expand=updated)


class RelativeCompose(Compose):
    _ATT_MIMETYPES = ('application/pgp-signature', )
    _TEXT_PARTTYPES = ('text', 'quote', 'pgpsignedtext', 'pgpsecuretext',
                       'pgpverifiedtext')


class Reply(RelativeCompose):
    """Reply(-all) to one or more messages"""
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
                if self.BLANK_TAG:
                    self._tag_emails([email], self.BLANK_TAG)

            except NoFromAddressError:
                return self._error('You must configure a From address first.')

            return self._edit_messages([email])
        else:
            return self._error('No message found')


class Forward(RelativeCompose):
    """Forward messages (and attachments)"""
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

            if self.BLANK_TAG:
                self._tag_emails([email], self.BLANK_TAG)

            return self._edit_messages([email])
        else:
            return self._error('No message found')


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

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        bounce_to = []
        while self.args and '@' in self.args[-1]:
            bounce_to.append(self.args.pop(-1))
        for rcpt in (self.data.get('to', []) +
                     self.data.get('cc', []) +
                     self.data.get('bcc', [])):
            bounce_to.extend(ExtractEmails(rcpt))

        args = self.args[:]
        args.extend(['=%s' % mid for mid in self.data.get('mid', [])])
        mids = self._choose_messages(args)

        # Process one at a time so we don't eat too much memory
        sent = []
        for email in [Email(idx, i) for i in mids]:
            try:
                msg_mid = email.get_msg_info(idx.MSG_MID)
                SendMail(session, [PrepareMail(email,
                                               rcpts=(bounce_to or None))])
                sent.append(email)
            except:
                session.ui.error('Failed to send %s' % email)
                self._ignore_exception()

        if 'compose' in config.get('debug', ''):
            sys.stderr.write(('compose/Sendit: Send %s to %s (sent: %s)\n'
                              ) % (mids, bounce_to or '(header folks)', sent))

        if sent:
            if self.BLANK_TAG:
                self._untag_emails(sent, self.BLANK_TAG)
            if self.DRAFT_TAG:
                self._untag_emails(sent, self.DRAFT_TAG)
            if self.SENT_TAG:
                self._tag_emails(sent, self.SENT_TAG)
            return self._return_search_results(sent, sent=sent)
        else:
            return self._error('Nothing was sent')


mailpile.plugins.register_commands(Compose, Reply, Forward, # Create
                                   Draft, Update, Attach,   # Manipulate
                                   Sendit)                  # Send
