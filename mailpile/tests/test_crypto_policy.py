from __future__ import print_function
from mailpile.vcard import MailpileVCard, VCardLine
from mailpile.tests import MailPileUnittest

VCARD_CRYPTO_POLICY = 'X-MAILPILE-CRYPTO-POLICY'


class CryptoPolicyBaseTest(MailPileUnittest):
    def setUp(self):
        self.config.vcards.clear()
        pass

    def _add_vcard(self, full_name, email):
        card = MailpileVCard(VCardLine(name='fn', value=full_name),
                             VCardLine(name='email', value=email))
        self.config.vcards.add_vcards(card)
        return card


class UpdateCryptoPolicyForUserTest(CryptoPolicyBaseTest):
    def test_args_are_checked(self):
        self.assertEqual('error',
            self.mp.crypto_policy_set().as_dict()['status'])
        self.assertEqual('error',
            self.mp.crypto_policy_set('one arg').as_dict()['status'])

    def test_policies_are_validated(self):
        self._add_vcard('Test', 'test@test.local')

        for policy in ['default', 'none', 'sign', 'sign-encrypt',
                       'encrypt', 'best-effort']:
            r = self.mp.crypto_policy_set('test@test.local', policy)
            print('%s' % r.as_dict())
            self.assertEqual('success', r.as_dict()['status'])

        for policy in ['anything', 'else']:
            r = self.mp.crypto_policy_set('test@test.local', policy).as_dict()
            self.assertEqual('error', r['status'])
            self.assertEqual('Policy has to be one of none|sign|encrypt'
                             '|sign-encrypt|best-effort|default', r['message'])

    def test_vcard_has_to_exist(self):
        res = self.mp.crypto_policy_set('test@test.local', 'sign').as_dict()
        self.assertEqual('error', res['status'])
        self.assertEqual('No vCard for email test@test.local!', res['message'])

    def test_vcard_is_updated(self):
        vcard = self._add_vcard('Test', 'test@test.local')
        for policy in ['none', 'sign', 'encrypt']:
            self.mp.crypto_policy_set('test@test.local', policy)
            self.assertEqual(policy, vcard.get(VCARD_CRYPTO_POLICY).value)


class CryptoPolicyForUserTest(CryptoPolicyBaseTest):
    def test_no_email_provided(self):
        res = self.mp.crypto_policy().as_dict()
        self.assertEqual('error', res['status'])

    def test_no_msg_with_email_(self):
        res = self.mp.crypto_policy('undefined@test.local').as_dict()
        self.assertEqual('success', res['status'])
        self.assertEqual('best-effort', res['result']['crypto-policy'])

    def test_with_signed_email(self):
        res = self.mp.crypto_policy('signer@test.local').as_dict()
        self.assertEqual('success', res['status'])
        self.assertEqual('best-effort', res['result']['crypto-policy'])

    def test_with_encrypted_email(self):
        res = self.mp.crypto_policy('encrypter@test.local').as_dict()
        self.assertEqual('success', res['status'])
        self.assertEqual('best-effort', res['result']['crypto-policy'])

    def test_vcard_overrides_mail_history(self):
        vcard = self._add_vcard('Encrypter', 'encrypter@test.local')
        vcard.add(VCardLine(name=VCARD_CRYPTO_POLICY, value='sign'))

        res = self.mp.crypto_policy('encrypter@test.local').as_dict()

        self.assertEqual('success', res['status'])
        self.assertEqual('sign', res['result']['crypto-policy'])
