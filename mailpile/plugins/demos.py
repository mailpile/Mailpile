# This is a collection of very short demo-plugins to illustrate how
# to create and register hooks into the various parts of Mailpile
#
# To start creating a new plugin, it may make sense to copy this file,
# globally search/replace the word "Demo" with your preferred plugin
# name and then go delete sections you aren't going to use.
#
# Happy hacking!

import mailpile.plugins


##[ Pluggable configuration ]#################################################

# FIXME


##[ Pluggable keyword extractors ]############################################

# FIXME


##[ Pluggable search terms ]##################################################

# FIXME


##[ Pluggable vcard functions ]###############################################
from mailpile.vcard import *


class DemoVCardImporter(VCardImporter):
    """
    This VCard importer simply generates VCards based on data in the
    configuration. This is not particularly useful, but it demonstrates
    how each importer can define (and use) its own settings.
    """
    FORMAT_NAME = 'Demo Contacts'
    FORMAT_DESCRPTION = 'This is the demo importer'
    SHORT_NAME = 'demo'
    CONFIG_RULES = {
         'name': ['Contact name', str, 'Mr. Rogers'],
         'email': ['Contact email', 'email', 'mr@rogers.com']
    }

    def get_vcards(self):
        """Returns just a single contact, based on data from the config."""
        return [SimpleVCard(
            VCardLine(name='fn', value=self.config.name),
            VCardLine(name='email', value=self.config.email)
        )]


mailpile.plugins.register_vcard_importers(DemoVCardImporter)


##[ Pluggable commands ]######################################################

# FIXME



