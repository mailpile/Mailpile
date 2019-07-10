from __future__ import print_function
import unittest
from nose.tools import assert_equal, assert_less

from mailpile.tests import get_shared_mailpile


def checkSearch(query, expected_count=1):
    class TestSearch(object):
        def __init__(self):
            self.mp = get_shared_mailpile()[0]
            results = self.mp.search(*query)
            try:
                assert_equal(results.result['stats']['count'], expected_count)
                assert_less(float(results.as_dict()["elapsed"]), 0.2)
            except:
                print('BAD RESULT:\n%s' % results.as_text())
                raise
    TestSearch.description = "Searching for %s" % str(query)
    return TestSearch


def test_generator():
    # All mail
    yield checkSearch(['all:mail'], 13)
    # Full match
    yield checkSearch(['brennan'])
    # Partial match
    yield checkSearch(['agirorn'])
    # Subject
    yield checkSearch(['subject:emerging'])
    # From
    yield checkSearch(['from:twitter'], 2)
    # From date
    yield checkSearch(['dates:2013-09-17', 'feministinn'])
    # with attachment
    #  - Note: this differs from mailpile-test.py because we do not have the
    #          keys required to decrypt, so encrypted mail => attachment.
    yield checkSearch(['has:attachment'], 5)
    # In attachment name
    yield checkSearch(['att:jpg'])
    # term + term
    yield checkSearch(['brennan', 'twitter'])
    # term + special
    yield checkSearch(['brennan', 'from:twitter'])
    # Not found
    yield checkSearch(['subject:Moderation', 'kde-isl'], 0)
    yield checkSearch(['has:crypto'], 4)

    # Test that we do not crash when searching for a non-existant tag.
    yield checkSearch(['in:doesnotexist'], 0)
