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
        'gpg_home': [_('Location of keyring'), 'path', DEF_GNUPG_HOME],
    }

    def get_vcards(self):
    	gnupg = GnuPG()
    	keys = gnupg.list_keys()
    	results = []

    	for key in keys.values():
    		vc = SimpleVCard(VCardLine(name="KEY", 
    			value="data:application/x-pgp-fingerprint,%s" 
    			% key["fingerprint"]))
    		for uid in key["uids"]:
    			if "email" in uid and uid["email"]:
    				vc.add(VCardLine(name="email", value=uid["email"]))
    			if "name" in uid and uid["name"]:
	    			vc.add(VCardLine(name="fn", value=uid["name"]))

	    	results.append(vc)

        return results


mailpile.plugins.register_vcard_importers(GnuPGImporter)
del _
