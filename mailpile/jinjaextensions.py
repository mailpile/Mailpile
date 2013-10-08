from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.utils import contextfunction, import_string, Markup
from commands import Action
import re
import datetime

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