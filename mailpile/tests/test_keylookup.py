from mock import patch
import datetime

from mailpile.tests import MailPileUnittest
from mailpile.tests import get_shared_mailpile

from mailpile.plugins.keylookup import lookup_crypto_keys, KeyserverLookupHandler
from mailpile.plugins.keylookup.email_keylookup import *
from mailpile.plugins.keylookup.dnspka import *

GPG_MOCK_RETURN = {
    '08A650B8E2CBC1B02297915DC65626EED13C70DA': {
        'uids': [{'comment': '', 'name': 'Mailpile!', 'email': 'test@mailpile.is'}],
        'keysize': '4096',
        'keytype_name': 'RSA',
        'created': datetime.datetime(2014, 6, 22, 2, 37, 23),
        'fingerprint': '08A650B8E2CBC1B02297915DC65626EED13C70DA',
    }
}

fpr = "08A650B8E2CBC1B02297915DC65626EED13C70DA"
url = "https://mailpile.is/gpgkey.gpg"
DNSPKA_MOCK_RETURN = [{
    'typename': 'TXT', 'name': 'test._pka.mailpile.is',
    'data': ['v=pka1;fpr=%s;uri=%s' % (fpr, url)],
}]



class KeylookupBaseTest(MailPileUnittest):
    def setUp(self):
        pass


class KeylookupDNSPKILookup(KeylookupBaseTest):
    def test_lookup_dnspki(self):
        with patch('DNS.Request') as dns_mock:
            dns_mock.return_value.req.return_value.answers = DNSPKA_MOCK_RETURN
            d = DNSPKALookupHandler(None, {})
            res = d.lookup('test@mailpile.is')

        self.assertIsNotNone(res)
        self.assertEqual(res[fpr]["fingerprint"], fpr)
        self.assertEqual(res[fpr]["url"], url)


class KeylookupPGPKeyserverLookup(KeylookupBaseTest):
    def test_lookup_pgpkeyserver(self):
        with patch('mailpile.crypto.gpgi.GnuPG.search_key') as gpg_mock:
            gpg_mock.return_value = GPG_MOCK_RETURN
            d = KeyserverLookupHandler(None, {})
            res = d.lookup('test@mailpile.is')
        self.assertIsNotNone(res)


class KeylookupEmailLookup(KeylookupBaseTest):
    def test_lookup_emailkeys(self):
        m = get_shared_mailpile()[0]
        d = EmailKeyLookupHandler(m._session, {})
        res = d.lookup('smari@mailpile.is')
        self.assertIsNotNone(res)


class KeylookupOverallTest(KeylookupBaseTest):
    def test_lookup(self):
        with patch('DNS.Request') as dns_mock, patch('mailpile.crypto.gpgi.GnuPG.search_key') as gpg_mock:
            gpg_mock.return_value = GPG_MOCK_RETURN
            dns_mock.return_value.req.return_value.answers = DNSPKA_MOCK_RETURN

            m = get_shared_mailpile()[0]
            res = lookup_crypto_keys(m._session, 'smari@mailpile.is')

        self.assertIsNotNone(res)
        self.assertEqual(type(res), list)
        for r in res:
            self.assertEqual(type(r), dict)

