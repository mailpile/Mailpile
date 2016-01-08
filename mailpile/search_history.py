import time
import zlib

import mailpile.util
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


SEARCH_HISTORY_LOCK = UiRLock()


class SearchHistory(object):
    #
    # This is an in-memory cache of search results, which can be used to
    # give a "search context" to various commands. The actual results are
    # preserved, so adding/removing/retagging messages won't change the
    # context and meaning of "next" or "message number five".
    #
    DEFAULT_TTL = 5 * 24 * 3600  # This is a LRU cache, we evict after 5 days
    RAW_RESULT_TTL = 600         # Compress results after 10 minutes or so

    PICKLE_NAME = 'search-history.dat'

    @classmethod
    def Load(cls, config, merge=None):
        with SEARCH_HISTORY_LOCK:
            try:
                sh = config.load_pickle(cls.PICKLE_NAME)
            except (IOError, EOFError):
                sh = SearchHistory()
            if merge is not None:
                sh.cache.update(merge.cache)
        return sh

    def __init__(self):
        self.changed = False
        self.cache = {}

    def save(self, config):
        with SEARCH_HISTORY_LOCK:
            self.expire()
            if self.changed:
                self.changed = False
                config.save_pickle(self, self.PICKLE_NAME)

    def _to_bitmask(self, results):
        if not results:
            return str('\0')
        bitmask = [0] * (max(results) // 8 + 1)
        for r in results:
            bitmask[r//8] |= 1 << (r % 8)
        return ''.join(chr(b) for b in bitmask)

    def _from_bitmask(self, bitmask):
        results = []
        for i in range(0, len(bitmask)):
            v = ord(bitmask[i])
            if v:
                results += [(i * 8 + b) for b in range(0, 8) if v & (1 << b)]
        return results

    def _compress(self, results, order):
        # This generates a compact but complete representation of the search,
        # compact enough that we COULD embed in API responses if we wanted to
        # do away with the server-side persistence.
        # TODO: Explore if this is a better format for posting lists!
        return zlib.compress(':'.join([self._to_bitmask(results), str(order)]))

    def _decompress(self, compressed_bitmask):
        bitmask, order = zlib.decompress(compressed_bitmask).rsplit(':', 1)
        return self._from_bitmask(bitmask), order

    def add(self, terms, results, order):
        now = int(time.time())
        data = {
            'terms': terms[:],
            'results': results[:],
            'order': order,
            't': now
        }
        with SEARCH_HISTORY_LOCK:
            fprint = md5_hex(str(terms), str(results), str(order))
            self.cache[fprint] = data
            self.changed = True
            return fprint

    def get(self, session, fprint):
        with SEARCH_HISTORY_LOCK:
            search = self.cache[fprint]
            self.cache[fprint]['t'] = int(time.time())
            if 'results' not in search and 'c' in search:
                results, order = self._decompress(search['c'])
                session.config.index.sort_results(session, results, order)
                search['results'] = results
                search['order'] = order
            return tuple(search[t] for t in ('terms', 'results', 'order'))

    def expire(self, ttl=None, compact=None):
        expired = time.time() - (ttl or self.DEFAULT_TTL)
        compact = time.time() - (compact or self.RAW_RESULT_TTL)
        with SEARCH_HISTORY_LOCK:
            for fp in [f for f in self.cache
                       if expired <= self.cache[f]['t'] < compact]:
                search = self.cache[fp]
                if 'results' not in search:
                    continue
                if 'c' not in search:
                    try:
                        search['c'] = self._compress(search['results'],
                                                     search['order'])
                    except TypeError:
                        pass
                if 'c' in search:
                    del search['results']
                    del search['order']
                # Note: do not set self.changed, as the actual data being
                # cached is still the same - we just changed the format.

            expire = [f for f in self.cache if self.cache[f]['t'] < expired]
            for fp in expire:
                del self.cache[fp]
                self.changed = True
