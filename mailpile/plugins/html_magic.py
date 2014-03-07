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

        return {
            'lalala': 'all the stuff'
        }


mailpile.plugins.register_commands(JsApi)
