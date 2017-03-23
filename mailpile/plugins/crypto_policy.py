from datetime import datetime, timedelta

import mailpile.security as security
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
    pass


class UpdateCryptoPolicyForUser(CryptoPolicyBaseAction):
    """ Update crypto policy for a single user """
    SYNOPSIS = (None, 'crypto_policy/set', 'crypto_policy/set',
                '<email address> none|sign|encrypt|sign-encrypt|default')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('POST',)
    HTTP_QUERY_VARS = {'email': 'contact email', 'policy': 'new policy'}
    COMMAND_SECURITY = security.CC_CHANGE_CONTACTS

    def command(self):
        email, policy = self._parse_args()

        if policy not in CRYPTO_POLICIES:
            return self._error('Policy has to be one of %s' %
                               '|'.join(CRYPTO_POLICIES))

        vcard = self.session.config.vcards.get_vcard(email)
        if vcard:
            vcard.crypto_policy = policy
            vcard.save()
            return self._success(_('Set crypto policy for %s to %s'
                                   ) % (email, policy),
                                 result={'email': email, 'policy:': policy})
        else:
            return self._error(_('No vCard for email %s!') % email)

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


# FIXME: These decisions belong in mailpile.security!
class CryptoPolicy(CryptoPolicyBaseAction):
    """Calculate the aggregate crypto policy for a set of users"""
    SYNOPSIS = (None, 'crypto_policy', 'crypto_policy', '[<emailaddresses>]')
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ('GET',)
    HTTP_QUERY_VARS = {'email': 'e-mail addresses'}

    @classmethod
    def ShouldAttachKey(cls, config, vcards=None, emails=None, ttl=90):
        now = datetime.now()
        offset = timedelta(days=ttl)  # FIXME: Magic number!
        never = datetime.fromtimestamp(0)
        dates = []

        # who = dict of email -> vcard
        who = dict((vc.email, vc) for vc in (vcards or []) if vc)
        for e in emails or []:
            if e not in who:
                who[e] = config.vcards.get(e)

        # Examine each one. The policy is to only attach a key if everyone
        # can use keys AND someone needs a key.
        needs_key = 0
        for email, vc in who.iteritems():

            if vc and vc.kind == 'profile':
                continue  # Ignore self

            ts = None
            if vc:
                try:
                    # FIXME: This doesn't check *which* key we sent! This
                    #        needs to be made smarter for key rollover and
                    #        mutliple-key scenarios.
                    ts = datetime.fromtimestamp(float(vc.pgp_key_shared))
                except (ValueError, TypeError, AttributeError):
                    pass

            if (ts or never) + offset < now:
                # This user hasn't been sent a key recently.
                needs_key += 1

                # Can they do crypto?
                ratio = cls._encryption_ratio(
                    config.background, config.index, email, minimum=1)
                if ratio <= 0:
                    # Nope, let's not spam them with keys
                    return False

        # Someone needs a key update, attach.
        return (needs_key > 0)

    @classmethod
    def _vcard_policy(self, config, email):
        vcard = config.vcards.get_vcard(email)
        if vcard:
            return (vcard, vcard.kind, email,
                    vcard.crypto_policy or 'default',
                    vcard.crypto_format or 'default')
        return (None, None, email, 'default', 'default')

    @classmethod
    def _encryption_ratio(self, session, idx, email, minimum=5):
        # This method needs to return quickly, so we perform the more
        # restrictive search first before calculating a proper ratio.
        crypto = idx.search(session, ['from:' + email, 'has:crypto'])
        if len(crypto) < minimum:
            return 0.0

        # We also assume index order is roughly date order, which will
        # only be true once users have used the app for a while...
        recent = idx.search(session, ['from:' + email]).as_set()
        recent = set(sorted(list(recent))[-25:])
        crypto = crypto.as_set() & recent

        return float(len(crypto)) / len(recent)

    @classmethod
    def crypto_policy(cls, session, idx, emails):
        config = session.config
        for i in range(0, len(emails)):
            if '<' in emails[i]:
                emails[i] = (emails[i].split('<', 1)[1]
                                      .split('>', 1)[0]
                                      .rsplit('#', 1)[0].strip())
        policies = [cls._vcard_policy(config, e) for e in set(emails)]
        default = [(v, k, e, p, f) for v, k, e, p, f in policies
                   if k == 'profile']
        default = default[0] if default else (None, None, None,
                                              'best-effort', 'send_keys')
        cpolicy = default[-2]
        cformat = default[-1]

        # Try and merge all the user policies into one. This may lead
        # to conflicts which cannot be resolved.
        policy = cpolicy
        reason = None
        for vc, kind, email, cpol, cfmt in policies:
            if cpol and cpol not in ('default', 'best-effort'):
                if policy in ('default', 'best-effort'):
                    policy = cpol
                elif policy != cpol:
                    reason = _('Recipients have conflicting encryption '
                               'policies.')
                    policy = 'conflict'
        if policy == 'default':
            policy = 'best-effort'
        if not reason:
            reason = _('The encryption policy for these recipients is: %s'
                       ) % policy

        # If we don't have a key ourselves, that limits our options...
        if default[0]:
            if default[0].get_all('KEY'):
                can_sign = True
                can_encrypt = None  # not False and not True
            else:
                can_sign = False
                can_encrypt = False
                if policy in ('sign', 'sign-encrypt', 'encrypt'):
                    reason = _('This account does not have an encryption key.')
                    policy = 'conflict'
                elif policy in ('default', 'best-effort'):
                    reason = _('This account does not have an encryption key.')
                    policy = 'none'
        else:
            can_sign = False
            can_encrypt = False
        if can_encrypt is not False:
            can_encrypt = len([1 for v, k, e, p, f in policies
                               if not v or not v.get_all('KEY')]) == 0
        if not can_encrypt and 'encrypt' in policy:
            policy = 'conflict'
            if 'encrypt' in cpolicy:
                reason = _('Your policy is to always encrypt, '
                           'but we do not have keys for everyone!')
            else:
                reason = _('Some recipients require encryption, '
                           'but we do not have keys for everyone!')

        # If the policy is "best-effort", then we would like to sign and
        # encrypt if possible/safe. The bar for signing is lower.
        if policy == 'best-effort':
            should_encrypt = can_encrypt
            if should_encrypt:
                for v, k, e, p, f in policies:
                    if k and k == 'profile':
                        pass
                    elif cls._encryption_ratio(session, idx, e) < 0.8:
                        should_encrypt = False
                        break
                if should_encrypt:
                    policy = 'sign-encrypt'
                    reason = _('We have keys for everyone!')
            if can_sign and not should_encrypt:
                # FIXME: Should we check if anyone is using a lame MUA?
                policy = 'sign'
                if can_encrypt:
                    reason = _('Will not encrypt because '
                               'historic data is insufficient.')
                else:
                    reason = _('Cannot encrypt because we '
                               'do not have keys for all recipients.')

        if 'send_keys' in cformat:
            send_keys = cls.ShouldAttachKey(
                config,
                vcards=[p[0] for p in policies],
                emails=[p[2] for p in policies if not p[0]])
        else:
            send_keys = False

        return {
          'reason': reason,
          'can-sign': can_sign,
          'can-encrypt': can_encrypt,
          'crypto-policy': policy,
          'crypto-format': cformat,
          'send-keys': send_keys,
          'addresses': dict([(e, AddressInfo(e, vc.fn if vc else e, vcard=vc))
                             for vc, k, e, p, f in policies if vc])
        }

    def command(self):
        emails = list(self.args) + self.data.get('email', [])
        if len(emails) < 1:
            return self._error('Please provide at least one email address!')

        result = self.crypto_policy(self.session, self._idx(), emails)
        return self._success(result['reason'], result=result)


_plugins.register_commands(CryptoPolicy, UpdateCryptoPolicyForUser)
