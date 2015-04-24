import os
import random
import sys
import datetime
from urllib import urlencode

import mailpile.auth
from mailpile.defaults import CONFIG_RULES
from mailpile.i18n import ListTranslations, ActivateTranslation, gettext
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.plugins import PLUGINS
from mailpile.plugins.contacts import AddProfile
from mailpile.plugins.contacts import ListProfiles
from mailpile.plugins.migrate import Migrate
from mailpile.plugins.tags import AddTag
from mailpile.commands import Command
from mailpile.config import SecurePassphraseStorage
from mailpile.crypto.gpgi import GnuPG, SignatureInfo, EncryptionInfo
from mailpile.crypto.gpgi import GnuPGKeyGenerator, GnuPGKeyEditor
from mailpile.httpd import BLOCK_HTTPD_LOCK, Idle_HTTPD
from mailpile.smtp_client import SendMail, SendMailError
from mailpile.urlmap import UrlMap
from mailpile.ui import Session, SilentInteraction
from mailpile.util import *


_ = lambda s: s
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
            'flag_msg_only': True,
            'display': 'invisible',
            'name': _('Blank'),
        },
        'Drafts': {
            'type': 'drafts',
            'flag_editable': True,
            'flag_msg_only': True,
            'display': 'priority',
            'display_order': 1,
            'icon': 'icon-compose',
            'label_color': '03-gray-dark',
            'name': _('Drafts'),
        },
        'Outbox': {
            'type': 'outbox',
            'flag_msg_only': True,
            'display': 'priority',
            'display_order': 3,
            'icon': 'icon-outbox',
            'label_color': '06-blue',
            'name': _('Outbox'),
        },
        'Sent': {
            'type': 'sent',
            'flag_msg_only': True,
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
        'Conversations': {
            'type': 'tag',
            'icon': 'icon-forum',
            'label_color': '05-blue-light',
            'search_terms': 'in:mp_rpl',
            'name': _('Conversations'),
            'template': 'conversations',
            'display_order': 1001,
        },
        'Photos': {
            'type': 'tag',
            'icon': 'icon-photos',
            'label_color': '08-green',
            'search_terms': 'att:jpg to:me',
            'name': _('Photos'),
            'template': 'photos',
            'display_order': 1002,
        },
        'Files': {
            'type': 'tag',
            'icon': 'icon-document',
            'label_color': '06-blue',
            'search_terms': 'has:attachment to:me',
            'name': _('Files'),
            'template': 'files',
            'display_order': 1003,
        },
        'Links': {
            'type': 'tag',
            'icon': 'icon-links',
            'label_color': '12-red',
            'search_terms': 'http to:me',
            'name': _('Links'),
            'display_order': 1004,
        },
        # These are internal tags, used for tracking user actions on
        # messages, as input for machine learning algorithms. These get
        # automatically added, and may be automatically removed as well
        # to keep the working sets reasonably small.
        'mp_rpl': {'type': 'replied', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_fwd': {'type': 'fwded', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_tag': {'type': 'tagged', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_read': {'type': 'read', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_ham': {'type': 'ham', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
    }

    def basic_app_config(self, session,
                         save_and_update_workers=True,
                         want_daemons=True):
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
                    'flag_msg_only': True,
                    'display': 'invisible',
                    'label': False,
                })

        if 'New' in created:
            session.ui.notify(_('Created default tags'))

        # Import all the basic plugins
        reload_config = False
        for plugin in PLUGINS:
            if plugin not in session.config.sys.plugins:
                session.config.sys.plugins.append(plugin)
                reload_config = True
        for plugin in session.config.plugins.WANTED:
            if plugin in session.config.plugins.available():
                session.config.sys.plugins.append(plugin)
        if reload_config:
            with session.config._lock:
                session.config.save()
                session.config.load(session)

        try:
            # If spambayes is not installed, this will fail
            import mailpile.plugins.autotag_sb
            if 'autotag_sb' not in session.config.sys.plugins:
                session.config.sys.plugins.append('autotag_sb')
                session.ui.notify(_('Enabling spambayes autotagger'))
        except ImportError:
            session.ui.warning(_('Please install spambayes '
                                 'for super awesome spam filtering'))

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

        if save_and_update_workers:
            session.config.save()
            session.config.prepare_workers(session, daemons=want_daemons)

    def setup_command(self, session, do_gpg_stuff=False):
        do_gpg_stuff = do_gpg_stuff or ('do_gpg_stuff' in self.args)

        # Stop the workers...
        want_daemons = session.config.cron_worker is not None
        session.config.stop_workers()

        # Perform any required migrations
        Migrate(session).run(before_setup=True, after_setup=False)

        # Basic app config, tags, plugins, etc.
        self.basic_app_config(session,
                              save_and_update_workers=False,
                              want_daemons=want_daemons)

        # Assumption: If you already have secret keys, you want to
        #             use the associated addresses for your e-mail.
        #             If you don't already have secret keys, you should have
        #             one made for you, if GnuPG is available.
        #             If GnuPG is not available, you should be warned.
        if do_gpg_stuff:
            gnupg = GnuPG(None)
            accepted_keys = []
            if gnupg.is_available():
                keys = gnupg.list_secret_keys()
                cutoff = (datetime.date.today() + datetime.timedelta(days=365)
                          ).strftime("%Y-%m-%d")
                for key, details in keys.iteritems():
                    # Ignore revoked/expired/disabled keys.
                    revoked = details.get('revocation_date')
                    expired = details.get('expiration_date')
                    if (details.get('disabled') or
                            (revoked and revoked <= cutoff) or
                            (expired and expired <= cutoff)):
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
                           and details["capabilities_map"]["encrypt"]):
                        session.config.prefs.gpg_recipient = key
                        session.ui.notify(_('Encrypting config to %s') % key)
                    if session.config.prefs.crypto_policy == 'none':
                        session.config.prefs.crypto_policy = 'openpgp-sign'

                if len(accepted_keys) == 0:
                    # FIXME: Start background process generating a key once a
                    #        user has supplied a name and e-mail address.
                    pass

            else:
                session.ui.warning(_('Oh no, PGP/GPG support is unavailable!'))

        # If we have a GPG key, but no master key, create it
        self.make_master_key()

        # Perform any required migrations
        Migrate(session).run(before_setup=False, after_setup=True)

        session.config.save()
        session.config.prepare_workers(session, daemons=want_daemons)

        return self._success(_('Performed initial Mailpile setup'))

    def make_master_key(self):
        session = self.session
        if (session.config.prefs.gpg_recipient not in (None, '', '!CREATE')
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
            if self._idx() and self._idx().INDEX:
                session.ui.warning(_('Unable to obfuscate search index '
                                     'without losing data. Not indexing '
                                     'encrypted mail.'))
            else:
                session.config.prefs.obfuscate_index = True
                session.config.prefs.index_encrypted = True
                session.ui.notify(_('Obfuscating search index and enabling '
                                    'indexing of encrypted e-mail. Yay!'))
            return True
        else:
            return False

    def command(self, *args, **kwargs):
        session = self.session
        if session.config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))
        return self.setup_command(session, *args, **kwargs)


class TestableWebbable(SetupMagic):
    HTTP_AUTH_REQUIRED = 'Maybe'
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
        path = self.data.get('_path', [None])[0]
        data = dict([(k, v) for k, v in self.data.iteritems()
                     if k not in self.HTTP_POST_VARS
                     and k not in ('_method',)])

        nxt = Setup.Next(self.session.config, None, needed_auth=False)
        if nxt:
            url = '/%s/' % nxt.SYNOPSIS[2]
        elif path and path != '/%s/' % Setup.SYNOPSIS[2]:
            # Use the same redirection logic as the Authenticator
            mailpile.auth.Authenticate.RedirectBack(path, data)
        else:
            url = '/'

        qs = urlencode([(k, v) for k, vl in data.iteritems() for v in vl])
        raise UrlRedirectException(''.join([self.session.config.sys.subdirectory, url, '?%s' % qs if qs else '']))

    def _success(self, message, result=True, advance=False):
        if (advance or
                self.TRUTHY.get(self.data.get('advance', ['no'])[0].lower())):
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

    def bg_setup_stage_1(self):
        # Wait a bit, so the user has something to look at befor we
        # block the web server and do real work.
        time.sleep(2)

        # Intial configuration of app goes here...
        if not self.session.config.tags:
            with BLOCK_HTTPD_LOCK, Idle_HTTPD(allowed=0):
                self.basic_app_config(self.session)

        # Next, if we have any secret GPG keys, extract all the e-mail
        # addresses and create a profile for each one.
        with BLOCK_HTTPD_LOCK, Idle_HTTPD(allowed=0):
            SetupProfiles(self.session).auto_create_profiles()

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

            config.slow_worker.add_unique_task(
                session, 'Setup, Stage 1', lambda: self.bg_setup_stage_1())

        results = {
            'languages': ListTranslations(config),
            'language': config.prefs.language
        }
        return self._success(_('Welcome to Mailpile!'), results)


class SetupCrypto(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/crypto', None)

    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'choose_key': 'Select an existing key to use',
        'passphrase': 'Specify a passphrase',
        'passphrase_confirm': 'Confirm the passphrase',
        'index_encrypted': 'y/n: index encrypted mail?',
#       'obfuscate_index': 'y/n: obfuscate keywords?',  # Omitted do to DANGER
        'encrypt_mail': 'y/n: encrypt locally stored mail?',
        'encrypt_index': 'y/n: encrypt search index?',
        'encrypt_vcards': 'y/n: encrypt vcards?',
        'encrypt_events': 'y/n: encrypt event log?',
        'encrypt_misc': 'y/n: encrypt plugin and misc data?'
    })
    TEST_DATA = {}

    def list_secret_keys(self):
        cutoff = (datetime.date.today() + datetime.timedelta(days=365)
                  ).strftime("%Y-%m-%d")
        keylist = {}
        for key, details in self._gnupg().list_secret_keys().iteritems():
            # Ignore (soon to be) revoked/expired/disabled keys.
            revoked = details.get('revocation_date')
            expired = details.get('expiration_date')
            if (details.get('disabled') or
                    (revoked and revoked <= cutoff) or
                    (expired and expired <= cutoff)):
                continue

            # Ignore keys that cannot both encrypt and sign
            caps = details["capabilities_map"]
            if not caps["encrypt"] or not caps["sign"]:
                continue

            keylist[key] = details
        return keylist

    def gpg_key_ready(self, gpg_keygen):
        if not gpg_keygen.failed:
            self.session.config.prefs.gpg_recipient = gpg_keygen.generated_key
            self.make_master_key()
            self._background_save(config=True)
            self.save_profiles_to_key()

    def save_profiles_to_key(self, key_id=None, add_all=False, now=False,
                                   profiles=None):
        if key_id is None:
            if (Setup.KEY_CREATING_THREAD and
                    not Setup.KEY_CREATING_THREAD.failed):
                key_id = Setup.KEY_CREATING_THREAD.generated_key
                add_all = True

        if not add_all:
            self.session.ui.warning('FIXME: Not updating GPG key!')
            return

        if key_id is not None:
            uids = []
            data = ListProfiles(self.session).run().result
            for profile in data['profiles']:
                uids.append({
                    'name': profile["fn"],
                    'email': profile["email"][0]["email"],
                    'comment': profile.get('note', '')
                })
            if not uids:
                return

            editor = GnuPGKeyEditor(key_id, set_uids=uids,
                                    sps=self.session.config.gnupg_passphrase,
                                    deletes=max(10, 2*len(uids)))

            def start_editor(*unused_args):
                with Setup.KEY_WORKER_LOCK:
                    Setup.KEY_EDITING_THREAD = editor
                    editor.start()

            with Setup.KEY_WORKER_LOCK:
                 if now:
                     start_editor()
                 elif Setup.KEY_EDITING_THREAD is not None:
                     Setup.KEY_EDITING_THREAD.on_complete('edit keys',
                                                          start_editor)
                 elif Setup.KEY_CREATING_THREAD is not None:
                     Setup.KEY_CREATING_THREAD.on_complete('edit keys',
                                                           start_editor)
                 else:
                     start_editor()

    def setup_command(self, session):
        changed = authed = False
        results = {
            'secret_keys': self.list_secret_keys(),
        }
        error_info = None

        if self.data.get('_method') == 'POST' or self._testing():

            # 1st, are we choosing or creating a new key?
            choose_key = self.data.get('choose_key', [''])[0]
            if choose_key and not error_info:
                if (choose_key not in results['secret_keys'] and
                        choose_key != '!CREATE'):
                    error_info = (_('Invalid key'), {
                        'invalid_key': True,
                        'chosen_key': choose_key
                    })

            # 2nd, check authentication...
            #
            # FIXME: Creating a new key will allow a malicious actor to
            #        bypass authentication and change settings.
            #
            try:
                passphrase = self.data.get('passphrase', [''])[0]
                passphrase2 = self.data.get('passphrase_confirm', [''])[0]
                chosen_key = ((not error_info) and choose_key
                              ) or session.config.prefs.gpg_recipient

                if not error_info:
                    assert(passphrase == passphrase2)
                    if chosen_key == '!CREATE':
                        assert(passphrase != '')
                        sps = SecurePassphraseStorage(passphrase)
                    elif chosen_key:
                        sps = mailpile.auth.VerifyAndStorePassphrase(
                            session.config,
                            passphrase=passphrase,
                            key=chosen_key)
                    else:
                        sps = mailpile.auth.VerifyAndStorePassphrase(
                            session.config, passphrase=passphrase)
                    if not chosen_key:
                        choose_key = '!CREATE'
                    results['updated_passphrase'] = True
                    session.config.gnupg_passphrase.data = sps.data
                    mailpile.auth.SetLoggedIn(self)
            except AssertionError:
                error_info = (_('Invalid passphrase'), {
                    'invalid_passphrase': True,
                    'chosen_key': session.config.prefs.gpg_recipient
                })

            # 3rd, if necessary master key and/or GPG key
            with BLOCK_HTTPD_LOCK, Idle_HTTPD():
                if choose_key and not error_info:
                    session.config.prefs.gpg_recipient = choose_key
                    # FIXME: This should probably only happen if the GPG
                    #        key was successfully created.
                    self.make_master_key()
                    changed = True

                with Setup.KEY_WORKER_LOCK:
                    if ((not error_info) and
                            (session.config.prefs.gpg_recipient
                             == '!CREATE') and
                            (Setup.KEY_CREATING_THREAD is None or
                             Setup.KEY_CREATING_THREAD.failed)):
                        gk = GnuPGKeyGenerator(
                            sps=session.config.gnupg_passphrase,
                            on_complete=('notify',
                                         lambda: self.gpg_key_ready(gk)))
                        Setup.KEY_CREATING_THREAD = gk
                        Setup.KEY_CREATING_THREAD.start()

            # Finally we update misc. settings
            for key in self.HTTP_POST_VARS.keys():
                # FIXME: This should probably only happen if the GPG
                #        key was successfully created.

                # Continue iff all is well...
                if error_info:
                    break
                if key in (['choose_key', 'passphrase', 'passphrase_confirm'] +
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

        results.update({
            'creating_key': (Setup.KEY_CREATING_THREAD is not None and
                             Setup.KEY_CREATING_THREAD.running),
            'creating_failed': (Setup.KEY_CREATING_THREAD is not None and
                                Setup.KEY_CREATING_THREAD.failed),
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


class SetupProfiles(SetupCrypto):
    SYNOPSIS = (None, None, 'setup/profiles', None)

    HTTP_AUTH_REQUIRED = True
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = dict_merge(TestableWebbable.HTTP_QUERY_VARS, {
    })
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'email': 'Create a profile for this e-mail address',
        'name': 'Name associated with this e-mail',
        'note': 'Profile note',
        'pass': 'Password for remote accounts',
        'route_id': 'Route ID for sending mail',
    })
    TEST_DATA = {}

    # This is where we cache the passwords we are given, for use later.
    # This is deliberately made a singleton on the class.
    PASSWORD_CACHE = {}

    def _auto_configurable(self, email):
        # FIXME: Actually look things up, this is super lame
        return email.endswith('@gmail.com')

    def get_profiles(self, secret_keys=None):
        data = ListProfiles(self.session).run().result
        profiles = {}
        for rid, ofs in data["rids"].iteritems():
            profile = data["profiles"][ofs]
            email = profile["email"][0]["email"]
            name = profile["fn"]
            note = profile.get('note', '')
            profiles[rid] = {
                "name": name,
                "note": note,
                "pgp_keys": [],  # FIXME
                "email": email,
                "route_id": profile.get('x-mailpile-profile-route', ''),
                "photo": profile.get('photo', [{}])[0].get('photo', ''),
                "auto_configurable": self._auto_configurable(email)
            }
        for key, info in (secret_keys or {}).iteritems():
            for uid in info['uids']:
                email = uid.get('email')
                if email in profiles:
                    profiles[email]["pgp_keys"].append(key)
        return profiles

    def discover_new_email_addresses(self, profiles):
        addresses = {}
        existing = set([p['email'] for p in profiles.values()])
        for key, info in self.list_secret_keys().iteritems():
            for uid in info['uids']:
                email = uid.get('email')
                note = uid.get('comment')
                if email:
                    if email in existing:
                        continue
                    if email not in addresses:
                        addresses[email] = {'pgp_keys': [],
                                            'name': '', 'note': ''}
                    ai = addresses[email]
                    name = uid.get('name')
                    ai['name'] = name if name else ai['name']
                    ai['note'] = note if note else ai['note']
                    ai['pgp_keys'].append(key)

        # FIXME: Scan Thunderbird and MacMail for e-mails, other apps...

        return addresses

    def auto_create_profiles(self):
        new_emails = self.discover_new_email_addresses(self.get_profiles())
        for email, info in new_emails.iteritems():
            AddProfile(self.session, data={
                '_method': 'POST',
                'email': [email],
                'note': [info["note"]],
                'name': [info['name']]
            }).run()

    def _result(self):
        profiles = self.get_profiles()
        return {
            'new_emails': self.discover_new_email_addresses(profiles),
            'profiles': profiles,
            'routes': self.session.config.routes,
            'default_email': self.session.config.prefs.default_email
        }

    def setup_command(self, session):
        changed = False
        if self.data.get('_method') == 'POST' or self._testing():
            name, email, note, pwd = (self.data.get(k, [None])[0] for k in
                                      ('name', 'email', 'note', 'pass'))
            if email:
                rv = AddProfile(session, data=self.data).run()
                if rv.status == 'success':
                    #
                    # FIXME: We need to fire off a background process to
                    #        try and auto-discover routes and sources.
                    #
                    if not session.config.prefs.default_email:
                        session.config.prefs.default_email = email
                        changed = True
                    self.save_profiles_to_key()
                else:
                    return self._error(_('Failed to add profile'),
                                       info=rv.error_info,
                                       result=self._result())
            if email and pwd:
                sps = SecurePassphraseStorage(pwd)
                SetupProfiles.PASSWORD_CACHE[email] = sps

            result = self._result()
            if not result['default_email']:
                profiles = result['profiles'].values()
                profiles.sort(key=lambda p: (len(p['pgp_keys']),
                                             len(p['name'])))
                e = result['default_email'] = profiles[-1]['email']
                session.config.prefs.default_email = e
                changed = True
        else:
            result = self._result()

        if changed:
            self._background_save(config=True)

        return self._success(_('Your profiles'), result)


class SetupConfigureKey(SetupProfiles):
    SYNOPSIS = (None, None, 'setup/configure_key', None)

    HTTP_AUTH_REQUIRED = True
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = dict_merge(TestableWebbable.HTTP_QUERY_VARS, {
    })
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
    })
    TEST_DATA = {}

    def _result(self):
        keylist = self.list_secret_keys()
        profiles = self.get_profiles(secret_keys=keylist)
        return {
            'secret_keys': keylist,
            'profiles': profiles,
        }

    def setup_command(self, session):

        # FIXME!

        return self._success(_('Configuring a key'), self._result())


class SetupTestRoute(SetupProfiles):
    SYNOPSIS = (None, None, 'setup/test_route', None)

    HTTP_AUTH_REQUIRED = True
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS,
                                dict((k, v[0]) for k, v in
                                     CONFIG_RULES['routes'][1].iteritems()),
                                {'route_id': 'ID of existing route'})
    TEST_DATA = {}

    def setup_command(self, session):

        if self.args:
            route_id = self.args[0]
        elif 'route_id' in self.data:
            route_id = self.data['route_id'][0]
        else:
            route_id = None

        if route_id:
            route = self.session.config.routes[route_id]
            assert(route)
        else:
            route = {}
            for k in CONFIG_RULES['routes'][1]:
                if k not in self.data:
                    pass
                elif CONFIG_RULES['routes'][1][k][1] in (int, 'int'):
                    route[k] = int(self.data[k][0])
                else:
                    route[k] = self.data[k][0]

        fromaddr = route.get('username', '')
        if '@' not in fromaddr:
            fromaddr = self.session.config.get_profile()['email']
        if not fromaddr or '@' not in fromaddr:
            fromaddr = '%s@%s' % (route.get('username', 'test'),
                                  route.get('host', 'example.com'))
        assert(fromaddr)

        error_info = {'error': _('Unknown error')}
        try:
            assert(SendMail(self.session, None,
                            [(fromaddr,
                              [fromaddr, 'test@mailpile.is'],
                              None,
                              [self.event])],
                            test_only=True, test_route=route))
            return self._success(_('Route is working'),
                                 result=route)
        except OSError:
            error_info = {'error': _('Invalid command'),
                          'invalid_command': True}
        except SendMailError, e:
            error_info = {'error': e.message,
                          'sendmail_error': True}
            error_info.update(e.error_info)
        except:
            import traceback
            traceback.print_exc()

        return self._error(_('Route is not working'),
                           result=route, info=error_info)


class Setup(TestableWebbable):
    """Enter setup flow"""
    SYNOPSIS = (None, 'setup', 'setup', '[do_gpg_stuff]')

    ORDER = ('Internals', 0)
    LOG_PROGRESS = True
    HTTP_CALLABLE = ('GET',)
    HTTP_AUTH_REQUIRED = True

    # These are a global, may be modified...
    KEY_WORKER_LOCK = CryptoRLock()
    KEY_CREATING_THREAD = None
    KEY_EDITING_THREAD = None

    @classmethod
    def _check_profiles(self, config):
        session = Session(config)
        session.ui = SilentInteraction(config)
        session.ui.block()
        data = ListProfiles(session).run().result
        okay = routes = bad = 0
        for rid, ofs in data["rids"].iteritems():
            profile = data["profiles"][ofs]
            if profile.get('email', None):
                okay += 1
                route_id = profile.get('x-mailpile-profile-route', '')
                if route_id:
                    if route_id in config.routes:
                        routes += 1
                    else:
                        bad += 1
            else:
                bad += 1
        return (routes > 0) and (okay > 0) and (bad == 0)

    @classmethod
    def _CHECKPOINTS(self, config):
        return [
            # Stage 0: Welcome: Choose app language
            ('language', lambda: config.prefs.language, SetupWelcome),

            # Stage 1: Crypto: Configure our master key stuff
            ('crypto', lambda: config.prefs.gpg_recipient, SetupCrypto),

            # Stage 2: Identity (via. single page install flow)
            ('profiles', lambda: self._check_profiles(config), Setup),

            # Stage 3: Routes (via. single page install flow)
            ('routes', lambda: config.routes, Setup),

            # Stage 4: Sources (via. single page install flow)
            ('sources', lambda: config.sources, Setup),

            # Stage 5: Is All Complete
            ('complete', lambda: config.web.setup_complete, Setup),

            # FIXME: Check for this too?
            #(lambda: config.prefs.crypto_policy != 'none', SetupConfigureKey),
        ]

    @classmethod
    def Next(cls, config, default, needed_auth=True):
        if not config.loaded_config:
            return default

        for name, guard, step in cls._CHECKPOINTS(config):
            auth_required = (step.HTTP_AUTH_REQUIRED is True
                             or (config.prefs.gpg_recipient and
                                 step.HTTP_AUTH_REQUIRED == 'Maybe'))
            if not guard():
                if (not needed_auth) or (not auth_required):
                    return step

        return default

    def setup_command(self, session):
        if '_method' in self.data:
            return self._success(_('Entering setup flow'), result=dict(
                ((c[0], c[1]() and True or False)
                 for c in self._CHECKPOINTS(session.config)
            )))
        else:
            return SetupMagic.setup_command(self, session)


_ = gettext
_plugins.register_commands(SetupMagic,
                           SetupGetEmailSettings,
                           SetupWelcome,
                           SetupCrypto,
                           SetupProfiles,
                           SetupConfigureKey,
                           SetupTestRoute,
                           Setup)
