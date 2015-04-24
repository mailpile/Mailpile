#coding:utf-8
import os

from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.crypto.gpgi import GnuPG
from mailpile.vcard import *


_plugins = PluginManager(builtin=__file__)


# User default GnuPG key file
DEF_GNUPG_HOME = os.path.expanduser('~/.gnupg')


class GnuPGImporter(VCardImporter):
    FORMAT_NAME = 'GnuPG'
    FORMAT_DESCRIPTION = _('Import contacts from GnuPG keyring')
    SHORT_NAME = 'gpg'
    CONFIG_RULES = {
        'active': [_('Enable this importer'), bool, True],
        'gpg_home': [_('Location of keyring'), 'path', DEF_GNUPG_HOME],
    }
    VCL_KEY_FMT = 'data:application/x-pgp-fingerprint,%s'

    # Merge by own identifier, email or key (in that order)
    MERGE_BY = ['x-gpg-mrgid', 'email']

    # Update index's email->name mapping
    UPDATE_INDEX = True

    def get_vcards(self, selectors=None, public=True, secret=True):
        if not self.config.active:
            return []
        return self.gnupg_keys_as_vcards(GnuPG(self.session.config),
                                         selectors=selectors,
                                         public=public,
                                         secret=secret)

    @classmethod
    def key_is_useless(cls, key):
        return (key.get("disabled") or key.get("revoked") or
                not key["capabilities_map"].get("encrypt") or
                not key["capabilities_map"].get("sign"))

    @classmethod
    def key_vcl(cls, key_id, key):
        attrs = {}
        for a in ('keysize', 'creation_date',
                  'expiration_date', 'keytype_name'):
            if key.get(a):
                attrs[a.split('_')[0]] = key[a]
        return VCardLine(name='KEY',
                         value=cls.VCL_KEY_FMT % key_id,
                         **attrs)

    @classmethod
    def vcards_one_per_uid(cls, keys, vcards, kindhint=None):
        """This creates one VCard per e-mail address found in UIDs"""
        new_vcards = []
        for key_id, key in keys.iteritems():
            if cls.key_is_useless(key):
                continue
            for uid in key.get('uids', []):
                email = uid.get('email')
                if email:
                    vcls = [cls.key_vcl(key_id, key)]
                    if uid.get('name'):
                        vcls.append(VCardLine(name='fn', value=uid['name']))
                    if kindhint:
                        vcls += [VCardLine(name='x-mailpile-kind-hint',
                                           value=kindhint)]
                    card = vcards.get(email)
                    if card:
                        card.add(*vcls)
                    else:
                        vcls += [VCardLine(name='x-gpg-mrgid', value=email),
                                 VCardLine(name='email', value=email)]
                        vcards[email] = card = MailpileVCard(*vcls)
                        new_vcards.append(card)
        return new_vcards

    @classmethod
    def vcards_merged(cls, keys, vcards):
        """This creates merged VCards, grouping by uid/e-mail and key"""
        new_vcards = []
        for key_id, key in keys.iteritems():
            if cls.key_is_useless(key):
                continue
            vcls = [cls.key_vcl(key_id, key)]
            card = None
            emails = []
            for uid in key.get('uids', []):
                if uid.get('email'):
                    vcls.append(VCardLine(name='email', value=uid['email']))
                    card = card or vcards.get(uid['email'])
                    emails.append(uid['email'])
                if uid.get('name'):
                    name = uid['name']
                    vcls.append(VCardLine(name='fn', value=name))
            if card and emails:
                card.add(*vcls)
            elif emails:
                # This is us taking care to only create one card for each
                # set of e-mail addresses.
                card = MailpileVCard(*vcls)
                card.add(VCardLine(name='x-gpg-mrgid', value=key_id))
                for email in emails:
                    vcards[email] = card
                new_vcards.append(card)
        return new_vcards

    @classmethod
    def gnupg_keys_as_vcards(cls, gnupg,
                             selectors=None, public=True, secret=True):
        results = []
        vcards = {}

        # Secret keys first, as they'll probably all show up on the public
        # list as well and we want to be done handling them here.
        if secret:
            secret_keys = gnupg.list_secret_keys(selectors=selectors)
            results += cls.vcards_one_per_uid(secret_keys, vcards,
                                              kindhint='profile')
        else:
            secret_keys = []

        if public:
            keys = gnupg.list_keys(selectors=selectors)
            for key in secret_keys:
                if key in keys:
                    del keys[key]
            results += cls.vcards_merged(keys, vcards)

        # Set ranking markers on the best/newest key
        for card in results:
            keylines = card.get_all('key')
            if len(keylines) > 1:
                keylines.sort(key=lambda k: (k.get('keysize', '0000'),
                                             k.get('creation', '1970-01-01')))
                for idx, kl in enumerate(keylines):
                    keylines[idx].set_attr('x-rank', 2*(idx+1))

        return results


class PGPKeysAsVCards(Command):
    """PGP keys as VCards (keychain import logic)"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/vcards', 'crypto/gpg/vcards', '<selectors>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        'q': 'selectors',
        'no_public': 'omit public keys',
        'no_secret': 'omit secret keys'
    }

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                return ('\n\n'.join(vc.as_vCard() for vc in self.result)
                        ).decode('utf-8')
            else:
                return _("No results")

    def command(self):
        selectors = [a for a in self.args if not a.startswith('-')]
        selectors.extend(self.data.get('q', []))

        public = not (int(self.data.get('no_public', [0])[0]) or
                      '-no_public' in self.args)
        secret = not (int(self.data.get('no_secret', [0])[0]) or
                      '-no_secret' in self.args)

        vcards = GnuPGImporter.gnupg_keys_as_vcards(
            self._gnupg(),
            selectors=selectors,
            public=public,
            secret=secret)

        return self._success(_('Extracted %d VCards from GPG keychain'
                               ) % len(vcards), vcards)


_plugins.register_commands(PGPKeysAsVCards)
_plugins.register_vcard_importers(GnuPGImporter)
