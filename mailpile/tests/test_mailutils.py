# SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
# SPDX-License-Identifier: AGPL-3.0-or-later

import unittest

import mailpile
from mailpile.tests import MailPileUnittest
from mailpile.mailutils.header import decode_header


class TestCommands(MailPileUnittest):
    def test_decode_header_no_encoding(self):
        res = decode_header("olmsted")
        self.assertEqual(res, [('olmsted', None)])
