#!/usr/bin/python
from mailpile.util import *
from mailpile.mailutils import Email

COMMANDS = {
  'A:': ('add=',     'path/to/mbox',  'Add a mailbox',                      60),
  'F:': ('filter=',  'options',       'Add/edit/delete auto-tagging rules', 56),
  'h':  ('help',     '',              'Print help on how to use mailpile',   0),
  'L':  ('load',     '',              'Load the metadata index',            61),
  'n':  ('next',     '',              'Display next page of results',       91),
  'o:': ('order=',   '[rev-]what',   ('Sort by: date, from, subject, '
                                      'random or index'),                   93),
  'O':  ('optimize', '',              'Optimize the keyword search index',  62),
  'p':  ('previous', '',              'Display previous page of results',   92),
  'P:': ('print=',   'var',           'Print a setting',                    52),
  'R':  ('rescan',   '',              'Scan all mailboxes for new messages',63),
  's:': ('search=',  'terms ...',     'Search!',                            90),
  'S:': ('set=',     'var=value',     'Change a setting',                   50),
  't:': ('tag=',     '[+|-]tag msg',  'Tag or untag search results',        94),
  'T:': ('addtag=',  'tag',           'Create a new tag',                   55),
  'U:': ('unset=',   'var',           'Reset a setting to the default',     51),
  'v:': ('view=',    '[raw] m1 ...',  'View one or more messages',          95),
  'W':  ('www',      '',              'Just run the web server',            56),
}
def Choose_Messages(session, words):
  msg_ids = set()
  for what in words:
    if what.lower() == 'these':
      b, c = session.displayed
      msg_ids |= set(session.results[b:b+c])
    elif what.lower() == 'all':
      msg_ids |= set(session.results)
    elif what.startswith('='):
      try:
        msg_ids.add(int(what[1:], 36))
      except ValueError:
        session.ui.warning('What message is %s?' % (what, ))
    elif '-' in what:
      try:
        b, e = what.split('-')
        msg_ids |= set(session.results[int(b)-1:int(e)])
      except:
        session.ui.warning('What message is %s?' % (what, ))
    else:
      try:
        msg_ids.add(session.results[int(what)-1])
      except:
        session.ui.warning('What message is %s?' % (what, ))
  return msg_ids

def Action_Load(session, config, reset=False, wait=True, quiet=False):
  if not reset and config.index:
    return config.index
  def do_load():
    if reset:
      config.index = None
      if session:
        session.results = []
        session.searched = []
        session.displayed = (0, 0)
    idx = config.get_index(session)
    idx.update_tag_stats(session, config)
    if session:
      session.ui.reset_marks(quiet=quiet)
    return idx
  if wait:
    return config.slow_worker.do(session, 'Load', do_load)
  else:
    config.slow_worker.add_task(session, 'Load', do_load)
    return None

def Action_Tag(session, opt, arg, save=True):
  idx = Action_Load(session, session.config)
  try:
    words = arg.split()
    op = words[0][0]
    tag = words[0][1:]
    tag_id = session.config.get_tag_id(tag)

    msg_ids = Choose_Messages(session, words[1:])
    if op == '-':
      idx.remove_tag(session, tag_id, msg_idxs=msg_ids)
    else:
      idx.add_tag(session, tag_id, msg_idxs=msg_ids)

    session.ui.reset_marks()

    if save:
      # Background save makes things feel fast!
      def background():
        idx.update_tag_stats(session, session.config)
        idx.save()
      session.config.slow_worker.add_task(None, 'Save index', background)
    else:
      idx.update_tag_stats(session, session.config)

    return True

  except (TypeError, ValueError, IndexError):
    session.ui.reset_marks()
    session.ui.error('That made no sense: %s %s' % (opt, arg))
    return False

def Action_Filter_Add(session, config, flags, args):
  terms = ('new' in flags) and ['*'] or session.searched
  if args and args[0][0] == '=':
    tag_id = args.pop(0)[1:]
  else:
    tag_id = config.nid('filter')

  if not terms or (len(args) < 1):
    raise UsageError('Need search term and flags')

  tags, tids = [], []
  while args and args[0][0] in ('-', '+'):
    tag = args.pop(0)
    tags.append(tag)
    tids.append(tag[0]+config.get_tag_id(tag[1:]))

  if not args:
    args = ['Filter for %s' % ' '.join(tags)]

  if 'notag' not in flags and 'new' not in flags:
    for tag in tags:
      if not Action_Tag(session, 'filter/tag', '%s all' % tag, save=False):
        raise UsageError()

  if (config.parse_set(session, ('filter:%s=%s'
                                 ) % (tag_id, ' '.join(args)))
  and config.parse_set(session, ('filter_tags:%s=%s'
                                 ) % (tag_id, ' '.join(tids)))
  and config.parse_set(session, ('filter_terms:%s=%s'
                                 ) % (tag_id, ' '.join(terms)))):
    session.ui.reset_marks()
    def save_filter():
      config.save()
      config.index.save(None)
    config.slow_worker.add_task(None, 'Save filter', save_filter)
  else:
    raise Exception('That failed, not sure why?!')

def Action_Filter_Delete(session, config, flags, args):
  if len(args) < 1 or args[0] not in config.get('filter', {}):
    raise UsageError('Delete what?')

  fid = args[0]
  if (config.parse_unset(session, 'filter:%s' % fid)
  and config.parse_unset(session, 'filter_tags:%s' % fid)
  and config.parse_unset(session, 'filter_terms:%s' % fid)):
    config.save()
  else:
    raise Exception('That failed, not sure why?!')

def Action_Filter_Move(session, config, flags, args):
  raise Exception('Unimplemented')

def Action_Filter(session, opt, arg):
  config = session.config
  args = arg.split()
  flags = []
  while args and args[0] in ('add', 'set', 'delete', 'move', 'list',
                             'new', 'notag'):
    flags.append(args.pop(0))
  try:
    if 'delete' in flags:
      return Action_Filter_Delete(session, config, flags, args)
    elif 'move' in flags:
      return Action_Filter_Move(session, config, flags, args)
    elif 'list' in flags:
      return session.ui.print_filters(config)
    else:
      return Action_Filter_Add(session, config, flags, args)
  except UsageError:
    pass
  except Exception, e:
    session.error(e)
    return
  session.ui.say(
    'Usage: filter [new] [notag] [=ID] <[+|-]tags ...> [description]\n'
    '       filter delete <id>\n'
    '       filter move <id> <pos>\n'
    '       filter list')

def Action_Rescan(session, config):
  if 'rescan' in config.RUNNING: return
  config.RUNNING['rescan'] = True
  idx = config.index
  count = 0
  try:
    pre_command = config.get('rescan_command', None)
    if pre_command:
      session.ui.mark('Running: %s' % pre_command)
      subprocess.check_call(pre_command, shell=True)
    count = 1
    for fid, fpath in config.get_mailboxes():
      if QUITTING: break
      count += idx.scan_mailbox(session, fid, fpath, config.open_mailbox)
      config.clear_mbox_cache()
      session.ui.mark('\n')
    count -= 1
    if not count: session.ui.mark('Nothing changed')
  except (KeyboardInterrupt, subprocess.CalledProcessError), e:
    session.ui.mark('Aborted: %s' % e)
  finally:
    if count:
      session.ui.mark('\n')
      idx.save(session)
  idx.update_tag_stats(session, config)
  session.ui.reset_marks()
  del config.RUNNING['rescan']
  return True

def Action_Optimize(session, config, arg):
  try:
    idx = config.index
    filecount = PostingList.Optimize(session, idx,
                                     force=(arg == 'harder'))
    session.ui.reset_marks()
  except KeyboardInterrupt:
    session.ui.mark('Aborted')
    session.ui.reset_marks()
  return True

def Action(session, opt, arg):
  config = session.config
  session.ui.reset_marks(quiet=True)
  num_results = config.get('num_results', None)

  if not opt or opt in ('h', 'help'):
    session.ui.print_help(COMMANDS, tags=session.config.get('tag', {}),
                                    index=config.get_index(session))

  elif opt in ('W', 'webserver'):
    config.prepare_workers(session, daemons=True)
    while not QUITTING: time.sleep(1)

  elif opt in ('A', 'add'):
    if os.path.exists(arg):
      arg = os.path.abspath(arg)
      if config.parse_set(session,
                          'mailbox:%s=%s' % (config.nid('mailbox'), arg)):
        config.slow_worker.add_task(None, 'Save config', lambda: config.save())
    else:
      session.error('No such file/directory: %s' % arg)

  elif opt in ('T', 'addtag'):
    if (arg
    and ' ' not in arg
    and arg.lower() not in [v.lower() for v in config['tag'].values()]):
      if config.parse_set(session,
                          'tag:%s=%s' % (config.nid('tag'), arg)):
        config.slow_worker.add_task(None, 'Save config', lambda: config.save())
    else:
      session.error('Invalid tag: %s' % arg)

  elif opt in ('F', 'filter'):
    Action_Filter(session, opt, arg)

  elif opt in ('O', 'optimize'):
    config.slow_worker.do(session, 'Optimize',
                          lambda: Action_Optimize(session, config, arg))

  elif opt in ('P', 'print'):
    session.ui.print_key(arg.strip().lower(), config)

  elif opt in ('U', 'unset'):
    if config.parse_unset(session, arg):
      config.slow_worker.add_task(None, 'Save config', lambda: config.save())

  elif opt in ('S', 'set'):
    if config.parse_set(session, arg):
      config.slow_worker.add_task(None, 'Save config', lambda: config.save())

  elif opt in ('R', 'rescan'):
    Action_Load(session, config)
    config.slow_worker.do(session, 'Rescan',
                          lambda: Action_Rescan(session, config))

  elif opt in ('L', 'load'):
    Action_Load(session, config, reset=True)

  elif opt in ('n', 'next'):
    idx = Action_Load(session, config)
    session.ui.reset_marks()
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   start=pos+count,
                                                   num=num_results)
    session.ui.reset_marks()

  elif opt in ('p', 'previous'):
    idx = Action_Load(session, config)
    pos, count = session.displayed
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   end=pos,
                                                   num=num_results)
    session.ui.reset_marks()

  elif opt in ('t', 'tag'):
    Action_Tag(session, opt, arg)

  elif opt in ('o', 'order'):
    idx = Action_Load(session, config)
    session.order = arg or None
    idx.sort_results(session, session.results,
                     how=session.order)
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   num=num_results)
    session.ui.reset_marks()

  elif (opt in ('s', 'search')
        or opt.lower() in [t.lower() for t in config['tag'].values()]):
    idx = Action_Load(session, config)

    # FIXME: This is all rather dumb.  Make it smarter!

    session.searched = []
    if opt not in ('s', 'search'):
      tid = config.get_tag_id(opt)
      session.searched = ['tag:%s' % tid[0]]

    if arg.startswith('@'):
      try:
        if ' ' in arg:
          args = arg[1:].split(' ')
          start = args.pop(0)
        else:
          start, args = arg[1:], []
        start = int(start)-1
        arg = ' '.join(args)
      except ValueError:
        raise UsageError('Weird starting point')
    else:
      start = 0

    if ':' in arg or '-' in arg or '+' in arg:
      session.searched.extend(arg.lower().split())
    else:
      session.searched.extend(re.findall(WORD_REGEXP, arg.lower()))

    session.results = list(idx.search(session, session.searched))
    idx.sort_results(session, session.results, how=session.order)
    session.displayed = session.ui.display_results(idx, session.results,
                                                   session.searched,
                                                   start=start,
                                                   num=num_results)
    session.ui.reset_marks()

  elif opt in ('v', 'view'):
    args = arg.split()
    if args and args[0].lower() == 'raw':
      raw = args.pop(0)
    else:
      raw = False
    idx = Action_Load(session, config)
    emails = [Email(idx, i) for i in Choose_Messages(session, args)]
    session.ui.display_messages(emails, raw=raw)
    session.ui.reset_marks()

  else:
    raise UsageError('Unknown command: %s' % opt)


