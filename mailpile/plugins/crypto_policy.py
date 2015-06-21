from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.vcard import VCardLine, AddressInfo
from mailpile.commands import Command
from mailpile.mailutils import Email


_plugins = PluginManager(builtin=__file__)


VCARD_CRYPTO_POLICY = 'X-MAILPILE-CRYPTO-POLICY'
CRYPTO_POLICIES = ['none', 'sign', 'encrypt', 'sign-encrypt',
                   'best-effort', 'default']


##[ Commands ]################################################################

class CryptoPolicyBaseAction(Command):
    """ Base class for crypto policy commands """

    def _search(self, email, terms):
        return self._idx().search(self.session, ['from:' + email] + terms)

    def _find_policy_based_on_mails(self, mail_idxs):
        # FIXME: Unused, and very expensive. Check tags instead.
        idx = self._idx()
        for mail_idx in mail_idxs.as_set():
            mail = Email(idx, mail_idx).get_msg()

            if mail.encryption_info.get('status') != 'none':
                return 'encrypt'
            if mail.signature_info.get('status') != 'none':
                return 'sign'

        return 'none'

    def _best_effort_policy(self, email):
        # FIXME: Unused, but should be used in best-effort eval below.
        mail_idxs = self._search(email, ['has:crypto'])

        if mail_idxs:
            return self._find_policy_based_on_mails(mail_idxs)
        else:
            return 'default'


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
            vcard.crypto_policy = policy
            vcard.save()
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


class CryptoPolicyForUsers(CryptoPolicyBaseAction):
    """Calculate the aggregate crypto policy for a set of users"""
    SYNOPSIS = (None, 'crypto_policy', 'crypto_policy', '[<emailaddresses>]')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('GET',)

    def command(self):
        if len(self.args) < 1:
            return self._error('Please provide at least one email address!')

        policies = [self._vcard_policy(email) for email in self.args]
        default = [(v, k, e, p) for v, k, e, p in policies if k == 'profile']
        default = default[0] if default else (None, None, None, 'best-effort')

        # Try and merge all the user policies into one. This may lead
        # to conflicts which cannot be resolved.
        policy = default[-1]
        reason = None
        for vc, kind, email, cpol in policies:
            if cpol and cpol not in ('default', 'best-effort'):
                if policy in ('default', 'best-effort'):
                    policy = cpol
                elif policy != cpol:
                    reason = _('Recipients have conflicting encryption policies.')
                    policy = 'conflict'
        if not reason:
            reason = _('The encryption policy for these recipients is: %s'
                       ) % policy

        # If we don't have a key ourselves, that limits our options...
        if default[0] and not default[0].get_all('KEY'):
            if policy in ('sign', 'sign-encrypt'):
                reason = _('This account does not have an encryption key.')
                policy = 'conflict'
            elif policy in ('default', 'best-effort'):
                reason = _('This account does not have an encryption key.')
                policy = 'none'

        # If the policy is "best-effort", then we would like to sign and
        # encrypt if possible/safe. The bar for signing is lower.
        if policy == 'best-effort':
            missing_keys = [1 for v, k, e, p in policies
                            if not v or not v.get_all('KEY')]
            if not missing_keys:
                # FIXME: This is way too aggressive!
                policy = 'sign-encrypt'
                reason = _('Signing and encrypting because we have keys for everyone!')
            else:
                # FIXME: Should we check if anyone is using a lame MUA?
                policy = 'sign'
                reason = _('Signing, but cannot encrypt because we do not have keys for all recipients.')

        result = {
          'reason': reason,
          'crypto-policy': policy,
          'addresses': [AddressInfo(e, vc.fn if vc else e, vcard=vc)
                        for vc, k, e, p in policies if vc]
        }
        return self._success(reason, result=result)

    def _vcard_policy(self, email):
        vcard = self.session.config.vcards.get_vcard(email)
        if vcard:
            return (vcard, vcard.kind, email, vcard.crypto_policy)
        return (None, None, email, 'default')


_plugins.register_commands(CryptoPolicyForUsers,
                           UpdateCryptoPolicyForUser)
