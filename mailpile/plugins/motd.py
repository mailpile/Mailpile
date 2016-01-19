import os
import json
import sys
from datetime import datetime as dtime
from urllib2 import urlopen

from mailpile.conn_brokers import Master as ConnBroker
from mailpile.defaults import APPVER
from mailpile.plugins import PluginManager
from mailpile.commands import Command
from mailpile.config import PublicConfigRule as p
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


_ = lambda t: t
_plugins = PluginManager(builtin=__file__)


_plugins.register_config_variables('prefs', {
    'motd_url': p(
        _('URL to the Message Of The Day'),
        'url',
        'https://www.mailpile.is/motd/%(ver)s/motd.json?l=%(lang)s&p=%(py)s'
    )
})


class MessageOfTheDay(Command):
    """Download and/or display the Message Of The Day"""
    SYNOPSIS = (None, 'motd', 'motd', '[--silent|--ifnew] [--[no]update|--check]')
    ORDER = ('Internals', 6)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False

    @classmethod
    def _seen_release_notes(cls, session):
        return not session.config.web.release_notes

    @classmethod
    def update(cls, session):
        # Don't auto-update the MOTD if the user hasn't seen the release
        # notes. This keeps us from hitting the network right away on first
        # install, and keeps this from triggering in test code. Also, we
        # don't want to overload the user with new stuff.
        if cls._seen_release_notes(session):
            cls(session, arg=['--silent', '--update']).run()

    def _get(self, url):
        if url.startswith('file:'):
            return open(url[5:], 'r').read()

        if url.startswith('https:'):
            conn_need = [ConnBroker.OUTGOING_HTTPS]
        elif url.startswith('http:'):
            conn_need = [ConnBroker.OUTGOING_HTTP]
        else:
            return _('Unsupported URL for message of the day: %s') % url

        conn_reject = [ConnBroker.OUTGOING_TRACKABLE]
        with ConnBroker.context(need=conn_need, reject=conn_reject) as ctx:
            self.session.ui.mark('Getting: %s' % url)
            return urlopen(url, data=None, timeout=10).read()

    class CommandResult(Command.CommandResult):
        def as_text(self):
            motd = self.result.get('_motd')
            if not motd:
                return ''

            date = dtime.fromtimestamp(self.result.get('timestamp', 0))
            return '%s, %4.4d-%2.2d-%2.2d:\n\n    %s\n\n*** %s ***\n' % (
                _('Message Of The Day'),
                date.year, date.month, date.day,
                motd.replace('\n', '\n    '),
                self.result.get('_version_info')
            )

    def command(self):
        session, config = self.session, self.session.config

        old_motd = motd = None
        try:
            old_motd = motd = config.load_pickle('last_motd')
            message = '%s: %s' % (_('Message Of The Day'), _('Loaded'))
        except (OSError, IOError):
            pass

        if '--ifnew' in self.args and not self._seen_release_notes(session):
            # Silently return nothing in this case.
            return self._success('', result={})

        if '--update' in self.args:
            motd = None
        elif motd and '--check' in self.args:
            if motd['_updated'] < time.time() - 23.5 * 3600:
                motd = None

        if not motd:
            if '--noupdate' in self.args:
                # Silently return nothing in this case.
                return self._success('', result={})

            url = config.prefs.motd_url % {
                'ver': APPVER,
                'lang': config.prefs.language or 'en',
                'py': '%s-%s' % (sys.platform, sys.version.split()[0])
            }
            try:
                motd = json.loads(self._get(url))
                motd['_updated'] = int(time.time())
                motd['_is_new'] = False
                if (not old_motd
                        or old_motd.get("timestamp") != motd.get("timestamp")):
                    config.save_pickle(motd, 'last_motd', encrypt=False)
                    motd['_is_new'] = True
                    message = '%s: %s' % (_('Message Of The Day'), _('Updated'))
            except (IOError, OSError):
                pass

        if not motd:
            motd = old_motd

        if motd:
            self.event.data['motd'] = motd

            lang = config.prefs.language or 'en'
            motd['_motd'] = motd.get(lang, motd.get('en'))

            latest = motd.get('latest_version')
            if not latest:
                motd['_version_info'] = _('Mailpile update info unavailable')
            elif latest == APPVER:
                motd['_version_info'] = _('Your Mailpile is up to date')
            else:
                motd['_version_info'] = _('An upgrade for Mailpile is '
                                          'available, version %s'
                                          ) % latest

            if '--silent' in self.args:
                motd = {}
            elif '--ifnew' in self.args and not motd.get('_is_new'):
                motd = {}

            return self._success(message, result=motd)
        else:
            message = '%s: %s' % (_('Message Of The Day'), _('Unknown'))
            return self._error(message, result={})


_plugins.register_commands(MessageOfTheDay)
_plugins.register_slow_periodic_job('motd', 3600, MessageOfTheDay.update)
