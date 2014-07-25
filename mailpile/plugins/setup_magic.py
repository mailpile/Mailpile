import os
import random
from datetime import date
from urllib import urlencode

import mailpile.auth
from mailpile.i18n import ActivateTranslation
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.plugins import __all__ as PLUGINS
from mailpile.commands import Command
from mailpile.crypto.gpgi import GnuPG, SignatureInfo, EncryptionInfo
from mailpile.util import *
from mailpile.plugins.migrate import Migrate
from mailpile.plugins.tags import AddTag


_plugins = PluginManager(builtin=__file__)


##[ Commands ]################################################################

class SetupMagic(Command):
    """Perform initial setup"""
    SYNOPSIS = (None, None, None, None)
    ORDER = ('Internals', 0)
    LOG_PROGRESS = True

    TAGS = {
        'New': {
            'type': 'unread',
            'label': False,
            'display': 'invisible',
            'icon': 'icon-new',
            'label_color': '03-gray-dark',
            'name': _('New'),
        },
        'Inbox': {
            'type': 'inbox',
            'display': 'priority',
            'display_order': 2,
            'icon': 'icon-inbox',
            'label_color': '06-blue',
            'name': _('Inbox'),
        },
        'Blank': {
            'type': 'blank',
            'flag_editable': True,
            'display': 'invisible',
            'name': _('Blank'),
        },
        'Drafts': {
            'type': 'drafts',
            'flag_editable': True,
            'display': 'priority',
            'display_order': 1,
            'icon': 'icon-compose',
            'label_color': '03-gray-dark',
            'name': _('Drafts'),
        },
        'Outbox': {
            'type': 'outbox',
            'display': 'priority',
            'display_order': 3,
            'icon': 'icon-outbox',
            'label_color': '06-blue',
            'name': _('Outbox'),
        },
        'Sent': {
            'type': 'sent',
            'display': 'priority',
            'display_order': 4,
            'icon': 'icon-sent',
            'label_color': '03-gray-dark',
            'name': _('Sent'),
        },
        'Spam': {
            'type': 'spam',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 5,
            'icon': 'icon-spam',
            'label_color': '10-orange',
            'name': _('Spam'),
        },
        'MaybeSpam': {
            'display': 'invisible',
            'icon': 'icon-spam',
            'label_color': '10-orange',
            'name': _('MaybeSpam'),
        },
        'Ham': {
            'type': 'ham',
            'display': 'invisible',
            'name': _('Ham'),
        },
        'Trash': {
            'type': 'trash',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 6,
            'icon': 'icon-trash',
            'label_color': '13-brown',
            'name': _('Trash'),
        },
        # These are magical tags that perform searches and show
        # messages in contextual views.
        'All Mail': {
            'type': 'tag',
            'icon': 'icon-logo',
            'label_color': '06-blue',
            'search_terms': 'all:mail',
            'name': _('All Mail'),
            'display_order': 1000,
        },
        'Photos': {
            'type': 'tag',
            'icon': 'icon-photos',
            'label_color': '08-green',
            'search_terms': 'att:jpg',
            'name': _('Photos'),
            'template': 'photos',
            'display_order': 1001,
        },
        'Files': {
            'type': 'tag',
            'icon': 'icon-document',
            'label_color': '06-blue',
            'search_terms': 'has:attachment',
            'name': _('Files'),
            'template': 'files',
            'display_order': 1002,
        },
        'Links': {
            'type': 'tag',
            'icon': 'icon-links',
            'label_color': '12-red',
            'search_terms': 'http',
            'name': _('Links'),
            'display_order': 1003,
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

    def setup_command(self, session):
        # Stop the workers...
        want_daemons = session.config.cron_worker is not None
        session.config.stop_workers()

        # Perform any required migrations
        Migrate(session).run(before_setup=True, after_setup=False)

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
        accepted_keys = []
        if gnupg.is_available():
            keys = gnupg.list_secret_keys()
            for key, details in keys.iteritems():
                # Ignore revoked/expired keys.
                if ("revocation-date" in details and
                    details["revocation-date"] <=
                        date.today().strftime("%Y-%m-%d")):
                    continue

                accepted_keys.append(key)
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
                if (session.config.prefs.gpg_recipient in (None, '', '!CREATE')
                       and details["capabilities_map"][0]["encrypt"]):
                    session.config.prefs.gpg_recipient = key
                    session.ui.notify(_('Encrypting config to %s') % key)
                if session.config.prefs.crypto_policy == 'none':
                    session.config.prefs.crypto_policy = 'openpgp-sign'

            if len(accepted_keys) == 0:
                # FIXME: Start background process generating a key once a user
                #        has supplied a name and e-mail address.
                pass

        else:
            session.ui.warning(_('Oh no, PGP/GPG support is unavailable!'))

        if (session.config.prefs.gpg_recipient not in (None, '', '!CREATE')
                and not (self._idx() and self._idx().INDEX)
                and not session.config.master_key
                and not session.config.prefs.obfuscate_index):
            #
            # This secret is arguably the most critical bit of data in the
            # app, it is used as an encryption key and to seed hashes in
            # a few places.  As such, the user may need to type this in
            # manually as part of data recovery, so we keep it reasonably
            # sized and devoid of confusing chars.
            #
            # The strategy below should give about 281 bits of randomness:
            #
            #   import math
            #   math.log((25 + 25 + 8) ** (12 * 4), 2) == 281.183...
            #
            secret = ''
            chars = 12 * 4
            while len(secret) < chars:
                secret = sha512b64(os.urandom(1024),
                                   '%s' % session.config,
                                   '%s' % time.time())
                secret = CleanText(secret,
                                   banned=CleanText.NONALNUM + 'O01l'
                                   ).clean[:chars]
            session.config.master_key = secret
            session.config.prefs.obfuscate_index = True
            session.config.prefs.index_encrypted = True
            session.ui.notify(_('Obfuscating search index and enabling '
                                'indexing of encrypted e-mail. '))

        # Perform any required migrations
        Migrate(session).run(before_setup=False, after_setup=True)

        session.config.save()
        session.config.prepare_workers(session, daemons=want_daemons)

        return self._success(_('Performed initial Mailpile setup'))

    def command(self):
        session = self.session
        if session.config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))
        return self.setup_command(session)


class TestableWebbable(SetupMagic):
    HTTP_AUTH_REQUIRED = False
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        '_path': 'Redirect path'
    }
    HTTP_POST_VARS = {
        'testing': 'Yes or No, if testing',
        'advance': 'Yes or No, advance setup flow',
    }
    TRUTHY = {
        '0': False, 'no': False, 'fuckno': False, 'false': False,
        '1': True, 'yes': True, 'hellyeah': True, 'true': True,
    }

    def _advance(self):
        from mailpile.urlmap import UrlMap

        path = self.data.get('_path', [None])[0]
        data = dict([(k, v) for k, v in self.data.iteritems()
                     if k not in self.HTTP_POST_VARS
                     and k not in ('_method',)])

        if path and path != '/%s/' % Setup.SYNOPSIS[2]:
            nxt = Setup.Next(self.session.config, None)
            if nxt:
                url = '/%s/' % nxt.SYNOPSIS[2]
            else:
                # Use the same redirection logic as the Authenticator
                mailpile.auth.Authenticate.RedirectBack(path, data)
        else:
            url = '/%s/' % Setup.Next(self.session.config, SetupWelcome
                                      ).SYNOPSIS[2]

        qs = urlencode([(k, v) for k, vl in data.iteritems() for v in vl])
        raise UrlRedirectException(''.join([url, '?%s' % qs if qs else '']))

    def _success(self, message, result=True, advance=False):
        if (advance or
                self.data.get('advance', [''])[0].lower() in self.TRUTHY):
            self._advance()
        return SetupMagic._success(self, message, result=result)

    def _testing(self):
        self._testing_yes(lambda: True)
        return (self.testing is not None)

    def _testing_yes(self, method, *args, **kwargs):
        testination = self.data.get('testing')
        if testination:
            self.testing = random.randint(0, 1)
            if testination[0].lower() in self.TRUTHY:
                self.testing = self.TRUTHY[testination[0].lower()]
            return self.testing
        self.testing = None
        return method(*args, **kwargs)

    def _testing_data(self, method, tdata, *args, **kwargs):
        result = self._testing_yes(method, *args, **kwargs) or []
        return (result
                if (self.testing is None) else
                (self.testing and tdata or []))

    def setup_command(self, session):
        raise Exception('FIXME')


class SetupCheckKeychain(TestableWebbable):
    """Gather some stats about the local keychain"""
    SYNOPSIS = (None, None, 'setup/check_keychain', None)

    def _have_gnupg_keyring(self):
        raise Exception('FIXME')

    def setup_command(self, session):
        accepted_keys = []
        if not self._testing_yes(self._have_gnupg_keyring):
            return self._error(_('Oh noes, we have no GnuPG'))

        if self._testing():
            return self._success(_('Found a keychain'), result={
                'private_keys': 5,
                'public_keys': 31337
            })

        raise Exception('FIXME')


class SetupCreateNewKey(SetupCheckKeychain):
    """Create a new PGP key and keychain"""
    SYNOPSIS = (None, 'setup/create_key', 'setup/create_key', None)

    def setup_command(self, session):
        if not self._testing_yes(self._have_gnupg_keyring):
            return self._error(_('Oh noes, we have no GnuPG'))

        if self.testing:
            time.sleep(90)
            return self._success(_('Created a new key'), result={
                'type': 'OpenPGP',
                'bits': 42,
                'algorithm': 'Ballistic Carve',
                'fingerprint': '0123456789ABCDEF0123456789ABCDEF'
            })

        raise Exception('FIXME')


class SetupGuessEmails(TestableWebbable):
    """Discover and guess which emails this user has"""
    SYNOPSIS = (None, 'setup/guess_emails', 'setup/guess_emails', None)

    def _get_tbird_emails(self):
        raise Exception('FIXME')

    def _get_macmail_emails(self):
        raise Exception('FIXME')

    def _get_gnupg_emails(self):
        raise Exception('FIXME')

    def setup_command(self, session):
        # FIXME: Implement and add more potential sources of e-mails
        macmail_emails = self._testing_data(self._get_macmail_emails, ['1'])
        tbird_emails = self._testing_data(self._get_tbird_emails, ['1'])
        gnupg_emails = self._testing_data(self._get_gnupg_emails, [
            {
                'name': 'Innocent Adventurer',
                'address': 'luncheon@meat.trunch.eon',
                'source': 'The Youtubes'
            },
            {
                'name': 'Chelsea Manning',
                'address': 'chelsea@manning.org',
                'source': 'Internal Tribute Store'
            },
            {
                'name': 'MUSCULAR',
                'address': 'muscular@nsa.gov',
                'source': 'Well funded adversaries'
            }
        ])

        emails = macmail_emails + tbird_emails + gnupg_emails
        if not emails:
            return self._error(_('No e-mail addresses found'))
        else:
            return self._success(_('Discovered e-mail addresses'), {
                'emails': emails
            })


class SetupTestEmailSettings(TestableWebbable):
    """Test the settings for an e-mail account"""
    SYNOPSIS = (None, 'setup/test_mailroute', 'setup/test_mailroute', None)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'protocol': 'IMAP, POP3 or SMTP',
        'username': 'User name',
        'password': 'Password',
        'host': 'Server host name',
        'port': 'Server port number',
        'use_tls': 'Use TLS to connect'
    })

    def _test_settings(self):
        raise Exception('FIXME')

    def setup_command(self, session):
        # This will throw a keyerror if any of the settings are missing
        try:
            settings = dict([(p, self.data[p][0]) for p in
                             set(self.HTTP_POST_VARS.keys())
                             - set(['testing'])])
        except KeyError:
            return self._error(_('Incomplete settings'))

        if self._testing_yes(self._test_settings):
            return self._success(_('That all worked'))
        else:
            return self._error(_('Invalid settings'))



class SetupGetEmailSettings(TestableWebbable):
    """Guess server details for an e-mail address"""
    SYNOPSIS = (None, 'setup/email_servers', 'setup/email_servers', None)
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = dict_merge(TestableWebbable.HTTP_QUERY_VARS, {
        'email': 'E-mail address'
    })
    TEST_DATA = {
        'imap_host': 'imap.wigglebonk.com',
        'imap_port': 993,
        'imap_tls': True,
        'pop3_host': 'pop3.wigglebonk.com',
        'pop3_port': 110,
        'pop3_tls': False,
        'smtp_host': 'smtp.wigglebonk.com',
        'smtp_port': 465,
        'smtp_tls': False
    }

    def _get_domain_settings(self, domain):
        raise Exception('FIXME')

    def setup_command(self, session):
        results = {}
        for email in list(self.args) + self.data.get('email'):
            settings = self._testing_data(self._get_domain_settings,
                                          self.TEST_DATA, email)
            if settings:
                results[email] = settings
        if results:
            self._success(_('Found settings for %d addresses'), results)
        else:
            self._error(_('No settings found'))


class SetupWelcome(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/welcome', None)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'language': 'Language selection'
    })

    def setup_command(self, session):
        config = session.config
        if self.data.get('_method') == 'POST' or self._testing():
            language = self.data.get('language', [''])[0]
            if language:
                try:
                    i18n = lambda: ActivateTranslation(session, config,
                                                       language)
                    if not self._testing_yes(i18n):
                        raise ValueError('Failed to configure i18n')
                    config.prefs.language = language
                    if not self._testing():
                        self._background_save(config=True)
                except ValueError:
                    return self._error(_('Invalid language: %s') % language)

        results = {
            'language': config.prefs.language
        }
        return self._success(_('Welcome to Mailpile!'), results)


class SetupCrypto(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/crypto', None)

    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'choose_key': 'Select an existing key to use',
        'passphrase': 'Specify a passphrase',
        'index_encrypted': 'y/n: index encrypted mail?',
        'obfuscate_index': 'y/n: obfuscate keywords?',
        'encrypt_mail': 'y/n: encrypt locally stored mail?',
        'encrypt_index': 'y/n: encrypt search index?',
        'encrypt_vcards': 'y/n: encrypt vcards?',
        'encrypt_events': 'y/n: encrypt event log?',
        'encrypt_misc': 'y/n: encrypt plugin and misc data?'
    })
    TEST_DATA = {}

    def setup_command(self, session):
        changed = authed = False
        results = {
            'secret_keys': self._gnupg().list_secret_keys(),
        }
        error_info = None

        if self.data.get('_method') == 'POST' or self._testing():
            for key in self.HTTP_POST_VARS.keys():
                if key in (['choose_key', 'passphrase'] +
                           TestableWebbable.HTTP_POST_VARS.keys()):
                    continue
                try:
                    val = self.data.get(key, [''])[0]
                    if val:
                        session.config.prefs[key] = self.TRUTHY[val.lower()]
                        changed = True
                except (ValueError, KeyError):
                    error_info = (_('Invalid preference'), {
                        'invalid_setting': True,
                        'variable': key
                    })
                    break

            choose_key = self.data.get('choose_key', [''])[0]
            if choose_key and not error_info:
                if choose_key not in results['secret_keys']:
                    error_info = (_('Invalid passphrase'), {
                        'invalid_key': True,
                        'chosen_key': choose_key
                    })
                else:
                    session.config.prefs.gpg_recipient = choose_key
                    changed = True

            try:
                passphrase = self.data.get('passphrase', [''])[0]
                if passphrase and not error_info:
                    sps = mailpile.auth.VerifyAndStorePassphrase(
                        session.config, passphrase=passphrase)
                    session.config.gnupg_passphrase.data = sps.data
                    if not session.config.prefs.gpg_recipient:
                        session.config.prefs.gpg_recipient = '!CREATE'
                    changed = results['updated_passphrase'] = True
            except AssertionError:
                error_info = (_('Invalid passphrase'), {
                    'invalid_passphrase': True,
                    'chosen_key': session.config.prefs.gpg_recipient
                })

        results.update({
            'chosen_key': session.config.prefs.gpg_recipient,
            'prefs': {
                'index_encrypted': session.config.prefs.index_encrypted,
                'obfuscate_index': session.config.prefs.obfuscate_index,
                'encrypt_mail': session.config.prefs.encrypt_mail,
                'encrypt_index': session.config.prefs.encrypt_index,
                'encrypt_vcards': session.config.prefs.encrypt_vcards,
                'encrypt_events': session.config.prefs.encrypt_events,
                'encrypt_misc': session.config.prefs.encrypt_misc
            }
        })

        if changed:
            self._background_save(config=True)

        if error_info:
            return self._error(error_info[0],
                               info=error_info[1], result=results)
        elif changed:
            return self._success(_('Updated crypto preferences'), results)
        else:
            return self._success(_('Configure crypto preferences'), results)


class SetupProfiles(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/profiles', None)

    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = dict_merge(TestableWebbable.HTTP_QUERY_VARS, {
    })
    TEST_DATA = {}

    def setup_command(self, session):
        results = {}
        return self._success(_(''), results)


class SetupRoutes(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/routes', None)

    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = dict_merge(TestableWebbable.HTTP_QUERY_VARS, {
    })
    TEST_DATA = {}

    def setup_command(self, session):
        results = {}
        return self._success(_(''), results)


class SetupSources(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/sources', None)

    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = dict_merge(TestableWebbable.HTTP_QUERY_VARS, {
    })
    TEST_DATA = {}

    def setup_command(self, session):
        results = {}
        return self._success(_(''), results)


class Setup(SetupMagic):
    """Enter setup flow"""
    SYNOPSIS = (None, 'setup', 'setup', None)

    ORDER = ('Internals', 0)
    LOG_PROGRESS = True
    HTTP_CALLABLE = ('GET',)

    @classmethod
    def Next(cls, config, final):
        if not config.loaded_config:
            return final

        for guard, step in [
            (config.prefs.language, SetupWelcome),
            (config.prefs.gpg_recipient, SetupCrypto),
            #(config.prefs.default_email, SetupProfiles),
            #(config.routes, SetupRoutes),
            #(config.sources, SetupSources),
        ]:
            if not guard:
                return step

        return final

    def setup_command(self, session):
        if '_method' in self.data:
            return self.success(_('Entering setup flow'), advance=True)
        else:
            return SetupMagic.setup_command(self, session)


_plugins.register_commands(SetupMagic,
                           SetupCheckKeychain, SetupCreateNewKey,
                           SetupGuessEmails, SetupTestEmailSettings,
                           SetupGetEmailSettings,
                           SetupWelcome,
                           SetupCrypto,
                           SetupProfiles,
                           SetupRoutes,
                           SetupSources,
                           Setup)
