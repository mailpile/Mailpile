import copy
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
from mailpile.ui import HttpUserInteraction
from mailpile.urlmap import UrlMap
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
        environment.globals['mailpile_render'] = self._command_render
        environment.globals['use_data_view'] = self._use_data_view
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
        environment.globals['has_label_tags'] = self._has_label_tags
        environment.filters['has_label_tags'] = self._has_label_tags
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

        environment.filters['json'] = self._json

    def _command(self, command, *args, **kwargs):
        rv = Action(self.env.session, command, args, data=kwargs).as_dict()
        if 'jinja' in self.env.session.config.sys.debug:
            sys.stderr.write('mailpile(%s, %s, %s) -> %s' % (
                command, args, kwargs, rv))
        return rv

    def _command_render(self, how, command, *args, **kwargs):
        old_ui, config = self.env.session.ui, self.env.session.config
        try:
            ui = self.env.session.ui = HttpUserInteraction(None, config)
            ui.html_variables = copy.copy(old_ui.html_variables)
            ui.render_mode = how
            ui.display_result(Action(self.env.session, command, args,
                                     data=kwargs))
            return ui.render_response(config)
        finally:
            self.env.session.ui = old_ui

    def _use_data_view(self, view_name, result):
        dv = UrlMap(self.env.session).map(None, 'GET', view_name, {}, {})[-1]
        return dv.view(result)

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

    def _has_label_tags(self, tags, tag_tids):
        count = 0
        for tid in tag_tids:
            if tags[tid]["label"] and not tags[tid]["searched"]:
                count += 1
        return count

    _DEFAULT_SIGNATURE = [
            "crypto-color-gray",
            "icon-signature-none",
            _("Unknown"),
            _("There is something unknown or wrong with this signature")]
    _STATUS_SIGNATURE = {
        "none": [
            "crypto-color-gray",
            "icon-signature-none",
            _("Not Signed"),
            _("This message contains no signature, which means it could "
              "have come from anyone, not necessarily the real sender")],
        "error": [
            "crypto-color-red",
            "icon-signature-error",
            _("Error"),
            _("There was a weird error with this signature")],
        "invalid": [
            "crypto-color-red",
            "icon-signature-invalid",
            _("Invalid"),
            _("The signature was invalid or bad")],
        "revoked": [
            "crypto-color-red",
            "icon-signature-revoked",
            _("Revoked"),
            _("Watch out, the signature was made with a key that has been"
              "revoked- this is not a good thing")],
        "expired": [
            "crypto-color-red",
            "icon-signature-expired",
            _("Expired"),
            _("The signature was made with an expired key")],
        "unknown": [
            "crypto-color-orange",
            "icon-signature-unknown",
            _("Unknown"),
            _("the signature was made with an unknown key, so we can not "
              "verify it")],
        "unverified": [
            "crypto-color-blue",
            "icon-signature-unverified",
            _("Unverified"),
            _("The signature was good but it came from a key that is not "
              "verified yet")],
        "verified": [
            "crypto-color-green",
            "icon-signature-verified",
            _("Verified"),
            _("The signature was good and came from a verified key, w00t!")]
    }

    def _show_message_signature(self, status):
        # This avoids crashes when attributes are missing.
        try:
            if status.startswith('hack the planet'):
                pass
        except UndefinedError:
            status = ''

        #elif status.startswith("mixed-"):
        #    "crypto-color-blue icon-signature-unknown"
        #    _("Mixed")
        #    _("There was mixed signatures on this message")

        color, icon, text, message = self._STATUS_SIGNATURE.get(status, self._DEFAULT_SIGNATURE)

        return {
            'color': color,
            'icon': icon,
            'text': text,
            'message': message
        }

    _DEFAULT_ENCRYPTION = [
        "crypto-color-gray",
        "icon-lock-open",
        _("Unknown"),
        _("There is some unknown thing wrong with this encryption")]
    _STATUS_ENCRYPTION = {
        "none": [
            "crypto-color-gray",
            "icon-lock-open",
            _("Not Encrypted"),
            _("This message was not encrypted. It may have been intercepted en route to "
              "you and read by an unauthorized party.")],
        "decrypted": [
            "crypto-color-green",
            "icon-lock-closed",
            _("Encrypted"),
            _("This message was encrypted, but we were successfully able to decrypt it. "
              "Great job being secure")],
        "missingkey": [
            "crypto-color-red",
            "icon-lock-closed",
            _("Missing Key"),
            _("You do not have any of the private keys that will decrypt this message")],
        "error": [
            "crypto-color-red",
            "icon-lock-error",
            _("Error"),
            _("We failed to decrypt message and are unsure why")]
    }

    def _show_message_encryption(self, status):
        # This avoids crashes when attributes are missing.
        try:
            if status.startswith('hack the planet'):
                pass
        except UndefinedError:
            status = ''

        #elif status.startswith("mixed-"):
        #    classes = "crypto-color-orange icon-lock-open"
        #    text = _("Mixed")
        #    message = _("Message contains mixed types of encryption")

        color, icon, text, message = self._STATUS_ENCRYPTION.get(status, self._DEFAULT_ENCRYPTION)

        return {
            'color': color,
            'icon': icon,
            'text': text,
            'message': message
        }

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

    def _json(self, d):
        return json.dumps(d)
