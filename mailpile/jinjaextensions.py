import datetime
import hashlib
import re
import urllib
import json
from gettext import gettext as _
from jinja2 import nodes, UndefinedError
from jinja2.ext import Extension
from jinja2.utils import contextfunction, import_string, Markup

from mailpile.commands import Action
from mailpile.util import *
from mailpile.plugins import get_activities, get_selection_actions
from mailpile.plugins import get_display_actions, get_display_modes
from mailpile.plugins import get_assets, get_body_blocks


class MailpileCommand(Extension):
    """Run Mailpile Commands, """
    tags = set(['mpcmd'])

    def __init__(self, environment):
        Extension.__init__(self, environment)
        self.env = environment
        environment.globals['mailpile'] = self._command
        environment.globals['regex_replace'] = self._regex_replace
        environment.filters['regex_replace'] = self._regex_replace
        environment.globals['friendly_bytes'] = self._friendly_bytes
        environment.filters['friendly_bytes'] = self._friendly_bytes
        environment.globals['friendly_number'] = self._friendly_number
        environment.filters['friendly_number'] = self._friendly_number
        environment.globals['show_avatar'] = self._show_avatar
        environment.filters['show_avatar'] = self._show_avatar
        environment.globals['navigation_on'] = self._navigation_on
        environment.filters['navigation_on'] = self._navigation_on
        environment.globals['show_tags'] = self._show_tags
        environment.filters['show_tags'] = self._show_tags
        environment.globals['show_message_signature'
                            ] = self._show_message_signature
        environment.filters['show_message_signature'
                            ] = self._show_message_signature
        environment.globals['show_message_encryption'
                            ] = self._show_message_encryption
        environment.filters['show_message_encryption'
                            ] = self._show_message_encryption
        environment.globals['contact_url'] = self._contact_url
        environment.filters['contact_url'] = self._contact_url
        environment.globals['contact_name'] = self._contact_name
        environment.filters['contact_name'] = self._contact_name

        # See utils.py for these functions:
        environment.globals['elapsed_datetime'] = elapsed_datetime
        environment.filters['elapsed_datetime'] = elapsed_datetime
        environment.globals['friendly_datetime'] = friendly_datetime
        environment.filters['friendly_datetime'] = friendly_datetime
        environment.globals['friendly_time'] = friendly_time
        environment.filters['friendly_time'] = friendly_time

        # See plugins/__init__.py for these functions:
        environment.globals['get_activities'] = get_activities
        environment.globals['get_selection_actions'] = get_selection_actions
        environment.globals['get_display_actions'] = get_display_actions
        environment.globals['get_display_modes'] = get_display_modes
        environment.globals['get_assets'] = get_assets
        environment.globals['get_body_blocks'] = get_body_blocks

        # This is a worse versin of urlencode, but without it we require
        # Jinja 2.7, which isn't apt-get installable.
        environment.globals['urlencode'] = self._urlencode
        environment.filters['urlencode'] = self._urlencode


    def _command(self, command, *args, **kwargs):
        return Action(self.env.session, command, args, data=kwargs).as_dict()

    def _regex_replace(self, s, find, replace):
        """A non-optimal implementation of a regex filter"""
        return re.sub(find, replace, s)

    def _friendly_number(self, number, decimals=0):
        # See mailpile/util.py:friendly_number if this needs fixing
        return friendly_number(number, decimals=decimals, base=1000)

    def _friendly_bytes(self, number, decimals=0):
        # See mailpile/util.py:friendly_number if this needs fixing
        return friendly_number(number,
                               decimals=decimals, base=1024, suffix='B')

    def _show_avatar(self, contact):
        if "photo" in contact:
            photo = contact['photo']
        else:
            photo = '/static/img/avatar-default.png'
        return photo

    def _navigation_on(self, search_tag_ids, on_tid):
        if search_tag_ids:
            for tid in search_tag_ids:
                if tid == on_tid:
                    return "navigation-on"
                else:
                    return ""

    def _show_tags(self, search_terms, tags):
        return True

    def _show_message_signature(self, status):
        # This avoids crashes when attributes are missing.
        try:
            if status.startswith('hack the planet'):
                pass
        except UndefinedError:
            status = ''

        if status == "none":
            classes = "crypto-color-gray icon-signature-none"
            text = _("No Signature")
            message = _("There is no signature on this message")
        elif status == "error":
            classes = "crypto-color-red icon-signature-" + status
            text = _("Error")
            message = _("There was some weird error with"
                        "this signature")
        elif status == "invalid":
            classes = "crypto-color-red icon-signature-" + status
            text = _("Invalid")
            message = _("The signature was invalid or bad")
        elif status == "revoked":
            classes = "crypto-color-red icon-signature-" + status
            text = _("Revoked")
            message = _("Watch out, the signature was made with"
                        "a key that has been revoked")
        elif status == "expired":
            classes = "crypto-color-red icon-signature-" + status
            text = _("Expired")
            message = _("The signature was made with an expired key")
        elif status == "unknown":
            classes = "crypto-color-orange icon-signature-" + status
            text = _("Unknown")
            message = _("the signature was made with an unknown key,"
                        "so we can't verify it")
        elif status == "unverified":
            classes = "crypto-color-blue icon-signature-unverified"
            text = _("Unverified")
            message = _("The signature was good, and came from a key"
                        "that isn't verified")
        elif status == "verified":
            classes = "crypto-color-green icon-signature-verified"
            text = _("Verified")
            message = _("The signature was good, and came from a"
                        "verified key, w00t!")
        elif status.startswith("mixed-"):
            classes = "crypto-color-blue icon-signature-unknown"
            text = _("Mixed")
            message = _("There was mixed signatures on this message")
        else:
            classes = "crypto-color-gray icon-signature-none"
            text = _("Unknown")
            message = _("There is some unknown thing wrong with"
                        "this encryption")
        return classes

    def _show_message_encryption(self, status):
        # This avoids crashes when attributes are missing.
        try:
            if status.startswith('hack the planet'):
                pass
        except UndefinedError:
            status = ''

        if status == "none":
            classes = "crypto-color-gray icon-lock-open"
            text = _("Not Encrypted")
            message = _("This message was not encrypted."
                        "It may have been intercepted en route to"
                        "you and read by an"
                        "unauthorized party.")
        elif status == "decrypted":
            classes = "crypto-color-green icon-lock-closed"
            text = _("Encrypted")
            message = _("This was encrypted, but we successfully"
                        "decrypted the message")
        elif status == "missingkey":
            classes = "crypto-color-red icon-lock-closed"
            text = _("Missing Key")
            message = _("You do not have any of the private keys that will"
                        "decrypt this message")
        elif status == "error":
            classes = "crypto-color-red icon-lock-error"
            text = _("Error")
            message = _("We failed to decrypt message and are unsure why")
        elif status.startswith("mixed-"):
            classes = "crypto-color-orange icon-lock-open"
            text = _("Mixed")
            message = _("Message contains mixed types of encryption")
        else:
            classes = "crypto-color-gray icon-lock-open"
            text = _("Unknown")
            messaage = _("There is some unknown thing wrong with"
                         "this encryption")
        return classes

    def _contact_url(self, person):
        if 'contact' in person['flags']:
            url = "/contact/" + person['address'] + "/"
        else:
            url = "/contact/add/" + person['address'] + "/"
        return url

    def _contact_name(self, profiles, person):
        name = person['fn']
        for profile in profiles:
            if profile['email'] == person['address']:
                name = _('You')
                break
        return name

    def _urlencode(self, s):
        if type(s) == 'Markup':
            s = s.unescape()
        return Markup(urllib.quote_plus(s.encode('utf-8')))
