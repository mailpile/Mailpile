#coding:utf-8
import os

import mailpile.security as security
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

    def get_guid(self, vcard):
        return '%s/%s' % (self.config.guid, vcard.get('x-gpg-mrgid').value)

    def import_vcards(self, session, vcard_store, *args, **kwargs):
        kwargs['vcards'] = vcard_store
        return VCardImporter.import_vcards(self, session, vcard_store,
                                           *args, **kwargs)

    def get_vcards(self,
                   selectors=None, public=True, secret=True, vcards=None):
        if not self.config.active:
            return []

        # Generate all the nice new cards!
        new_cards = self.gnupg_keys_as_vcards(GnuPG(self.session.config),
                                              selectors=selectors,
                                              public=public,
                                              secret=secret)

        # Generate tombstones for keys which are gone from the keyring.
        if vcards:
            deleted = set()
            deleted_names = {}
            search = ';%s/' % self.config.guid
            for cardid, vcard in (vcards or {}).iteritems():
                for vcl in vcard.get_all('clientpidmap'):
                    if search in vcl.value:
                        key_id = vcl.value.split(';')[1]
                        deleted.add(key_id)
                        deleted_names[key_id] = vcard.fn
            if selectors:
                deleted = set([guid for guid in deleted
                               if guid.split('/')[-1] in selectors])
            deleted -= set([self.get_guid(card) for card in new_cards])
            for guid in deleted:
                mrgid = guid.split('/')[-1]
                fn = deleted_names[guid]
                new_cards.append(MailpileVCard(VCardLine(name='fn', value=fn),
                                               VCardLine(name='x-gpg-mrgid',
                                                         value=mrgid)))

        return new_cards

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
    def vcards_per_key(cls, keys, vcards):
        """This creates on VCards per key"""
        new_vcards = []
        for key_id, key in keys.iteritems():
            if cls.key_is_useless(key):
                continue
            vcls = [cls.key_vcl(key_id, key)]
            emails = []
            for uid in key.get('uids', []):
                if uid.get('email'):
                    vcls.append(VCardLine(name='email', value=uid['email']))
                    emails.append(uid['email'])
                if uid.get('name'):
                    name = uid['name']
                    vcls.append(VCardLine(name='fn', value=name))
            if emails:
                # This is us taking care to only create one card for each
                # set of e-mail addresses.
                card = MailpileVCard(*vcls)
                card.add(VCardLine(name='x-gpg-mrgid', value=key_id))
                for email in emails:
                    if email not in vcards:
                        vcards[email] = card
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
        secret_keys = gnupg.list_secret_keys(selectors=selectors)
        if secret:
            results += cls.vcards_one_per_uid(secret_keys, vcards,
                                              kindhint='profile')

        if public:
            keys = gnupg.list_keys(selectors=selectors)
            for key in secret_keys:
                if key in keys:
                    del keys[key]
            results += cls.vcards_per_key(keys, vcards)

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

        return self._success(_('Extracted %d vCards from GPG keychain'
                               ) % len(vcards), vcards)


class PGPKeysImportAsVCards(Command):
    """Import PGP keys as VCards"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/vcardimport',
                      'crypto/gpg/vcardimport', '<selectors>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        'q': 'selectors',
        'no_public': 'omit public keys',
        'no_secret': 'omit secret keys'
    }
    COMMAND_SECURITY = security.CC_CHANGE_CONTACTS

    def command(self):
        session, config = self.session, self.session.config

        selectors = [a for a in self.args if not a.startswith('-')]
        selectors.extend(self.data.get('q', []))

        public = not (int(self.data.get('no_public', [0])[0]) or
                      '-no_public' in self.args)
        secret = not (int(self.data.get('no_secret', [0])[0]) or
                      '-no_secret' in self.args)

        imported = 0
        for cfg in config.prefs.vcard.importers.gpg:
            gimp = GnuPGImporter(session, cfg)
            imported += gimp.import_vcards(session, config.vcards,
                                           selectors=selectors)

        return self._success(_('Imported %d vCards from GPG keychain'
                               ) % imported, {'vcards': imported})


_plugins.register_commands(PGPKeysAsVCards, PGPKeysImportAsVCards)
_plugins.register_vcard_importers(GnuPGImporter)
