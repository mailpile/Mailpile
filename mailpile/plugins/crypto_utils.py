import datetime
import re
import time
from gettext import gettext as _

import mailpile.plugins
from mailpile.commands import Command

from mailpile.crypto.gpgi import GnuPG

class GPGKeySearch(Command):
    """Search for a GPG Key."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/searchkey', 'crypto/gpg/searchkey', '<terms>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {'q': 'search terms'}

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                return '\n'.join(["%s: %s <%s>" % (keyid, x["name"], x["email"]) for keyid, det in self.result.iteritems() for x in det["uids"]])
            else:
                return _("No results")

    def command(self):
        args = self.args[:]
        for q in self.data.get('q', []):
            args.extend(q.split())

        g = GnuPG()
        return g.search_key(" ".join(args))

class GPGKeyReceive(Command):
    """Fetch a GPG Key."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/receivekey', 'crypto/gpg/receivekey', '<keyid>')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {'keyid': 'ID of key to fetch'}


    def command(self):
        keyid = self.data.get("keyid", self.args)
        g = GnuPG()
        res = []
        for key in keyid:
            res.append(g.recv_key(key))

        return res


mailpile.plugins.register_commands(GPGKeySearch)
mailpile.plugins.register_commands(GPGKeyReceive)