# This plugin generates Javascript, HTML or CSS fragments based on the
# current theme, skin and active plugins.
#
# It also takes care of safely downloading random stuff from the Internet,
# using the appropriate proxying policies.
#
from urllib2 import urlopen, HTTPError

import mailpile.config
import mailpile.security as security
from mailpile.commands import Command, RenderPage
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.ui import SuppressHtmlOutput
from mailpile.urlmap import UrlMap
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)


##[ Commands ]################################################################

class JsApi(RenderPage):
    """Output API bindings, plugin code and CSS as CSS or Javascript"""
    SYNOPSIS = (None, None, 'jsapi', None)
    ORDER = ('Internals', 0)
    HTTP_CALLABLE = ('GET', )
    HTTP_AUTH_REQUIRED = 'Maybe'
    HTTP_QUERY_VARS = {'ts': 'Cache busting timestamp'}

    def max_age(self):
        # Set a long TTL if we know which version of the config this request
        # applies to, as changed config should avoid the outdated cache.
        if 'ts' in self.data:
            return 7 * 24 * 3600
        else:
            return 30

    def etag_data(self):
        # This summarizes the config state this page depends on, for
        # generating an ETag which the HTTPD can use for caching.
        config = self.session.config
        return ([config.version,
                 config.timestamp,
                 # The above should be enough, the rest is belt & suspenders
                 config.prefs.language,
                 config.web.setup_complete] +
                sorted(config.sys.plugins))

    def command(self, save=True, auto=False):
        res = {
            'api_methods': [],
            'javascript_classes': [],
            'css_files': []
        }
        if self.args:
            # Short-circuit if we're serving templates...
            return self._success(_('Serving up API content'), result=res)

        session, config = self.session, self.session.config
        urlmap = UrlMap(session)
        for method in ('GET', 'POST', 'UPDATE', 'DELETE'):
            for cmd in urlmap._api_commands(method, strict=True):
                cmdinfo = {
                    "url": cmd.SYNOPSIS[2],
                    "method": method
                }
                if hasattr(cmd, 'HTTP_QUERY_VARS'):
                    cmdinfo["query_vars"] = cmd.HTTP_QUERY_VARS
                if hasattr(cmd, 'HTTP_POST_VARS'):
                    cmdinfo["post_vars"] = cmd.HTTP_POST_VARS
                if hasattr(cmd, 'HTTP_OPTIONAL_VARS'):
                    cmdinfo["optional_vars"] = cmd.OPTIONAL_VARS
                res['api_methods'].append(cmdinfo)

        created_js = []
        for cls, filename in sorted(list(
                config.plugins.get_js_classes().iteritems())):
            try:
                parts = cls.split('.')[:-1]
                for i in range(1, len(parts)):
                    parent = '.'.join(parts[:i+1])
                    if parent not in created_js:
                        res['javascript_classes'].append({
                            'classname': parent,
                            'code': ''
                        })
                        created_js.append(parent)
                with open(filename, 'rb') as fd:
                    res['javascript_classes'].append({
                        'classname': cls,
                        'code': fd.read().decode('utf-8')
                    })
                    created_js.append(cls)
            except (OSError, IOError, UnicodeDecodeError):
                self._ignore_exception()

        for cls, filename in sorted(list(
                config.plugins.get_css_files().iteritems())):
            try:
                with open(filename, 'rb') as fd:
                    res['css_files'].append({
                        'classname': cls,
                        'css': fd.read().decode('utf-8')
                    })
            except (OSError, IOError, UnicodeDecodeError):
                self._ignore_exception()

        return self._success(_('Generated Javascript API'), result=res)


class HttpProxyGetRequest(Command):
    """HTTP GET content from the public web"""
    SYNOPSIS = (None, None, 'http_proxy', None)
    ORDER = ('Internals', 0)
    RAISES = (AccessError, SuppressHtmlOutput)
    HTTP_CALLABLE = ('GET', )
    HTTP_AUTH_REQUIRED = True
    HTTP_QUERY_VARS = {
        'ts': 'Cache busting timestamp',
        'timeout': 'Timeout in seconds',
        'url': 'URL to fetch',
        'csrf': 'CSRF token'
    }

    def command(self):
        html_variables = self.session.ui.html_variables
        request = html_variables['http_request']

        if not (html_variables and
                security.valid_csrf_token(request,
                                          html_variables['http_session'],
                                          self.data.get('csrf', [''])[0])):
            raise AccessError('Invalid CSRF token')

        url = self.data['url'][0]
        timeout = float(self.data.get('timeout', ['10'])[0])

        conn_reject = []  # FIXME: reject ConnBroker.OUTGOING_TRACKABLE ?
        if url[:6].lower() == 'https:':
            conn_need = [ConnBroker.OUTGOING_HTTP]
        elif url[:5].lower() == 'http:':
            conn_need = [ConnBroker.OUTGOING_HTTPS]
        else:
            raise AccessError('Invalid URL scheme')

        try:
            with ConnBroker.context(need=conn_need, reject=conn_reject) as ctx:
                self.session.ui.mark('Getting: %s' % url)
                response = urlopen(url, data=None, timeout=timeout)
        except HTTPError, e:
            response = e

        data = response.read()
        headers = response.headers
        contenttype = headers.get('content-type', 'application/octet-stream')
        request.send_http_response(response.code, response.msg)
        request.send_standard_headers(mimetype=contenttype,
                                      header_list=[('Content-Length',
                                                    len(data))])
        request.wfile.write(data)
        request.send_full_response(response.code, response.msg)

        raise SuppressHtmlOutput()


_plugins.register_commands(JsApi, HttpProxyGetRequest)
