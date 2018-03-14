import json
import select
import socket
import threading
import time

import mailpile.auth
import mailpile.util
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.plugins import PluginManager
from mailpile.ui import Session
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)
_GUIS = {}


def UpdateGUIState():
    for gui in _GUIS.values():
        gui.change_state()


def GetUserSecret(config):
    """Return a secret that only this Unix user could know."""
    return 'FIXME12345'


class GuiOMaticConnection(threading.Thread):
    def __init__(self, config, sock, main=False):
        threading.Thread.__init__(self)
        self.daemon = True
        self.config = config
        self._am_main = True # main
        self._sock = sock
        self._state = self._state_startup
        self._lock = threading.Lock()

    def _do(self, command, **args):
        try:
            if self._sock:
                self._sock.sendall('%s %s\n' % (command, json.dumps(args)))
        except IOError:
            if self._am_main:
                from mailpile.plugins.core import Quit
                Quit(self.config.background, 'quit').run()
            self._sock = False

    def _select_sleep(self, seconds):
        select.select([self._sock], [], [self._sock], seconds)

    def _state_startup(self, in_state):
        if in_state:
            self._do('set_status', status='startup')
            self._do('notify_user', message=_('Connected'))
            if self._am_main:
                self._do('set_item_label',
                    item='quit', label=_("Shutdown Mailpile"))
                self._do('set_item_label',
                    item='quit_button', label=_("Shutdown"))
            for ss in ('mailpile', 'logged_in', 'remote_access'):
                self._do('set_substatus', substatus=ss, color='#999')
        else:
            self._select_sleep(2)
            self._do('hide_splash_screen')
            self._do('show_main_window')
            self._do('set_item_sensitive', item='main')
            self._do('set_item_sensitive', item='browse')
            self._do('set_substatus',
                substatus='mailpile',
                color='#333',
                icon='icon:logo',
                label=_('Welcome to Mailpile!'),
                hint=_('Mailpile is now running on this computer.'))

    def _state_need_setup(self, in_state):
        if in_state:
            self._do('set_status', status='attention')
            self._do('set_substatus',
                substatus="logged-in",
                color='#333',
                icon='icon:new-setup',
                label=_('Brand new installation!'),
                hint=(_('This appears to be a new installation of Mailpile!')
                      + '\n' +
                      _('You need to choose a language, password and privacy policy.')
                      + '\n' +
                      _('To proceed, open Mailpile in your web browser.')))

    def _state_please_log_in(self, in_state):
        if in_state:
            self._do('set_status', status='attention')
            self._do('set_substatus',
                substatus="logged-in",
                color='#777',
                icon='icon:logged-out',
                label=_('Not logged in'),
                hint=(_('Your data is stored encrypted and is'
                        ' inaccessible until you log in.')
                      + '\n' +
                      _('To proceed, open Mailpile in your web browser.')))

    def _state_logged_in(self, in_state):
        if in_state:
            self._do('set_status', status='normal')
            self._do('set_substatus',
                substatus='logged-in',
                icon='icon:logged-in',
                color='#444',
                label=_('You are logged in'),
                hint=_('Mailpile can now process and display your e-mail.'))

    def _state_shutting_down(self, in_state):
        if in_state:
            self._do('set_status', status='shutdown')
            self._do('notify_user', message=_('Shutting down'))

    def _choose_state(self):
        from mailpile.plugins.setup_magic import Setup
        if mailpile.util.QUITTING:
            return self._state_shutting_down
        elif Setup.Next(self.config, 'anything') != 'anything':
            return self._state_need_setup
        elif not self.config.loaded_config:
            return self._state_please_log_in
        else:
            return self._state_logged_in

    def change_state(self):
        with self._lock:
            next_state = self._choose_state()
            if next_state != self._state:
                self._state(False)
                self._state = next_state
                self._state(True)
                return True
            else:
                if self.config.index:
                    msg_count = len(self.config.index.INDEX)
                    label = _('Mailpile: %d messages') % msg_count
                elif not self.config.loaded_config:
                    label = _('Mailpile') + ': ' + _('Please log in')
                else:
                    label = _('This is Mailpile!')
                self._do('set_item_label', item="status", label=label)
                return False

    def run(self):
        tid = self.ident
        try:
            with self._lock:
                _GUIS[tid] = self
                self._state(True)
            while self._sock:
                self._select_sleep(1)  # FIXME: Lengthen this when possible
                self.change_state()
        finally:
            del _GUIS[tid]


class ConnectToGuiOMatic(Command):
    """Connect to a waiting gui-o-matic GUI"""
    SYNOPSIS = (None, 'gui', 'gui', '[<secret>] [main|watch] <port>')
    ORDER = ('Internals', 9)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_AUTH_REQUIRED = False

    def command(self):
        if self.data.get('_method'):
            secret, style, port = self.args
            if secret != GetUserSecret(self.session.config):
                raise AccessError('Invalid User Secret')
        elif len(self.args) == 2:
            style, port = self.args
        elif len(self.args) == 1:
            style, port = 'main', self.args[0]

        with ConnBroker.context(need=[ConnBroker.OUTGOING_RAW]):
            guic = GuiOMaticConnection(
                self.session.config,
                socket.create_connection(('localhost', int(port))),
                main=(style == 'main'))
        guic.start()

        return self._success("OK")


_plugins.register_commands(ConnectToGuiOMatic)
