import os

import mailpile.commands
import mailpile.security as security
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager


_plugins = PluginManager(builtin=__file__)


class Plugins(mailpile.commands.Command):
    """List the currently available plugins."""
    SYNOPSIS = (None, 'plugins', None, '[<plugins>]')
    ORDER = ('Config', 9)
    HTTP_CALLABLE = ()

    def command(self):
        pm = self.session.config.plugins
        wanted = self.args

        info = dict((d, {
            'loaded': d in pm.LOADED,
            'builtin': d not in pm.DISCOVERED
        }) for d in pm.available() if (not wanted or d in wanted))

        for plugin in info:
            if plugin in pm.DISCOVERED:
                info[plugin]['manifest'] = pm.DISCOVERED[plugin][1]

        return self._success(_('Listed available plugins'), info)


class LoadPlugin(mailpile.commands.Command):
    """Load and enable a given plugin."""
    SYNOPSIS = (None, 'plugins/load', None, '<plugin>')
    ORDER = ('Config', 9)
    HTTP_CALLABLE = ()
    COMMAND_SECURITY = security.CC_CHANGE_CONFIG

    def command(self):
        config = self.session.config
        plugins = config.plugins
        for plugin in self.args:
            if plugin in plugins.LOADED:
                return self._error(_('Already loaded: %s') % plugin,
                                   info={'loaded': plugin})

        for plugin in self.args:
            try:
                # FIXME: This fails to update the ConfigManger
                plugins.load(plugin, process_manifest=True, config=config)
                config.sys.plugins.append(plugin)
            except Exception, e:
                self._ignore_exception()
                return self._error(_('Failed to load plugin: %s') % plugin,
                                   info={'failed': plugin})

        config.save()
        return self._success(_('Loaded plugins: %s') % ', '.join(self.args),
                             {'loaded': self.args})


class DisablePlugin(mailpile.commands.Command):
    """Disable a plugin."""
    SYNOPSIS = (None, 'plugins/disable', None, '<plugin>')
    ORDER = ('Config', 9)
    HTTP_CALLABLE = ()
    COMMAND_SECURITY = security.CC_CHANGE_CONFIG

    def command(self):
        config = self.session.config
        plugins = config.plugins
        for plugin in self.args:
            if plugin in plugins.REQUIRED:
                return self._error(_('Required plugins can not be disabled: %s'
                                     ) % plugin)
            if plugin not in config.sys.plugins:
                return self._error(_('Plugin not loaded: %s') % plugin)

        for plugin in self.args:
            while plugin in config.sys.plugins:
                config.sys.plugins.remove(plugin)

        config.save()
        return self._success(_('Disabled plugins: %s (restart required)'
                               ) % ', '.join(self.args),
                             {'disabled': self.args})


_plugins.register_commands(Plugins, LoadPlugin, DisablePlugin)
