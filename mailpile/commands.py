# These are the Mailpile commands, the public "API" we expose for searching,
# tagging and editing e-mail.
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


class Command:
  """Generic command object all others inherit from"""
  SYNOPSIS = (None,  # CLI shortcode, e.g. A:
              None,  # CLI shortname, e.g. add
              None,  # API endpoint, e.g. sys/addmailbox
              None)  # Positional argument list
  EXAMPLES = None
  FAILURE = 'Failed: %(name)s %(args)s'
  IS_HELP = False
  ORDER = (None, 0)
  SERIALIZE = False
  SPLIT_ARG = 10000  # A big number!
  RAISES = (UsageError, )

  HTTP_CALLABLE = ('GET', )
  HTTP_POST_VARS = { }
  HTTP_QUERY_VARS = { }

  # Deprecating:
  SUBCOMMANDS = {}

  class CommandResult:
    def __init__(self, session, command, template_id, doc, result,
                       args=[], kwargs={}):
      self.session = session
      self.command = command
      self.args = args
      self.kwargs = kwargs
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
        'command_parts': self.command.split(" "),
        'args': self.args,
        'kwargs': self.kwargs,
        'result': self.result,
        'elapsed': '%.3f' % self.session.ui.time_elapsed
      }

    def as_html(self, template=None):
      path_parts = self.template_id.split('/')
      if len(path_parts) == 1:
        path_parts.append('index')
      if template not in (None, 'html', 'as.html'):
        # Security: The template request may come from the URL, so we
        #           sanitize it very aggressively before heading off to
        #           the filesystem.
        path_parts[-1] += '-%s' % CleanText(template.replace('.html', ''),
                                            banned=CleanText.FS)
      tpath = os.path.join(*path_parts)
      return self.session.ui.render_html(self.session.config, [tpath],
                                         self.as_dict())

    def as_json(self):
      return self.session.ui.render_json(self.as_dict())

  def __init__(self, session, name=None, arg=None, data=None):
    self.session = session
    self.serialize = self.SERIALIZE
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
        session.displayed = {'start': 1, 'count': 0}
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
        b = self.session.displayed['start'] - 1
        c = self.session.displayed['count']
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
    return self.CommandResult(self.session, self.name, self.SYNOPSIS[2],
                              command.__doc__ or self.__doc__,
                              rv, self.args, self.data)

  def _run(self, *args, **kwargs):
    try:
      def command(self, *args, **kwargs):
        return self.command(*args, **kwargs)
      self._starting()
      return self._finishing(command, command(self, *args, **kwargs))
    except self.RAISES:
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

class Load(Command):
  """Load or reload the metadata index"""
  SYNOPSIS = (None, 'load', None, None)
  ORDER = ('Internals', 1)

  def command(self, reset=True, wait=True, quiet=False):
    return self._idx(reset=reset, wait=wait, quiet=quiet) and True or False


class Rescan(Command):
  """Scan all mailboxes for new messages"""
  SYNOPSIS = (None, 'rescan', None, None)
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
  SYNOPSIS = (None, 'optimize', None, '[harder]')
  ORDER = ('Internals', 3)
  SERIALIZE = 'Optimize'

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
  SYNOPSIS = (None, 'recount', None, None)
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
  SYNOPSIS = (None, 'www', None, None)
  ORDER = ('Internals', 5)

  def command(self):
    self.session.config.prepare_workers(self.session, daemons=True)
    while not mailpile.util.QUITTING:
      time.sleep(1)
    return True


##[ Configuration commands ]###################################################

class ConfigSet(Command):
  """Change a setting"""
  SYNOPSIS = ('S', 'set', None, '<var=value>')
  ORDER = ('Config', 1)
  SPLIT_ARG = False
  HTTP_CALLABLE = ('POST', 'UPDATE')

  def command(self):
    session, config = self.session, self.session.config
    if config.parse_set(session, self.args[0]):
      self._serialize('Save config', lambda: config.save())
    return True


class ConfigUnset(Command):
  """Reset a setting to the default"""
  SYNOPSIS = ('U', 'unset', None, '<var>')
  ORDER = ('Config', 2)
  SPLIT_ARG = False
  HTTP_CALLABLE = ('POST', )

  def command(self):
    session, config = self.session, self.session.config
    if config.parse_unset(session, self.args[0]):
      self._serialize('Save config', lambda: config.save())
    return True


class ConfigPrint(Command):
  """Print a setting"""
  SYNOPSIS = ('P', 'print', 'config/get', '<var>')
  ORDER = ('Config', 3)
  SPLIT_ARG = False

  def command(self):
    key = self.args[0].strip().lower()
    try:
      return {key: self.session.config[key]}
    except KeyError:
      self.session.error('No such key: %s' % key)
      return False


class AddMailbox(Command):
  """Add a mailbox"""
  SYNOPSIS = ('A', 'add', None, '<path/to/mailbox>')
  ORDER = ('Config', 4)
  SPLIT_ARG = False
  HTTP_CALLABLE = ('POST', 'UPDATE')

  def command(self):
    session, config, raw_fn = self.session, self.session.config, self.args[0]
    fn = os.path.expanduser(raw_fn)
    if fn in config.get('mailbox', {}).values():
      session.ui.warning('Already in the pile: %s' % fn)
    else:
      if fn.startswith("imap://"):
        arg = fn
      else:
        if os.path.exists(fn):
          arg = os.path.abspath(fn)
        else:
          return self._error('No such file/directory: %s' % raw_fn)
      if config.parse_set(session,
                          'mailbox:%s=%s' % (config.nid('mailbox'), fn)):
        self._serialize('Save config', lambda: config.save())
    return True

###############################################################################

class Output(Command):
  """Choose format for command results."""
  SYNOPSIS = (None, 'output', None, '[json|text|html|<template>.html|...]')
  ORDER = ('Internals', 7)

  def command(self):
    self.session.ui.render_mode = self.args and self.args[0] or 'text'
    return {'output': self.session.ui.render_mode}


class Help(Command):
  """Print help on Mailpile or individual commands."""
  SYNOPSIS = ('h', 'help', 'help', '[<command-group>|variables]')
  ABOUT = 'This is Mailpile!'
  ORDER = ('Config', 9)
  IS_HELP = True

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
                           args and ('%s' % (args, )) or '',
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

  def command(self):
    self.session.ui.reset_marks(quiet=True)
    if self.args:
      command = self.args.pop(0)
      for cls in COMMANDS:
        name = cls.SYNOPSIS[1]
        if name and name == command:
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
        for cls in COMMANDS:
          c, name, url, synopsis = cls.SYNOPSIS[:4]
          if cls.ORDER[0] == grp:
            cmd_list[c or '_%s' % name] = (name, synopsis, cls.__doc__,
                                           count + cls.ORDER[1])
      return {
        'commands': cmd_list,
        'tags': GetCommand('tag/list')(self.session).run(),
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
    return self.CommandResult(self.session, self.name, self.SYNOPSIS[2],
                              command.__doc__ or self.__doc__, rv)

  SUBCOMMANDS = {
    'variables': (help_vars, ''),
    'splash': (help_splash, ''),
  }


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
  if opt.lower() in [t.lower() for t in config.get('tag', {}).values()]:
    s = ['tag:%s' % config.get_tag_id(opt)[0]]
    return GetCommand('search')(session, opt, arg=arg, data=data
                                ).run(search=s)

  # OK, give up!
  raise UsageError('Unknown command: %s' % opt)


# Commands starting with _ don't get single-letter shortcodes...
COMMANDS = [
  Optimize, Rescan, RunWWW, UpdateStats,
  ConfigPrint, ConfigSet, ConfigUnset, AddMailbox,
  Output, Help
]
COMMAND_GROUPS = ['Internals', 'Config', 'Searching', 'Tagging', 'Composing']

