# This plugin generates Javascript, HTML or CSS fragments based on the
# current theme, skin and active plugins.
#
from gettext import gettext as _

import mailpile.plugins
import mailpile.config
from mailpile.commands import Command
from mailpile.urlmap import UrlMap
from mailpile.util import *


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
    """Add or remove tags on a set of messages"""
    SYNOPSIS = (None, None, 'jsapi', None)
    ORDER = ('Internals', 0)
    HTTP_CALLABLE = ('GET', )

    def command(self, save=True, auto=False):
        session, config = self.session, self.session.config

        urlmap = UrlMap(session)
        res = {
            'api_methods': [],
            'javascript_classes': []
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

        for cls, filename in config.plugins.get_js_classes().iteritems():
            res['javascript_classes'].append({
                'classname': cls,
                'code': open(filename, 'rb').read().decode('utf-8')
            })

        return res

mailpile.plugins.register_commands(JsApi)
