import os
from gettext import gettext as _

import mailpile.plugins
from mailpile.plugins import __all__ as PLUGINS
from mailpile.commands import Command
from mailpile.util import *
from mailpile.gpgi import GnuPG

from mailpile.plugins.tags import AddTag, Filter


##[ Commands ]################################################################

class Setup(Command):
    """Perform initial setup"""
    SYNOPSIS = (None, 'setup', None, None)
    ORDER = ('Internals', 0)

    TAGS = {
        'New': {
            'type': 'unread',
            'label': False,
            'display': 'invisible'
        },
        'Inbox': {
            'display': 'priority',
            'display_order': 2,
        },
        'Blank': {
            'type': 'blank',
            'flag_editable': True,
            'display': 'invisible'
        },
        'Drafts': {
            'type': 'drafts',
            'flag_editable': True,
            'display': 'priority',
            'display_order': 1,
        },
        'Outbox': {
            'type': 'outbox',
            'display': 'priority',
            'display_order': 3,
        },
        'Sent': {
            'type': 'sent',
            'display': 'priority',
            'display_order': 4,
        },
        'Spam': {
            'type': 'spam',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 5,
        },
        'MaybeSpam': {
            'display': 'invisible',
        },
        'Ham': {
            'type': 'ham',
            'display': 'invisible',
        },
        'Trash': {
            'type': 'trash',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 6,
        },
        # These are internal tags, used for tracking user actions on
        # messages, as input for machine learning algorithms. These get
        # automatically added, and may be automatically removed as well
        # to keep the working sets reasonably small.
        'mp_rpl': {'type': 'replied', 'label': False, 'display': 'invisible'},
        'mp_tag': {'type': 'tagged', 'label': False, 'display': 'invisible'},
        'mp_read': {'type': 'read', 'label': False, 'display': 'invisible'},
        'mp_ham': {'type': 'ham', 'label': False, 'display': 'invisible'},
    }

    def command(self):
        session = self.session

        # Create local mailboxes
        session.config.open_local_mailbox(session)

        # Create standard tags and filters
        created = []
        for t in self.TAGS:
            if not session.config.get_tag_id(t):
                AddTag(session, arg=[t]).run()
                created.append(t)
            session.config.get_tag(t).update(self.TAGS[t])
        if 'New' in created:
            Filter(session,
                   arg=['new', '+Inbox', '+New', 'New Mail filter']).run()

        # Import all the basic plugins
        for plugin in PLUGINS:
            if plugin not in session.config.sys.plugins:
                session.config.sys.plugins.append(plugin)
        try:
            # If spambayes is not installed, this will fail
            import mailpile.plugins.autotag_sb
            if 'autotag_sb' not in session.config.sys.plugins:
                session.config.sys.plugins.append('autotag_sb')
        except ImportError:
            session.ui.warning(_('Please install spambayes '
                                 'for super awesome spam filtering'))
        session.config.save()
        session.config.load(session)

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

        if ('autotag_sb' in session.config.sys.plugins and
                len(session.config.prefs.autotag_sb) == 0):
            session.config.prefs.autotag_sb.append({
                'match_tag': 'spam',
                'unsure_tag': 'maybespam',
            })
            session.config.prefs.autotag_sb[0].exclude_tags[0] = 'ham'

        session.config.save()
        return True


mailpile.plugins.register_commands(Setup)
