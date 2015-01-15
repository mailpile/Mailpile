import time

import mailpile.util
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *
from mailpile.ui import Session, BackgroundInteraction


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
        self._lag = 0.5
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

    def get_result(self, fprint, dirty_check=True, extend=60):
        with self.lock:
            exp, req, ss, co, result_obj, a = match = self.cache[fprint]
        recent = (a > time.time() - self._lag)
        dirty = (dirty_check and (req & self.dirty_set(after=a)))
        if recent or dirty:
            # If item is too new, or requirements are dirty, pretend this
            # item does not exist.
            self.debug('Suppressing cache result %s, recent=%s dirty=%s'
                       % (fprint, recent, sorted(list(dirty))))
            raise KeyError(fprint)
        match[0] = min(match[0] + extend, time.time() + 5 * extend)
        co.session = result_obj.session = ss
        self.debug('Returning cached result for %s' % fprint)
        return result_obj

    def dirty_set(self, after=0):
        dirty = set()
        with self.lock:
            for ts, req in self.dirty:
                if (after == 0) or (ts > after):
                    dirty |= req
        return dirty

    def mark_dirty(self, requirements):
        with self.lock:
            self.dirty.append((time.time(), set(requirements)))
        self.debug('Marked dirty: %s' % sorted(list(requirements)))

    def refresh(self, extend=0, runtime=4, event_log=None):
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
        for fprint in fingerprints:
            try:
                e, req, ss, co, ro, a = self.cache[fprint]
                now = time.time()
                dirty = (req & self.dirty_set(after=a))
                if (a + self._lag < now) and dirty:
                    if now < started + runtime:
                        co.session = ro.session = ss
                        ro = co.refresh()
                        if extend > 0:
                            e = min(e + extend, now + 5*extend)
                        with self.lock:
                            # Make sure we do not overwrite new results from
                            # elsewhere at this time.
                            if self.cache[fprint][-1] == a:
                                self.cache[fprint] = [e, req, ss, co, ro, now]
                            refreshed.append(fprint)
                        play_nice_with_threads()
                    else:
                        # Out of time, evict because otherwise it may be
                        # assumed to be up-to-date.
                        with self.lock:
                            del self.cache[fprint]
            except (ValueError, IndexError, TypeError):
                # Broken stuff just gets evicted
                with self.lock:
                    if fprint in self.cache:
                        self.debug('Evicted: %s' % fprint)
                        del self.cache[fprint]

        if refreshed and event_log:
            event_log.log(message=_('New results are available'),
                          source=self,
                          data={'cache_ids': refreshed},
                          flags=Event.COMPLETE)
            self.debug('Refreshed: %s' % refreshed)
