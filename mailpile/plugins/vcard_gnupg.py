#coding:utf-8
import os

import mailpile.plugins
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
        return []


mailpile.plugins.register_vcard_importers(GnuPGImporter)
del _
