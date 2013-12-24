# This is an auto-tagging plugin that invokes external tools.

import math
import time
import datetime
from gettext import gettext as _

import mailpile.plugins
import mailpile.config


##[ Configuration ]###########################################################

mailpile.plugins.register_config_section('prefs', 'autotag', ["Auto-tag",
{
    'command': ['Shell command to invoke', str, ''],
    'match_tag': ['Tag we are adding to automatically', str, ''],
    'unsure_tag': ['If unsure, add to this tag', str, ''],
    'ignore_kws': ['Ignore messages with these keywords', str, []],
}, {}])


##[ Keywords ]################################################################

def filter_hook(session, msg_mid, msg, keywords):
    """Classify this message."""
    config = session.config.prefs.autotag

    # FIXME: Iterate through all the autotag config options, invoke
    #        the external command and interpret the response.

    return keywords


# We add a filter post-hook with a high (late) priority, to maximize
# the amount of data we are feeding to the classifier.
mailpile.plugins.register_filter_hook_post('90-autotag', filter_hook)
