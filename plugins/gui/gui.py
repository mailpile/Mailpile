import json
import os
import sys
import threading
import time

import mailpile.auth
from mailpile.util import *
from mailpile.i18n import gettext as _
from mailpile.safe_popen import Popen, PIPE


__GUI__ = None


def indicator(command, **kwargs):
    __GUI__.stdin.write('%s %s\n' % (command, json.dumps(kwargs)))


def startup(config):
    th = threading.Thread(target=_real_startup, args=[config])
    th.daemon = True
    th.start()


def _real_startup(config):
    while config.http_worker is None:
        time.sleep(0.1)

    session_id = config.http_worker.httpd.make_session_id(None)
    mailpile.auth.SetLoggedIn(None, user='GUI plugin client',
                                    session_id=session_id)
    cookie = config.http_worker.httpd.session_cookie
    base_url = 'http://%s:%s' % (config.sys.http_host, config.sys.http_port)

    script_dir = os.path.dirname(os.path.realpath(__file__))
    script = os.path.join(script_dir, 'gui-o-matic.py')

    global __GUI__
    gui = __GUI__ = Popen(['python', '-u', script],
                          bufsize=1,  # line buffered
                          stdin=PIPE,
                          long_running=True)
    ico = lambda s: os.path.join(script_dir, 'icons-%(theme)s', s)
    gui.stdin.write(json.dumps({
        'app_name': 'Mailpile',
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

    while config.index is None or not config.tags:
        time.sleep(1)

    indicator('set_status_normal')
    indicator('set_menu_sensitive', item='open')
    indicator('set_menu_sensitive', item='quit')

    # FIXME: We should do more with the indicator... this is a bit lame.
    while True:
        if mailpile.util.QUITTING:
            indicator('set_status_shutdown')
            indicator('set_menu_sensitive', item='open', sensitive=False)
            indicator('set_menu_sensitive', item='quit', sensitive=False)
            indicator('set_menu_label',
                item='status',
                label=_('Shutting down...'))
            time.sleep(300)
        else:
            indicator('set_menu_label',
                item='status',
                label=_('%d messages') % len(config.index.INDEX))
            time.sleep(5)
