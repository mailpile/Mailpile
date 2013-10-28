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
        session.config.get_tag('New').update({
            'type': 'unread',
            'label': False,
            'display': 'invisible'
        })
        session.config.get_tag('Blank').update({
            'type': 'drafts',
            'write_flag': True,
            'display': 'invisible'
        })
        session.config.get_tag('Drafts').update({
            'type': 'drafts',
            'write_flag': True,
            'display': 'priority',
            'display_order': 1,
        })
        session.config.get_tag('Inbox').update({
            'display': 'priority',
            'display_order': 2,
        })
        session.config.get_tag('Sent').update({
            'display': 'priority',
            'display_order': 3,
        })
        session.config.get_tag('Spam').update({
            'type': 'spam',
            'hides_flag': True,
            'display': 'priority',
            'display_order': 4,
        })
        session.config.get_tag('Trash').update({
            'type': 'trash',
            'hides_flag': True,
            'display': 'priority',
            'display_order': 5,
        })
        if 'New' in created:
            Filter(session,
                   arg=['new', '+Inbox', '+New', 'New Mail filter']).run()
            Filter(session,
                   arg=['read', '-New', 'Read Mail filter']).run()

        for old in ('invisible_tags', 'writable_tags'):
            if old in  session.config.sys:
                del session.config.sys[old]

        session.config.save()
        return True


mailpile.plugins.register_commands(Setup)
