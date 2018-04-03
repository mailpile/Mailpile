#!/usr/bin/python2.7
#
# This is a basic GUI launcher for Mailpile.
#
# It relies on gui-o-matic for the actual GUI, the logic here is used to
# figure out if we need to launch a new Mailpile or if we can connect to
# one that is already running in the background.
#
# The script can also be run with --script as an argument to simply
# output the gui-o-matic launch sequence.
#
# It also supports --profile=... and --home=... for selecting alternate
# Mailpile data directories.
#
# Note: Most of the GUI behaviours are defined in `mailpile.plugins.gui`.
#       The logic here is just enough to configure our windows and display
#       a splash-screen. Arguably, more of this logic should be moved
#       into `mailpile.plugins.gui` so everything is in one place.
#
import copy
import fasteners
import json
import os
import sys
import subprocess
import threading
from cStringIO import StringIO

from mailpile.config.defaults import CONFIG_RULES
from mailpile.config.manager import ConfigManager
from mailpile.i18n import ActivateTranslation
from mailpile.i18n import gettext as _
from mailpile.plugins.gui import GetUserSecret


APPDIR = os.path.abspath(os.path.dirname(__file__))
if not os.path.exists(os.path.join(APPDIR, 'media', 'splash.jpg')):
    APPDIR = os.path.abspath(os.path.join(
        ConfigManager.DEFAULT_SHARED_DATADIR(), 'mailpile-gui'))

MEDIA_PATH = os.path.join(APPDIR, 'media')
ICONS_PATH = os.path.join(APPDIR, 'icons-%(theme)s')

MAILPILE_HOME_IMAGE   = os.path.join(MEDIA_PATH, 'background.jpg')
MAILPILE_SPLASH_IMAGE = os.path.join(MEDIA_PATH, 'splash.jpg')


def SPLASH_SCREEN(state, message):
    return {
        "background": MAILPILE_SPLASH_IMAGE,
        "width": 396,
        "height": 594,
        "message_y": 0.80,
        "progress_bar": True,
        "message": message}


def BASIC_GUI_CONFIGURATION(state):
    mailpile_home = state.base_url
    mailpile_quit = state.base_url + 'quitquitquit'
    oib_checked = True if state.pub_config.prefs.open_in_browser else False
    return {
        "app_name": "Mailpile",
        "app_icon": "image:logo",
        "images": {
            "logo":       os.path.join(MEDIA_PATH, 'logo-color.png'),
            "new-setup":  os.path.join(MEDIA_PATH, 'new-setup.svg'),
            "logged-in":  os.path.join(MEDIA_PATH, 'lock-open.svg'),
            "logged-out": os.path.join(MEDIA_PATH, 'lock-closed.svg'),
            "ra-on":      os.path.join(MEDIA_PATH, 'remote-access-on.svg'),
            "ra-off":     os.path.join(MEDIA_PATH, 'remote-access-off.svg'),
            "startup":    os.path.join(ICONS_PATH, 'startup.png'),
            "normal":     os.path.join(ICONS_PATH, 'normal.png'),
            "attention":  os.path.join(ICONS_PATH, 'attention.png'),
            "working":    os.path.join(ICONS_PATH, 'working.png'),
            "shutdown":   os.path.join(ICONS_PATH, 'shutdown.png')},
        "font_styles": {
            "title": {
                "family": "normal",
                "points": 18,
                "bold": True
            },
            "details": {
                "points": 10
            },
            "splash": {
                "points": 16
            },
            "notification": {
                "italic": True
            }
        },
        "main_window": {
            "show": False,
            "close_quits": False,
            "width": 550,
            "height": 330,
            "background": MAILPILE_HOME_IMAGE,
            "initial_notification": '',
            "status_displays": [{
                "id": "mailpile",
                "icon": "image:logo",
                "title": _("Mailpile is starting up"),
                "details": _("Patience is a virtue...")
            },{
                "id": "logged-in",
                "icon": "image:logged-out",
                "title": _("You are not logged in"),
            },{
                "id": "remote-access",
                "icon": "image:ra-off",
                "title": _("Remote access is disabled"),
                "details": _(
                    "Enable remote access if you would like to access\n"
                    "Mailpile from your phone or another computer.")
            }],
            "action_items": [{
                "id": "open",
                "position": "first",
                "label": _("Open in Web Browser"),
                "op": "show_url",
                "args": [mailpile_home]
            },{
                "id": "quit_button",
                "label": _("Quit GUI"),
                "position": "last",
                "op": "quit"}]},
        "indicator": {
            "initial_status": "startup",
            "menu_items": [{
                "id": "notification",
                "label": _("Starting up"),
                "sensitive": False
            },{
                "separator": True
            },{
                "id": "main",
                "label": _("Show Status Window"),
                "sensitive": False,
                "op": "show_main_window",
                "args": [],
            },{
                "id": "browse",
                "label": _("Open in Web Browser"),
                "sensitive": False,
                "op": "show_url",
                "args": [mailpile_home]
            },{
                "id": "screen",
                "label": _("Open in Terminal"),
                "sensitive": True,
                "op": "terminal",
                "args": {
                    "command": "screen -r -x mailpile",
                    "title": "mailpile"}
            },{
                "separator": True
            },{
                "id": "quit",
                "op": "quit",
                "sensitive": True,
                "args": [],
                "label": _("Quit GUI")}]}}


class MailpileState(object):
    def __init__(self):
        self.base_url = 'http://localhost:33411/'
        self.pub_config = None
        self.is_running = None
        self.secret = ''

    def check_if_running(self):
        # FIXME: This is rather slow. We should refactor upstream to speed
        #        up or include our own custom parser if that is infeasible.
        wd_lock_path = ConfigManager.LOCK_PATHS()[1]
        wd_lock = fasteners.InterProcessLock(wd_lock_path)
        try:
            if wd_lock.acquire(blocking=False):
                wd_lock.release()
                return False
            else:
                return True
        except (OSError, IOError):
            return False

    def _load_public_config(self):
        self.pub_config = ConfigManager(rules=CONFIG_RULES)
        try:
            self.pub_config.load(None, public_only=True)
            self.secret = GetUserSecret(self.pub_config)
            self.base_url = 'http://%s:%s%s/' % (
                self.pub_config.sys.http_host,
                self.pub_config.sys.http_port,
                self.pub_config.sys.http_path)
        except:
            self.pub_config = None

    def discover(self, argv):
        self._load_public_config()
        self.is_running = self.check_if_running()
        self.http_port = self.pub_config.sys.http_port

        # Check if we have a screen session?

        return self


def GenerateConfig(state):
    """Generate the basic gui-o-matic window configuration."""
    config = BASIC_GUI_CONFIGURATION(state)
    return json.dumps(config, indent=2)


def GenerateBootstrap(state):
    """
    Generate the gui-o-matic bootstrap sequence.

    Once this sequence completes, either we have failed and will die,
    or Mailpile (specifically `mailpile.plugins.gui`) will take over and
    start sending gui-o-matic commands to update the UI.
    """
    bootstrap = ["OK LISTEN"]

    if state.is_running:
        # If Mailpile is running already, connect and ask it to talk to us.
        bootstrap += [
            "show_main_window {}",
            "notify_user %s" % json.dumps({
                'message': _("Connecting to Mailpile")}),
            "set_next_error_message %s" % json.dumps({
                'message': _("Failed to connect to Mailpile!")}),
            "OK LISTEN HTTP: " + (
                '%sgui/%s/watch/%%PORT%%/' % (state.base_url, state.secret))]
    else:
        # If Mailpile is not running already, launch it in a screen session.
        bootstrap += [
            "show_splash_screen %s" % json.dumps(
                SPLASH_SCREEN(state, _("Launching Mailpile"))),
            "set_next_error_message %s" % json.dumps({
                'message': _("Failed to launch Mailpile!")}),
            "OK LISTEN TCP: " + (
                # FIXME: This should launch a screen session using the
                #        same concepts as multipile's mailpile-admin.
                'screen -S mailpile -d -m mailpile'
                ' --set="prefs.open_in_browser = false" '
                ' --gui=%PORT% --interact')]

    return '\n'.join(bootstrap)


def Main(argv):
    set_profile = set_home = False
    for arg in argv:
        if arg.startswith('--profile='):
            os.environ['MAILPILE_PROFILE'] = arg.split('=', 1)[-1]
            if 'MAILPILE_HOME' in os.environ:
                del os.environ['MAILPILE_HOME']
            set_profile = True
        elif arg.startswith('--home='):
            os.environ['MAILPILE_HOME'] = arg.split('=', 1)[-1]
            if 'MAILPILE_PROFILE' in os.environ:
                del os.environ['MAILPILE_PROFILE']
            set_home = True
    if set_home and set_profile:
        raise ValueError('Please only use one of --home and --profile')

    state = MailpileState().discover(argv)
    ActivateTranslation(None, state.pub_config, None)

    script = [
        GenerateConfig(state),
        GenerateBootstrap(state)]

    if '--script' in argv:
        print '\n'.join(script)

    else:
        # FIXME: We shouldn't need to do this, refactoring upstream
        #        to pull in less weird stuff would make sense.
        from mailpile.safe_popen import MakePopenUnsafe
        MakePopenUnsafe()

        from gui_o_matic.control import GUIPipeControl
        GUIPipeControl(StringIO('\n'.join(script) + '\n')).bootstrap()


if __name__ == "__main__":
    Main(sys.argv)
