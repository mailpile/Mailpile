import datetime
import hashlib
import re
import urllib
from gettext import gettext as _
from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.utils import contextfunction, import_string, Markup

from mailpile.commands import Action
from mailpile.util import *
from mailpile.plugins import get_activities, get_selection_actions, get_display_actions, get_display_modes


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
        return friendly_number(number, decimals=decimals, base=1024, suffix='B')

    def _show_avatar(self, contact):

      if "photo" in contact:
        photo = contact['photo']
      else:
        photo = '/static/img/avatar-default.png'

      return photo

    def _navigation_on(self, search_tags, slug):
        if search_tags:
          for tag in search_tags:
            if tag.slug == slug:
              return "navigation-on"
            else:
              return ""

    def _show_tags(self, search_terms, tags):
    
      return
