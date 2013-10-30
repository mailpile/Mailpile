import unittest
from generic_mailpile import MailPileUnittest
import mailpile


class TestCommands(MailPileUnittest):
  def test_index(self):
    res = self.mp.rescan()
    self.assertEqual(res.as_dict()["result"], True)

  def test_search(self):
    # A random search must return results in less than 0.2 seconds.
    res = self.mp.search("foo")
    self.assertLess(float(res.as_dict()["elapsed"]), 0.2)

  def test_optimize(self):
    res = self.mp.optimize()
    self.assertEqual(res.as_dict()["result"], True)

  def test_recount(self):
    res = self.mp.recount()
    self.assertEqual(res.as_dict()["result"], True)

  def test_set(self):
    self.mp.set("num_results=1")
    results = self.mp.search("twitter")
    self.assertEqual(len(results.result), 1)

  def test_unset(self):
    self.mp.unset("num_results")
    results = self.mp.search("twitter")
    self.assertEqual(len(results.result), 1)

  def test_add(self):
    res = self.mp.add("/tmp")
    self.assertEqual(res.as_dict()["result"], True)

  def test_add_mailbox_already_in_pile(self):
    res = self.mp.add("/tmp")
    res = self.mp.add("/tmp")
    self.assertEqual(res.as_dict()["result"], True)

  def test_add_mailbox_no_such_directory(self):
    res = self.mp.add("wut?")
    self.assertEqual(res.as_dict()["result"], False)

  def test_output(self):
    res = self.mp.output("json")
    self.assertEqual(res.as_dict()["result"], {'output': 'json'})

  def test_help(self):
    res = self.mp.help()
    self.assertEqual(len(res.result), 3)

  def test_help_with_param_search(self):
    res = self.mp.help('search')
    self.assertEqual(res.result['pre'], 'Search your mail!')

  def test_help_splash(self):
    res = self.mp.help_splash()
    self.assertEqual(len(res.result), 2)
    self.assertGreater(res.result['splash'], 0)
    self.assertGreater(res.as_text(), 0)

  def test_help_urlmap_as_text(self):
    res = self.mp.help_urlmap()
    self.assertEqual(len(res.result), 1)
    self.assertGreater(res.as_text(), 0)


class TestCommandResult(MailPileUnittest):
  def test_command_result_as_dict(self):
    res = self.mp.help_splash()
    self.assertGreater(len(res.as_dict()), 0)

  def test_command_result_as_text(self):
    res = self.mp.help_splash()
    self.assertGreater(res.as_text(), 0)

  def test_command_result_as_text_for_boolean_result(self):
    res = self.mp.rescan()
    self.assertEquals(res.as_text(), "Succeeded: Scan all mailboxes for new messages")

  def test_command_result_non_zero(self):
    res = self.mp.help_splash()
    self.assertTrue(res)

  def test_command_result_as_json(self):
    res = self.mp.help_splash()
    self.assertGreater(res.as_json(), 0)

  def test_command_result_as_html(self):
    res = self.mp.help_splash()
    self.assertGreater(res.as_html(), 0)


class TestTagging(MailPileUnittest):
  def test_addtag(self):
    pass


if __name__ == '__main__':
  unittest.main()

