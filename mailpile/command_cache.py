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

    def __init__(self):
        self.cache = {}
        self.lock = UiRLock()
        self.dirty = set()

    def cache_result(self, fprint, expires, req, command_obj, result_obj):
        with self.lock:
            self.cache[str(fprint)] = (expires, req, command_obj, result_obj)

    def get_result(self, fprint):
        fprint = str(fprint)
        if fprint in self.dirty:
            raise KeyError()
        return self.cache[fprint][3]

    def mark_dirty(self, requirements):
        with self.lock:
            for fprint, (e, r, co, ro) in self.cache.iteritems():
                for req in requirements:
                    if req in r:
                        self.dirty.add(fprint)
                        break

    def refresh(self, extend=60):
        now = time.time()
        with self.lock:
            expired = set([f for f in self.cache if self.cache[f][0] < now])
            for fp in expired:
                del self.cache[fp]
            dirty, self.dirty = self.dirty, set()

        #for fprint in (dirty - expired):
        #    exp, req, co, ro = self.cache[fprint]
        #    ro = co.refresh()
        #    self.cache[fprint] = (exp + extend, req, co, ro)

