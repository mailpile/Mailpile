from __future__ import print_function
import json
import time
import traceback
from urllib import urlencode, quote_plus

from mailpile.i18n import gettext
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.plugins.setup_magic import TestableWebbable
from mailpile.util import *


_ = lambda s: s
_plugins = PluginManager(builtin=__file__)


##[ Configuration ]###########################################################

_plugins.register_config_section(
    'oauth', ['OAuth configuration and state', False, {
        'providers': ('Known OAuth providers', {
            'protocol':      ('OAuth* protocol', str, ''),
            'server_re':     ('Regular expression to match servers', str, ''),
            'client_id':     ('The OAuth Client ID', str, ''),
            'client_secret': ('The OAuth token itself', str, ''),
            'redirect_re':   ('Regexp of URLs we can redirect to', str, ''),
            'token_url':     ('The OAuth token endpoint', str, ''),
            'oauth_url':     ('The OAuth authentication endpoint', str, ''),
        }, {}),

        'tokens': ('Current OAuth tokens', {
            'provider':      ('Provider ID', str, ''),
            'access_token':  ('Access token', str, ''),
            'token_type':    ('Access token type', str, ''),
            'expires_at':    ('Access token expiration time', int, 0),
            'refresh_token': ('Refresh token', str, '')
        }, {})
    }])


##[ Commands ]################################################################

class OAuth2(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/oauth2', None)
    RAISES = (AccessError,)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'mailsource': 'Mail source ID',
        'mailroute': 'Mail route ID',
        'hostname': 'Mail server',
        'username': 'User name',
        'code': 'Authorization code',
        'error': 'Error code',
        'scope': 'OAuth2 scope (ignored)',
        'state': 'State token'
    }
    HARD_CODED_OAUTH2 = {
        'GMail': {
            'protocol': 'Google',
            'server_re': '.*\\.(google|gmail)\\.com$',
            'client_id': ('174733765695-1dnhaq06gt61tg432t0d6jlt76nng2t1'
                          '.apps.googleusercontent.com'),
            'client_secret': 'vbUxR2Dvqb1c-nI2-X_7NvCu',
            'redirect_re': '^http://localhost[:/]',
            'token_url': ('https://www.googleapis.com/oauth2/v4/token'),
            'oauth_url': ('https://accounts.google.com/o/oauth2/v2/auth'
                          '?response_type=code'
                          '&access_type=offline'
                          '&scope=https://mail.google.com/'
                          '&redirect_uri=%(redirect_uri)s'
                          '&client_id=%(client_id)s'
                          '&state=%(state)s'
                          '&login_hint=%(username)s')}}
    OAUTH2_OOB_REDIRECT = "urn:ietf:wg:oauth:2.0:oob"

    @classmethod
    def RedirectURI(cls, config, oauth2_cfg, http_host=None):
        if not http_host:
            http_host = "%s:%s" % config.http_worker.httpd.sspec[:2]
        meth = 'http' if http_host.startswith('localhost:') else 'https'
        url = '/'.join([
            '%s://%s%s' % (meth, http_host, config.http_worker.httpd.sspec[2]),
            cls.SYNOPSIS[2],
            ''])

        url_re = oauth2_cfg.get('redirect_re')
        if url_re and not re.match(url_re, url, re.DOTALL):
            return cls.OAUTH2_OOB_REDIRECT

        return url

    @classmethod
    def ActivateHardCodedOAuth(cls, config):
        for name, cfg in cls.HARD_CODED_OAUTH2.iteritems():
            if name not in config.oauth.providers.keys():
                config.oauth.providers[name] = cfg

    @classmethod
    def GetOAuthConfig(cls, config, hostname=None, oname=None):
        cls.ActivateHardCodedOAuth(config)
        if oname:
            return (oname, config.oauth.providers[oname])
        for name, cfg in config.oauth.providers.iteritems():
            if re.match(cfg['server_re'], hostname):
                 return (name, cfg)
        return (None, None)

    @classmethod
    def GetOAuthURLVars(cls, session, ocfg, username):
        # FIXME: Make this a custom token just for OAuth
        state = '%s/%s/%s' % (
            username, ocfg._key, session.ui.html_variables['csrf_token'])
        http_host = session.ui.html_variables.get("http_host")
        return {
            'redirect_uri': quote_plus(
                 cls.RedirectURI(session.config, ocfg, http_host)),
            'client_id': quote_plus(ocfg['client_id']),
            'username': quote_plus(username),
            'state': state}

    @classmethod
    def GetOAuthURL(cls, session, ocfg, username, url_vars=None):
        if url_vars is None:
            url_vars = cls.GetOAuthURLVars(session, ocfg, username)
        return ocfg['oauth_url'] % url_vars

    @classmethod
    def XOAuth2Response(cls, username, token_info):
        return 'user=%s\x01auth=Bearer %s\x01\x01' % (
            username, token_info.access_token)

    @classmethod
    def GetToken(cls, session, oauth2_cfg, code, tok_id=None):
        """
        Fetch a token and associated details from an authorization server.

        Returns something like this:
          {
            'access_token': 'tsbk6pcSPSNffdzEkxVicwf...',
            'token_type': 'Bearer',
            'expires_at': 123456789,
            'refresh_token': '1CtboygBSKA-Ut1e7...'
          }
        """
        post_data = urlencode([
            ('code', code),
            ('client_id', oauth2_cfg['client_id']),
            ('client_secret', oauth2_cfg['client_secret']),
            ('redirect_uri', cls.RedirectURI(
                session.config, oauth2_cfg,
                session.ui.html_variables.get("http_host"))),
            ('grant_type', 'authorization_code')])

        data = json.loads(cls.URLGet(
           session, oauth2_cfg['token_url'], data=post_data))

        tok_id = tok_id or ('%x' % time.time())
        session.config.oauth.tokens[tok_id] = {}
        tok_info = session.config.oauth.tokens[tok_id]
        tok_info.provider = oauth2_cfg._key
        tok_info.token_type = data['token_type']
        tok_info.access_token = data['access_token']
        tok_info.expires_at = int(time.time() + data['expires_in'])
        tok_info.refresh_token = data['refresh_token']
        if 'oauth' in session.config.sys.debug:
            session.ui.debug("Fetched OAuth2 token for %s" % tok_id)

        return tok_id, tok_info

    @classmethod
    def GetFreshTokenInfo(cls, session, tok_id):
        oauth2_cfg, post_data = {}, None
        try:
            tok_info = session.config.oauth.tokens[tok_id]
            if (tok_info.expires_at > (time.time() + 300)
                    or not tok_info.refresh_token):
                return tok_info

            oauth2_cfg = session.config.oauth.providers[tok_info.provider]
            post_data = urlencode([
                ('refresh_token', tok_info.refresh_token),
                ('client_id', oauth2_cfg['client_id']),
                ('client_secret', oauth2_cfg['client_secret']),
                ('grant_type', 'refresh_token')])
            data = json.loads(cls.URLGet(
               session, oauth2_cfg['token_url'], data=post_data))

            tok_info.access_token = data['access_token']
            tok_info.expires_at = int(time.time() + data['expires_in'])
            if 'oauth' in session.config.sys.debug:
                session.ui.debug("Refreshed OAuth2 token for %s" % tok_id)

            return tok_info
        except:
            if 'oauth' in session.config.sys.debug:
                session.ui.debug(traceback.format_exc())
                session.ui.debug('Failed: POST %s, data=%s' % (
                    oauth2_cfg.get('token_url'), post_data))
            return False

    def setup_command(self, session):
        config = session.config

        code = self.data.get('code', [''])[0]
        msid = self.data.get('mailsource', [''])[0]
        rtid = self.data.get('mailroute', [''])[0]
        username = self.data.get('username', [''])[0]
        hostname = self.data.get('hostname', [''])[0]
        state = self.data.get('state', [''])[0]
        results = { 'error': self.data.get('error', [''])[0] }

        if msid:
            username = config.sources[msid].username
            hostname = config.sources[msid].host
        elif rtid:
            username = config.routes[rtid].username
            hostname = config.routes[rtid].host

        if code:
            username, oname, csrf = state.split('/', 2)
            if not session.ui.valid_csrf_token(csrf):
                print('Invalid CSRF token: %s' % csrf)
                raise AccessError('Invalid CSRF token')

            oname, ocfg = self.GetOAuthConfig(config, oname=oname)
            tok_id, tok_info = self.GetToken(session, ocfg, code,
                                             tok_id=username)

            # This helps the mail sources/routes detect that it may
            # be worth trying the connection again...
            for msid, source in config.sources.iteritems():
                if source.username == username:
                    source.password = tok_info.access_token
            for msid, route in config.routes.iteritems():
                if route.username == username:
                    route.password = tok_info.access_token

            results['success'] = True

        elif username and hostname:
            oname, ocfg = self.GetOAuthConfig(config, hostname)
            uv = self.GetOAuthURLVars(session, ocfg, username)
            hr = (uv['redirect_uri'] != quote_plus(self.OAUTH2_OOB_REDIRECT))
            results.update(uv)
            results.update({
                'have_redirect': hr,
                'username': username,
                'oauth_url': self.GetOAuthURL(session, ocfg, username,
                                              url_vars=uv) })

        return self._success(_('OAuth2 Authorization'), results)


_ = gettext
_plugins.register_commands(OAuth2)
