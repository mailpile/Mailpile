import time

import mailpile.util
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


class CommandCache(object):
    #
    # This is a persistent cache of commands and results we may want
    # to refresh in the background and/or reuse.
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

    def __init__(self):
        self.lock = UiRLock()
        self.cache = {}     # The cache itself
        self.dirty = set()  # Requirements that have changed recently

    def cache_result(self, fprint, expires, req, cmd_obj, result_obj):
        with self.lock:
            # Note: We cache this even if the requirements are "dirty",
            #       as mere presence in the cache makes this a candidate
            #       for refreshing.
            self.cache[str(fprint)] = (expires, req, cmd_obj, result_obj)

    def get_result(self, fprint):
        exp, req, co, ro = self.cache[fprint]
        if req & self.dirty:
            # If requirements are dirty, pretend this item does not exist.
            raise KeyError()
        return self.cache[fprint][3]

    def mark_dirty(self, requirements):
        self.dirty |= set(requirements)
        print 'DIRTY: %s' % requirements

    def refresh(self, extend=60, event_log=None):
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
                    ro = co.refresh()
                    with self.lock:
                        self.cache[fprint] = (exp + extend, req, co, ro)
                    refreshed.append(fprint)
                    play_nice_with_threads()
            except (ValueError, IndexError, TypeError):
                # Broken stuff just gets evicted
                with self.lock:
                    if fprint in self.cache:
                        del self.cache[fprint]

        if refreshed and event_log:
            event_log.log(message=_('New results are available'),
                          source=self,
                          data={'cache_ids': refreshed})
            print 'REFRESHED: %s' % refreshed
