import datetime
import os
import os.path
import re
import traceback

import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import Email
from mailpile.search import MailIndex
from mailpile.util import *

from mailpile.plugins.search import Search, SearchResults


class EditableSearchResults(SearchResults):
  def _prune_msg_tree(self, *args, **kwargs):
    kwargs['editable'] = True
    return SearchResults._prune_msg_tree(self, *args, **kwargs)


class ReturnsSearchResults(Search):
  def _return_search_results(self, session, idx, emails, expand=None):
    session.results = [e.msg_idx for e in emails]
    session.displayed = EditableSearchResults(session, idx,
                                              num=len(emails), expand=expand)
    return [session.displayed]


class Compose(ReturnsSearchResults):
  """(Continue) Composing an e-mail"""
  ORDER = ('Composing', 0)
  TEMPLATE_IDS = ['compose'] + Search.TEMPLATE_IDS

  SYNOPSIS = '<[msg]>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    if self.args:
      emails = [Email(idx, i) for i in self._choose_messages(self.args)]
    else:
      local_id, lmbox = config.open_local_mailbox(session)
      emails = [Email.Create(idx, local_id, lmbox)]
      try:
        msg_idxs = [int(e.get_msg_info(idx.MSG_IDX), 36) for e in emails]
        idx.add_tag(session, session.config.get_tag_id('Drafts'),
                    msg_idxs=msg_idxs, conversation=False)
      except (TypeError, ValueError, IndexError):
        self._ignore_exception()

    return self._edit_new_messages(session, idx, emails)

  def _edit_new_messages(self, session, idx, emails):
    session.ui.edit_messages(emails)
    session.ui.mark('%d message(s) created as drafts' % len(emails))
    return self._return_search_results(session, idx, emails, emails)


class Update(ReturnsSearchResults):
  """Update message from a file"""
  ORDER = ('Composing', 1)
  TEMPLATE_IDS = ['update'] + Compose.TEMPLATE_IDS

  SYNOPSIS = '<msg path/to/f>'
  def command(self):
    if len(self.args) > 1:
      session, config, idx = self.session, self.session.config, self._idx()
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
  ORDER = ('Composing', 2)
  TEMPLATE_IDS = ['attach'] + Compose.TEMPLATE_IDS

  SYNOPSIS = '<msg path/to/f>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()

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


class Reply(Compose):
  """Reply(-all) to one or more messages"""
  ORDER = ('Composing', 3)
  TEMPLATE_IDS = ['reply'] + Compose.TEMPLATE_IDS

  SYNOPSIS = '<[all] m1 ...>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()

    if self.args and self.args[0].lower() == 'all':
      reply_all = self.args.pop(0) or True
    else:
      reply_all = False

    refs = [Email(idx, i) for i in self._choose_messages(self.args)]
    if refs:
      trees = [m.evaluate_pgp(m.get_message_tree(), decrypt=True) for m in refs]
      ref_ids = [t['headers_lc'].get('message-id') for t in trees]
      ref_subjs = [t['headers_lc'].get('subject') for t in trees]
      msg_to = [t['headers_lc'].get('reply-to',
                                    t['headers_lc']['from']) for t in trees]
      msg_cc = []
      if reply_all:
        msg_cc += [t['headers_lc'].get('to', '') for t in trees]
        msg_cc += [t['headers_lc'].get('cc', '') for t in trees]
      msg_bodies = []
      for t in trees:
        # FIXME: Templates/settings for how we quote replies?
        text = (('%s wrote:\n' % t['headers_lc']['from']) +
                 ''.join([p['data'] for p in t['text_parts']
                          if p['type'] in ('text', 'quote',
                                           'pgpsignedtext',
                                           'pgpsecuretext',
                                           'pgpverifiedtext')]))
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
          idx.add_tag(session, session.config.get_tag_id('Drafts'),
                      msg_idxs=[int(email.get_msg_info(idx.MSG_IDX), 36)],
                      conversation=False)
        except (TypeError, ValueError, IndexError):
          self._ignore_exception()

      except NoFromAddressError:
        return self._error('You must configure a From address first.')

      return self._edit_new_messages(session, idx, [email])
    else:
      return self._error('No message found')


class Forward(Compose):
  """Forward messages (and attachments)"""
  ORDER = ('Composing', 4)
  TEMPLATE_IDS = ['forward'] + Compose.TEMPLATE_IDS

  SYNOPSIS = '<[att] m1 ...>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()

    if self.args and self.args[0].lower().startswith('att'):
      with_atts = self.args.pop(0) or True
    else:
      with_atts = False

    refs = [Email(idx, i) for i in self._choose_messages(self.args)]
    if refs:
      trees = [m.evaluate_pgp(m.get_message_tree(), decrypt=True) for m in refs]
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
                         if p['type'] in ('text', 'quote',
                                          'pgpsignedtext',
                                          'pgpsecuretext',
                                          'pgpverifiedtext')])
        msg_bodies.append(text)
        if with_atts:
          for att in t['attachments']:
            if att['mimetype'] not in ('application/pgp-signature', ):
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
        idx.add_tag(session, session.config.get_tag_id('Drafts'),
                    msg_idxs=[int(email.get_msg_info(idx.MSG_IDX), 36)],
                    conversation=False)
      except (TypeError, ValueError, IndexError):
        self._ignore_exception()

      return self._edit_new_messages(session, idx, [email])
    else:
      return self._error('No message found')


class Mail(ReturnsSearchResults):
  """Mail/bounce a message (to someone)"""
  ORDER = ('Composing', 5)
  TEMPLATE_IDS = ['mail']

  SYNOPSIS = '<msg [email]>'
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
        SendMail(session, [PrepareMail(email, rcpts=(bounce_to or None))])
        Tag(session, arg=['-Drafts', '+Sent', '=%s'% msg_idx]).run()
        sent.append(email)
      except:
        session.ui.error('Failed to send %s' % email)
        self._ignore_exception()

    return self._return_search_results(session, idx, sent)


mailpile.plugins.register_command('a:', 'attach=',  Attach)
mailpile.plugins.register_command('c:', 'compose=', Compose)
mailpile.plugins.register_command('f:', 'forward=', Forward)
mailpile.plugins.register_command('m:', 'mail=',    Mail)
mailpile.plugins.register_command('r:', 'reply=',   Reply)
mailpile.plugins.register_command('u:', 'update=',  Update)
