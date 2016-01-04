# -*- coding: utf-8 -*-
import unittest
import mailpile

from mailpile.tests import MailPileUnittest

from mailpile import mail_generator as mail_generator

class TestMailGenerator(MailPileUnittest):

    def test_is8bitstring(self):
        res = mail_generator._is8bitstring("Ä")
        self.assertEqual(res, True)
        for input_types_generating_false in [1, "a"]:
            res = mail_generator._is8bitstring(input_types_generating_false)
            self.assertEqual(res, False)