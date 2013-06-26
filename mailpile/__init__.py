#!/usr/bin/python

import mailpile.app
import mailpile.commands
import mailpile.ui

__all__ = ["app", "commands", "mailutils", "search", "ui", "util"]

class Mailpile(object):
  """This object provides a simple Python API to Mailpile."""

  def __init__(self, ui=mailpile.ui.TextUI):
    self._config = mailpile.app.ConfigManager()
    self._session = mailpile.ui.Session(self._config)
    self._session.config.load(self._session)
    self._session.main = True
    self._ui = self._session.ui = ui()

    for (cmd, args, hlp, order) in mailpile.commands.COMMANDS.values():
      cmd, fnc = self._mk_action(cmd)
      fnc.__doc__ = hlp
      setattr(self, cmd, fnc)

  def _mk_action(self, cmd):
    if cmd.endswith('='):
      cmd = cmd[:-1]
      def fnc(args):
        return mailpile.commands.Action(self._session, cmd, args)
      return cmd, fnc
    else:
      def fnc():
        return mailpile.commands.Action(self._session, cmd, '')
      return cmd, fnc

