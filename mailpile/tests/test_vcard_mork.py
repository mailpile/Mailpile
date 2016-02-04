import unittest
import mailpile

from mailpile.tests import MailPileUnittest

from mailpile.plugins import vcard_mork as vcard_mork

class TestVCard(MailPileUnittest):

    def test_hexcmp(self):
        res = vcard_mork.hexcmp('AB', 'CD')
        self.assertEqual(res, -1)
        res = vcard_mork.hexcmp('b9', '57')
        self.assertEqual(res, 1)
        res = vcard_mork.hexcmp('AA', 'AA')
        self.assertEqual(res, 0)
        res = vcard_mork.hexcmp('1', '2')
        self.assertEqual(res, -1)
        res = vcard_mork.hexcmp('3', '2')
        self.assertEqual(res, 1)
        res = vcard_mork.hexcmp('6', '6')
        self.assertEqual(res, 0)