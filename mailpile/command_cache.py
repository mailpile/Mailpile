import time

import mailpile.util
from mailpile.commands import Command
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.util import *
from mailpile.ui import Session, BackgroundInteraction


_plugins = PluginManager(builtin=__name__)


class CommandCache(object):
    #
    # This is an in-memory cache of commands and results we may want to
    # refresh in the background and/or reuse.
    #
    # The way this works:
    #     - Cache-able commands generate a fingerprint describing themselves.
    #     - If the fingerprint is found in cache, reuse the result object.
    #     - Otherwise, run, generate a list of requirements and cache all of:
    #       the command object itself, the requirements, the result object.
    #     - Internal state changes (tag ops, new mail, etc.) call mark_dirty()
    #       describing which assets (requirements) have changed.
    #     - Periodically, the cache is refreshed, which re-runs any dirtied
    #       commands and fires events notifying the UI about changes.
    #
    # Examples of requirements:
    #
    #    - Search terms, eg. 'in:inbox' or 'potato' or 'salad'
    #    - Messages: 'msg:INDEX' where INDEX is a number (not a MID)
    #    - Threads: 'thread:MID' were MID is the thread ID.
    #    - The app configuration: '!config'
    #

    def __init__(self, debug=None):
        self.debug = debug or (lambda s: None)
        self.lock = UiRLock()
        self._lag = 0.1
        self.cache = {}       # id -> [exp, req, ss, cmd_obj, res_obj, added]
        self.dirty = []       # (ts, req): Requirements that changed & when
        self._dirty_ttl = 10

    def cache_result(self, fprint, expires, req, cmd_obj, result_obj):
        with self.lock:
            # Make a snapshot of the session, as it provides context
            ss = Session.Snapshot(cmd_obj.session, ui=False)
            ss.ui = BackgroundInteraction(cmd_obj.session.config,
                                          log_parent=cmd_obj.session.ui)

            # Note: We cache this even if the requirements are "dirty",
            #       as mere presence in the cache makes this a candidate
            #       for refreshing.
            self.cache[str(fprint)] = [expires, req, ss, cmd_obj, result_obj,
                                       time.time()]
            self.debug('Cached %s, req=%s' % (fprint, sorted(list(req))))

    def get_result(self, fprint, dirty_check=True, extend=300):
        with self.lock:
            exp, req, ss, co, result_obj, a = match = self.cache[fprint]
        if dirty_check:
            recent = (a > time.time() - self._lag)
            dirty = (req & self.dirty_set(after=a))
            if recent or dirty:
                # If item is too new, or requirements are dirty, pretend this
                # item does not exist.
                self.debug('Suppressing cache result %s, recent=%s dirty=%s'
                           % (fprint, recent, sorted(list(dirty))))
                raise KeyError(fprint)
        match[0] = time.time() + extend
        co.session = result_obj.session = ss
        self.debug('Returning cached result for %s' % fprint)
        return result_obj

    def dirty_set(self, after=0):
        dirty = set(['!timedout'])
        with self.lock:
            for ts, req in self.dirty:
                if (after == 0) or (ts > after):
                    dirty |= req
        return dirty

    def mark_dirty(self, requirements):
        with self.lock:
            self.dirty.append((time.time(), set(requirements)))
        self.debug('Marked dirty: %s' % sorted(list(requirements)))

    def refresh(self, extend=0, runtime=5, event_log=None):
        if mailpile.util.LIVE_USER_ACTIVITIES > 0:
            self.debug('Skipping cache refresh, user is waiting.')
            return

        started = now = time.time()
        with self.lock:
            # Expire things from the cache
            expired = set([f for f in self.cache if self.cache[f][0] < now])
            for fp in expired:
                del self.cache[fp]

            # Expire things from the dirty set
            self.dirty = [(ts, req) for ts, req in self.dirty
                          if ts >= (now - self._dirty_ttl)]

            # Decide which fingerprints to look at this time around
            fingerprints = list(self.cache.keys())

        refreshed = []
        fingerprints.sort(key=lambda k: -self.cache[k][0])
        for fprint in fingerprints:
            req = None
            try:
                e, req, ss, co, ro, a = self.cache[fprint]
                now = time.time()
                dirty = (req & self.dirty_set(after=a))
                if (a + self._lag < now) and dirty:
                    if now < started + runtime:
                        play_nice_with_threads()
                        co.session = ro.session = ss
                        ro = co.refresh()
                        if extend > 0:
                            e = min(e + extend, now + 5*extend)
                        if '!timedout' in req:
                            req.remove('!timedout')
                        with self.lock:
                            # Make sure we do not overwrite new results from
                            # elsewhere at this time.
                            if self.cache[fprint][-1] == a:
                                e = max(e, self.cache[fprint][0])  # Clobber?
                                self.cache[fprint] = [e, req, ss, co, ro, now]
                            refreshed.append(fprint)
                    else:
                        # Out of time, mark as dirty.
                        req.add('!timedout')
            except (ValueError, IndexError, TypeError):
                # Treat broken things as if they had timed out
                if req:
                    req.add('!timedout')

        if refreshed and event_log:
            event_log.log(message=_('New results are available'),
                          source=self,
                          data={'cache_ids': refreshed},
                          flags=Event.COMPLETE)
            self.debug('Refreshed: %s' % refreshed)


class Cached(Command):
    """Fetch results from the command cache."""
    SYNOPSIS = (None, 'cached', 'cached', '[<cache-id>]')
    ORDER = ('Internals', 7)
    HTTP_QUERY_VARS = {'id': 'Cache ID of command to redisplay'}
    IS_USER_ACTIVITY = False
    LOG_NOTHING = True

    # Warning: This depends on internals of Command, how things are run there.
    def run(self):
        try:
            cid = self.args[0] if self.args else self.data.get('id', [None])[0]
            rv = self.session.config.command_cache.get_result(cid)
            self.session.copy(rv.session)
            rv.session.ui.render_mode = self.session.ui.render_mode
            return rv
        except:
            self._starting()
            self._error(self.FAILURE % {'name': self.name,
                                        'args': ' '.join(self.args)})
            return self._finishing(False)


_plugins.register_commands(Cached)
