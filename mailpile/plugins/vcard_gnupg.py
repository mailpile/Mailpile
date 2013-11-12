#coding:utf-8
import mailpile.plugins

from mailpile.vcard import *


class GnuPGImporter(VCardImporter):
    FORMAT_NAME = 'GnuPG'
    SHORT_NAME = 'gpg'
    CONFIG_RULES = {}


mailpile.plugins.register_vcard_importers(GnuPGImporter)
