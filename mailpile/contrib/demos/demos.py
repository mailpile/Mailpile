# This is a collection of very short demo-plugins to illustrate how
# to create and register hooks into the various parts of Mailpile
#
# To start creating a new plugin, it may make sense to copy this file,
# globally search/replace the word "Demo" with your preferred plugin
# name and then go delete sections you aren't going to use.
#
# Happy hacking!

from gettext import gettext as _
from mailpile.plugins import PluginManager


##[ Pluggable configuration ]#################################################

# FIXME


##[ Pluggable keyword extractors ]############################################

# FIXME


##[ Pluggable search terms ]##################################################

# Pluggable search terms allow plugins to enhance the behavior of the
# search engine in various ways. Examples of basic enhanced search terms
# are the date: and size: keywords, which accept human-friendly ranges
# and input, and convert those to a list of "low level" keywords to
# actually search for.

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
        return [MailpileVCard(
            VCardLine(name='fn', value=self.config.name),
            VCardLine(name='email', value=self.config.email)
        )]


##[ Pluggable cron jobs ]#####################################################

def TickJob(session):
    """
    This is a very minimal cron job - just a function that runs within
    a session.

    Note that generally it is a better pattern to create a Command which
    is then invoked by the cron job, so power users can access the
    functionality directly.  It is also a good idea to make the interval
    configurable by registering a setting and referencing that instead of
    a fixed number.  See compose.py for an example of how this is done.
    """
    session.ui.notify('Tick!')


##[ Pluggable commands and data views ]#######################################

from mailpile.commands import Command
from mailpile.util import md5_hex


class md5sumCommand(Command):
    """This command calculates MD5 sums"""
    SYNOPSIS_ARGS = '[<data to hash>]'
    SPLIT_ARG = False
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
       'data': 'Data to hash'
    }

    def command(self):
        if 'data' in self.data:
            data = self.data['data'][0]
        else:
            data = ''.join(self.args)

        for gross in self.session.config.sys.md5sum_blacklist.split():
            if gross in data or not data:
                return self._error(_('I refuse to work with empty '
                                     'or gross data'),
                                   info={'data': data})

        return self._success(_('I hashed your data for you, yay!'),
                             result=md5_hex(data))


class md5sumWordyView(md5sumCommand):
    """Represent MD5 sums in a more wordy way."""
    @classmethod
    def view(cls, result):
        return 'MD5:%s' % result


def on_plugin_start(config):
    """Called once after plugin is loaded.

    You can initialize external or expensive dependencies here.

    Args:
        config: The Mailpile configuration dictionary

    Returns:
        void
    """
    # initialize some external dependencies
    pass


def on_plugin_shutdown(config):
    """Called before plugin is stopped.

    Shutdown external dependencies here, especially if they created some threads.

    Args:
        config: The Mailpile configuration dictionary

    Returns:
        void
    """
    # properly shutdown external dependencies
    pass


class DemoMailbox(object):
    """A dysfunctional demo mailbox. See mailpile.mailboxes.* for proper mailbox examples"""
    @classmethod
    def parse_path(cls, config, fn, create=False):
        raise ValueError('This is only a demo mailbox class!')
