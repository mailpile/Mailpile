from tests.gui import MailpileSeleniumTest


class ContactsGuiTest(MailpileSeleniumTest):
    def test_add_new_contact(self):
        self.go_to_mailpile_home()
        self.navigate_to('Contacts')

        self.click_button_with_id('button-contact-add')

        self.write_to_input('@contactname', 'Foo Bar')
        self.write_to_input('@contactemail', 'foo.bar@test.local')
        self.submit_form('form-contact-add')

        self.navigate_to('Contacts')

        # we now should find a contact with name Foo Bar
        self.assert_link_with_text('Foo Bar')
        self.assert_link_with_text('foo.bar@test.local')
