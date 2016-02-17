# -*- coding: utf-8 -*-
import unittest

import mailpile
from mailpile.tests import MailPileUnittest
from mailpile.mailutils import decode_header
from mailpile.mailutils import FormatMbxId


class TestCommands(MailPileUnittest):
    def test_decode_header_no_encoding(self):
        res = decode_header("olmsted")
        self.assertEqual(res, [('olmsted', None)])

    def test_decode_header_encoded_valid1(self):
        res = decode_header("=?charset?q?Hello_World?=")
        self.assertEqual(res, [('Hello World', 'charset')])

    def test_decode_header_encoded_valid2(self):
        res = decode_header("=?\u?q?Hello_World?=")
        self.assertEqual(res, [('Hello World', '\\u')])

    def test_FormatMbxId_string_len_less_than_four(self):
        res = FormatMbxId("a")
        self.assertEqual(res, "000a")

    def test_FormatMbxId_string_len_four(self):
        res = FormatMbxId("abcd")
        self.assertEqual(res, "abcd")

    def test_FormatMbxId_unicode(self):
        res = FormatMbxId('Ţ¼')
        self.assertEqual(res, "\xc5\xa2\xc2\xbc")        