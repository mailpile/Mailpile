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
from mailpile.i18n import ngettext as _n
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
        self._notified = {}

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
                self._do('set_item', id='quit', label=_("Shutdown Mailpile"))
                self._do('set_item', id='quit_button', label=_("Shutdown"))
            for ss in ('mailpile', 'logged-in', 'remote-access'):
                self._do('set_status_display', id=ss, color='#999')
        else:
            self._select_sleep(1)
            self._do('hide_splash_screen')
            self._do('show_main_window')
            self._do('set_item', id='main', sensitive=True)
            self._do('set_item', id='browse', sensitive=True)
            self._do('set_status_display',
                id='mailpile',
                color='#333',
                icon='image:logo',
                title=_('Welcome to Mailpile!'),
                details=_('Mailpile is now running on this computer.'))

    def _state_need_setup(self, in_state):
        if in_state:
            self._do('set_status', status='attention')
            self._do('set_status_display',
                id="logged-in",
                color='#333',
                icon='image:new-setup',
                title=_('Brand new installation!'),
                details=(
                    _('This appears to be a new installation of Mailpile!')
                    + '\n' +
                    _('You need to choose a language, password and privacy policy.')
                    + '\n' +
                    _('To proceed, open Mailpile in your web browser.')))

    def _state_please_log_in(self, in_state):
        if in_state:
            self._do('set_status', status='attention')
            self._do('set_status_display',
                id="logged-in",
                color='#777',
                icon='image:logged-out',
                title=_('Not logged in'),
                details=(_('Your data is stored encrypted and is'
                           ' inaccessible until you log in.')
                         + '\n' +
                         _('To proceed, open Mailpile in your web browser.')))

    def _state_loading_index(self, in_state):
        if in_state:
            self._do('set_status', status='working')
            self._do('set_status_display',
                id='logged-in',
                color='#444',
                title=_('Logging you in...'))

    def _state_logged_in(self, in_state):
        if in_state:
            self._do('set_status', status='normal')
            self._do('set_status_display',
                id='logged-in',
                icon='image:logged-in',
                color='#444',
                title=_('You are logged in'),
                details=_('Mailpile can now process and display your e-mail.'))

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
        elif self.config.index_loading:
            return self._state_loading_index
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
                label = None

                if self.config.index_loading:
                    pass  # new_mail_notifications handles this
                elif self._state in (self._state_need_setup,):
                    label =  _('Mailpile') + ': ' + _('New Installation')
                elif self._state not in (
                        self._state_logged_in, self._state_shutting_down):
                    label = _('Mailpile') + ': ' + _('Please log in')

                # FIXME: We rely on sending garbage over the socket
                #        regularly to check for errors. When that is
                #        gone we might not need to be so chatty.
                #        Until then: do not remove, it breaks shutdown!
                if label:
                    self._do('set_item', id="notification", label=label)

                return False

    def new_mail_notifications(self, summarize=False):
        # FIXME: This is quite a lot of set operations that don't really
        #        belong here. Or do they? This feels out of place.
        if self.config.index_loading:
            self._do('set_status_display',
                id='logged-in',
                details=_(
                    'Loaded metadata for {num} messages so far, please wait.'
                    ).format(num=len(self.config.index_loading.INDEX)))
            return
        if self._state != self._state_logged_in:
            return
        if not self._notified:
            summarize = True

        new_messages = set([])
        for tag in self.config.get_tags(type='unread'):
            new_messages |= self.config.index.TAGS.get(tag._key, set([]))

        hidden_messages = set([])
        for tag in self.config.get_tags(flag_hides=True):
            hidden_messages |= self.config.index.TAGS.get(tag._key, set([]))

        notify = {}
        for tag in self.config.get_tags(notify_new=True):
            already_notified = self._notified.get(tag._key, set([]))
            all_in_tag = (self.config.index.TAGS.get(tag._key, set([]))
                          - hidden_messages)
            new_in_tag = (all_in_tag & new_messages)
            new_new_in_tag = (all_in_tag - already_notified)
            if new_in_tag or new_new_in_tag:
                notify[tag._key] = (tag, new_in_tag, new_new_in_tag)
            self._notified[tag._key] = all_in_tag

        all_new = set([])
        all_new_new = set([])
        for tag, new_in_tag, new_new_in_tag in notify.values():
            all_new |= new_in_tag
            all_new_new |= new_new_in_tag
        unread = len(all_new)
        count = len(all_new_new)

        if count == 1:
            # FIXME: There is only one brand new message.
            #        Tell the user more about it.
            pass

        tag_count = len(notify.keys())
        if (tag_count == 0) and (count == 0):
            message=_('No new mail, {num} messages total.'
                      ).format(num=len(self.config.index.INDEX))

        elif tag_count == 1:
            tag, new_msgs, new_new_msgs = notify.values()[0]
            if new_new_msgs and not summarize:
                message=_('{tagName}: {new} new messages ({num} unread)'
                          ).format(new=len(new_new_msgs),
                                   num=len(new_msgs),
                                   tagName=tag.name)
            else:
                message=_('{tagName}: {num} unread messages'
                          ).format(num=len(new_msgs), tagName=tag.name)
        else:
            message=_('You have {num} unread messages in {tags} tags'
                      ).format(num=unread, tags=tag_count)

        self._do('notify_user', popup=(count > 0), message=message)


    def run(self):
        tid = self.ident
        try:
            with self._lock:
                _GUIS[tid] = self
                self._state(True)
            self.new_mail_notifications(summarize=True)
            loop_count = 0
            while self._sock:
                loop_count += 1
                self._select_sleep(1)  # FIXME: Lengthen this when possible
                self.change_state()
                if loop_count % 5 == 0:
                    # FIXME: This involves a fair number of set operations,
                    #        should only do this after new mail has arrived.
                    self.new_mail_notifications()
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
