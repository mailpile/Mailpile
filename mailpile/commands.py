#! /usr/bin/env python
#
# These are the Mailpile commands, the public "API" we expose for searching,
# tagging and editing e-mail.
#
# Consulte the COMMANDS dict at the bottom of this file for a list of which
# commands have been defined and what their names and command-line flags are.
#
import os
import os.path
import traceback

import mailpile.util
from mailpile.mailutils import Email, NotEditableError, NoFromAddressError, PrepareMail, SendMail
from mailpile.search import MailIndex, PostingList, GlobalPostingList
from mailpile.util import *

try:
  from GnuPGInterface import GnuPG
except ImportError:
  GnuPG = None


class Command:
  """Generic command object all others inherit from"""
  ORDER = (None, 0)
  SYNOPSIS = None
  SUBCOMMANDS = {}
  FAILURE = 'Failed: %(name)s %(args)s'
  SERIALIZE = False
  SPLIT_ARG = 10000  # A big number!

  def __init__(self, session, name=None, arg=None, data=None):
    self.session = session
    self.name = name
    self.data = data or {}
    if type(arg) in (type(list()), type(tuple())):
      self.args = list(arg)
    elif arg:
      if self.SPLIT_ARG:
        self.args = arg.split(' ', self.SPLIT_ARG)
      else:
        self.args = [arg]
    else:
      self.args = []

  def _idx(self, reset=False, wait=True, quiet=False):
    session, config = self.session, self.session.config
    if not reset and config.index:
      return config.index

    def do_load():
      if reset:
        config.index = None
        session.results = []
        session.searched = []
        session.displayed = (0, 0)
      idx = config.get_index(session)
      idx.update_tag_stats(session, config)
      if not wait:
        session.ui.reset_marks(quiet=quiet)
      return idx
    if wait:
      return config.slow_worker.do(session, 'Load', do_load)
    else:
      config.slow_worker.add_task(session, 'Load', do_load)
      return None

  def _choose_messages(self, words):
    msg_ids = set()
    all_words = []
    for word in words:
      all_words.extend(word.split(','))
    for what in all_words:
      if what.lower() == 'these':
        b, c = session.displayed
        msg_ids |= set(self.session.results[b:b+c])
      elif what.lower() == 'all':
        msg_ids |= set(self.session.results)
      elif what.startswith('='):
        try:
          msg_id = int(what[1:], 36)
          if msg_id >= 0 and msg_id < len(self._idx().INDEX):
            msg_ids.add(msg_id)
          else:
            self.session.ui.warning('ID out of bounds: %s' % (what[1:], ))
        except ValueError:
          self.session.ui.warning('What message is %s?' % (what, ))
      elif '-' in what:
        try:
          b, e = what.split('-')
          msg_ids |= set(self.session.results[int(b)-1:int(e)])
        except:
          self.session.ui.warning('What message is %s?' % (what, ))
      else:
        try:
          msg_ids.add(self.session.results[int(what)-1])
        except:
          self.session.ui.warning('What message is %s?' % (what, ))
    return msg_ids

  def _error(self, message):
    if self.name:
      self.session.ui.reset_marks()
    self.session.ui.error(message)
    return False

  def _read_file_or_data(self, fn):
    if fn in self.data:
      return self.data[fn]
    else:
      return open(fn, 'rb').read()

  def _ignore_exception(self):
    if self.session.config.get('debug'):
      self.session.ui.say(traceback.format_exc())

  def _serialize(self, name, function):
    session, config = self.session, self.session.config
    return config.slow_worker.do(session, name, function)

  def _background(self, name, function):
    session, config = self.session, self.session.config
    return config.slow_worker.add_task(session, name, function)

  def run(self, *args, **kwargs):
    if self.SERIALIZE:
      # Some functions we always run in the slow worker, to make sure
      # they don't get run in parallel with other things.
      return self._serialize(self.SERIALIZE, lambda: self._run(*args, **kwargs))
    else:
      return self._run(*args, **kwargs)

  def _run(self, *args, **kwargs):
    try:
      if self.SUBCOMMANDS and self.args and self.args[0] in self.SUBCOMMANDS:
        subcmd = self.args.pop(0)
        self.name += ' ' + subcmd
        return self.SUBCOMMANDS[subcmd][0](self, *args, **kwargs)
      else:
        return self.command(*args, **kwargs)
    except UsageError:
      raise
    except:
      self._ignore_exception()
      return self._error(self.FAILURE % {'name': self.name,
                                         'args': ' '.join(self.args) })
    finally:
      if self.name:
        self.session.ui.reset_marks()

  def command(self):
    return None


##[ Internals ]###############################################################

class Setup(Command):
  """Perform initial setup"""
  ORDER = ('Internals', 0)
  def command(self):
    session = self.session

    # Create local mailboxes
    session.config.open_local_mailbox(session)

    # Create standard tags and filters
    tags = session.config.get('tag', {}).values()
    for t in ('New', 'Inbox', 'Spam', 'Drafts', 'Sent', 'Trash'):
      if t not in tags:
        Tag(session, 'tag', arg=['add', t]).run()
    if 'New' not in tags:
      Filter(session, arg=['new', '+Inbox', '+New', 'New Mail filter']).run()
      Filter(session, arg=['read', '-New', 'Read Mail filter']).run()

    return True


class Load(Command):
  """Load or reload the metadata index"""
  ORDER = ('Internals', 1)
  def command(self, reset=True, wait=True, quiet=False):
    return self._idx(reset=reset, wait=wait, quiet=quiet)


class Rescan(Command):
  """Scan all mailboxes for new messages"""
  ORDER = ('Internals', 2)
  SERIALIZE = 'Rescan'
  def command(self):
    session, config = self.session, self.session.config

    # FIXME: Need a lock here?
    if 'rescan' in config.RUNNING:
      return True
    config.RUNNING['rescan'] = True

    idx = self._idx()
    count = 0
    rv = True
    try:
      pre_command = config.get('rescan_command', None)
      if pre_command:
        session.ui.mark('Running: %s' % pre_command)
        subprocess.check_call(pre_command, shell=True)
      count = 1
      for fid, fpath in config.get_mailboxes():
        if mailpile.util.QUITTING: break
        count += idx.scan_mailbox(session, fid, fpath, config.open_mailbox)
        config.clear_mbox_cache()
        session.ui.mark('\n')
      count -= 1
      if count:
        if not mailpile.util.QUITTING:
          GlobalPostingList.Optimize(session, idx, quick=True)
      else:
        session.ui.mark('Nothing changed')
    except (KeyboardInterrupt, subprocess.CalledProcessError), e:
      session.ui.mark('Aborted: %s' % e)
      self._ignore_exception()
      return False
    finally:
      if count:
        session.ui.mark('\n')
        if count < 500:
          idx.save_changes(session)
        else:
          idx.save(session)
      del config.RUNNING['rescan']
      idx.update_tag_stats(session, config)
    return True


class Optimize(Command):
  """Optimize the keyword search index"""
  ORDER = ('Internals', 3)
  SYNOPSIS = '[harder]'
  SERIALIZE = 'Optimize'
  def command(self):
    try:
      GlobalPostingList.Optimize(self.session, self._idx(),
                                 force=('harder' in self.args))
      return True
    except KeyboardInterrupt:
      session.ui.mark('Aborted')
      return False


class UpdateStats(Command):
  """Force statistics update"""
  ORDER = ('Internals', 4)
  def command(self):
    session, config = self.session, self.session.config
    idx = config.index
    tags = config.get("tag", {})
    idx.update_tag_stats(session, config, tags.keys())
    session.ui.mark("Statistics updated")
    return True


class RunWWW(Command):
  """Just run the web server"""
  ORDER = ('Internals', 5)
  def command(self):
    self.session.config.prepare_workers(self.session, daemons=True)
    while not mailpile.util.QUITTING: time.sleep(1)
    return True


##[ Tags and Filters ]#########################################################

class Tag(Command):
  """Add/remove/list/edit message tags"""
  ORDER = ('Tagging', 0)
  SYNOPSIS = '<[+|-]tags msgs>'
  def command(self, save=True):
    idx = self._idx()
    words = self.args[:]
    ops = []
    while words and words[0][0] in ('-', '+'):
      ops.append(words.pop(0))
    msg_ids = self._choose_messages(words)
    for op in ops:
      tag_id = self.session.config.get_tag_id(op[1:])
      if op[0] == '-':
        idx.remove_tag(self.session, tag_id, msg_idxs=msg_ids, conversation=True)
      else:
        idx.add_tag(self.session, tag_id, msg_idxs=msg_ids, conversation=True)

    if save:
      # Background save makes things feel fast!
      def background():
        idx.update_tag_stats(self.session, self.session.config)
        idx.save_changes()
      self._background('Save index', background)
    else:
      idx.update_tag_stats(self.session, self.session.config)

    return True

  def add_tag(self):
    config = self.session.config
    existing = [v.lower() for v in config.get('tag', {}).values()]
    for tag in self.args:
      if ' ' in tag:
        return self._error('Invalid tag: %s' % tag)
      if tag.lower() in existing:
        return self._error('Tag already exists: %s' % tag)
    for tag in self.args:
      if config.parse_set(self.session, 'tag:%s=%s' % (config.nid('tag'), tag)):
        self._background('Save config', lambda: config.save())
    return True

  def list_tags(self):
    pass

  SUBCOMMANDS = {
    'add':  (add_tag,   '<tag>'),
    'list': (list_tags, ''),
  }


class Filter(Command):
  """Add/edit/delete/list auto-tagging rules"""
  ORDER = ('Tagging', 1)
  SYNOPSIS = '[new|read] [notag] [=ID] <[+|-]tags ...> [description]'
  def command(self):
    args, session, config = self.args, self.session, self.session.config

    flags = []
    while args and args[0] in ('add', 'set', 'new', 'read', 'notag'):
      flags.append(args.pop(0))

    if args and args[0] and args[0][0] == '=':
      tag_id = args.pop(0)[1:]
    else:
      tag_id = config.nid('filter')

    if 'read' in flags:
      terms = ['@read']
    elif 'new' in flags:
      terms = ['*']
    else:
      terms = session.searched

    if not terms or (len(args) < 1):
      raise UsageError('Need flags and search terms or a hook')

    tags, tids = [], []
    while args and args[0][0] in ('-', '+'):
      tag = args.pop(0)
      tags.append(tag)
      tids.append(tag[0]+config.get_tag_id(tag[1:]))

    if not args:
      args = ['Filter for %s' % ' '.join(tags)]

    if 'notag' not in flags and 'new' not in flags and 'read' not in flags:
      if not Tag(session, 'filter/tag', tags + ['all']).run(save=False):
        raise UsageError()

    if (config.parse_set(session, ('filter:%s=%s'
                                   ) % (tag_id, ' '.join(args)))
    and config.parse_set(session, ('filter_tags:%s=%s'
                                   ) % (tag_id, ' '.join(tids)))
    and config.parse_set(session, ('filter_terms:%s=%s'
                                   ) % (tag_id, ' '.join(terms)))):
      def save_filter():
        config.save()
        if config.index: config.index.save_changes()
        return True
      self._serialize('Save filter', save_filter)
      return True
    else:
      raise Exception('That failed, not sure why?!')

  def rm(self):
    session, config = self.session, self.session.config
    if len(self.args) < 1 or self.args[0] not in config.get('filter', {}):
      raise UsageError('Delete what?')
    fid = self.args[0]
    if (config.parse_unset(session, 'filter:%s' % fid)
    and config.parse_unset(session, 'filter_tags:%s' % fid)
    and config.parse_unset(session, 'filter_terms:%s' % fid)):
      config.save()
    else:
      raise Exception('That failed, not sure why?!')

  def mv(self):
    raise Exception('Unimplemented')

  def ls(self):
    return self.session.ui.print_filters(self.session.config)

  SUBCOMMANDS = {
    'delete': (rm, '<id>'),
    'move':   (mv, '<id> <pos>'),
    'list':   (ls, ''),
  }


##[ Composing e-mail ]#########################################################

class Compose(Command):
  """(Continue) Composing an e-mail"""
  ORDER = ('Composing', 0)
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

    session.ui.edit_messages(emails)
    session.ui.mark('%d message(s) created as drafts' % len(emails))
    return True


class Update(Command):
  """Update message from a file"""
  ORDER = ('Composing', 1)
  SYNOPSIS = '<msg path/to/f>'
  def command(self):
    if len(self.args) > 1:
      session, config, idx = self.session, self.session.config, self._idx()
      update = self._read_file_or_data(self.args.pop(-1))
      emails = [Email(idx, i) for i in self._choose_messages(self.args)]
      for email in emails:
        email.update_from_string(update)
      session.ui.say('%d message(s) updated' % len(emails))
    else:
      return self._error('Nothing to update!')
    return True


class Attach(Command):
  """Attach a file to a message"""
  ORDER = ('Composing', 2)
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
    session.ui.say('Attaching %s to...' % ', '.join(files))
    for email in emails:
      subject = email.get_msg_info(MailIndex.MSG_SUBJECT)
      try:
        email.add_attachments(files)
        session.ui.say(' - %s' % subject)
      except NotEditableError:
        session.ui.error('Read-only message: %s' % subject)
      except:
        session.ui.error('Error attaching to %s' % subject)
        self._ignore_exception()

    return True


class Reply(Command):
  """Reply(-all) to one or more messages"""
  ORDER = ('Composing', 3)
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

      if session.interactive:
        session.ui.edit_messages([email])
      else:
        session.ui.say('Message created as draft')
        session.ui.reset_marks()
      return True
    else:
      return self._error('No message found')


class Forward(Command):
  """Forward messages (and attachments)"""
  ORDER = ('Composing', 4)
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

      if session.interactive:
        session.ui.edit_messages([email])
      else:
        session.ui.say('Message created as draft')
      return True
    else:
      return self._error('No message found')


class Mail(Command):
  """Mail/bounce a message (to someone)"""
  ORDER = ('Composing', 5)
  SYNOPSIS = '<msg [email]>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()

    bounce_to = []
    while self.args and '@' in self.args[-1]:
      bounce_to.append(self.args.pop(-1))

    # Process one at a time so we don't eat too much memory
    for email in [Email(idx, i) for i in self._choose_messages(self.args)]:
      try:
        msg_idx = email.get_msg_info(idx.MSG_IDX)
        SendMail(session, [PrepareMail(email, rcpts=(bounce_to or None))])
        Tag(session, arg=['-Drafts', '+Sent', '=%s'% msg_idx]).run()
      except:
        session.ui.error('Failed to send %s' % email)
        self._ignore_exception()

    return True


##[ Searching and browsing ]##################################################

class Search(Command):
  """Search your mail!"""
  ORDER = ('Searching', 0)
  SYNOPSIS = '<terms ...>'
  def command(self, search=None):
    session, config, idx = self.session, self.session.config, self._idx()
    session.searched = search or []
    num_results = config.get('num_results', None)

    if self.args and self.args[0].startswith('@'):
      try:
        start = int(self.args.pop(0)[1:])-1
      except ValueError:
        raise UsageError('Weird starting point')
    else:
      start = 0

    # FIXME: Is this dumb?
    for arg in self.args:
      if ':' in arg or (arg and arg[0] in ('-', '+')):
        session.searched.append(arg.lower())
      else:
        session.searched.extend(re.findall(WORD_REGEXP, arg.lower()))

    session.results = list(idx.search(session, session.searched))
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   start=start,
                                                   num=num_results)
    return True


class Next(Command):
  """Display next page of results"""
  ORDER = ('Searching', 1)
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    num_results = config.get('num_results', None)
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   start=pos+count,
                                                   num=num_results)
    return True


class Previous(Command):
  """Display previous page of results"""
  ORDER = ('Searching', 2)
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    num_results = config.get('num_results', None)
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   end=pos,
                                                   num=num_results)
    return True


class Order(Command):
  """Sort by: date, from, subject, random or index"""
  ORDER = ('Searching', 3)
  SYNOPSIS = '<terms ...>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    num_results = config.get('num_results', None)
    session.order = self.args and self.args[0] or None
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   num=num_results)
    return True


class View(Command):
  """View one or more messages"""
  ORDER = ('Searching', 4)
  SYNOPSIS = '<[raw] m1 ...>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    if self.args and self.args[0].lower() == 'raw':
      raw = self.args.pop(0)
    else:
      raw = False
    emails = [Email(idx, i) for i in self._choose_messages(self.args)]
    if emails:
      idx.apply_filters(session, '@read', msg_idxs=[e.msg_idx for e in emails])
      session.ui.clear()
      session.ui.display_messages(emails, raw=raw)
    return True


class Extract(Command):
  """Extract attachment(s) to file(s)"""
  ORDER = ('Searching', 5)
  SYNOPSIS = '<att msg [>fn]>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    cid = self.args.pop(0)
    if len(self.args) > 0 and self.args[-1].startswith('>'):
      name_fmt = self.args.pop(-1)[1:]
    else:
      name_fmt = None
    emails = [Email(idx, i) for i in self._choose_messages(self.args)]
    for email in emails:
      email.extract_attachment(session, cid, name_fmt=name_fmt)
    return True


class Delete(Command):
  """Delete a message from the index"""
  ORDER = ('Searching', 6)
  SYNOPSIS = '<msg>'
  def command(self):
    session, config, idx = self.session, self.session.config, self._idx()
    raise Exception('Unimplemented')


##[ Configuration commands ]###################################################

class ConfigSet(Command):
  """Change a setting"""
  ORDER = ('Config', 1)
  SYNOPSIS = '<var=value>'
  SPLIT_ARG = False
  def command(self):
    session, config = self.session, self.session.config
    if config.parse_set(session, self.args[0]):
      self._serialize('Save config', lambda: config.save())
    return True


class ConfigUnset(Command):
  """Reset a setting to the default"""
  ORDER = ('Config', 2)
  SYNOPSIS = '<var>'
  SPLIT_ARG = False
  def command(self):
    session, config = self.session, self.session.config
    if config.parse_unset(session, self.args[0]):
      self._serialize('Save config', lambda: config.save())
    return True


class ConfigPrint(Command):
  """Print a setting"""
  ORDER = ('Config', 3)
  SYNOPSIS = '<var>'
  SPLIT_ARG = False
  def command(self):
    self.session.ui.print_key(self.args[0].strip().lower(),
                              self.session.config)
    return True


class AddMailbox(Command):
  """Add a mailbox"""
  ORDER = ('Config', 4)
  SYNOPSIS = '</path/to/mbx>'
  SPLIT_ARG = False
  def command(self):
    session, config, raw_fn = self.session, self.session.config, self.args[0]
    fn = os.path.expanduser(raw_fn)
    if fn in config.get('mailbox', {}).values():
      session.ui.warning('Already in the pile: %s' % fn)
    else:
      if os.path.exists(fn):
        arg = os.path.abspath(fn)
        if config.parse_set(session,
                            'mailbox:%s=%s' % (config.nid('mailbox'), fn)):
          self._serialize('Save config', lambda: config.save())
      else:
        return self._error('No such file/directory: %s' % raw_fn)
    return True


class GPG(Command):
  """GPG commands"""
  ORDER = ('Config', 5)
  def command(self):
    raise Exception('FIXME: Should print instructions')

  def recv_key(self):
    session, config, arg = self.session, self.session.config, self.args[0]
    try:
      session.ui.mark('Invoking GPG to fetch key %s' % arg)
      keyserver = config.get('gpg_keyserver', 'pool.sks-keyservers.net')
      gpg = GnuPG().run(['--utf8-strings',
                         '--keyserver', keyserver,
                         '--recv-key', arg], create_fhs=['stderr'])
      session.ui.say(gpg.handles['stderr'].read().decode('utf-8'))
      gpg.handles['stderr'].close()
      gpg.wait()
      session.ui.mark('Done')
    except IOError:
      return self._error('Failed to fetch key %s' % arg)
    return True

  def list_keys(self):
    session, config = self.session, self.session.config
    keys = []
    try:
      session.ui.mark('Listing available GPG keys')
      gpg = GnuPG().run(['--list-keys'], create_fhs=['stderr', 'stdout'])
      keylines = gpg.handles['stdout'].readlines()
      curkey = {}
      for line in keylines:
        if line[0:3] == "pub":
          if curkey != {}:
            keys.append(curkey)
            curkey = {}
          args = line.split("pub")[1].strip().split(" ")
          if len(args) == 3:
            expiry = args[2]
          else:
            expiry = None
          keytype, keyid = args[0].split("/")
          created = args[1]
          curkey["subkeys"] = []
          curkey["uids"] = []
          curkey["pub"] = {"keyid": keyid, "type": keytype, "created": created, "expires": expiry}
        elif line[0:3] == "sec":
          if curkey != {}:
            keys.append(curkey)
            curkey = {}
          args = line.split("pub")[1].strip().split(" ")
          if len(args) == 3:
            expiry = args[2]
          else:
            expiry = None
          keytype, keyid = args[0].split("/")
          created = args[1]
          curkey["subkeys"] = []
          curkey["uids"] = []
          curkey["sec"] = {"keyid": keyid, "type": keytype, "created": created, "expires": expiry}
        elif line[0:3] == "uid":
          curkey["uids"].append(line.split("uid")[1].strip())
        elif line[0:3] == "sub":
          args = line.split("sub")[1].strip().split(" ")
          if len(args) == 3:
            expiry = args[2]
          else:
            expiry = None
          keytype, keyid = args[0].split("/")
          created = args[1]
          curkey["subkeys"].append({"keyid": keyid, "type": keytype, "created": created, "expires": expiry})
      gpg.handles['stderr'].close()
      gpg.handles['stdout'].close()
      gpg.wait()
      session.ui.display_gpg_keys(keys)
    except IndexError, e:
      self._ignore_exception()
    except IOError:
      return False
    return True

  SUBCOMMANDS = {
    'recv': (recv_key, '<key-ID>'),
    'list': (list_keys, '')
  }


###############################################################################

class Help(Command):
  """Print help on Mailpile or individual commands."""
  ORDER = ('Config', 9)
  def command(self):
    if self.args:
      raise Exception('FIXME: Per-command help is missing')
    else:
      cmd_list = {}
      count = 0
      for grp in COMMAND_GROUPS:
        count += 10
        for c in COMMANDS:
          name, cls = COMMANDS[c]
          if cls.ORDER[0] == grp:
            cmd_list[c] = (name, cls.SYNOPSIS, cls.__doc__, count+cls.ORDER[1])
      self.session.ui.print_help(cmd_list,
                                 tags=self.session.config.get('tag', {}),
                                 index=self._idx())
    return True

  def help_vars(self):
    self.session.ui.print_variable_help(self.session.config)
    return True

  SUBCOMMANDS = {
    'variables': (help_vars, ''),
  }


def Action(session, opt, arg, data=None):
  session.ui.reset_marks(quiet=True)
  config = session.config

  if session.config.get('debug'):
    session.ui.say('Running: %s "%s" data=%s' % (opt, arg, data))

  if not opt:
    return Help(session, 'help').run()

  # Use the COMMANDS dict by default.
  if len(opt) == 1:
    if opt in COMMANDS:
      return COMMANDS[opt][1](session, opt, arg, data=data).run()
    elif opt+':' in COMMANDS:
      return COMMANDS[opt+':'][1](session, opt, arg, data=data).run()
  for name, cls in COMMANDS.values():
    if opt == name or opt == name[:-1]:
      return cls(session, opt, arg, data=data).run()

  # Backwards compatibility
  if opt == 'addtag':
    return Tag(session, 'tag', ['add'] + arg.split()).run()
  elif opt == 'gpgrecv':
    return GPG(session, 'gpg', ['recv'] + arg.split()).run()

  # Tags are commands
  elif opt.lower() in [t.lower() for t in config.get('tag', {}).values()]:
    tid = config.get_tag_id(opt)
    return Search(session, opt, arg, data=data).run(search=['tag:%s' % tid[0]])

  # OK, give up!
  raise UsageError('Unknown command: %s' % opt)

# Commands starting with _ don't get single-letter shortcodes...
COMMANDS = {
  '_setup': ('setup',    Setup),
  'A:':     ('add=',     AddMailbox),
  'a:':     ('attach=',  Attach),
  'c:':     ('compose=', Compose),
  'd:':     ('delete=',  Delete),
  'e:':     ('extract=', Extract),
  'F:':     ('filter=',  Filter),
  'h':      ('help',     Help),
  '_load':  ('load',     Load),
  'm:':     ('mail=',    Mail),
  'f:':     ('forward=', Forward),
  'n':      ('next',     Next),
  'o:':     ('order=',   Order),
  '_optim': ('optimize', Optimize),
  'p':      ('previous', Previous),
  'P:':     ('print=',   ConfigPrint),
  'r:':     ('reply=',   Reply),
  '_resca': ('rescan',   Rescan),
  'g:':     ('gpg',      GPG),
  's:':     ('search=',  Search),
  'S:':     ('set=',     ConfigSet),
  't:':     ('tag=',     Tag),
  'U:':     ('unset=',   ConfigUnset),
  'u:':     ('update=',  Update),
  'v:':     ('view=',    View),
  '_www':   ('www',      RunWWW),
  '_recou': ('recount',  UpdateStats)
}
COMMAND_GROUPS = ['Internals', 'Config', 'Searching', 'Tagging', 'Composing']

