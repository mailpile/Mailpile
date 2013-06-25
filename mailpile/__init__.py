#!/usr/bin/python

import mailpile.app
import mailpile.commands
import mailpile.ui

__all__ = ["app", "commands", "mailutils", "search", "ui", "util"]

class Mailpile(object):

  def __init__(self, ui=mailpile.ui.TextUI):
    self._config = mailpile.app.ConfigManager()
    self._session = mailpile.ui.Session(self._config)
    self._session.config.load(self._session)
    self._session.main = True
    self._ui = self._session.ui = ui()

    for (cmd, args, hlp, order) in mailpile.commands.COMMANDS.values():
      if cmd.endswith('='):
        cmd = cmd[:-1]
        def r(s, args):
          return mailpile.commands.Action(s._session, cmd, args)
      else:
        def r(s):
          return mailpile.commands.Action(s._session, cmd, '')
      setattr(self, cmd, r)

    self._config.prepare_workers(self._session)

