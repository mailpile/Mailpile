import datetime
import hashlib
import re
import urllib
import json
from gettext import gettext as _
from jinja2 import nodes
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
        environment.globals['message_signature_classes'
                            ] = self._message_signature_classes
        environment.filters['message_signature_classes'
                            ] = self._message_signature_classes
        environment.globals['message_encryption_classes'
                            ] = self._message_encryption_classes
        environment.filters['message_encryption_classes'
                            ] = self._message_encryption_classes
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
        return ""

    def _message_signature_classes(self, status):    
        if status == "none":
            state = "icon-signature-none"
        elif status in ("error", "invalid", "revoked"):
            status = "crypto-color-red icon-signature-" + status
        elif status in ("expired", "unknown"):
            state = "crypto-color-orange icon-signature-" + status
        elif status == "unverified":
            state = "crypto-color-blue icon-signature-unverified"
        elif status == "verified":
            state = "crypto-color-green icon-signature-verified"
        elif status.startswith("mixed-"):
            state = "crypto-color-blue icon-signature-unknown"
        else:
            state = "icon-signature-none"      
        return state

    def _message_encryption_classes(self, status):
        if status == "none":
            state = "icon-lock-open"
        elif status == "decrypted":
            state = "crypto-color-green icon-lock-closed"
        elif status == "missingkey":
            state = "crypto-color-red icon-lock-closed"
        elif status == "error":
            state = "crypto-color-red icon-lock-error"
        elif status == "partial-decrypted":
            state = "crypto-color-orange icon-lock-open"
        elif status.startswith("mixed-"):
            state = "crypto-color-orange icon-lock-open"
        else:
            state = "icon-lock-open"
        return state

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
