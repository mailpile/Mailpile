import json
import unittest
import mailpile
from mailpile.ui import UserInteraction

from mailpile.tests import capture, MailPileUnittest


class TestUI(MailPileUnittest):
    def _ui_swap(self):
        o, self.mp._ui = self.mp._ui, UserInteraction(self.mp._session.config)
        return o

    def test_ui_debug_log_debug_not_set(self):
        old_ui = self._ui_swap()
        try:
            self.mp._ui.log_prefix = 'testprefix'
            with capture() as out:
                self.mp._ui._debug_log("text", UserInteraction.LOG_ALL)
            self.assertNotIn("testprefixlog(99): text", ''.join(out))
        finally:
            self.mp._ui = old_ui

    def test_ui_debug_log_debug_set(self):
        old_ui = self._ui_swap()
        try:
            self.mp._ui.log_prefix = 'testprefix'
            with capture() as out:
                self.mp.set("sys.debug=log")
                self.mp._ui._debug_log("text", UserInteraction.LOG_ALL)
            self.assertIn("testprefixlog(99): text", ''.join(out))
        finally:
            self.mp._ui = old_ui

    def test_ui_log_block(self):
        old_ui = self._ui_swap()
        try:
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
            self.assertEquals(output, ['urgent', 'result', 'error',
                                       'notify', 'warning', 'progress',
                                       'debug', 'all', ''])
            # Progress has \r in the end instead of \n
            progress_str = [x for x in out[1].split('\r\n')
                            if 'progress' in x][0].strip()
            self.assertEquals(progress_str,
                              ''.join(['progress', ' ' * 71, '\rdebug']))
        finally:
            self.mp._ui = old_ui

    def test_ui_clear_log(self):
        old_ui = self._ui_swap()
        try:
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
        finally:
            self.mp._ui = old_ui

    def test_ui_display_result_text(self):
        old_ui = self._ui_swap()
        try:
            with capture() as out:
                self.mp._ui.render_mode = 'text'
                result = self.mp.rescan()
                self.mp._ui.display_result(result)

            # Parse resulting json for easier assertions
            json_result = json.loads(out[0])
            vcard_sources = json_result.get('vcard_sources', [])
            self.assertEqual(json_result.get('mailboxes'), 0)
            self.assertEqual(json_result.get('messages'), 0)
            self.assertEqual(json_result.get('vcards'), 0)
            self.assertIn('gravatar', vcard_sources)
            self.assertIn('gpg', vcard_sources)
            self.assertIn('carddav', vcard_sources)
            self.assertIn('mork', vcard_sources)
        finally:
            self.mp._ui = old_ui
