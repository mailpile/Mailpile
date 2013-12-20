import os
from gettext import gettext as _

import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *
from mailpile.gpgi import GnuPG

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
        for t in ('New', 'Inbox', 'Outbox', 'Spam', 'Drafts', 'Blank',
                  'Sent', 'Trash'):
            if not session.config.get_tag_id(t):
                AddTag(session, arg=[t]).run()
                created.append(t)
        session.config.get_tag('New').update({
            'type': 'unread',
            'label': False,
            'display': 'invisible'
        })
        session.config.get_tag('Blank').update({
            'type': 'blank',
            'flag_editable': True,
            'display': 'invisible'
        })
        session.config.get_tag('Drafts').update({
            'type': 'drafts',
            'flag_editable': True,
            'display': 'priority',
            'display_order': 1,
        })
        session.config.get_tag('Inbox').update({
            'display': 'priority',
            'display_order': 2,
        })
        session.config.get_tag('Outbox').update({
            'type': 'outbox',
            'display': 'priority',
            'display_order': 3,
        })
        session.config.get_tag('Sent').update({
            'type': 'sent',
            'display': 'priority',
            'display_order': 4,
        })
        session.config.get_tag('Spam').update({
            'type': 'spam',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 5,
        })
        session.config.get_tag('Trash').update({
            'type': 'trash',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 6,
        })
        if 'New' in created:
            Filter(session,
                   arg=['new', '+Inbox', '+New', 'New Mail filter']).run()
            Filter(session,
                   arg=['read', '-New', 'Read Mail filter']).run()

        for old in ('invisible_tags', 'writable_tags'):
            if old in  session.config.sys:
                del session.config.sys[old]

        vcard_importers = session.config.prefs.vcard.importers

        if not vcard_importers.gravatar:
            vcard_importers.gravatar.append({'active': True})

        gpg_home = os.path.expanduser('~/.gnupg')
        if os.path.exists(gpg_home) and not vcard_importers.gpg:
            vcard_importers.gpg.append({'active': True,
                                        'gpg_home': gpg_home})

        # Assumption: If you already have secret keys, you want to 
        #             use the associated addresses for your e-mail.
        #             If you don't already have secret keys, you should have
        #             one made for you, if GnuPG is available.
        #             If GnuPG is not available, you should be warned.
        gnupg = GnuPG()
        if gnupg.is_available():
            keys = gnupg.list_secret_keys()
            if len(keys) == 0:
                # FIXME: Start background process generating a key once a user
                #        has supplied a name and e-mail address.
                pass
            else:
                for key, details in keys.iteritems():
                    for uid in details["uids"]:
                        if "email" not in uid or uid["email"] == "":
                            continue

                        if uid["email"] in [x["email"] 
                                            for x in session.config.profiles]:
                            # Don't set up the same e-mail address twice.
                            continue

                        # FIXME: Add route discovery mechanism.
                        profile = {
                            "email": uid["email"],
                            "name": uid["name"],
                        }
                        session.config.profiles.append(profile)
        else:
            # FIXME: Alert the user to the fact that PGP was not discovered
            pass

        session.config.save()
        return True


mailpile.plugins.register_commands(Setup)
