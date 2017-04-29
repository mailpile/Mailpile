# This is our very own Clippy replacement...

import time

from gettext import gettext
from mailpile.plugins import PluginManager

_ = lambda t: t


##[ Pluggable commands and data views ]#######################################

import random
from mailpile.config.defaults import APPVER
from mailpile.commands import Command
from mailpile.util import md5_hex


TIMESTAMPS = None


class hintsCommand(Command):
    """Provide periodic hints to the user"""
    SYNOPSIS_ARGS = '[now|reset]'
    SPLIT_ARG = True
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
       'now': 'Request a single due hint',
       'context': 'Current UI context'
    }

    ALL_HINTS = [
        # ID, Min age (in days), Interval, Short hint, Details, [Precondition]
        (APPVER, 0, 99999,
            _('This is Mailpile version %s') % APPVER,
            # Note: The style of quotes matters here, because the JS sucks
            #       a bit. Single quotes only please!
            "javascript:Mailpile.plugins.hints.release_notes();"),
        ('deletion', 3, 30,
            _('Your Mailpile is configured to never delete e-mail'),
            '/page/hints/deletion.html',
            lambda cfg, ctx: not cfg.prefs.allow_deletion),
        ('keyboard', 5, 30,
            _('Mailpile has keyboard short-cuts!'),
            "javascript:Mailpile.plugins.hints.keybindings();"),
        ('backups', 7, 6,
            _('You really should make backups of your Mailpile'),
            '/page/hints/backups.html'),

	# FIXME: Say something about the spam filter
	# Kept pattern of incrementing the minimum age by two days.
	#Chose interval as 6, because the user should manage their spam on a frequent basis.
	('spam', 9, 6,
            _('No one likes Spam!'),
            '/page/hints/spam.html'),

	# FIXME: Say something about autotagging
	# Kept pattern of incrementing the minimum age by two days.
	# Chose interval of 30, because this hint won't affect the security of their email. 		
	# Becasue it is a usability hint, the interval can be longer.
	('autotagging', 11, 30,
            _('What is autotagging anyway?'),
            '/page/hints/autotagging.html')]
       
        

    def _today(self):
        return int(time.time() // (24*3600))

    def timestamps(self):
        global TIMESTAMPS
        if TIMESTAMPS is None:
            try:
                TIMESTAMPS = self.session.config.load_pickle('hints.dat')
            except:
                TIMESTAMPS = {'initial': self._today()}
                self.save_timestamps()
        return TIMESTAMPS

    def save_timestamps(self):
        global TIMESTAMPS
        if TIMESTAMPS:
            self.session.config.save_pickle(TIMESTAMPS, 'hints.dat')

    def _days(self):
        return int(self._today() - self.timestamps()['initial'])

    def _hint_days(self, hint):
        # This will allow the user to postpone a hint; we check the timestamp
        # data file before falling back to the hardcoded default.
        return int(self.timestamps().get('days:%s' % hint[0], hint[1]))

    def _postpone_hint(self, hint, days=None):
        ts = self.timestamps()
        ts['days:%s' % hint[0]] = int(self._days() + (days or hint[2]))
        ts['last_displayed'] = self._today()
        self.save_timestamps()

    def _hint_applies(self, hint, ctx):
        if len(hint) > 5:
            return hint[5](self.session.config, ctx)
        else:
            return True

    def _hint_event(self, ctx, hint):
        applies = self._hint_applies(hint, ctx)

        in_days = max(0, self._hint_days(hint) - self._days())
        if in_days > 9999:
            in_days = _('never')

        action_url, action_cls = hint[4], ''
        if action_url.startswith('/page/'):
            action_cls = 'auto-modal'

        return {
            'action_cls': action_cls,
            'action_url': action_url,
            'action_text': _('learn more') if hint[3] else '',
            'applies': applies,
            'message': _('Did you know') + ' ...',
            'message2': _(hint[3]),
            'in_days': in_days,
            'interval': hint[2],
            'data': {},
            'name': hint[0]}

    def _choose_hint(self, ctx):
        if self._today() == self.timestamps().get('last_displayed'):
            return None

        days = self._days()
        hints = [(self._hint_days(h) - days, h)
                 for h in self.ALL_HINTS if self._hint_applies(h, ctx)]

        if hints:
            oldest = min(hints)
            if oldest[0] <= 0:
                return oldest[1]

        return None

    def command(self):
        ctx = self.data.get('context')

        if 'reset' in self.args:
            assert(self.data.get('_method', 'POST') == 'POST')
            ts = self.timestamps()
            for k in ts.keys():
                del ts[k]
            ts['initial'] = self._today()

        elif 'next' in self.args:
            assert(self.data.get('_method', 'POST') == 'POST')
            self.timestamps()['last_displayed'] = 0
            self.timestamps()['initial'] -= 30

        if 'now' in self.args or 'now' in self.data:
            hint = self._choose_hint(ctx)
            if hint:
                if 'POST' == self.data.get('_method', 'POST'):
                    self._postpone_hint(hint)
                return self._success(hint[3], result={
                    'hints': [self._hint_event(ctx, hint)]})
            else:
                return self._success(_('Nothing Happened'), result={
                    'hints': []})
        else:
            return self._success(_('Did you know') + ' ...', result={
                'today': self._today(),
                'days': self._days(),
                'ts': self.timestamps(),
                'hints': [self._hint_event(ctx, h) for h in self.ALL_HINTS]})


_ = gettext
# EOF #
