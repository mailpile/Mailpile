import time

import mailpile.util
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *
from mailpile.ui import Session


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
        self.cache = {}     # The cache itself
        self.dirty = set()  # Requirements that have changed recently

    def cache_result(self, fprint, expires, req, cmd_obj, result_obj):
        with self.lock:
            # Make a snapshot of the session, as it provides context
            snapshot = Session.Snapshot(cmd_obj.session, ui=False)
            snapshot.ui = cmd_obj.session.ui
            cmd_obj.session = result_obj.session = snapshot

            # Note: We cache this even if the requirements are "dirty",
            #       as mere presence in the cache makes this a candidate
            #       for refreshing.
            self.cache[str(fprint)] = [expires, req, cmd_obj, result_obj]
            self.debug('Cached %s, req=%s' % (fprint, req))

    def get_result(self, fprint, dirty_check=True):
        with self.lock:
            exp, req, co, result_obj = match = self.cache[fprint]
            match[0] += 60
        if dirty_check and req & self.dirty:
            # If requirements are dirty, pretend this item does not exist.
            raise KeyError()
        return result_obj

    def mark_dirty(self, requirements):
        self.dirty |= set(requirements)
        self.debug('Marked dirty: %s' % requirements)

    def refresh(self, extend=60, runtime=4, event_log=None):
        now = time.time()
        with self.lock:
            expired = set([f for f in self.cache if self.cache[f][0] < now])
            for fp in expired:
                del self.cache[fp]

            dirty, self.dirty = self.dirty, set()
            fingerprints = list(self.cache.keys())

        refreshed = []
        for fprint in fingerprints:
            try:
                exp, req, co, ro = self.cache[fprint]
                if req & dirty:
                    if time.time() < now + runtime:
                        ro = co.refresh()
                        with self.lock:
                            self.cache[fprint] = [exp + extend, req, co, ro]
                        refreshed.append(fprint)
                        play_nice_with_threads()
                    else:
                        # Out of time, just evict things.
                        with self.lock:
                            del self.cache[fprint]
            except (ValueError, IndexError, TypeError):
                # Broken stuff just gets evicted
                with self.lock:
                    if fprint in self.cache:
                        del self.cache[fprint]

        if refreshed and event_log:
            event_log.log(message=_('New results are available'),
                          source=self,
                          data={'cache_ids': refreshed},
                          flags=Event.COMPLETE)
            self.debug('Refreshed: %s' % refreshed)
