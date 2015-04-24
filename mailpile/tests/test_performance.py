import unittest
from nose.tools import assert_equal, assert_less

from mailpile.tests import get_shared_mailpile, MailPileUnittest


def checkSearch(postinglist_kb, query):
    class TestSearch(object):
        def __init__(self):
            self.mp = get_shared_mailpile()[0]
            self.mp.set("sys.postinglist_kb=%s" % postinglist_kb)
            self.mp.set("prefs.num_results=50")
            self.mp.set("prefs.default_order=rev-date")
            results = self.mp.search(*query)
            assert_less(float(results.as_dict()["elapsed"]), 0.2)
    return TestSearch


def test_generator():
    postinglist_kbs = [126, 62, 46, 30]
    search_queries = ['http', 'bjarni', 'ewelina', 'att:pdf',
                      'subject:bjarni', 'cowboy', 'unknown', 'zyxel']
    for postinglist_kb in postinglist_kbs:
        for search_query in search_queries:
            yield checkSearch(postinglist_kb, [search_query])
