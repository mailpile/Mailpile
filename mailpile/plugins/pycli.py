import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *


class PyCLI(Command):
    """Launch a Python REPL"""
    SYNOPSIS = (None, 'pycli', None, None)
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ()

    def command(self):
        import code
        import readline
        from mailpile import Mailpile
        variables = globals()
        variables['session'] = self.session
        variables['mp'] = Mailpile(session=self.session)
        return code.InteractiveConsole(locals=variables).interact("""

This is Python inside of Mailpile inside of Python.

   - The `mp` variable is a Pythonic API to the current pile of mail.
   - The `session` variable is the current UI session.
   - Press CTRL+D to return to the normal CLI.
""")


mailpile.plugins.register_commands(PyCLI)
