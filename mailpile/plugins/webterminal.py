import json
import random

from mailpile.app import FriendlyPipeTransform
from mailpile.commands import *
from mailpile.plugins import PluginManager
from mailpile.ui import Session
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.security import CC_WEB_TERMINAL

_plugins = PluginManager(builtin=__file__)

SESSIONS = {}


class TerminalSessionNew(Command):
    """Create a terminal session."""
    SYNOPSIS = ('', '', 'terminal_session_new', '')
    ABOUT = ('Start a new named session.')
    HTTP_CALLABLE = ('POST', )
    CONFIG_REQUIRED = True
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = CC_WEB_TERMINAL

    def command(self):
        global SESSIONS
        config = self.session.config

        s = Session(config)
        s.ui.log_parent = self.session.ui
        s.ui.render_mode = 'text'
        sid = "%08x" % random.randint(0, 1000000000)
        SESSIONS[sid] = s

        return self._success('Created a session', result={"sid": sid})


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
        global SESSIONS

        config = self.session.config
        sid = self.data.get('sid', [''])[0]
        if sid == '':
            return self._error('No SID supplied')

        del(SESSIONS[sid])

        return self._success('Ended a session', result={"sid": sid})


class TerminalCommand(Command):
    """Execute a terminal command."""
    SYNOPSIS = ('', '', 'terminal_command', '<command> <session>')
    ABOUT = ('Run a terminal command via the API')
    CONFIG_REQUIRED = True
    IS_USER_ACTIVITY = True
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {
        'sid': 'id of session to use',
        'width': 'width of terminal in characters',
        'command': 'command to execute'
    }
    TERMINAL_BLACKLIST = ["eventlog/watch", "hacks/pycli", "quit"]
    COMMAND_SECURITY = CC_WEB_TERMINAL

    def command(self):
        global SESSIONS

        config = self.session.config
        sid = self.data.get('sid', [''])[0]
        if sid == '':
            return self._error('No session ID supplied')
        if sid not in SESSIONS:
            return self._error(
                'Unknown session ID: %s' % sid, result={'sessions': SESSIONS.keys()})

        wt_session = SESSIONS[sid]
        max_width = int(float(self.data.get('width', [79])[0]))
        cmd = self.data.get('command', [''])[0]
        old_render_mode, cmd = FriendlyPipeTransform(wt_session, cmd)
        cmd = cmd.split(" ")
        command = cmd[0]
        args = ' '.join(cmd[1:])

        if command in self.TERMINAL_BLACKLIST:
            return self._error(
                _('This command is not allowed in the web terminal.'),
                result={})
        try:
            main_ui = wt_session.ui
            from mailpile.ui import CapturingUserInteraction as CUI
            wt_session.ui = capture = CUI(self.session.config, log_parent=self.session.ui)
            wt_session.ui.render_mode = main_ui.render_mode
            wt_session.ui.term.max_width = max_width

            result = Action(wt_session, command, args)
            if wt_session.ui.render_mode == 'html':
                wt_session.ui.render_mode = 'html!content'
            capture.display_result(result)
            rendered = [capture.render_mode.split('!')[0], capture.captured]

            # Allow the user to persistently change the render mode
            main_ui.render_mode = capture.render_mode
        except Exception as e:
            result = {"error": "%s" % e}
            rendered = ["text", "error: %s" % e]
        finally:
            wt_session.ui = main_ui

        if old_render_mode is not None:
            wt_session.ui.render_mode = old_render_mode
        return self._success(_('Ran a command'), result={
            'result': rendered,
            'raw_result': result,
            'sessions': SESSIONS.keys()})


_plugins.register_commands(
    TerminalCommand, TerminalSessionNew, TerminalSessionEnd)
