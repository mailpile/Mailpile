from mailpile.tests.gui import MailpileSeleniumTest


class MailGuiTest(MailpileSeleniumTest):
    def test_read_mail(self):
        return  # FIXME: Test disabled

        self.go_to_mailpile_home()

        self.wait_until_element_is_visible('pile-message-8')
        self.click_element_with_link_text('Bjarni R. Einarsson, you have '
                                          'new followers on Twitter!')

        self.wait_until_element_is_visible('content-view')
        self.assertEqual("Bjarni R. Einarsson, you have new followers "
                         "on Twitter! | None's mailpile", self.page_title())
        self.assert_text('Samuel Faunt')
