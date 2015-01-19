from mailpile.tests.gui import MailpileSeleniumTest


class ContactsGuiTest(MailpileSeleniumTest):
    def test_add_new_contact(self):
        return  # FIXME: Test disabled

        self.go_to_mailpile_home()
        self.navigate_to('Contacts')

        self.click_element_with_class('btn-activity-contact_add')

        self.fill_form_field('name', 'Foo Bar')
        self.fill_form_field('email', 'foo.bar@test.local')
        self.submit_form('form-contact-add')

        self.navigate_to('Contacts')

        # we now should find a contact with name Foo Bar
        self.assert_link_with_text('Foo Bar')
