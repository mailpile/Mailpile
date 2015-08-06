import time

import mailpile.util
import mailpile.security as security
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)


class Events(Command):
    """Display events from the event log"""
    SYNOPSIS = (None, 'eventlog', 'eventlog',
                '[incomplete] [wait] [<count>] '
                '[<field>=<val> <f>!=<v> <f>=~<re> ...]')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        'wait': 'seconds to wait for new data',
        'gather': 'gather time (minimum wait), seconds',
        'incomplete': 'incomplete events only?',
        # Filtering by event attributes
        'event_id': 'an event ID',
        'flag': 'require a flag',
        'flags': 'match all flags',
        'since': 'wait for new data?',
        'source': 'source class',
        # Filtering by event data (syntax is a bit weird)
        'data': 'var:value',
        'private_data': 'var:value'
    }
    LOG_NOTHING = True
    IS_HANGING_ACTIVITY = True
    IS_USER_ACTIVITY = False

    DEFAULT_WAIT_TIME = 10.0
    GATHER_TIME = 0.5

    _FALSE = ('0', 'off', 'no', 'false')

    def command(self):
        session, config, index = self.session, self.session.config, self._idx()
        event_log = config.event_log

        incomplete = (self.data.get('incomplete', ['no']
                                    )[0].lower() not in self._FALSE)
        waiting = int(self.data.get('wait', [0])[0])
        gather = float(self.data.get('gather', [self.GATHER_TIME])[0])

        limit = 0
        filters = {}
        for arg in self.args:
            if arg.lower() == 'incomplete':
                incomplete = True
            elif arg.lower() == 'wait':
                waiting = self.DEFAULT_WAIT_TIME
            elif '=' in arg:
                field, value = arg.split('=', 1)
                filters[unicode(field)] = unicode(value)
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
            if arg in ('source', 'flags', 'flag', 'since', 'event_id'):
                fset(arg, self.data[arg][0])
            elif arg in ('data', 'private_data'):
                for data in self.data[arg]:
                    var, val = data.split(':', 1)
                    fset('%s_%s' % (arg, var), val)

        # Compile regular expression matches
        for arg in filters:
            if filters[arg][:1] == '~':
                filters[arg] = re.compile(filters[arg][1:])

        now = time.time()
        expire = now + waiting - gather
        if waiting:
            if 'since' not in filters:
                filters['since'] = now
            if float(filters['since']) < 0:
                filters['since'] = float(filters['since']) + now
            time.sleep(gather)

        events = []
        while not waiting or (expire + gather) > time.time():
            if incomplete:
                events = list(config.event_log.incomplete(**filters))
            else:
                events = list(config.event_log.events(**filters))
            if events or not waiting:
                break
            else:
                config.event_log.wait(expire - time.time())
                time.sleep(gather)

        if limit:
            if 'since' in filters:
                events = events[:limit]
            else:
                events = events[-limit:]

        return self._success(_('Found %d events') % len(events),
                             result={
            'count': len(events),
            'ts': max([0] + [e.ts for e in events]) or time.time(),
            'events': [e.as_dict() for e in events]
        })


class Cancel(Command):
    """Cancel events"""
    SYNOPSIS = (None, 'eventlog/cancel', 'eventlog/cancel', 'all|<eventIDs>')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
        'event_id': 'Event ID'
    }
    IS_USER_ACTIVITY = False
    COMMAND_SECURITY = security.CC_CHANGE_CONFIG

    def command(self):
        if self.args and 'all' in self.args:
            events = self.session.config.event_log.events()
        else:
            events = [self.session.config.event_log.get(eid)
                      for eid in (list(self.args) +
                                  self.data.get('event_id', []))]
        canceled = []
        for event in events:
            if event and event.COMPLETE not in event.flags:
                try:
                    event.source_class.Cancel(self, event)
                except (NameError, AttributeError):
                    event.flags = event.COMPLETE
                    self.session.config.event_log.log_event(event)
                canceled.append(event.event_id)
        return self._success(_('Canceled %d events') % len(canceled),
                             canceled)


class Undo(Command):
    """Undo either the last action or one specified by Event ID"""
    SYNOPSIS = ('u', 'undo', 'eventlog/undo', '[<Event ID>]')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
        'event_id': 'Event ID'
    }
    IS_USER_ACTIVITY = False

    def command(self):
        event_id = (self.data.get('event_id', [None])[0]
                    or (self.args and self.args[0])
                    or (self.session.last_event_id))
        if not event_id:
            return self._error(_('Need an event ID!'))
        event = self.session.config.event_log.get(event_id)
        if event:
            try:
                sc = event.source_class
                forbid = security.forbid_command(self, sc.COMMAND_SECURITY)
                if forbid:
                    return self._error(forbid)
                else:
                    return sc.Undo(self, event)
            except (NameError, AttributeError):
                self._ignore_exception()
                return self._error(_('Event %s is not undoable') % event_id)
        else:
            return self._error(_('Event %s not found') % event_id)


class Watch(Command):
    """Watch the events fly by"""
    SYNOPSIS = (None, 'eventlog/watch', None, None)
    ORDER = ('Internals', 9)
    IS_USER_ACTIVITY = False

    def command(self):
        self.session.ui.notify(
            _('Watching logs: Press CTRL-C to return to the CLI'))
        unregister = self.session.config.event_log.ui_watch(self.session.ui)
        try:
            self.session.ui.unblock(force=True)
            while not mailpile.util.QUITTING:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            if unregister:
                self.session.config.event_log.ui_unwatch(self.session.ui)
        return self._success(_('That was fun!'))


_plugins.register_commands(Events, Cancel, Undo, Watch)
