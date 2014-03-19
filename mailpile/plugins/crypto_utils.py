import datetime
import re
import time
from gettext import gettext as _

import mailpile.plugins
from mailpile.commands import Command

from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.nicknym import Nicknym

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

class GPGKeyImport(Command):
    """Import a GPG Key."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/importkey', 'crypto/gpg/importkey',
                '<key_file>')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {'key_data': 'Contents of public key to be imported',
                       'key_file': 'Location of file containing the public key'}

    def command(self):
        key_data = ""
        if len(self.args) != 0:
            key_file = self.data.get("key_file", self.args[0])
            with  open(key_file) as file:
                key_data = file.read()
        if "key_data" in self.data:
            key_data = self.data.get("key_data")
        elif "key_file" in self.data:
            pass
        g = GnuPG()
        return g.import_keys(key_data)

class NicknymGetKey(Command):
    """Get a key from a nickserver"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/nicknym/getkey', 'crypto/nicknym/getkey', '<address> [<keytype>] [<server>]')

    HTTP_CALLABLE = ('POST',)
    HTTP_QUERY_VARS = {'address': 'The nick/address to fetch a key for',
                       'keytype': 'What type of key to import (defaults to OpenPGP)',
                       'server': 'The Nicknym server to use (defaults to autodetect)'}

    def command(self):
        address = self.data.get('address', self.args[0])
        keytype = self.data.get('keytype', None)
        server = self.data.get('server', None)
        if len(self.args) > 1:
            keytype = self.args[1]
        else:
            keytype = 'openpgp'

        if len(self.args) > 2:
            server = self.args[2]

        n = Nicknym(self.session.config)
        return n.get_key(address, keytype, server)

class NicknymRefreshKeys(Command):
    """Get a key from a nickserver"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/nicknym/refreshkeys', 'crypto/nicknym/refreshkeys', '')

    HTTP_CALLABLE = ('POST',)

    def command(self):
        n = Nicknym(self.config)
        n.refresh_keys()
        return True

mailpile.plugins.register_commands(GPGKeySearch)
mailpile.plugins.register_commands(GPGKeyReceive)
mailpile.plugins.register_commands(GPGKeyImport)
mailpile.plugins.register_commands(NicknymGetKey)
mailpile.plugins.register_commands(NicknymRefreshKeys)
