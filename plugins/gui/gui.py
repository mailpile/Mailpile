import json
import os
import subprocess
import sys
import threading
import time

import mailpile.auth
from mailpile.util import *
from mailpile.i18n import gettext as _


__INDICATOR = None


def indicator(command, **kwargs):
    __INDICATOR.stdin.write('%s %s\n' % (command, json.dumps(kwargs)))


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

    script = os.path.join(os.path.dirname(__file__), 'mailpile-indicator.py')

    global __INDICATOR
    i = __INDICATOR = subprocess.Popen(['python', '-u', script],
                                       bufsize=1,  # line buffered
                                       stdin=subprocess.PIPE,
                                       **popen_ignore_signals)
    i.stdin.write(json.dumps({
        'cookie': cookie,
        'session_id': session_id,
        'menu': [
            ['status', '',     ''],
            ['open',   'show', base_url],
            ['quit',   'get',  base_url + '/api/0/quitquitquit/']
        ]
    }).strip() + '\nOK GO\n')

    indicator('set_menu_name', item='status', name=_('Starting up ...'))
    indicator('set_menu_name', item='open', name=_('Open Mailpile'))
    indicator('set_menu_name', item='quit', name=_('Quit'))
    while config.index is None or not config.tags:
        time.sleep(1)

    indicator('set_status_normal')
    indicator('set_menu_sensitive', item='open')
    indicator('set_menu_sensitive', item='quit')

    # FIXME: We should do more with the indicator... this is a bit lame.
    while True:
        if mailpile.util.QUITTING:
            indicator('set_status_working')
            indicator('set_menu_sensitive', item='open', sensitive=False)
            indicator('set_menu_sensitive', item='quit', sensitive=False)
            indicator('set_menu_name',
                item='status', name=_('Shutting down...'))
            i.stdin.close()
            break
        else:
            indicator('set_menu_name',
                item='status',
                name=_('%d messages') % len(config.index.INDEX))
            time.sleep(5)
