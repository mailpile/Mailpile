# This is a collection of very short demo-plugins to illustrate how
# to create and register hooks into the various parts of Mailpile
#
# To start creating a new plugin, it may make sense to copy this file,
# globally search/replace the word "Demo" with your preferred plugin
# name and then go delete sections you aren't going to use.
#
# Happy hacking!

import mailpile.plugins

# Helper for i18n
_ = lambda x: x


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
    FORMAT_NAME = _('Demo Contacts')
    FORMAT_DESCRPTION = _('This is the demo importer')
    SHORT_NAME = 'demo'
    CONFIG_RULES = {
         'active': [_('Activate demo importer'), bool, True],
         'name': [_('Contact name'), str, 'Mr. Rogers'],
         'email': [_('Contact email'), 'email', 'mr@rogers.com']
    }

    def get_vcards(self):
        """Returns just a single contact, based on data from the config."""
        # Notes to implementors:
        #
        #  - It is important to only return one card per (set of)
        #    e-mail addresses, as internal overwriting may cause
        #    unexpected results.
        #  - If data is to be deleted from the contact list, it
        #    is important to return a VCard for that e-mail address
        #    which has the relevant data removed.
        #
        if not self.config.active:
            return []
        return [SimpleVCard(
            VCardLine(name='fn', value=self.config.name),
            VCardLine(name='email', value=self.config.email)
        )]


mailpile.plugins.register_vcard_importers(DemoVCardImporter)


##[ Pluggable commands ]######################################################

# FIXME



# i18n cleanup
del _
