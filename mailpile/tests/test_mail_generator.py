# -*- coding: utf-8 -*-
import unittest
import mailpile

from mailpile.tests import MailPileUnittest

import mailpile.mailutils.generator as mail_generator

class TestMailGenerator(MailPileUnittest):

    def test_is8bitstring(self):
        res = mail_generator._is8bitstring("Ä")
        self.assertEqual(res, True)
        for input_types_generating_false in [1, "a"]:
            res = mail_generator._is8bitstring(input_types_generating_false)
            self.assertEqual(res, False)
            
    def test_make_boundary(self):
        for input_types in [None, "abc"]:
            res = mail_generator._make_boundary()
            self.assertEqual(len(res), 17 + mail_generator._width)
            self.assertEqual(res[:15], '===============')
            self.assertEqual(res[15:-2].isdigit(), True)
            self.assertEqual(res[-2:], '==')
