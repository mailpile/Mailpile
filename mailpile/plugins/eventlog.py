import time
from gettext import gettext as _

import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *


class Events(Command):
    """Display events from the event log"""
    SYNOPSIS = (None, 'events', 'events',
                '[incomplete] [wait] [<count>] [<field>=<val> ...]')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ()

    WAIT_TIME = 10.0
    GATHER_TIME = 0.1

    def command(self):
        session, config, index = self.session, self.session.config, self._idx()
        event_log = config.event_log

        limit = 0
        incomplete = False
        waiting = False
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
        self.message = _('Found %d events' % len(result))
        return result



mailpile.plugins.register_commands(Events)
