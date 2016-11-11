import time

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n


class SearchResultSet:
    """
    Search results!
    """
    def __init__(self, idx, terms, results, exclude):
        self.terms = set(terms)
        self._index = idx
        self.set_results(results, exclude)

    def set_results(self, results, exclude):
        self._results = {
            'raw': set(results),
            'excluded': set(exclude) & set(results)
        }
        return self

    def __len__(self):
        return len(self._results.get('raw', []))

    def as_set(self, order='raw'):
        return self._results[order] - self._results['excluded']

    def excluded(self):
        return self._results['excluded']


SEARCH_RESULT_CACHE = {}


class CachedSearchResultSet(SearchResultSet):
    """
    Cached search result.
    """
    def __init__(self, idx, terms):
        global SEARCH_RESULT_CACHE
        self.terms = set(terms)
        self._index = idx
        self._results = SEARCH_RESULT_CACHE.get(self._skey(), {})
        self._results['_last_used'] = time.time()

    def _skey(self):
        return ' '.join(self.terms)

    def set_results(self, *args):
        global SEARCH_RESULT_CACHE
        SearchResultSet.set_results(self, *args)
        SEARCH_RESULT_CACHE[self._skey()] = self._results
        self._results['_last_used'] = time.time()
        return self

    @classmethod
    def DropCaches(cls, msg_idxs=None, tags=None):
        # FIXME: Make this more granular
        global SEARCH_RESULT_CACHE
        SEARCH_RESULT_CACHE = {}


if __name__ == '__main__':
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
