#!/usr/bin/env python2.7

import mailpile.app
import mailpile.commands
import mailpile.ui

# Load the standard plugins
from mailpile.plugins import *

__all__ = ['Mailpile',
           "app", "commands", "plugins", "mailutils", "search", "ui", "util"]

class Mailpile(object):
  """This object provides a simple Python API to Mailpile."""

  def __init__(self, ui=mailpile.ui.UserInteraction):
    self._config = mailpile.app.ConfigManager()
    self._session = mailpile.ui.Session(self._config)
    self._session.config.load(self._session)
    self._session.main = True
    self._ui = self._session.ui = ui()
    for (cmd, cls) in mailpile.commands.COMMANDS.values():
      cmd, fnc = self._mk_action(cmd)
      if cls.SYNOPSIS:
        fnc.__doc__ = '%s(%s)  # %s' % (cmd, cls.SYNOPSIS, cls.__doc__)
      else:
        fnc.__doc__ = '%s()  # %s' % (cmd, cls.__doc__)
      setattr(self, cmd, fnc)

  def _mk_action(self, cmd):
    if cmd.endswith('='):
      cmd = cmd[:-1]
      def fnc(*args):
        return mailpile.commands.Action(self._session, cmd, args)
      return cmd, fnc
    else:
      def fnc():
        return mailpile.commands.Action(self._session, cmd, '')
      return cmd, fnc

