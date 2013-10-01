import unittest
from generic_mailpile import MailPileUnittest, capture
import mailpile
from mailpile.ui import UserInteraction


class TestUI(MailPileUnittest):
  def test_ui_debug_log_debug_not_set(self):
    with capture() as out:
      self.mp._ui._debug_log("text", UserInteraction.LOG_ALL, prefix='testprefix')
    self.assertNotIn("testprefixlog(99): text", ''.join(out))

  def test_ui_debug_log_debug_set(self):
    self.mp._ui.clear_log()
    with capture() as out:
      self.mp.set("debug=log")
      self.mp._ui._debug_log("text", UserInteraction.LOG_ALL, prefix='testprefix')
    self.assertIn("testprefixlog(99): text", ''.join(out))

  def test_ui_log_block(self):
    self.mp._ui.clear_log()
    self.mp._ui.block()
    with capture() as out:
      self.mp._ui.log(UserInteraction.LOG_URGENT, "urgent")
      self.mp._ui.log(UserInteraction.LOG_RESULT, "result")
      self.mp._ui.log(UserInteraction.LOG_ERROR, "error")
      self.mp._ui.log(UserInteraction.LOG_NOTIFY, "notify")
      self.mp._ui.log(UserInteraction.LOG_WARNING, "warning")
      self.mp._ui.log(UserInteraction.LOG_PROGRESS, "progress")
      self.mp._ui.log(UserInteraction.LOG_DEBUG, "debug")
      self.mp._ui.log(UserInteraction.LOG_ALL, "all")
    self.assertEquals(out, ['', ''])
    with capture() as out:
      self.mp._ui.unblock()
    self.assertEquals(len(out), 2)
    self.assertEquals(out[0], '')
    # Check stripped output
    output = [x.strip() for x in out[1].split('\r')]
    self.assertEquals(output, ['urgent', 'result', 'error', 'notify', 'warning', 'progress', 'debug', 'all', ''])
    # Progress has \r in the end instead of \n
    progress_str = [x for x in out[1].split('\r\n') if 'progress' in x][0].strip()
    self.assertEquals(progress_str, ''.join(['progress', ' '*71, '\rdebug']))

  def test_ui_clear_log(self):
    self.mp._ui.clear_log()
    self.mp._ui.block()
    with capture() as out:
      self.mp._ui.log(UserInteraction.LOG_URGENT, "urgent")
      self.mp._ui.log(UserInteraction.LOG_RESULT, "result")
      self.mp._ui.log(UserInteraction.LOG_ERROR, "error")
      self.mp._ui.log(UserInteraction.LOG_NOTIFY, "notify")
      self.mp._ui.log(UserInteraction.LOG_WARNING, "warning")
      self.mp._ui.log(UserInteraction.LOG_PROGRESS, "progress")
      self.mp._ui.log(UserInteraction.LOG_DEBUG, "debug")
      self.mp._ui.log(UserInteraction.LOG_ALL, "all")
      self.mp._ui.clear_log()
      self.mp._ui.unblock()
    self.assertEquals(out, ['', ''])

  def test_ui_display_result_text(self):
    self.mp._ui.clear_log()
    with capture() as out:
      self.mp._ui.render_mode = 'text'
      result = self.mp.rescan()
      self.mp._ui.display_result(result)
    self.assertEquals(out[0], "Succeeded: Scan all mailboxes for new messages\n")

