import time
from urlparse import parse_qs, urlparse
from urllib import quote, urlencode

from mailpile.commands import Command
from mailpile.crypto.gpgi import GnuPG
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
    username = username or 'DEFAULT'
    sps = config.passphrases and config.passphrases.get(username)
    return sps.compare(password) and username


def IndirectPassword(config, pwd):
    pp = pwd.split(':')
    if len(pp) > 2 and pp[0] == '_SECRET_':
        if pp[1] in config.secrets:
            return config.secrets[pp[1]].password
        if pp[1] in config.passphrases:
            return config.passphrases[pp[1]].get_passphrase()
    return pwd


SESSION_CACHE = UserSessionCache()
LOGIN_FAILURES = []


def LogoutAll():
    for k in list(SESSION_CACHE.keys()):
        del SESSION_CACHE[k]


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

        # These are here to prevent people from abusing this to redirect to
        # arbitrary URLs on the Internet.
        if path:
            url = urlparse(path)
            assert(not url.scheme and not url.netloc)

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
                return self._error(_('Invalid password, please try again'))

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
        'mailsource': 'Mail source ID',
        'mailroute': 'Mail route ID',
        'is_locked': 'Assume key is locked'
    }
    HTTP_POST_VARS = {
        'password': 'KeyID or account name',
        'policy-ttl': 'Combined policy and TTL',
        'policy': 'store|cache-only|fail|forget',
        'ttl': 'Seconds after which it expires, -1 = never',
        'update_mailsources': 'If true, update mail source settings',
        'update_mailroutes': 'If true, update mail route settings',
        'redirect': 'URL to redirect to on success'
    }

    def _get_profiles(self):
        return self.session.config.vcards.find_vcards([], kinds=['profile'])

    def _get_policy(self, fingerprint):
        if fingerprint in self.session.config.secrets:
            return self.session.config.secrets[fingerprint].policy
        elif fingerprint in self.session.config.passphrases:
            return 'cache-only'
        return None

    def _massage_key_info(self, fingerprint, key_info, profiles=None, is_locked=False):
        config = self.session.config
        fingerprint = fingerprint.lower()

        key_info["uids"].sort(
            key=lambda k: (k.get("name"), k.get("email"), k.get("comment")))

        if not is_locked:
            key_info['policy'] = self._get_policy(fingerprint)
            if key_info['policy'] is None:
                del key_info['policy']

        key_info["accounts"] = []
        if profiles is None:
            profiles = self._get_profiles()
        for vc in profiles:
            vc_pgp_key = (vc.pgp_key or '').lower()
            if vc_pgp_key == fingerprint:
                key_info["accounts"].append({
                    'name': vc.fn,
                    'email': vc.email,
                    'rid': vc.random_uid})

        return key_info

    def _lookup_key(self, keyid, **kwargs):
        keylist = self._gnupg().list_secret_keys(selectors=[keyid])
        if len(keylist) != 1:
            raise ValueError("Too many or too few keys found!")
        fingerprint, key_info = keylist.keys()[0], keylist.values()[0]
        return fingerprint, self._massage_key_info(
            fingerprint, key_info, **kwargs)

    def _list_keys(self, **kwargs):
        keylist = self._gnupg().list_secret_keys()
        profiles = self._get_profiles()
        for fingerprint, key_info in keylist.iteritems():
            self._massage_key_info(fingerprint, key_info,
                                   profiles=profiles, **kwargs)
        return keylist

    def _get_account(self, cfg):
        username = cfg.username
        if cfg.username and '@' not in cfg.username:
            username = '%s@%s' % (username, cfg.host)
        return username

    def _user_fingerprint(self, username):
        return username.replace('@', '_').replace('.', '_').lower()

    def _list_accounts(self, only=None):
        accounts = {}
        def _add_account(cfg, which):
            username = self._get_account(cfg)
            if (username
                    and ((username == only) or only is None)
                    and cfg.auth_type == 'password'):
                if username in accounts:
                    accounts[username][which] = cfg.host
                else:
                    fingerprint = self._user_fingerprint(username)
                    accounts[username] = {
                        which: cfg.host,
                        'username': username,
                        'policy': self._get_policy(fingerprint)}
                    if accounts[username]['policy'] is None:
                        del accounts[username]['policy']

        for msid, route in self.session.config.routes.iteritems():
            _add_account(route, 'route')
        for msid, source in self.session.config.sources.iteritems():
            _add_account(source, 'source')

        return accounts

    def _account_details(self, account):
        return self._list_accounts(only=account).get(account)

    def _check_master_password(self, password, account=None, fingerprint=None):
        return CheckPassword(self.session.config, None, password)

    def _check_password(self, password, account=None, fingerprint=None):
        if account:
            # We're going to keep punting on this for a while...
            return True
        elif fingerprint:
            sps = SecurePassphraseStorage(password)
            gpg = GnuPG(self.session.config)
            status, sig = gpg.sign('OK', fromkey=fingerprint, passphrase=sps)
            return (status == 0)
        else:
            return True

    def _prepare_result(self, account=None, keyid=None, is_locked=False):
        if account:
            fingerprint = self._user_fingerprint(account)
            result = {'account': self._account_details(account)}
        elif keyid:
            fingerprint, info = self._lookup_key(keyid, is_locked=is_locked)
            result = {'key': info}
        else:
            fingerprint = None
            result = {
                'keylist': self._list_keys(is_locked=is_locked),
                'accounts': self._list_accounts()}
        return fingerprint, result

    def command(self):
        config = self.session.config

        policyttl = self.args[1] if (len(self.args) > 1) else 'cache-only:-1'
        is_locked = self.data.get('is_locked', [0])[0]
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

        fingerprint = info = account = keyid = None
        which = self.args[0] if self.args else self.data.get('id', [None])[0]
        if which and '@' in which:
            account = which
        else:
            keyid = which

        if not account and not keyid:
            msid = self.data.get('mailsource', [None])[0]
            if msid:
                account = self._get_account(config.sources[msid])
            mrid = self.data.get('mailroute', [None])[0]
            if mrid:
                account = self._get_account(config.routes[mrid])

        fingerprint, result = self._prepare_result(
            account=account, keyid=keyid, is_locked=is_locked)

        if policy in ('display', 'unprotect'):
            pass_prompt = _('Enter your Mailpile password')
            pass_check = self._check_master_password
        else:
            pass_prompt = _('Enter your password')
            pass_check = self._check_password

        if self.data.get('_method', None) == 'GET':
            return self._success(pass_prompt, result)

        assert(fingerprint is not None)
        fingerprint = fingerprint.lower()
        if fingerprint in config.secrets:
            if config.secrets[fingerprint].policy == 'protect':
                if policy not in ('unprotect', 'display'):
                    result['error'] = _('That key is managed by Mailpile,'
                                        ' it cannot be changed directly.')
                    return self._error(_('Protected secret'), result=result)

        if self.data.get('_method', None) == 'POST':
            password = self.data.get('password', [None])[0]
            update_ms = self.data.get('update_mailsources', [False])[0]
            update_mr = self.data.get('update_mailroutes', [False])[0]
        else:
            password = self.session.ui.get_password(pass_prompt + ': ')
            update_ms = update_mr = (account is not None)

        if update_ms or update_mr:
            assert(account is not None)

        if not pass_check(password, account=account, fingerprint=fingerprint):
            result['error'] = _('Password incorrect! Try again?')
            return self._error(_('Incorrect password'), result=result)

        def _account_matches(cfg):
            return (account == cfg.username or
                    account == '%s@%s' % (cfg.username, cfg.host))
        def happy(msg, refresh=True, changed=True):
            if changed:
                # Fun side effect: changing the passphrase invalidates the
                # message cache
                import mailpile.mailutils
                mailpile.mailutils.ClearParseCache(full=True)

                indirect_pwd = '_SECRET_:%s:%s' % (fingerprint, time.time())
                if update_ms:
                    for msid, source in config.sources.iteritems():
                        if _account_matches(source):
                            source.password = indirect_pwd
                if update_mr:
                    for msid, route in config.routes.iteritems():
                        if _account_matches(route):
                            route.password = indirect_pwd

                self._background_save(config=True)

            redirect = self.data.get('redirect', [None])[0]
            if redirect:
                raise UrlRedirectException(redirect)

            result['op_completed'] = policy
            if refresh:
              fp, r = self._prepare_result(account=account, keyid=keyid)
              result.update(r)

            return self._success(msg, result)

        if policy == 'display':
            if fingerprint in config.passphrases:
                pwd = config.passphrases[fingerprint].get_passphrase()
            elif fingerprint in config.secrets:
                pwd = config.secrets[fingerprint].password
            else:
                return self._error(_('No password found'), result=result)
            result['stored_password'] = pwd
            return happy(_('Retrieved stored password'),
                         refresh=False, changed=False)

        if policy == 'forget':
            if fingerprint in config.passphrases:
                del config.passphrases[fingerprint]
            if fingerprint in config.secrets:
                config.secrets[fingerprint] = {'policy': 'fail'}
                del config.secrets[fingerprint]
            return happy(_('Password forgotten!'))

        if policy == 'fail':
            if fingerprint in config.passphrases:
                del config.passphrases[fingerprint]
            config.secrets[fingerprint] = {'policy': policy}
            return happy(_('Password will never be stored'))

        if policy == 'store':
            if fingerprint in config.passphrases:
                del config.passphrases[fingerprint]
            config.secrets[fingerprint] = {
                'password': password,
                'policy': policy}
            return happy(_('Password remembered!'))

        elif policy == 'cache-only' and password:
            sps = SecurePassphraseStorage(password)
            if ttl > 0:
                sps.expiration = time.time() + ttl
            config.passphrases[fingerprint] = sps
            if fingerprint in config.secrets:
                config.secrets[fingerprint] = {'policy': 'fail'}
                del config.secrets[fingerprint]
            return happy(_('The password has been stored temporarily'))

        else:
            return self._error(_('Invalid password policy'), result=result)


plugin_manager = PluginManager(builtin=True)
plugin_manager.register_commands(Authenticate,
                                 DeAuthenticate,
                                 SetPassphrase)
