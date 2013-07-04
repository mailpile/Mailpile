import mailpile.plugins
from mailpile.commands import Command, VCard, Tag, Filter

##[ Config variables ]########################################################



##[ Search terms ]############################################################

def search(config, term, hits):
  group = config.vcards.get(term.split(':', 1)[1])
  rt, emails = [], []
  if group and group.kind == 'group':
    for email, attrs in group.get('EMAIL', []):
      contact = config.vcards.get(email.lower(), None)
      if contact:
        emails.extend([e[0].lower() for e in contact.get('EMAIL', [])])
      else:
        emails.append(email.lower())
  fromto = term.startswith('group:') and 'from' or 'to'
  for email in set(emails):
    rt.extend(hits('%s:%s' % (email, fromto)))
  return rt

mailpile.plugins.register_search_term('group', search)
mailpile.plugins.register_search_term('togroup', search)


##[ Commands ]################################################################

class Group(VCard):
  """Add/remove/list/edit groups"""
  ORDER = ('Tagging', 4)
  SYNOPSIS = '<group>'
  KIND = 'group'

  def _valid_vcard_handle(self, vc_handle):
    # If there is already a tag by this name, complain.
    return (vc_handle
       and  ('-' != vc_handle[0])
       and  ('@' not in vc_handle)
       and  (not self.session.config.get_tag_id(vc_handle)))

  def _prepare_new_vcard(self, vcard):
    session, handle = self.session, vcard.nickname
    return (Tag(session, arg=['add', handle]).run()
       and  Filter(session, arg=['add', 'group:%s' % handle,
                                 '+%s' % handle, vcard.fn]).run())

  def _add_from_messages(self):
    raise ValueError('Invalid group ids: %s' % self.args)

  def _pre_delete_vcard(self, vcard):
    session, handle = self.session, vcard.nickname
    return (Filter(session, arg=['delete', 'group:%s' % handle]).run()
       and  Tag(session, arg=['delete', handle]).run())

mailpile.plugins.register_command('G:', 'group=', Group)
