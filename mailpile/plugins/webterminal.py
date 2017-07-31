import random

from mailpile.commands import *
from mailpile.plugins import PluginManager
from mailpile.ui import Session
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.security import CC_WEB_TERMINAL

_plugins = PluginManager(builtin=__file__)

sessions = {}

class TerminalSessionNew(Command):
    """Create a terminal session."""
    SYNOPSIS = ('', '', 'terminal_session_new', '')
    ABOUT = ('Start a new named session.')
    HTTP_CALLABLE = ('POST', )
    CONFIG_REQUIRED = True
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = CC_WEB_TERMINAL

    def command(self):
        config = self.session.config

        s = Session(config)
        sid = "%08x" % random.randint(0, 1000000000)
        sessions[sid] = s

        return self._success(_('Created a session'), result={
            "sid": sid,
        })


class TerminalSessionEnd(Command):
    """End a terminal session."""
    SYNOPSIS = ('', '', 'terminal_session_end', '')
    ABOUT = ('End a named session.')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {
        'sid': 'id of session to use',
    }
    CONFIG_REQUIRED = True
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = CC_WEB_TERMINAL

    def command(self):
        config = self.session.config
        sid = self.data.get('sid', [''])[0]
        if sid == '':
            return self._error(_('No SID supplied'))

        del(sessions[sid])

        return self._success(_('Ended a session'), result={
            "sid": sid,
        })


class TerminalCommand(Command):
    """Execute a terminal command."""
    SYNOPSIS = ('', '', 'terminal_command', '<command> <session>')
    ABOUT = ('Run a terminal command via the API')
    CONFIG_REQUIRED = True
    IS_USER_ACTIVITY = True
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {
        'sid': 'id of session to use',
        'command': 'command to execute'
    }
    TERMINAL_BLACKLIST = ["pipe", "eventlog/watch"]
    COMMAND_SECURITY = CC_WEB_TERMINAL

    def command(self):
        global sessions

        config = self.session.config
        cmd = self.data.get('command', [''])[0]
        sid = self.data.get('sid', [''])[0]
        if sid == '':
            return self._error(_('No session ID supplied'), result={'sessions': sessions.keys()})
        if sid not in sessions.keys():
            return self._error(_('Unknown session ID'), result={'sessions': sessions.keys()})
        session = sessions[sid]

        cmd = cmd.split(" ")
        command = cmd[0]
        args = ' '.join(cmd[1:])

        if command in self.TERMINAL_BLACKLIST:
            return self._error(_('Command disallowed'), result={})
        try:
            result = Action(session, command, args)
        except Exception, e:
            result = {"error": "Fail!"}

        return self._success(_('Ran a command'), result={
            'result': result,
            'sessions': sessions.keys()
        })

_plugins.register_commands(
    TerminalCommand, TerminalSessionNew, TerminalSessionEnd
)
