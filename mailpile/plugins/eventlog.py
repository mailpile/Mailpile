import time
from gettext import gettext as _

from mailpile.plugins import PluginManager
from mailpile.commands import Command
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)


class Events(Command):
    """Display events from the event log"""
    SYNOPSIS = (None, 'eventlog', 'eventlog',
                '[incomplete] [wait] [<count>] [<field>=<val> ...]')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        'wait': 'wait for new data?',
        'incomplete': 'incomplete events only?',
        # Filtering by event attributes
        'flag': 'require a flag',
        'flags': 'match all flags',
        'since': 'wait for new data?',
        'source': 'source class',
        # Filtering by event data (syntax is a bit weird)
        'data': 'var:value',
        'private_data': 'var:value'
    }

    WAIT_TIME = 10.0
    GATHER_TIME = 0.1

    _FALSE = ('0', 'off', 'no', 'false')

    def command(self):
        session, config, index = self.session, self.session.config, self._idx()
        event_log = config.event_log

        incomplete = (self.data.get('incomplete', ['no']
                                    )[0].lower() not in self._FALSE)
        waiting = (self.data.get('wait', ['no']
                                 )[0].lower() not in self._FALSE)
        limit = 0
        filters = {}
        for arg in self.args:
            if arg.lower() == 'incomplete':
                incomplete = True
            elif arg.lower() == 'wait':
                waiting = True
            elif '=' in arg:
                field, value = arg.split('=', 1)
                filters[str(field)] = str(value)
            else:
                try:
                    limit = int(arg)
                except ValueError:
                    raise UsageError('Bad argument: %s' % arg)

        # Handle args from the web
        def fset(arg, val):
            if val.startswith('!'):
                filters[arg+'!'] = val[1:]
            else:
                filters[arg] = val
        for arg in self.data:
            if arg in ('source', 'flags', 'flag', 'since'):
                fset(arg, self.data[arg][0])
            elif arg in ('data', 'private_data'):
                for data in self.data[arg]:
                    var, val = data.split(':', 1)
                    fset('%s_%s' % (arg, var), val)

        if waiting:
            tries = 2
            if 'since' not in filters:
                filters['since'] = time.time()
        else:
            tries = 1

        expire = time.time() + self.WAIT_TIME - self.GATHER_TIME
        while expire > time.time():
            if incomplete:
                events = list(config.event_log.incomplete(**filters))
            else:
                events = list(config.event_log.events(**filters))
            if events or not waiting:
                break
            else:
                config.event_log.wait(expire - time.time())
                time.sleep(self.GATHER_TIME)

        result = [e.as_dict() for e in events[-limit:]]
        return self._success(_('Found %d events') % len(result),
                             result=result)


_plugins.register_commands(Events)
