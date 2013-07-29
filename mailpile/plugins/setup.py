import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *

from mailpile.plugins.tags import Tag, Filter


##[ Commands ]################################################################

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


mailpile.plugins.register_command('_setup', 'setup', Setup)
