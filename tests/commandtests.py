import unittest
import mailpile

class TestSearch(unittest.TestCase):
  def setUp(self):
    self.mp = mailpile.Mailpile()

  def test_index(self):
    res = self.mp.rescan()
    self.assertEqual(res.as_dict()["result"], True)

  def test_search(self):
    # A random search must return results in less than 0.2 seconds.
    res = self.mp.search("foo")
    self.assertLess(float(res.as_dict()["elapsed"]), 0.2)


class TestTagging(unittest.TestCase):
  def setUp(self):
    self.mp = mailpile.Mailpile()

  def test_addtag(self):
    pass


if __name__ == '__main__':
  unittest.main()
