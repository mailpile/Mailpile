import time
from urlparse import parse_qs, urlparse
from urllib import quote, urlencode

from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.security import SecurePassphraseStorage
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


def VerifyAndStorePassphrase(config, passphrase=None, sps=None,
                                     key=None):
    if passphrase and not sps:
        sps = SecurePassphraseStorage(passphrase)
        passphrase = 'this probably does not really overwrite :-( '

    assert(sps is not None)
    assert(config.load_master_key(sps))

    # Fun side effect: changing the passphrase invalidates the message cache
    import mailpile.mailutils
    mailpile.mailutils.ClearParseCache(full=True)

    return sps


def SetLoggedIn(cmd, user=None, redirect=False, session_id=None):
    user = user or 'DEFAULT'

    sid = session_id or cmd.session.ui.html_variables.get('http_session')
    if sid:
        if cmd:
            cmd.session.ui.debug('Logged in %s as %s' % (sid, user))
        SESSION_CACHE[sid] = UserSession(auth=user, data={
            't': '%x' % int(time.time()),
        })

    if cmd:
        if redirect:
            return cmd._do_redirect()
    else:
        return True


def CheckPassword(config, username, password):
    # FIXME: Do something with the username
    sps = config.passphrases and config.passphrases.get(username or 'DEFAULT')
    return sps.compare(password) and username


SESSION_CACHE = UserSessionCache()
LOGIN_FAILURES = []


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

    @classmethod
    def RedirectBack(cls, url, data):
        qs = [(k, v.encode('utf-8')) for k, vl in data.iteritems() for v in vl
              if k not in ['_method', '_path'] + cls.HTTP_POST_VARS.keys()]
        qs = urlencode(qs)
        url = ''.join([url, '?%s' % qs if qs else ''])
        raise UrlRedirectException(url)

    def _result(self, result=None):
        global LOGIN_FAILURES
        result = result or {}
        result['login_banner'] = self.session.config.sys.login_banner
        result['login_failures'] = LOGIN_FAILURES
        return result

    def _error(self, message, info=None, result=None):
        global LOGIN_FAILURES
        LOGIN_FAILURES.append(int(time.time()))
        return Command._error(self, message,
                              info=info, result=self._result(result))

    def _success(self, message, result=None):
        return Command._success(self, message, result=self._result(result))

    def _do_redirect(self):
        path = self.data.get('_path', [None])[0]
        if (path and
               not path[1:].startswith(DeAuthenticate.SYNOPSIS[2] or '!') and
               not path[1:].startswith(self.SYNOPSIS[2] or '!')):
            self.RedirectBack(self.session.config.sys.http_path + path, self.data)
        else:
            raise UrlRedirectException('%s/' % self.session.config.sys.http_path)

    def _do_login(self, user, password, load_index=False, redirect=False):
        global LOGIN_FAILURES
        session, config = self.session, self.session.config
        session_id = self.session.ui.html_variables.get('http_session')

        # This prevents folks from sending us a DEFAULT user (upper case),
        # which is an internal security bypass below.
        user = user and user.lower()

        if not user:
            try:
                # Verify the passphrase
                if CheckPassword(config, None, password):
                    sps = config.passphrases['DEFAULT']
                else:
                    sps = VerifyAndStorePassphrase(config, passphrase=password)

                if sps:
                    # Load the config and index, if necessary
                    config = self._config()
                    self._idx(wait=False)
                    if load_index:
                        try:
                            while not config.index:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            pass

                    session.ui.debug('Good passphrase for %s' % session_id)
                    self.record_user_activity()
                    LOGIN_FAILURES = []
                    return self._success(_('Hello world, welcome!'), result={
                        'authenticated': SetLoggedIn(self, redirect=redirect)
                    })
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

        return self._error(_('Incorrect username or password'))

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
    HTTP_AUTH_REQUIRED = False
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


class SetPassphrase(Command):
    """Manage storage of passwords (passphrases)"""
    SYNOPSIS = (None, 'set/password', 'settings/set/password',
                      '<keyid> [store|cache-only[:<ttl>]|fail|forget]')
    ORDER = ('Config', 9)
    SPLIT_ARG = True
    IS_INTERACTIVE = True
    IS_USER_ACTIVITY = True
    CONFIG_REQUIRED = True
    HTTP_AUTH_REQUIRED = True
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'id': 'KeyID or account name',
    }
    HTTP_POST_VARS = {
        'password': 'KeyID or account name',
        'policy-ttl': 'Combined policy and TTL',
        'policy': 'store|cache-only|fail|forget',
        'ttl': 'Seconds after which it expires, -1 = never',
        'redirect': 'URL to redirect to on success'
    }

    def _lookup_key(self, keyid):
        keylist = self._gnupg().list_secret_keys(selectors=[keyid])
        if len(keylist) != 1:
            raise ValueError("Too many or too few keys found!")
        return keylist.keys()[0], keylist.values()[0]

    def command(self):
        config = self.session.config

        policyttl = self.args[1] if (len(self.args) > 1) else 'cache-only:-1'
        if 'policy-ttl' in self.data:
            policyttl = self.data['policy-ttl'][0]
        if ':' in policyttl:
            policy, ttl = policyttl.split(':')
        else:
            policy, ttl = policyttl, -1
        if 'policy' in self.data:
            policy = self.data['policy'][0]
        if 'ttl' in self.data:
            ttl = self.data['policy'][0]
        ttl = float(ttl)

        fingerprint = info = None
        keyid = self.args[0] if self.args else self.data.get('id', [None])[0]
        if keyid:
            fingerprint, info = self._lookup_key(keyid)
            result = {'key': info}
        else:
            result = {'keylist': self._gnupg().list_secret_keys()}

        if self.data.get('_method', None) == 'GET':
            password = False
            return self._success(_('Enter your password'), result)

        assert(keyid is not None and fingerprint is not None)
        def happy(msg):
            # Fun side effect: changing the passphrase invalidates the message cache
            import mailpile.mailutils
            mailpile.mailutils.ClearParseCache(full=True)

            redirect = self.data.get('redirect', [None])[0]
            if redirect:
                raise UrlRedirectException(redirect)
            return self._success(msg, result)

        if policy == 'forget':
            if fingerprint in config.passphrases:
                del config.passphrases[fingerprint]
            if fingerprint in config.secrets:
                config.secrets[fingerprint].password = ''
            return happy(_('Password forgotten!'))

        if policy == 'fail':
            if fingerprint in config.passphrases:
                del config.passphrases[fingerprint]
            config.secrets[fingerprint] = {
                'policy': policy
            }
            return happy(_('Password will never be stored'))

        if self.data.get('_method', None) == 'POST':
            password = self.data.get('password', [None])[0]
        else:
            password = self.session.ui.get_password(_('Enter your password:')
                                                    +' ')

        if policy == 'store':
            if fingerprint in config.passphrases:
                del config.passphrases[fingerprint]
            config.secrets[fingerprint] = {
                'password': password,
                'policy': policy
            }
            return happy(_('Password stored permanently'))

        elif policy == 'cache-only' and password:
            sps = SecurePassphraseStorage(password)
            if ttl > 0:
                sps.expiration = time.time() + ttl
            config.passphrases[fingerprint] = sps
            if fingerprint.lower() in config.secrets:
                del config.secrets[fingerprint.lower()]
            return happy(_('Password stored temporarily'))

        else:
            return self._error(_('Invalid password policy!'), result)


plugin_manager = PluginManager(builtin=True)
plugin_manager.register_commands(Authenticate,
                                 DeAuthenticate,
                                 SetPassphrase)
