import datetime
import re
import time

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.commands import Command
from mailpile.mailutils import Email, ClearParseCache
from mailpile.plugins import PluginManager
from mailpile.plugins.search import Search

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

        return self._gnupg().search_key(" ".join(args))


class GPGKeyReceive(Command):
    """Fetch a GPG Key."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/receivekey', 'crypto/gpg/receivekey', '<keyid>')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {'keyid': 'ID of key to fetch'}

    def command(self):
        keyid = self.data.get("keyid", self.args)
        res = []
        for key in keyid:
            res.append(self._gnupg().recv_key(key))

        # Previous crypto evaluations may now be out of date, so we
        # clear the cache so users can see results right away.
        ClearParseCache(pgpmime=True)

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
        rv = self._gnupg().import_keys(key_data)

        # Previous crypto evaluations may now be out of date, so we
        # clear the cache so users can see results right away.
        ClearParseCache(pgpmime=True)

        return rv


class GPGKeySign(Command):
    """Sign a key."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/signkey', 'crypto/gpg/signkey', '<keyid> [<signingkey>]')
    HTTP_CALLABLE = ('POST',)
    HTTP_QUERY_VARS = {'keyid': 'The key to sign',
                       'signingkey': 'The key to sign with'}

    def command(self):
        if self.session.config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))

        signingkey = None
        keyid = None
        args = list(self.args)
        try: keyid = args.pop(0)
        except: keyid = self.data.get("keyid", None)
        try: signingkey = args.pop(0)
        except: signingkey = self.data.get("signingkey", None)

        print keyid
        if not keyid:
            return self._error("You must supply a keyid", None)
        rv = self._gnupg().sign_key(keyid, signingkey)

        # Previous crypto evaluations may now be out of date, so we
        # clear the cache so users can see results right away.
        ClearParseCache(pgpmime=True)

        return rv


class GPGKeyImportFromMail(Search):
    """Import a GPG Key."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/importkeyfrommail', 
                'crypto/gpg/importkeyfrommail', '<mid>')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {'mid': 'Message ID', 'att': 'Attachment ID'}
    COMMAND_CACHE_TTL = 0

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
        if args and args[-1][0] == "#":
            attid = args.pop()
        else:
            attid = self.data.get("att", 'application/pgp-keys')
        args.extend(["=%s" % x for x in self.data.get("mid", [])])
        eids = self._choose_messages(args)
        if len(eids) < 0:
            return self._error("No messages selected", None)
        elif len(eids) > 1:
            return self._error("One message at a time, please", None)

        email = Email(idx, list(eids)[0])
        fn, attr = email.extract_attachment(session, attid, mode='inline')
        if attr and attr["data"]:
            res = self._gnupg().import_keys(attr["data"])

            # Previous crypto evaluations may now be out of date, so we
            # clear the cache so users can see results right away.
            ClearParseCache(pgpmime=True)

            return self._success("Imported key", res)

        return self._error("No results found", None)


class GPGKeyList(Command):
    """List GPG Keys."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/keylist', 
                'crypto/gpg/keylist', '<address>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {'address': 'E-mail address'}

    def command(self):
        args = list(self.args)
        if len(args) > 0:
            addr = args[0]
        else:
            addr = self.data.get("address", None)

        if addr is None:
            return self._error("Must supply e-mail address", None)

        res = self._gnupg().address_to_keys(addr)
        return self._success("Searched for keys for e-mail address", res)


class GPGKeyListSecret(Command):
    """List Secret GPG Keys"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/keylist/secret', 
                'crypto/gpg/keylist/secret', '<address>')
    HTTP_CALLABLE = ('GET', )

    def command(self):
        res = self._gnupg().list_secret_keys()
        return self._success("Searched for secret keys", res)


class GPGUsageStatistics(Search):
    """Get usage statistics from mail, given an address"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/gpg/statistics', 
                'crypto/gpg/statistics', '<address>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {'address': 'E-mail address'}
    COMMAND_CACHE_TTL = 0

    class CommandResult(Command.CommandResult):
        def __init__(self, *args, **kwargs):
            Command.CommandResult.__init__(self, *args, **kwargs)

        def as_text(self):
            if self.result:
                return "%d%% of e-mail from %s has PGP signatures (%d/%d)" % (
                    100*self.result["ratio"],
                    self.result["address"],
                    self.result["pgpsigned"],
                    self.result["messages"])
            return ""

    def command(self):
        args = list(self.args)
        if len(args) > 0:
            addr = args[0]
        else:
            addr = self.data.get("address", None)

        if addr is None:
            return self._error("Must supply an address", None)

        session, idx = self._do_search(search=["from:%s" % addr])
        total = 0
        for messageid in session.results:
            total += 1

        session, idx = self._do_search(search=["from:%s" % addr,  "has:pgp"])
        pgp = 0
        for messageid in session.results:
            pgp += 1

        if total > 0:
            ratio = float(pgp)/total
        else:
            ratio = 0

        res = {"messages": total, 
               "pgpsigned": pgp, 
               "ratio": ratio,
               "address": addr}

        return self._success("Got statistics for address", res)


_plugins.register_commands(GPGKeySearch)
_plugins.register_commands(GPGKeyReceive)
_plugins.register_commands(GPGKeyImport)
_plugins.register_commands(GPGKeyImportFromMail)
_plugins.register_commands(GPGKeySign)
_plugins.register_commands(GPGKeyList)
_plugins.register_commands(GPGUsageStatistics)
_plugins.register_commands(GPGKeyListSecret)
