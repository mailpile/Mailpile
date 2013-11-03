from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.utils import contextfunction, import_string, Markup
from commands import Action
import re
import datetime

# used for gravatar plugin
import urllib
import hashlib

class MailpileCommand(Extension):
    """Run Mailpile Commands, """
    tags = set(['mpcmd'])

    def __init__(self, environment):
        Extension.__init__(self, environment)
        self.env = environment
        environment.globals['mailpile'] = self._command
        environment.globals['regex_replace'] = self._regex_replace
        environment.filters['regex_replace'] = self._regex_replace
        environment.globals['friendly_date'] = self._friendly_date
        environment.filters['friendly_date'] = self._friendly_date
        environment.globals['show_avatar'] = self._show_avatar
        environment.filters['show_avatar'] = self._show_avatar
        environment.globals['navigation_on'] = self._navigation_on
        environment.filters['navigation_on'] = self._navigation_on
        environment.globals['abbreviate_number'] = self._abbreviate_number
        environment.filters['abbreviate_number'] = self._abbreviate_number


    def _command(self, command, *args, **kwargs):
        return Action(self.env.session, command, args, data=kwargs).as_dict()

    def _regex_replace(self, s, find, replace):
        """A non-optimal implementation of a regex filter"""
        return re.sub(find, replace, s)

    def _friendly_date(self, timestamp):
        ts = datetime.date.fromtimestamp(timestamp)
        days_ago = (datetime.date.today() - ts).days

        if days_ago < 1:
            return 'today'
        elif days_ago < 2:
            return 'yesterday'
        elif days_ago < 7:
            return '%d days ago' % days_ago
        else:
            return ts.strftime("%Y-%m-%d")

    def _show_avatar(self, protocol, host, email, size=60):

        if host == "localhost":
          default = protocol + "://" + host + "/static/img/avatar-default.png"
        else:
          default = "mm"

        gravatar_url = "http://www.gravatar.com/avatar/" + hashlib.md5(email.lower()).hexdigest() + "?"
        gravatar_url += urllib.urlencode({'d':default, 's':str(size)})

        return gravatar_url

    def _navigation_on(self, search_tags, slug):
        if search_tags:
          for tag in search_tags:
            if tag.slug == slug:
              return "navigation-on"
            else:
              return ""

    def _abbreviate_number(self, number):

      return number