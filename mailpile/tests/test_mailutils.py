import unittest

import mailpile
from mailpile.tests import MailPileUnittest
from mailpile.mailutils.header import decode_header


class TestCommands(MailPileUnittest):
    def test_decode_header_no_encoding(self):
        res = decode_header("olmsted")
        self.assertEqual(res, [('olmsted', None)])
