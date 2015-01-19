from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.vcard import VCardLine
from mailpile.commands import Command
from mailpile.mailutils import Email


_plugins = PluginManager(builtin=__file__)


VCARD_CRYPTO_POLICY = 'X-MAILPILE-CRYPTO-POLICY'
CRYPTO_POLICIES = ['none', 'sign', 'encrypt', 'sign-encrypt', 'default']

##[ Commands ]################################################################

class CryptoPolicyBaseAction(Command):
    """ Base class for crypto policy commands """

    def _get_keywords(self, e):
        idx = self._idx()
        mid = e.msg_mid()
        kws, snippet = idx.read_message(
            self.session,
            mid,
            e.get_msg_info(field=idx.MSG_ID),
            e.get_msg(),
            e.get_msg_size(),
            int(e.get_msg_info(field=idx.MSG_DATE), 36))
        return kws

    def _search(self, email):
        idx = self._idx()
        return idx.search(self.session,
                          ['to:' + email, 'has:crypto', 'has:pgp'],
                          order='date')

    def _find_policy_based_on_mails(self, mail_idxs):
        idx = self._idx()
        for mail_idx in mail_idxs.as_set():
            mail = Email(idx, mail_idx).get_msg()

            if mail.encryption_info.get('status') != 'none':
                return 'encrypt'
            if mail.signature_info.get('status') != 'none':
                return 'sign'

        return 'none'

    def _find_policy(self, email):
        mail_idxs = self._search(email)

        if mail_idxs:
            return self._find_policy_based_on_mails(mail_idxs)
        else:
            return 'none'

    def _update_vcard(self, vcard, policy):
        if 'default' == policy:
            for line in vcard.get_all(VCARD_CRYPTO_POLICY):
                vcard.remove(line.line_id)
        else:
            if len(vcard.get_all(VCARD_CRYPTO_POLICY)) > 0:
                vcard.get(VCARD_CRYPTO_POLICY).value = policy
            else:
                vcard.add(VCardLine(name=VCARD_CRYPTO_POLICY, value=policy))


class AutoDiscoverCryptoPolicy(CryptoPolicyBaseAction):
    """ Auto discovers crypto policy for all known contacts """
    SYNOPSIS = (None, 'crypto_policy/auto_set_all', None, None)
    ORDER = ('AutoDiscover', 0)

    def _set_crypto_policy(self, email, policy):
        if policy != 'none':
            vcard = self.session.config.vcards.get_vcard(email)
            if vcard:
                self._update_vcard(vcard, policy)
                self.session.ui.mark('policy for %s will be %s' % (email, policy))
                return True
            else:
                self.session.ui.mark('skipped setting policy for %s to policy,  no vcard entry found' % email)
        return False

    def _update_crypto_state(self, email):
        policy = self._find_policy(email)

        return self._set_crypto_policy(email, policy)

    def command(self):
        idx = self._idx()

        updated = set()
        for email in idx.EMAIL_IDS:
            if self._update_crypto_state(email):
                updated.add(email)

        return self._success(_('Discovered crypto policy'), result=updated)


class UpdateCryptoPolicyForUser(CryptoPolicyBaseAction):
    """ Update crypto policy for a single user """
    SYNOPSIS = (None, 'crypto_policy/set', 'crypto_policy/set', '<email address> none|sign|encrypt|sign-encrypt|default')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('POST',)
    HTTP_QUERY_VARS = {'email': 'contact email', 'policy': 'new policy'}

    def command(self):
        email, policy = self._parse_args()

        if policy not in CRYPTO_POLICIES:
            return self._error('Policy has to be one of %s' % '|'.join(CRYPTO_POLICIES))

        vcard = self.session.config.vcards.get_vcard(email)
        if vcard:
            self._update_vcard(vcard, policy)
            return self._success(_('Set crypto policy for %s to %s'
                                   ) % (email, policy),
                                 result={'email': email, 'policy:': policy})
        else:
            return self._error(_('No vcard for email %s!') % email)

    def _parse_args(self):
        if self.data:
            email = unicode(self.data['email'][0])
            policy = unicode(self.data['policy'][0])
        else:
            if len(self.args) != 2:
                return self._error(_('Please provide email address and policy!'))

            email = self.args[0]
            policy = self.args[1]
        return email, policy


class CryptoPolicyForUser(CryptoPolicyBaseAction):
    """ Retrieve the current crypto policy for a user """
    SYNOPSIS = (None, 'crypto_policy', 'crypto_policy', '[<emailaddresses>]')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('GET',)

    def command(self):
        if len(self.args) != 1:
            return self._error('Please provide a single email address!')

        email = self.args[0]
        policy = self._vcard_policy(email) or self._find_policy(email)

        return self._success(_('Crypto policy for %s is %s') % (email, policy),
                             result=policy)

    def _vcard_policy(self, email):
        vcard = self.session.config.vcards.get_vcard(email)
        if vcard and len(vcard.get_all(VCARD_CRYPTO_POLICY)) > 0:
            return vcard.get(VCARD_CRYPTO_POLICY).value
        else:
            return None


_plugins.register_commands(AutoDiscoverCryptoPolicy,
                           CryptoPolicyForUser,
                           UpdateCryptoPolicyForUser)
