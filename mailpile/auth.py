import time
from gettext import gettext as _
from urlparse import parse_qs, urlparse
from urllib import quote, urlencode

from mailpile.commands import Command
from mailpile.crypto.gpgi import GnuPG
from mailpile.plugins import PluginManager
from mailpile.util import *


class UserSession(object):
    EXPIRE_AFTER = 7 * 24 * 3600

    def __init__(self, ts=None, auth=None, data=None):
        self.ts = ts or time.time()
        self.auth = auth
        self.data = data or {}

    def is_expired(self, now=None):
        return (self.ts < (now or time.time()) - self.EXPIRE_AFTER)

    def update_ts(self):
        self.ts = time.time()


class UserSessionCache(dict):
    def delete_expired(self, now=None):
        now = now or time.time()
        for k in self.keys():
            if self[k].is_expired(now=now):
                del self[k]


def VerifyAndStorePassphrase(config, passphrase=None, sps=None):
    if passphrase and not sps:
        from mailpile.config import SecurePassphraseStorage
        sps = SecurePassphraseStorage(passphrase)
        passphrase = 'this probably does not really overwrite :-( '

    assert(sps is not None)
    gpg = GnuPG(use_agent=False)
    if gpg.is_available():
        gpg.passphrase = sps.get_reader()
        # FIXME: Sign with the gpg_recipient key, not just any key!
        assert(gpg.sign('Sign This!')[0] == 0)

    return sps


SESSION_CACHE = UserSessionCache()


class Authenticate(Command):
    """Authenticate a user (log in)"""
    SYNOPSIS = (None, 'login', 'auth/login', None)
    ORDER = ('Internals', 5)
    SPLIT_ARG = False
    IS_INTERACTIVE = True

    CONFIG_REQUIRED = False
    HTTP_AUTH_REQUIRED = False
    HTTP_STRICT_VARS = False
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = {
        'user': 'User to authenticate as',
        'pass': 'Password or passphrase'
    }

    def _do_redirect(self):
        if ('_path' in self.data and
               DeAuthenticate.SYNOPSIS[2] not in self.data['_path'][0] and
               self.SYNOPSIS[2] not in self.data['_path'][0]):
            qs = [(k, v) for k, vl in self.data.iteritems() for v in vl
                  if k not in ('_method', '_path', 'user', 'pass')]
            qs = urlencode(qs)
            url = ''.join([self.data['_path'][0], '?%s' % qs if qs else ''])
            raise UrlRedirectException(url)
        else:
            raise UrlRedirectException('/')

    def _logged_in(self, user=None, redirect=False):
        user = user or 'DEFAULT'

        session_id = self.session.ui.html_variables.get('http_session')
        if session_id:
            self.session.ui.debug('Logged in %s as %s' % (session_id, user))
            SESSION_CACHE[session_id] = UserSession(auth=user, data={
                't': '%x' % int(time.time()),
            })

        if redirect:
            self._do_redirect()

        return self._success(_('Hello world, welcome!'), result={
            'authenticated': user
        })

    def _do_login(self, user, password, load_index=False, redirect=False):
        session, config = self.session, self.session.config
        session_id = self.session.ui.html_variables.get('http_session')

        # This prevents folks from sending us a DEFAULT user (upper case),
        # which is an internal security bypass below.
        user = user and user.lower()

        if not user:
            try:
                # Verify the passphrase
                sps = VerifyAndStorePassphrase(config, passphrase=password)
                if sps:
                    # Store the varified passphrase
                    config.gnupg_passphrase.data = sps.data

                    # Load the config and index, if necessary
                    if not config.loaded_config:
                        self._config()
                        if load_index:
                            self._idx()
                        else:
                            pass  # FIXME: Start load in background

                    session.ui.debug('Good passphrase for %s' % session_id)
                    return self._logged_in(redirect=redirect)
                else:
                    session.ui.debug('No GnuPG, checking DEFAULT user')
                    # No GnuPG, see if there is a DEFAULT user in the config
                    user = 'DEFAULT'

            except (AssertionError, IOError):
                session.ui.debug('Bad passphrase for %s' % session_id)
                return self._error(_('Invalid passphrase, please try again'))

        if user in config.logins or user == 'DEFAULT':
            # FIXME: Salt and hash the password, check if it matches
            #        the entry in our user/password list (TODO).
            # NOTE:  This hack effectively disables auth without GnUPG
            if user == 'DEFAULT':
                session.ui.debug('FIXME: Unauthorized login allowed')
                return self._logged_in(redirect=redirect)
            raise Exception('FIXME')

        self._error(_('Incorrect username or password'))

    def command(self):
        session_id = self.session.ui.html_variables.get('http_session')

        if self.data.get('_method', '') == 'POST':
            if 'pass' in self.data:
                return self._do_login(self.data.get('user', [None])[0],
                                      self.data['pass'][0],
                                      redirect=True)

        elif not self.data:
            password = self.session.ui.get_password(_('Your password: '))
            return self._do_login(None, password, load_index=True)

        elif (session_id in SESSION_CACHE and
                SESSION_CACHE[session_id].auth and
                '_method' in self.data):
            self._do_redirect()

        return self._success(_('Please log in'))


class DeAuthenticate(Command):
    """De-authenticate a user (log out)"""
    SYNOPSIS = (None, 'logout', 'auth/logout', '[<session ID>]')
    ORDER = ('Internals', 5)
    SPLIT_ARG = False
    IS_INTERACTIVE = True
    CONFIG_REQUIRED = False
    HTTP_CALLABLE = ('GET', 'POST')

    def command(self):
        # FIXME: Should this only be a POST request?
        # FIXME: This needs CSRF protection.

        session_id = self.session.ui.html_variables.get('http_session')
        if self.args and not session_id:
            session_id = self.args[0]

        if session_id:
            try:
                self.session.ui.debug('Logging out %s' % session_id)
                del SESSION_CACHE[session_id]
                return self._success(_('Goodbye!'))
            except KeyError:
                pass

        return self._error(_('No session found!'))


plugin_manager = PluginManager(builtin=True)
plugin_manager.register_commands(Authenticate, DeAuthenticate)
