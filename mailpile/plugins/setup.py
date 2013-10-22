import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *

from mailpile.plugins.tags import AddTag, Filter


##[ Commands ]################################################################

class Setup(Command):
    """Perform initial setup"""
    SYNOPSIS = (None, 'setup', None, None)
    ORDER = ('Internals', 0)

    def command(self):
        session = self.session

        # Create local mailboxes
        session.config.open_local_mailbox(session)

        # Create standard tags and filters
        created = []
        for t in ('New', 'Inbox', 'Spam', 'Drafts', 'Blank', 'Sent', 'Trash'):
            if not session.config.get_tag_id(t):
                AddTag(session, arg=[t]).run()
                created.append(t)
        for writable in ('Blank', 'Drafts'):
            if writable not in session.config.sys.writable_tags:
                 tid = session.config.get_tag_id(writable)
                 session.config.sys.writable_tags.append(tid)
        if 'New' in created:
            Filter(session,
                   arg=['new', '+Inbox', '+New', 'New Mail filter']).run()
            Filter(session,
                   arg=['read', '-New', 'Read Mail filter']).run()

        session.config.save()
        return True


mailpile.plugins.register_commands(Setup)
