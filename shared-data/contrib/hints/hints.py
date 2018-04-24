# This is our very own Clippy replacement...

import time

from gettext import gettext
from mailpile.plugins import PluginManager

_ = lambda t: t


##[ Pluggable commands and data views ]#######################################

import random
from mailpile.config.defaults import APPVER
from mailpile.commands import Command
from mailpile.util import md5_hex, safe_assert


TIMESTAMPS = None


def BrokenSpambayes(cfg, ctx):
    if 'autotag_sb' not in cfg.sys.plugins:
        return True
    try:
        import spambayes
        return False
    except:
        return True


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

        ('deletion', 3, 90,
            _('Your Mailpile is configured to never delete e-mail'),
            '/page/hints/deletion.html',
            lambda cfg, ctx: not cfg.prefs.allow_deletion),

        ('spam-dependencies', 0, 1,
            _('Your spam filter is broken: please install spambayes'),
            '/page/hints/spambayes.html',
            BrokenSpambayes),

        ('keyboard', 4, 180,
            _('Mailpile has keyboard shortcuts!'),
            "/page/hints/keyboard-shortcuts.html",
            lambda cfg, cgx: not cfg.web.keybindings),

        # Remind the user to manage their spam every 3 months.
        # FIXME: Allow user to somehow say "I know, shutup".
        ('spam', 5, 90,
            _('Learn how to get the most out of Mailpile\'s spam filter'),
            '/page/hints/spam.html'),

	# Show the user how to organize their sidebar after 6 days.
	('organize-sidebar', 6, 99999,
	    _('Rearrange your sidebar to organize how you see your e-mail'),
	    '/page/hints/organize-sidebar.html'),

        # Introduce Gravatar integration after 10 days, and yearly repetition.
        # Remind of the privacy implications
        ('gravatar', 10, 365,
            _('Mailpile uses Gravatar thumbnails!'),
            '/page/hints/gravatar.html'),

        # Don't bother the user about backups unless they've been using the
        # app for at least 2 weeks. After that, only bug them every 6 months.
        # FIXME: Allow user to somehow say "I have backups, shutup".
        ('backups', 14, 180,
            _('You really should make backups of your Mailpile'),
            '/page/hints/backups.html'),

        # Introduce autotagging after 3 weeks, remind the user once per year.
        # This isn't something that justifies much nagging.
        ('autotagging', 21, 365,
            _('Mailpile can automatically tag or untag any kind of e-mail!'),
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
            safe_assert(self.data.get('_method', 'POST') == 'POST')
            ts = self.timestamps()
            for k in ts.keys():
                del ts[k]
            ts['initial'] = self._today()

        elif 'next' in self.args:
            safe_assert(self.data.get('_method', 'POST') == 'POST')
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
