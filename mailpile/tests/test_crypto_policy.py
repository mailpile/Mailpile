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
        self.config.vcards.index_vcard(card)
        return card


class CryptoPolicyAutoSetAll(CryptoPolicyBaseTest):
    def test_command_is_executable(self):
        res = self.mp.crypto_policy_auto_set_all()
        self.assertIsNotNone(res)

    def test_vcard_gets_updated(self):
        self._add_vcard('Signer', 'signer@test.local')
        self._add_vcard('Encrypter', 'encrypter@test.local')

        res = self.mp.crypto_policy_auto_set_all()

        self.assertEqual({'signer@test.local', 'encrypter@test.local'}, res.as_dict()['result'])
        signer_vcard = self.config.vcards.get_vcard('signer@test.local')
        encrypter_vcard = self.config.vcards.get_vcard('encrypter@test.local')
        self.assertEqual('sign', signer_vcard.get(VCARD_CRYPTO_POLICY).value)
        self.assertEqual('encrypt', encrypter_vcard.get(VCARD_CRYPTO_POLICY).value)


class UpdateCryptoPolicyForUserTest(CryptoPolicyBaseTest):
    def test_args_are_checked(self):
        self.assertEqual('error', self.mp.crypto_policy_set().as_dict()['status'])
        self.assertEqual('error', self.mp.crypto_policy_set('one arg').as_dict()['status'])

    def test_policies_are_validated(self):
        self._add_vcard('Test', 'test@test.local')

        for policy in ['default', 'none', 'sign', 'encrypt']:
            self.assertEqual('success', self.mp.crypto_policy_set('test@test.local', policy).as_dict()['status'])

        for policy in ['anything', 'else']:
            res = self.mp.crypto_policy_set('test@test.local', policy).as_dict()
            self.assertEqual('error', res['status'])
            self.assertEqual('Policy has to be one of none|sign|encrypt|sign-encrypt|default',
                             res['message'])

    def test_vcard_has_to_exist(self):
        res = self.mp.crypto_policy_set('test@test.local', 'sign').as_dict()
        self.assertEqual('error', res['status'])
        self.assertEqual('No vcard for email test@test.local!', res['message'])

    def test_vcard_is_updated(self):
        vcard = self._add_vcard('Test', 'test@test.local')
        for policy in ['none', 'sign', 'encrypt']:
            self.mp.crypto_policy_set('test@test.local', policy)
            self.assertEqual(policy, vcard.get(VCARD_CRYPTO_POLICY).value)

    def test_default_policy_removes_vcard_line(self):
        vcard = self._add_vcard('Test', 'test@test.local')
        vcard.add(VCardLine(name=VCARD_CRYPTO_POLICY, value='sign'))

        self.mp.crypto_policy_set('test@test.local', 'default')
        self.assertEqual(0, len(vcard.get_all(VCARD_CRYPTO_POLICY)))


class CryptoPolicyForUserTest(CryptoPolicyBaseTest):
    def test_no_email_provided(self):
        res = self.mp.crypto_policy().as_dict()
        self.assertEqual('error', res['status'])
        self.assertEqual('Please provide a single email address!', res['message'])

    def test_no_msg_with_email_(self):
        res = self.mp.crypto_policy('undefined@test.local').as_dict()
        self.assertEqual('success', res['status'])
        self.assertEqual('none', res['result'])

    def test_with_signed_email(self):
        res = self.mp.crypto_policy('signer@test.local').as_dict()
        self.assertEqual('success', res['status'])
        self.assertEqual('sign', res['result'])

    def test_with_encrypted_email(self):
        res = self.mp.crypto_policy('encrypter@test.local').as_dict()
        self.assertEqual('success', res['status'])
        self.assertEqual('encrypt', res['result'])

    def test_vcard_overrides_mail_history(self):
        vcard = self._add_vcard('Encrypter', 'encrypter@test.local')
        vcard.add(VCardLine(name=VCARD_CRYPTO_POLICY, value='sign'))

        res = self.mp.crypto_policy('encrypter@test.local').as_dict()

        self.assertEqual('success', res['status'])
        self.assertEqual('sign', res['result'])
