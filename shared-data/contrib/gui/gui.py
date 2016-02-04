import json
import os
import sys
import threading
import time
import webbrowser

import mailpile.auth
import mailpile.util
from mailpile.commands import Quit
from mailpile.i18n import gettext as _
from mailpile.safe_popen import Popen, PIPE, MakePopenSafe, MakePopenUnsafe
from mailpile.ui import Session
from mailpile.util import *


__GUI__ = None


def indicator(command, **kwargs):
    __GUI__.stdin.write('%s %s\n' % (command, json.dumps(kwargs)))


def startup(config):
    if sys.platform in ('darwin', ) or os.getenv('DISPLAY'):
        th = threading.Thread(target=_real_startup, args=[config])
        th.name = 'GUI'
        th.daemon = True
        th.start()


def output_eater(fd, buf):
    for line in fd:
        buf.append(line)


def _real_startup(config):
    return  # FIXME: Just disable this for now, it's dumb.

    while config.http_worker is None:
        time.sleep(0.1)

    try:
        session_id = config.http_worker.httpd.make_session_id(None)
        mailpile.auth.SetLoggedIn(None, user='GUI plugin client',
                                        session_id=session_id)
        cookie = config.http_worker.httpd.session_cookie
        sspec = config.http_worker.httpd.sspec
        base_url = 'http://%s:%s%s' % sspec

        script_dir = os.path.dirname(os.path.realpath(__file__))
        script = os.path.join(script_dir, 'gui-o-matic.py')

        global __GUI__
        gui = __GUI__ = Popen(['python', '-u', script],
                              bufsize=1,  # line buffered
                              stdin=PIPE, stderr=PIPE,
                              long_running=True)
        stderr = []
        eater = threading.Thread(target=output_eater,
                                 args=[gui.stderr, stderr])
        eater.name = 'GUI(stderr)'
        eater.daemon = True
        eater.start()

        ico = lambda s: os.path.join(script_dir, 'icons-%(theme)s', s)
        gui.stdin.write(json.dumps({
            'app_name': 'Mailpile',
            'external_browser': True,
            'indicator_icons': {
                'startup': ico('startup.png'),
                'normal': ico('normal.png'),
                'working': ico('working.png'),
                'attention': ico('attention.png'),
                'shutdown': ico('shutdown.png')
            },
            'indicator_menu': [
                {
                    'label': _('Starting up ...'),
                    'item': 'status'
                },{
                    'label': _('Open Mailpile'),
                    'item': 'open',
                    'op': 'show_url',
                    'args': [base_url]
                },{
                    'label': _('Quit'),
                    'item': 'quit',
                    'op': 'get_url',
                    'args': [base_url + '/api/0/quitquitquit/']
                }
            ],
            'http_cookies': {
                 base_url: [[cookie, session_id]]
            },
        }).strip() + '\nOK GO\n')

        indicator('show_splash_screen',
                  image=ico('startup.png'),
                  message=_("Starting Mailpile"),
                  progress_bar=False)
        indicator('set_menu_sensitive', item='quit')
        indicator('set_menu_sensitive', item='open')
        indicator('hide_splash_screen')
        if (gui.poll() is not None) or mailpile.util.QUITTING:
            return

    except:
        # If the basic indicator setup fails, we just assume it doesn't
        # work and go silently dead...
        return

    quitting = False
    try:
        # ...however, getting this far means if the indicator dies, then
        # the user tried to quit the app, so we should cooperate and die
        # (via the except below).

        while config.index is None or not config.tags:
            if mailpile.util.QUITTING:
                return
            if gui.poll() is not None:
                return
            time.sleep(1)
        indicator('set_status_normal')

        # FIXME: We should do more with the indicator... this is a bit lame.
        while True:
            if mailpile.util.QUITTING:
                quitting = True
                indicator('set_status_shutdown')
                indicator('set_menu_sensitive', item='open', sensitive=False)
                indicator('set_menu_sensitive', item='quit', sensitive=False)
                indicator('set_menu_label',
                    item='status',
                    label=_('Shutting down...'))
                l = threading.Lock()
                l.acquire()
                l.acquire()  # Deadlock, until app quits
            else:
                indicator('set_menu_label',
                    item='status',
                    label=_('%d messages') % len(config.index and
                                                 config.index.INDEX or []))
                time.sleep(1)

    except AttributeError:
        pass
    finally:
        try:
            if not quitting:
                Quit(Session(config)).run()
        except:
            pass
