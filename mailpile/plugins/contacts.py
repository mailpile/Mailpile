import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *


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


mailpile.plugins.register_command('C:',     'contact=', Contact)
mailpile.plugins.register_command('_vcard', 'vcard=',   VCard)

