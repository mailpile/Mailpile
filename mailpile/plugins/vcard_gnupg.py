#coding:utf-8
import os

import mailpile.plugins
from mailpile.gpgi import GnuPG
from mailpile.vcard import *

# Helper for i18n
_ = lambda x: x

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
    VCL_KEY_FMT = "data:application/x-pgp-fingerprint,%(fingerprint)s"

    def get_vcards(self):
        if not self.config.active:
            return []

        gnupg = GnuPG()
        keys = gnupg.list_keys()
        results = []
        vcards = {}
        for key in keys.values():
            vcls = [VCardLine(name="KEY",
                              value=self.VCL_KEY_FMT % key)]
            card = None
            emails = []
            for uid in key["uids"]:
                if "email" in uid and uid["email"]:
                    vcls.append(VCardLine(name="email", value=uid["email"]))
                    card = card or vcards.get(uid['email'])
                    emails.append(uid["email"])
                if "name" in uid and uid["name"]:
                    name = uid["name"]
                    vcls.append(VCardLine(name="fn", value=name))
            if card:
                card.add(*vcls)
            else:
                # This is us taking care to only create one card for each
                # set of e-mail addresses.
                # FIXME: We should still probably dedup lines within the vcard.
                card = SimpleVCard(*vcls)
                for email in emails:
                    vcards[email] = card
                results.append(card)

        return results


mailpile.plugins.register_vcard_importers(GnuPGImporter)
del _
