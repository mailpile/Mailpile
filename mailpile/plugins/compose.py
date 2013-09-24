import datetime
import os
import os.path
import re
import traceback

import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import Email
from mailpile.search import MailIndex
from mailpile.urlmap import UrlMap
from mailpile.util import *

from mailpile.plugins.search import Search, SearchResults


class EditableSearchResults(SearchResults):
    def __init__(self, session, idx, new_messages, **kwargs):
        SearchResults.__init__(self, session, idx, *kwargs)
        self.new_messages = new_messages

    def _prune_msg_tree(self, *args, **kwargs):
        kwargs['editable'] = True
        return SearchResults._prune_msg_tree(self, *args, **kwargs)


class ReturnsSearchResults(Search):
    class CommandResult(Search.CommandResult):
        def as_html(self, *args, **kwargs):
            for result in (self.result or []):
                if result.new_messages:
                    mid = b36(result.new_messages[0].msg_idx)
                    url = UrlMap(self.session).url_compose(mid)
                    raise UrlRedirectException(url)
            return Search.CommandResult.as_html(self, *args, **kwargs)

    def _return_search_results(self, session, idx, emails,
                                     expand=None, new=[]):
        session.results = [e.msg_idx for e in emails]
        session.displayed = EditableSearchResults(session, idx, new,
                                                  num=len(emails),
                                                  expand=expand)
        return [session.displayed]


class Compose(ReturnsSearchResults):
    """(Continue) Composing an e-mail"""
    SYNOPSIS = ('C', 'compose', 'message/compose', '[<messages>]')
    ORDER = ('Composing', 0)
    HTTP_QUERY_VARS = {
        'mid': 'metadata-ID',
    }
    HTTP_POST_VARS = {}
    RAISES = (UrlRedirectException, )

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        if self.args:
            emails = [Email(idx, i) for i in self._choose_messages(self.args)]
            return self._edit_messages(session, idx, emails, new=False)
        else:
            local_id, lmbox = config.open_local_mailbox(session)
            emails = [Email.Create(idx, local_id, lmbox)]
            try:
                idxs = [int(e.get_msg_info(idx.MSG_IDX), 36) for e in emails]
                idx.add_tag(session, session.config.get_tag_id('Drafts'),
                            msg_idxs=idxs, conversation=False)
            except (TypeError, ValueError, IndexError):
                self._ignore_exception()
            return self._edit_messages(session, idx, emails)

    def _edit_messages(self, session, idx, emails, new=True):
        session.ui.edit_messages(emails)
        if new:
          session.ui.mark('%d message(s) created as drafts' % len(emails))
        else:
          session.ui.mark('%d message(s) edited' % len(emails))
        self._idx().save()
        return self._return_search_results(session, idx, emails, emails,
                                           new=(new and emails))


class Update(ReturnsSearchResults):
    """Update message from a file or HTTP upload."""
    SYNOPSIS = ('u', 'update', 'message/update', '<messages> <path/to/update>')
    ORDER = ('Composing', 1)
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_QUERY_VARS = {}
    HTTP_POST_VARS = {
        'mid': 'metadata-ID',
        'subject': '..',
        'from': '..',
        'to': '..',
        'cc': '..',
        'bcc': '..',
        'body': '..',
    }

    def command(self):
        if len(self.args) > 1:
            session, idx = self.session, self._idx()
            update = self._read_file_or_data(self.args.pop(-1))
            emails = [Email(idx, i) for i in self._choose_messages(self.args)]
            for email in emails:
                email.update_from_string(update)
            session.ui.notify('%d message(s) updated' % len(emails))
            return self._return_search_results(session, idx, emails, emails)
        else:
            return self._error('Nothing to update!')


class Attach(ReturnsSearchResults):
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
        return self._return_search_results(session, idx, updated, updated)


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
                try:
                    msg_idx = int(email.get_msg_info(idx.MSG_IDX), 36)
                    idx.add_tag(session, session.config.get_tag_id('Drafts'),
                                msg_idxs=[msg_idx], conversation=False)
                except (TypeError, ValueError, IndexError):
                    self._ignore_exception()

            except NoFromAddressError:
                return self._error('You must configure a From address first.')

            return self._edit_messages(session, idx, [email])
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

            try:
                msg_idx = int(email.get_msg_info(idx.MSG_IDX), 36)
                idx.add_tag(session, session.config.get_tag_id('Drafts'),
                            msg_idxs=[msg_idx], conversation=False)
            except (TypeError, ValueError, IndexError):
                self._ignore_exception()

            return self._edit_messages(session, idx, [email])
        else:
            return self._error('No message found')


class Sendit(ReturnsSearchResults):
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

        # Process one at a time so we don't eat too much memory
        sent = []
        for email in [Email(idx, i) for i in self._choose_messages(self.args)]:
            try:
                msg_idx = email.get_msg_info(idx.MSG_IDX)
                SendMail(session, [PrepareMail(email,
                                               rcpts=(bounce_to or None))])
                Tag(session, arg=['-Drafts', '+Sent', '=%s' % msg_idx]).run()
                sent.append(email)
            except:
                session.ui.error('Failed to send %s' % email)
                self._ignore_exception()

        return self._return_search_results(session, idx, sent)


mailpile.plugins.register_commands(Compose, Update, Attach,
                                   Reply, Forward, Sendit)
