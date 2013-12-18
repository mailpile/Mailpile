from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.utils import contextfunction, import_string, Markup
from commands import Action
import re
import datetime

# used for gravatar plugin
import urllib
import hashlib

from mailpile.util import *


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
        return friendly_number(number, decimals=decimals,
                                       base=1024, suffix='B')

    def _show_avatar(self, protocol, host, email, size=60):

        if host == "localhost":
            default = protocol + "://" + host + "/static/img/avatar-default.png"
        else:
            default = "mm"

        digest = md5_hex(email.lower())
        gravatar_url = "https://www.gravatar.com/avatar/" + digest + "?"
        gravatar_url += urllib.urlencode({'d':default, 's':str(size)})

        return gravatar_url

    def _navigation_on(self, search_tags, slug):
        if search_tags:
          for tag in search_tags:
            if tag.slug == slug:
              return "navigation-on"
            else:
              return ""

    def _show_tags(self, search_terms, tags):
    
      return
