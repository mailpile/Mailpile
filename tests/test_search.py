import unittest
from generic_mailpile import MailPileUnittest, setUp
from nose.tools import assert_equal, assert_less



def checkSearch(query):
  class TestSearch(object):
    def __init__(self):
      setUp(self)
      results = self.mp.search(*query)
      assert_equal(len(results.result), 1)
      assert_equal(results.result[0]['count'], 1)
      assert_less(float(results.as_dict()["elapsed"]), 0.2)
  TestSearch.description = "Searching for %s" % str(query)
  return TestSearch


def test_generator():
  yield checkSearch(['brennan'])
  yield checkSearch(['agirorn'])
  yield checkSearch(['subject:emerging'])
  yield checkSearch(['from:twitter', 'brennan'])
  yield checkSearch(['dates:2013-09-17', 'feministinn'])
  yield checkSearch(['att:jpg', 'fimmtudaginn'])
  #yield checkSearch(['subject:Moderation', 'kde-isl'])

