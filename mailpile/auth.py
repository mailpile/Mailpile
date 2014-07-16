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


SESSION_CACHE = UserSessionCache()


class Authenticate(Command):
    """Authenticate a user"""
    SYNOPSIS = (None, 'login', 'auth', None)
    ORDER = ('Internals', 5)
    SPLIT_ARG = False
    IS_INTERACTIVE = True

    CONFIG_REQUIRED = False
    HTTP_AUTH_REQUIRED = False
    HTTP_STRICT_VARS = False
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = {
        'logout': 'Log the user out',
        'user': 'User to authenticate as',
        'pass': 'Password or passphrase'
    }

    def _logged_in(self, user=None):
        user = user or 'DEFAULT'

        session_id = self.session.ui.html_variables['http_session']
        SESSION_CACHE[session_id] = UserSession(auth=user)

        if '_path' in self.data:
            qs = [(k, v) for k, vl in self.data.iteritems() for v in vl
                  if k not in ('_method', '_path', 'user', 'pass')]
            qs = urlencode(qs)
            url = ''.join([self.data['_path'][0], '?%s' % qs if qs else ''])
            raise UrlRedirectException(url)

        return self._success(_('Hello world, welcome!'), result={
            'authenticated': user
        })

    def _do_logout(self):
        pass

    def _do_login(self, user, password, load_index=False):
        session, config = self.session, self.session.config
        if not user:
            from mailpile.config import SecurePassphraseStorage
            sps = SecurePassphraseStorage(password)
            password = ''
            try:
                # Verify the passphrase
                gpg = GnuPG(use_agent=False)
                gpg.passphrase = sps.get_reader()
                assert(gpg.sign('Sign This!')[0] == 0)

                # Store the varified passphrase
                config.gnupg_passphrase.data = sps.data

                # Load the config and index, if necessary
                if not config.loaded_config:
                    self._config()
                    if load_index:
                        self._idx()
                    else:
                        pass  # FIXME: Start load in background

                return self._logged_in()
            except (AssertionError, IOError):
                return self._error(_('Invalid passphrase, please try again'))

        elif user.lower() in config.logins:
            # FIXME: Salt and hash the password, check if it matches
            #        the entry in our user/password list.
            raise Exception('FIXME')

        self._error(_('Incorrect username or password'))

    def command(self):
        session_id = self.session.ui.html_variables.get('http_session')

        if self.data.get('_method', '') == 'POST':
            if 'logout' in self.data:
                return self._do_logout()
            if 'pass' in self.data:
                return self._do_login(self.data.get('user', [None])[0],
                                      self.data['pass'][0])

        elif not self.data:
            password = self.session.ui.get_password(_('Your password: '))
            return self._do_login(None, password, load_index=True)

        return self._error(_('Please log in'))


plugin_manager = PluginManager(builtin=True)
plugin_manager.register_commands(Authenticate)
