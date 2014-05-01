import datetime
import re
import time
from gettext import gettext as _

from mailpile.plugins import PluginManager
from mailpile.commands import Command
from mailpile.plugins.search import Search
from mailpile.mailutils import Email, MBX_ID_LEN

from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.nicknym import Nicknym


_plugins = PluginManager(builtin=__file__)


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
        args = list(self.args)
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

class GPGKeyImportFromMail(Search):
    """Import a GPG Key."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/importkeyfrommail', 
                'crypto/gpg/importkeyfrommail', '<mid>')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {'mid': 'Message ID'}

    class CommandResult(Command.CommandResult):
        def __init__(self, *args, **kwargs):
            Command.CommandResult.__init__(self, *args, **kwargs)

        def as_text(self):
            if self.result:
                return "Imported %d keys (%d updated, %d unchanged) from the mail" % (
                    self.result["results"]["count"],
                    self.result["results"]["imported"],
                    self.result["results"]["unchanged"])
            return ""

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)
        args.extend(["=%s" % x for x in self.data.get("mid", [])])
        eids = self._choose_messages(args)
        if len(eids) < 0:
            return self._error("No messages selected", None)
        elif len(eids) > 1:
            return self._error("One message at a time, please", None)

        email = Email(idx, list(eids)[0])
        fn, attr = email.extract_attachment(session, 'application/pgp-keys', 
            mode='inline')
        if attr and attr["data"]:
            g = GnuPG()
            res = g.import_keys(attr["data"])
            return self._success("Imported key", res)

        return self._error("No results found", None)

class NicknymGetKey(Command):
    """Get a key from a nickserver"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/nicknym/getkey', 'crypto/nicknym/getkey', 
        '<address> [<keytype>] [<server>]')

    HTTP_CALLABLE = ('POST',)
    HTTP_QUERY_VARS = {
        'address': 'The nick/address to fetch a key for',
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
    SYNOPSIS = (None, 'crypto/nicknym/refreshkeys', 
        'crypto/nicknym/refreshkeys', '')

    HTTP_CALLABLE = ('POST',)

    def command(self):
        n = Nicknym(self.session.config)
        n.refresh_keys()
        return True

_plugins.register_commands(GPGKeySearch)
_plugins.register_commands(GPGKeyReceive)
_plugins.register_commands(GPGKeyImport)
_plugins.register_commands(GPGKeyImportFromMail)
_plugins.register_commands(NicknymGetKey)
_plugins.register_commands(NicknymRefreshKeys)
