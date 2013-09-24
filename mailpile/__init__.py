import mailpile.app
import mailpile.commands
import mailpile.ui

# Load the standard plugins
from mailpile.plugins import *

__all__ = ['Mailpile',
           "app", "commands", "plugins", "mailutils", "search", "ui", "util"]


class Mailpile(object):
    """This object provides a simple Python API to Mailpile."""

    def __init__(self, ui=mailpile.ui.UserInteraction, workdir=None):
        self._config = mailpile.app.ConfigManager(workdir=workdir)
        self._session = mailpile.ui.Session(self._config)
        self._session.config.load(self._session)
        self._session.main = True
        self._ui = self._session.ui = ui()
        for cls in mailpile.commands.COMMANDS:
            if cls.SYNOPSIS[1]:
                cmd, fnc = self._mk_action(cls, *cls.SYNOPSIS)
                setattr(self, cmd.replace('/', '_'), fnc)

    def _mk_action(self, cls, cc, cmd, url, argspec, *moreargs):
        if argspec:

            def fnc(*args):
                return mailpile.commands.Action(self._session, cmd, args)
        else:

            def fnc():
                return mailpile.commands.Action(self._session, cmd, '')

        fnc.__doc__ = '%s(%s)  # %s' % (cmd, argspec or '', cls.__doc__)
        return cmd, fnc

    def Interact(self):
        return mailpile.app.Interact(self._session)
