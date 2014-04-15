from gettext import gettext as _

import mailpile.config
from mailpile.plugins import PluginManager
from mailpile.commands import Command
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)

# We might want to do this differently at some point, but 
# for now it's fine.


def migrate_routes(session):
    # Migration from route string to messageroute structure
    def route_parse(route):
        if route.startswith('|'):
            command = route[1:].strip()
            return {
                "name": command.split()[0],
                "protocol": "local",
                "command": command
            }
        else:
            res = re.split(
                "([\w]+)://([^:]+):([^@]+)@([\w\d.]+):([\d]+)[/]{0,1}", route)
            return {
                "name": _("%(user)s on %(host)s"
                          ) % {"user": res[2], "host": res[4]},
                "protocol": res[1],
                "username": res[2],
                "password": res[3],
                "host": res[4],
                "port": res[5]
            }

    def make_route_name(route_dict):
        # This will always return the same hash, no matter how Python
        # decides to order the dict internally.
        return md5_hex(str(sorted(list(route_dict.iteritems()))))[:8]

    if 'default_route' in session.config.prefs:
        route_dict = route_parse(session.config.prefs.default_route)
        route_name = make_route_name(route_dict)
        session.config.routes[route_name] = route_dict
        session.config.prefs.default_messageroute = route_name

    for profile in session.config.profiles:
        if 'route' in profile:
            route_dict = route_parse(profile.route)
            route_name = make_route_name(route_dict)
            session.config.routes[route_name] = route_dict
            profile.messageroute = route_name

    return True



MIGRATIONS = (migrate_routes,)

class Migrate(Command):
    """Perform any needed migrations"""
    SYNOPSIS = (None, 'setup/migrate', None, None)
    ORDER = ('Internals', 0)

    def command(self):
        session = self.session
        cnt = 0
        err = 0

        for mig in MIGRATIONS:
            if mig(session):
                cnt += 1
                session.config.save()
            else:
                err += 1

        return self._success(_('Performed %d migrations, failed %d.'
                               ) % (cnt, err))


_plugins.register_commands(Migrate)
