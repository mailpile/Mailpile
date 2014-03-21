import os
from gettext import gettext as _
from datetime import date 

import mailpile.plugins
from mailpile.plugins import __all__ as PLUGINS
from mailpile.commands import Command
from mailpile.crypto.gpgi import GnuPG, SignatureInfo, EncryptionInfo
from mailpile.util import *

from mailpile.plugins.tags import AddTag, Filter


##[ Commands ]################################################################

class Setup(Command):
    """Perform initial setup"""
    SYNOPSIS = (None, 'setup', None, None)
    ORDER = ('Internals', 0)
    LOG_PROGRESS = True

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
        'mp_fwd': {'type': 'fwded', 'label': False, 'display': 'invisible'},
        'mp_tag': {'type': 'tagged', 'label': False, 'display': 'invisible'},
        'mp_read': {'type': 'read', 'label': False, 'display': 'invisible'},
        'mp_ham': {'type': 'ham', 'label': False, 'display': 'invisible'},
    }

    def command(self):
        session = self.session

        if session.config.sys.lockdown:
            session.ui.warning(_('In lockdown, doing nothing.'))
            return False

        # Create local mailboxes
        session.config.open_local_mailbox(session)

        # Create standard tags and filters
        created = []
        for t in self.TAGS:
            if not session.config.get_tag_id(t):
                AddTag(session, arg=[t]).run(save=False)
                created.append(t)
            session.config.get_tag(t).update(self.TAGS[t])
        for stype, statuses in (('sig', SignatureInfo.STATUSES),
                                ('enc', EncryptionInfo.STATUSES)):
            for status in statuses:
                tagname = 'mp_%s-%s' % (stype, status)
                if not session.config.get_tag_id(tagname):
                    AddTag(session, arg=[tagname]).run(save=False)
                    created.append(tagname)
                session.config.get_tag(tagname).update({
                    'type': 'attribute',
                    'display': 'invisible',
                    'label': False,
                })

        if 'New' in created:
            Filter(session,
                   arg=['new', '@incoming', '+Inbox', '+New',
                        'Incoming mail filter']).run(save=False)
            session.ui.notify(_('Created default tags'))

        # Import all the basic plugins
        for plugin in PLUGINS:
            if plugin not in session.config.sys.plugins:
                session.config.sys.plugins.append(plugin)
        try:
            # If spambayes is not installed, this will fail
            import mailpile.plugins.autotag_sb
            if 'autotag_sb' not in session.config.sys.plugins:
                session.config.sys.plugins.append('autotag_sb')
                session.ui.notify(_('Enabling spambayes autotagger'))
        except ImportError:
            session.ui.warning(_('Please install spambayes '
                                 'for super awesome spam filtering'))
        session.config.save()
        session.config.load(session)

        vcard_importers = session.config.prefs.vcard.importers
        if not vcard_importers.gravatar:
            vcard_importers.gravatar.append({'active': True})
            session.ui.notify(_('Enabling gravatar image importer'))

        gpg_home = os.path.expanduser('~/.gnupg')
        if os.path.exists(gpg_home) and not vcard_importers.gpg:
            vcard_importers.gpg.append({'active': True,
                                        'gpg_home': gpg_home})
            session.ui.notify(_('Importing contacts from GPG keyring'))

        if ('autotag_sb' in session.config.sys.plugins and
                len(session.config.prefs.autotag) == 0):
            session.config.prefs.autotag.append({
                'match_tag': 'spam',
                'unsure_tag': 'maybespam',
                'tagger': 'spambayes',
                'trainer': 'spambayes'
            })
            session.config.prefs.autotag[0].exclude_tags[0] = 'ham'

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
                    # Ignore revoked/expired keys.
                    if "revocation-date" in details and details["revocation-date"] <= date.today().strftime("%Y-%m-%d"):
                        continue

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
                    if not session.config.prefs.gpg_recipient:
                        session.config.prefs.gpg_recipient = key
                        session.ui.notify(_('Encrypting config to %s') % key)
                    if session.config.prefs.crypto_policy == 'none':
                        session.config.prefs.crypto_policy = 'openpgp-sign'
        else:
            session.ui.warning(_('Oh no, PGP/GPG support is unavailable!'))

        if (session.config.prefs.gpg_recipient
                and not (self._idx() and self._idx().INDEX)
                and not session.config.prefs.obfuscate_index):
            randcrap = sha512b64(open('/dev/urandom').read(1024),
                                 session.config.prefs.gpg_recipient,
                                 '%s' % time.time())
            session.config.prefs.obfuscate_index = randcrap
            session.config.prefs.index_encrypted = True
            session.ui.notify(_('Obfuscating search index and enabling '
                                'indexing of encrypted e-mail. '))

        session.config.save()
        return True


mailpile.plugins.register_commands(Setup)
