import unittest
import mailpile

from mailpile.tests import MailPileUnittest

class TestVCard(MailPileUnittest):

    def test_VCardLine_with_args(self):
        vcl = mailpile.vcard.VCardLine(name="Jason",value="The Dude",pref=None)
        self.assertEqual(vcl.as_vcardline(), "JASON;PREF:The Dude")

    def test_VCardLine_no_args(self):
        vcl = mailpile.vcard.VCardLine()
        vcl.name = "FN"
        vcl.value = "Lebowski"
        self.assertEqual(vcl.as_vcardline(), "FN:Lebowski")
        
    def test_VCardLine_args_too_long(self): # when input is greater than 75 chars
        vcl = mailpile.vcard.VCardLine()
        vcl.name = "FN"
        vcl.value = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim"
        self.assertEqual(vcl.as_vcardline(), "FN:Lorem ipsum dolor sit amet\\, consectetur adipiscing elit\\, sed do eiusm\n od tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim")

    def test_VCardLine_with_vcard_data(self):
        vcl = mailpile.vcard.VCardLine("FN;type=Nickname:Bjarni")
        self.assertEqual(vcl.name, "fn")
        self.assertEqual(vcl.value, "Bjarni")
        self.assertEqual(vcl.get("type"), "Nickname")

    def test_VCardLine_set_line_id(self):
        vcl = mailpile.vcard.VCardLine("FN;type=Nickname:Bjarni")
        vcl.set_line_id(1)
        self.assertEqual(vcl.line_id, 1)

    def test_VCardLine_set_attr(self):
        vcl = mailpile.vcard.VCardLine("FN;type=Nickname:Bjarni")
        vcl.set_attr("TITLE", "Shrimp Man")
        self.assertEqual(vcl.get("TITLE"), "Shrimp Man")
        vcl.set_attr("type", "Person")
        self.assertEqual(vcl.get("type"), "Person")

    #
    # VCardLine.Quote should quote values for representing them in a VCardLine
    #
    def test_VCardLine_Quote(self):
        quoted = mailpile.vcard.VCardLine.Quote("Comma, semicolon; backslash\\ newline\\n")
        self.assertEqual(quoted, "Comma\\, semicolon\\; backslash\\\\ newline\\\\n")

    #
    # VCardLine.ParseLine should parse a single line respecting RFC6350 quoting
    #
    # it should return a tuple with name, attrs, value
    def test_VCardLine_ParseLine_unquoted(self):
        unquoted_line = "PHOTO;MEDIATYPE=image/gif:http://testing.mailpile.is/my_foto.gif"
        res = mailpile.vcard.VCardLine.ParseLine(unquoted_line)
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0], "photo")
        self.assertEqual(res[1][0], ("mediatype", "image/gif"))
        self.assertEqual(res[2], "http://testing.mailpile.is/my_foto.gif")

    def test_VCardLine_ParseLine_quoted(self):
        quoted_line = "PHOTO;THING=comma\\, semicolon\\; backslash\\\\:value"
        res = mailpile.vcard.VCardLine.ParseLine(quoted_line)
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0], "photo")
        self.assertEqual(res[1][0], ("thing", 'comma, semicolon; backslash\\'))
        self.assertEqual(res[2], "value")
