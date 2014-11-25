try:
    from selenium.webdriver.common.by import By
except ImportError:
    pass

from mailpile.tests.gui import MailpileSeleniumTest


class TagGuiTest(MailpileSeleniumTest):
    def test_mark_read_unread(self):
        return  # FIXME: Test disabled

        self.go_to_mailpile_home()
        self.wait_until_element_is_visible('pile-message-2')
        self._assert_element_has_class('pile-message-2', 'in_new')
        self._toggle_tag_bar()
        self._click_on_visible_element_with_class_name('bulk-action-read')
        self._assert_element_not_class('pile-message-2', 'in_new')
        self._toggle_tag_bar()
        self.wait_until_element_is_invisible_by_locator((By.CLASS_NAME, 'bulk-action-read'))
        self._toggle_tag_bar()
        self._click_on_visible_element_with_class_name('bulk-action-unread')
        self._assert_element_has_class('pile-message-2', 'in_new')
        self._toggle_tag_bar()
        self.wait_until_element_is_invisible_by_locator((By.CLASS_NAME, 'bulk-action-unread'))

    def _click_on_visible_element_with_class_name(self, class_name):
        self.wait_until_element_is_visible_by_locator((By.CLASS_NAME, class_name))
        unread_btn = self.find_element_by_class_name(class_name)
        unread_btn.click()

    def _toggle_tag_bar(self):
        checkbox = self.find_element_by_xpath('//*[@id="pile-message-2"]/td[6]/input')
        checkbox.click()
        return checkbox

    def _assert_element_has_class(self, element_id, class_name):
        self.wait_until_element_has_class((By.ID, element_id), class_name)

    def _assert_element_not_class(self, element_id, class_name):
        self.wait_until_element_has_not_class((By.ID, element_id), class_name)
