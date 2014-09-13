# This plugin generates Javascript, HTML or CSS fragments based on the
# current theme, skin and active plugins.
#
import mailpile.config
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.urlmap import UrlMap
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)


##[ Configuration ]###########################################################

#mailpile.plugins.register_config_section('tags', ["Tags", {
#    'name': ['Tag name', 'str', ''],
#}, {}])
#
#mailpile.plugins.register_config_variables('sys', {
#    'writable_tags': ['DEPRECATED', 'str', []],
#})


##[ Commands ]################################################################


class JsApi(Command):
    """Output API bindings, plugin code and CSS as CSS or Javascript"""
    SYNOPSIS = (None, None, 'jsapi', None)
    ORDER = ('Internals', 0)
    HTTP_CALLABLE = ('GET', )
    HTTP_AUTH_REQUIRED = 'Maybe'

    def command(self, save=True, auto=False):
        session, config = self.session, self.session.config

        urlmap = UrlMap(session)
        res = {
            'api_methods': [],
            'javascript_classes': [],
            'css_files': []
        }

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


_plugins.register_commands(JsApi)
