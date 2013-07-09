#!/usr/bin/env python
#
# These are the Mailpile commands, the public "API" we expose for searching,
# tagging and editing e-mail.
#
# Consulte the COMMANDS dict at the bottom of this file for a list of which
# commands have been defined and what their names and command-line flags are.
#
import datetime
import os
import os.path
import re
import traceback

import mailpile.util
import mailpile.ui
from mailpile.mailutils import Email, ExtractEmails, NotEditableError, NoFromAddressError, PrepareMail, SendMail
from mailpile.search import MailIndex, PostingList, GlobalPostingList
from mailpile.util import *

try:
  from GnuPGInterface import GnuPG
except ImportError:
  GnuPG = None


class Command:
  """Generic command object all others inherit from"""
  EXAMPLES = None
  FAILURE = 'Failed: %(name)s %(args)s'
  IS_HELP = False
  ORDER = (None, 0)
  SERIALIZE = False
  SPLIT_ARG = 10000  # A big number!
  SUBCOMMANDS = {}
  SYNOPSIS = None
  TEMPLATE_ID = 'command'

  class CommandResult:
    def __init__(self, session, command, template_id, doc, result):
      self.session = session
      self.command = command
      self.template_id = template_id
      self.doc = doc
      self.result = result

    def __nonzero__(self):
      return self.result.__nonzero__()

    def as_text(self):
      if type(self.result) == type(True):
        return '%s: %s' % (self.result and 'Succeeded' or 'Failed', self.doc)
      return unicode(self.result)
    __str__ = lambda self: self.as_text()
    __unicode__ = lambda self: self.as_text()

    def as_dict(self):
      return {
        'command': self.command,
        'result': self.result,
        'elapsed': '%.3f' % self.session.ui.time_elapsed
      }

    def as_html(self):
      return self.session.ui.render_html(self.session.config,
                                         'html/%s' % self.template_id,
                                         self.as_dict())

    def as_json(self):
      return self.session.ui.render_json(self.as_dict())

  def __init__(self, session, name=None, arg=None, data=None):
    self.session = session
    self.serialize = self.SERIALIZE
    self.template_id = self.TEMPLATE_ID
    self.name = name
    self.data = data or {}
    self.result = None
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

    def __do_load():
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
      return config.slow_worker.do(session, 'Load', __do_load)
    else:
      config.slow_worker.add_task(session, 'Load', __do_load)
      return None

  def _choose_messages(self, words):
    msg_ids = set()
    all_words = []
    for word in words:
      all_words.extend(word.split(','))
    for what in all_words:
      if what.lower() == 'these':
        b, c = self.session.displayed
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
    self.session.ui.error(message)
    return False

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

  def _starting(self):
    if self.name:
      self.session.ui.start_command(self.name, self.args, self.data)

  def _finishing(self, command, rv):
    if self.name:
       self.session.ui.finish_command()
    return self.CommandResult(self.session, self.name, self.template_id,
                              command.__doc__ or self.__doc__, rv)

  def _run(self, *args, **kwargs):
    try:
      def command(self, *args, **kwargs):
        return self.command(*args, **kwargs)
      if self.SUBCOMMANDS and self.args and self.args[0] in self.SUBCOMMANDS:
        subcmd = self.args.pop(0)
        self.template_id += '_' + subcmd
        if self.name:
          self.name += ' ' + subcmd
        command = self.SUBCOMMANDS[subcmd][0]
      elif self.SUBCOMMANDS and self.args and self.args[0] == 'help':
        if not self.IS_HELP:
          return Help(self.session, arg=[self.name]).run()
      self._starting()
      return self._finishing(command, command(self, *args, **kwargs))
    except UsageError:
      raise
    except:
      self._ignore_exception()
      self._error(self.FAILURE % {'name': self.name,
                                  'args': ' '.join(self.args) })
      return self._finishing(command, False)

  def run(self, *args, **kwargs):
    if self.serialize:
      # Some functions we always run in the slow worker, to make sure
      # they don't get run in parallel with other things.
      return self._serialize(self.serialize, lambda: self._run(*args, **kwargs))
    else:
      return self._run(*args, **kwargs)

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
        Tag(session, arg=['add', t]).run()
    if 'New' not in tags:
      Filter(session, arg=['new', '+Inbox', '+New', 'New Mail filter']).run()
      Filter(session, arg=['read', '-New', 'Read Mail filter']).run()

    return True


class Load(Command):
  """Load or reload the metadata index"""
  ORDER = ('Internals', 1)
  def command(self, reset=True, wait=True, quiet=False):
    return self._idx(reset=reset, wait=wait, quiet=quiet) and True or False


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
  SERIALIZE = 'Optimize'
  SYNOPSIS = '[harder]'
  def command(self):
    try:
      GlobalPostingList.Optimize(self.session, self._idx(),
                                 force=('harder' in self.args))
      return True
    except KeyboardInterrupt:
      self.session.ui.mark('Aborted')
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
    while not mailpile.util.QUITTING:
      time.sleep(1)
    return True


##[ Tags, Filters, Contacts, Groups, ... ]#####################################

class Tag(Command):
  """Add/remove/list/edit message tags"""
  ORDER = ('Tagging', 0)
  TEMPLATE_ID = 'tag'

  class CommandResult(Command.CommandResult):
    def _tags_as_text(self):
      tags = self.result['tags']
      wrap = int(78/23) # FIXME: Magic number
      text = []
      for i in range(0, len(tags)):
        text.append(('%s%5.5s %-18.18s'
                     ) % ((i%wrap) == 0 and '  ' or '',
                     '%s' % (tags[i]['new'] or ''),
                     tags[i]['name'])
                   + ((i%wrap)==(wrap-1) and '\n' or ''))
      return ''.join(text)+'\n'
    def _added_as_text(self):
      return ('Added tags: '
             +', '.join([k['name'] for k in self.result['added']]))
    def _tagging_as_text(self):
      what = []
      if self.result['tagged']:
        what.append('Tagged ' +
                    ', '.join([k['name'] for k in self.result['tagged']]))
      if self.result['untagged']:
        what.append('Untagged ' +
                    ', '.join([k['name'] for k in self.result['untagged']]))
      return '%s (%d messages)' % (', '.join(what), len(self.result['msg_ids']))
    def as_text(self):
      if not self.result:
        return 'Failed'
      return ''.join([
        ('added' in self.result) and self._added_as_text() or '',
        ('removed' in self.result) and self._added_as_text() or '',
        ('tags' in self.result) and self._tags_as_text() or '',
        ('msg_ids' in self.result) and self._tagging_as_text() or '',
      ])

  SYNOPSIS = '<[+|-]tags msgs>'
  def command(self, save=True):
    idx = self._idx()
    words = self.args[:]
    ops = []
    while words and words[0][0] in ('-', '+'):
      ops.append(words.pop(0))

    msg_ids = self._choose_messages(words)

    rv = {'msg_ids': [], 'tagged': [], 'untagged': []}
    rv['msg_ids'] = [b36(i) for i in msg_ids]
    for op in ops:
      tag_id = self.session.config.get_tag_id(op[1:])
      if op[0] == '-':
        idx.remove_tag(self.session, tag_id, msg_idxs=msg_ids, conversation=True)
        rv['untagged'].append({'name': op[1:], 'tid': tag_id})
      else:
        idx.add_tag(self.session, tag_id, msg_idxs=msg_ids, conversation=True)
        rv['tagged'].append({'name': op[1:], 'tid': tag_id})

    if save:
      # Background save makes things feel fast!
      def background():
        idx.update_tag_stats(self.session, self.session.config)
        idx.save_changes()
      self._background('Save index', background)
    else:
      idx.update_tag_stats(self.session, self.session.config)

    return rv

  def add_tag(self):
    config = self.session.config
    existing = [v.lower() for v in config.get('tag', {}).values()]
    for tag in self.args:
      if ' ' in tag:
        return self._error('Invalid tag: %s' % tag)
      if tag.lower() in existing:
        return self._error('Tag already exists: %s' % tag)
    result = []
    for tag in sorted(self.args):
      if config.parse_set(self.session, 'tag:%s=%s' % (config.nid('tag'), tag)):
        result.append({'name': tag, 'tid': config.get_tag_id(tag), 'new': 0})
    if result:
      self._background('Save config', lambda: config.save())
    return {'added': result}

  def list_tags(self):
    result, idx = [], self._idx()
    wanted = [t.lower() for t in self.args if not t.startswith('!')]
    unwanted = [t[1:].lower() for t in self.args if t.startswith('!')]
    for tid, tag in self.session.config.get('tag', {}).iteritems():
      if wanted and tag.lower() not in wanted: continue
      if unwanted and tag.lower() in unwanted: continue
      result.append({
        'name': tag,
        'tid': tid,
        'all': int(idx.STATS.get(tid, [0, 0])[0]),
        'new': int(idx.STATS.get(tid, [0, 0])[1]),
        'not': len(idx.INDEX) - int(idx.STATS.get(tid, [0, 0])[0])
      })
    result.sort(key=lambda k: k['name'])
    return {'tags': result}

  def rm_tag(self):
    session, config = self.session, self.session.config
    existing = [v.lower() for v in config.get('tag', {}).values()]
    clean_session = mailpile.ui.Session(config)
    clean_session.ui = session.ui
    result = []
    for tag in self.args:
      tag_id = config.get_tag_id(tag)
      if tag_id:
        # FIXME: Update filters too
        if (COMMANDS['s:'][1](clean_session, arg=['tag:%s' % tag]).run()
        and Tag(clean_session, arg=['-%s' % tag, 'all']).run()
        and config.parse_unset(session, 'tag:%s' % tag_id)):
          result.append({'name': tag, 'tid': tag_id})
        else:
          raise Exception('That failed, not sure why?!')
      else:
        self._error('No such tag %s' % tag)
    if result:
      config.save()
    return {'removed': result}

  SUBCOMMANDS = {
    'add':    (add_tag,   '<tag>'),
    'delete': (rm_tag,    '<tag>'),
    'list':   (list_tags, ''),
  }


class Filter(Command):
  """Add/edit/delete/list auto-tagging rules"""
  ORDER = ('Tagging', 1)
  SYNOPSIS = '[new|read] [notag] [=ID] [terms] <[+|-]tags ...> [description]'
  def command(self):
    args, session, config = self.args, self.session, self.session.config

    flags = []
    while args and args[0] in ('add', 'set', 'new', 'read', 'notag'):
      flags.append(args.pop(0))

    if args and args[0] and args[0][0] == '=':
      filter_id = args.pop(0)[1:]
    else:
      filter_id = config.nid('filter')

    auto_tag = False
    if 'read' in flags:
      terms = ['@read']
    elif 'new' in flags:
      terms = ['*']
    elif args[0] and args[0][0] not in ('-', '+'):
      terms = []
      while args and args[0][0] not in ('-', '+'):
        terms.append(args.pop(0))
    else:
      terms = session.searched
      auto_tag = True

    if not terms or (len(args) < 1):
      raise UsageError('Need flags and search terms or a hook')

    tags, tids = [], []
    while args and args[0][0] in ('-', '+'):
      tag = args.pop(0)
      tags.append(tag)
      tids.append(tag[0]+config.get_tag_id(tag[1:]))

    if not args:
      args = ['Filter for %s' % ' '.join(tags)]

    if auto_tag and 'notag' not in flags:
      if not Tag(session, arg=tags + ['all']).run(save=False):
        raise UsageError()

    if (config.parse_set(session, ('filter:%s=%s'
                                   ) % (filter_id, ' '.join(args)))
    and config.parse_set(session, ('filter_tags:%s=%s'
                                   ) % (filter_id, ' '.join(tids)))
    and config.parse_set(session, ('filter_terms:%s=%s'
                                   ) % (filter_id, ' '.join(terms)))):
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
    if len(self.args) < 1:
      raise UsageError('Delete what?')

    removed = 0
    filters = config.get('filter', {})
    filter_terms = config.get('filter_terms', {})
    for fid in self.args[:]:
      if fid not in filters:
        match = [f for f in filters if filter_terms[f] == fid]
        if match:
          self.args.remove(fid)
          self.args.extend(match)

    for fid in self.args:
      if (config.parse_unset(session, 'filter:%s' % fid)
      and config.parse_unset(session, 'filter_tags:%s' % fid)
      and config.parse_unset(session, 'filter_terms:%s' % fid)):
        removed += 1
      else:
        session.ui.warning('Failed to remove %s' % fid)
    if removed:
      config.save()
    return True

  def mv(self):
    raise Exception('Unimplemented')

  def ls(self):
    return self.session.ui.print_filters(self.session.config)

  SUBCOMMANDS = {
    'delete': (rm, '<id>'),
    'move':   (mv, '<id> <pos>'),
    'list':   (ls, ''),
  }


class VCard(Command):
  """Add/remove/list/edit vcards"""
  ORDER = ('Internals', 6)
  KIND = ''
  SYNOPSIS = '<nickname>'
  def command(self, save=True):
    session, config = self.session, self.session.config
    vcards = []
    for email in self.args:
      vcard = config.get_vcard(email)
      if vcard:
        vcards.append(vcard)
      else:
        session.ui.warning('No such contact: %s' % email)
    return vcards

  def _fparse(self, fromdata):
    email = ExtractEmails(fromdata)[0]
    name = fromdata.replace(email, '').replace('<>', '').strip()
    return email, (name or email)

  def _prepare_new_vcard(self, vcard):
    pass

  def _valid_vcard_handle(self, vc_handle):
    return (vc_handle and '@' in vc_handle[1:])

  def _add_from_messages(self):
    pairs, idx = [], self._idx()
    for email in [Email(idx, i) for i in self._choose_messages(self.args)]:
      pairs.append(self._fparse(email.get_msg_info(idx.MSG_FROM)))
    return pairs

  def _pre_delete_vcard(self, vcard):
    pass

  def add_vcards(self):
    session, config, idx = self.session, self.session.config, self._idx()
    if (len(self.args) > 2
    and self.args[1] == '='
    and self._valid_vcard_handle(self.args[0])):
      pairs = [(self.args[0], ' '.join(self.args[2:]))]
    else:
      pairs = self._add_from_messages()
    if pairs:
      vcards = []
      for handle, name in pairs:
        if handle.lower() not in config.vcards:
          vcard = config.add_vcard(handle, name, self.KIND)
          self._prepare_new_vcard(vcard)
          vcards.append(vcard)
        else:
          session.ui.warning('Already exists: %s' % handle)
    else:
      return self._error('Nothing to do!')
    return vcards

  def _format_values(self, key, vals):
    if key.upper() in ('MEMBER', ):
      return [['mailto:%s' % e, []] for e in vals]
    else:
      return [[e, []] for e in vals]

  def set_vcard(self):
    session, config = self.session, self.session.config
    handle, var = self.args[0], self.args[1]
    if self.args[2] == '=':
      val = ' '.join(self.args[3:])
    else:
      val = ' '.join(self.args[2:])
    try:
      vcard = config.get_vcard(handle)
      if not vcard:
        return self._error('Contact not found')
      config.deindex_vcard(vcard)
      if val:
        if ',' in val:
          vcard[var] = self._format_values(var, val.split(','))
        else:
          vcard[var] = val
      else:
        del vcard[var]
      vcard.save()
      config.index_vcard(vcard)
      session.ui.display_vcard(vcard, compact=False)
      return True
    except:
      self._ignore_exception()
      return self._error('Error setting %s = %s' % (var, val))

  def rm_vcards(self):
    session, config = self.session, self.session.config
    for handle in self.args:
      vcard = config.get_vcard(handle)
      if vcard:
        self._pre_delete_vcard(vcard)
        config.del_vcard(handle)
      else:
        session.ui.error('No such contact: %s' % handle)
    return True

  def find_vcards(self):
    session, config = self.session, self.session.config
    if self.args and self.args[0] == '--full':
      self.args.pop(0)
      compact = False
    else:
      compact = True
    kinds = self.KIND and [self.KIND] or []
    vcards = config.find_vcards(self.args, kinds=kinds)
    for vcard in vcards:
      session.ui.display_vcard(vcard, compact=compact)
    return True

  SUBCOMMANDS = {
    'add':    (add_vcards,  '<msgs>|<email> <name>'),
    'set':    (set_vcard,   '<email> <attr> <value>'),
    'list':   (find_vcards, '[--full] [<terms>]'),
    'delete': (rm_vcards,   '<email>'),
  }


class Contact(VCard):
  """Add/remove/list/edit contacts"""
  KIND = 'individual'
  ORDER = ('Tagging', 3)
  SYNOPSIS = '<email>'


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
      session.ui.notify('%d message(s) updated' % len(emails))
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
    session.ui.notify('Attaching %s to...' % ', '.join(files))
    for email in emails:
      subject = email.get_msg_info(MailIndex.MSG_SUBJECT)
      try:
        email.add_attachments(files)
        session.ui.notify(' - %s' % subject)
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
        session.ui.notify('Message created as draft')
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
        session.ui.notify('Message created as draft')
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


##[ Configuration commands ]###################################################

class ConfigSet(Command):
  """Change a setting"""
  ORDER = ('Config', 1)
  SPLIT_ARG = False
  SYNOPSIS = '<var=value>'
  def command(self):
    session, config = self.session, self.session.config
    if config.parse_set(session, self.args[0]):
      self._serialize('Save config', lambda: config.save())
    return True


class ConfigUnset(Command):
  """Reset a setting to the default"""
  ORDER = ('Config', 2)
  SPLIT_ARG = False
  SYNOPSIS = '<var>'
  def command(self):
    session, config = self.session, self.session.config
    if config.parse_unset(session, self.args[0]):
      self._serialize('Save config', lambda: config.save())
    return True


class ConfigPrint(Command):
  """Print a setting"""
  ORDER = ('Config', 3)
  SPLIT_ARG = False
  SYNOPSIS = '<var>'
  def command(self):
    self.session.ui.print_key(self.args[0].strip().lower(),
                              self.session.config)
    return True


class AddMailbox(Command):
  """Add a mailbox"""
  ORDER = ('Config', 4)
  SPLIT_ARG = False
  SYNOPSIS = '</path/to/mbx>'
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
      session.ui.debug(gpg.handles['stderr'].read().decode('utf-8'))
      gpg.handles['stderr'].close()
      gpg.wait()
      session.ui.mark('Fetched key %s' % arg)
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

class Output(Command):
  """Choose format for command results."""
  ORDER = ('Internals', 7)
  SYNOPSIS = "[mode]"
  def command(self):
    self.session.ui.render_mode = self.args and self.args[0] or 'text'
    return True


class Help(Command):
  """Print help on Mailpile or individual commands."""
  ABOUT = 'This is Mailpile!'
  ORDER = ('Config', 9)
  IS_HELP = True
  TEMPLATE_ID = 'help'

  class CommandResult(Command.CommandResult):
    def splash_as_text(self):
      return '\n'.join([
        self.result['splash'],
        'The web interface is %s' % (self.result['http_url'] or 'disabled.'),
        '',
        'For instructions, type `help`, press <CTRL-D> to quit.',
        ''
      ])
    def variables_as_text(self):
      text = []
      for group in self.result['variables']:
        text.append(group['name'])
        for var in group['variables']:
          sep =  ('=' in var['type']) and ': ' or ' = '
          text.append(('  %-35s %s'
                       ) % ('%s%s<%s>' % (var['var'], sep,
                                          var['type'].replace('=', '> = <')),
                            var['desc']))
        text.append('')
      return '\n'.join(text)
    def commands_as_text(self):
      text = ['Commands:']
      last_rank = None
      cmds = self.result['commands']
      width = self.result.get('width', 8)
      ckeys = cmds.keys()
      ckeys.sort(key=lambda k: cmds[k][3])
      for c in ckeys:
        cmd, args, explanation, rank = cmds[c]
        if not rank: continue
        if last_rank and int(rank/10) != last_rank: text.append('')
        last_rank = int(rank/10)
        if c[0] == '_':
          c = '  '
        else:
          c = '%s|' % c[0]
        fmt = '    %%s%%-%d.%ds' % (width, width)
        if explanation:
          fmt += ' %-15.15s %s'
        else:
          fmt += ' %s %s '
        text.append(fmt % (c, cmd.replace('=', ''),
                           args and ('%s' % args) or '',
                           (explanation.splitlines() or [''])[0]))
      if 'tags' in self.result:
        text.extend([
          '',
          'Tags:  (use a tag as a command to display tagged messages)',
          '',
          self.result['tags'].as_text()
        ])
      return '\n'.join(text)

    def as_text(self):
      if not self.result:
        return 'Error'
      return ''.join([
        ('splash' in self.result) and self.splash_as_text() or '',
        ('variables' in self.result) and self.variables_as_text() or '',
        ('commands' in self.result) and self.commands_as_text() or '',
      ])

  SYNOPSIS = "[command]"
  def command(self):
    self.session.ui.reset_marks(quiet=True)
    if self.args:
      command = self.args.pop(0)
      for name, cls in COMMANDS.values():
        if name.replace('=', '') == command:
          order = 1
          cmd_list = {'_main': (name, cls.SYNOPSIS, '', order)}
          for cmd in sorted(cls.SUBCOMMANDS.keys()):
            order += 1
            cmd_list['_%s' % cmd] = ('%s' % name,
                                     '%s %s' % (cmd, cls.SUBCOMMANDS[cmd][1]),
                                     '', order)
          return {
            'pre': cls.__doc__,
            'commands': cmd_list,
            'width': len(name),
            'post': cls.EXAMPLES
          }
      return self._error('Unknown command')
    else:
      cmd_list = {}
      count = 0
      for grp in COMMAND_GROUPS:
        count += 10
        for c in COMMANDS:
          name, cls = COMMANDS[c]
          synopsis = cls.SUBCOMMANDS and '<command ...>' or cls.SYNOPSIS
          if cls.ORDER[0] == grp:
            cmd_list[c] = (name, synopsis, cls.__doc__, count+cls.ORDER[1])
      return {
        'commands': cmd_list,
        'tags': Tag(self.session, arg=['list']).run(),
        'index': self._idx()
      }

  def help_vars(self):
    config = self.session.config
    result = []
    for cat in config.CATEGORIES.keys():
      variables = []
      for what in config.INTS, config.STRINGS, config.DICTS:
        for ii, i in what.iteritems():
          variables.append({
            'var': ii,
            'type': i[0],
            'desc': i[2]
          })
      variables.sort(key=lambda k: k['var'])
      result.append({
        'category': cat,
        'name': config.CATEGORIES[cat][1],
        'variables': variables
      })
    result.sort(key=lambda k: config.CATEGORIES[k['category']][0])
    return {'variables': result}

  def help_splash(self):
    http_worker = self.session.config.http_worker
    if http_worker:
      http_url = 'http://%s:%s/' % http_worker.httpd.sspec
    else:
      http_url = ''
    return {
      'splash': self.ABOUT,
      'http_url': http_url,
    }

  def _starting(self): pass
  def _finishing(self, command, rv):
    return self.CommandResult(self.session, self.name, self.template_id,
                              command.__doc__ or self.__doc__, rv)

  SUBCOMMANDS = {
    'variables': (help_vars, ''),
    'splash': (help_splash, ''),
  }


def Action(session, opt, arg, data=None):
  session.ui.reset_marks(quiet=True)
  config = session.config

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
    s = ['tag:%s' % config.get_tag_id(opt)[0]]
    return COMMANDS['s:'][1](session, opt, arg=arg, data=data).run(search=s)

  # OK, give up!
  raise UsageError('Unknown command: %s' % opt)


# Commands starting with _ don't get single-letter shortcodes...
COMMANDS = {
  'A:':     ('add=',     AddMailbox),
  'a:':     ('attach=',  Attach),
  'c:':     ('compose=', Compose),
  'C:':     ('contact=', Contact),
  'f:':     ('forward=', Forward),
  'F:':     ('filter=',  Filter),
  'g:':     ('gpg',      GPG),
  'h':      ('help',     Help),
  'm:':     ('mail=',    Mail),
  'P:':     ('print=',   ConfigPrint),
  'r:':     ('reply=',   Reply),
  'S:':     ('set=',     ConfigSet),
  't:':     ('tag=',     Tag),
  'U:':     ('unset=',   ConfigUnset),
  'u:':     ('update=',  Update),
  '_dmode': ('output=',  Output),
  '_setup': ('setup',    Setup),
  '_load':  ('load',     Load),
  '_optim': ('optimize', Optimize),
  '_resca': ('rescan',   Rescan),
  '_vcard': ('vcard=',   VCard),
  '_www':   ('www',      RunWWW),
  '_recou': ('recount',  UpdateStats)
}
COMMAND_GROUPS = ['Internals', 'Config', 'Searching', 'Tagging', 'Composing']

