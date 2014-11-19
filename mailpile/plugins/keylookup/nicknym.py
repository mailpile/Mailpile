#coding:utf-8

from mailpile.commands import Command
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.plugins import PluginManager
from mailpile.plugins.search import Search
from mailpile.mailutils import Email
# from mailpile.crypto.state import *
from mailpile.crypto.gpgi import GnuPG

import httplib
import re
import socket
import sys
import urllib
import urllib2
import ssl
import json

# TODO:
# * SSL certificate validation
# * Check nicknym server for a given host
# * Store provider keys on first discovery
# * Verify provider key signature


class Nicknym:
    def __init__(self, config):
        self.config = config

    def get_key(self, address, keytype="openpgp", server=None):
        """
        Request a key for address.
        """
        result, signature = self._nickserver_get_key(address, keytype, server)
        if self._verify_result(result, signature):
            return self._import_key(result, keytype)
        return False

    def refresh_keys(self):
        """
        Refresh all known keys.
        """
        for addr, keytype in self._get_managed_keys():
            result, signature = self._nickserver_get_key(addr, keytype)
            # TODO: Check whether it needs refreshing and is valid
            if self._verify_result(result, signature):
                self._import_key(result, keytype)

    def send_key(self, address, public_key, type):
        """
        Send a new key to the nickserver
        """
        # TODO: Unimplemented. There is currently no authentication mechanism
        #       defined in Nicknym standard
        raise NotImplementedError()


    def _parse_result(self, result):
        """Parse the result into a JSON blob and a signature"""
        # TODO: No signature implemented on server side yet.
        #       See https://leap.se/code/issues/5340
        return json.loads(result), ""

    def _nickserver_get_key(self, address, keytype="openpgp", server=None):
        if server == None: server = self._discover_server(address)

        data = urllib.urlencode({"address": address})
        with ConnBroker.context(need=[ConnBroker.OUTGOING_HTTP]):
            r = urllib2.urlopen(server, data)
        result = r.read()
        result, signature = self._parse_result(result)
        return result, signature

    def _import_key(self, result, keytype):
        if keytype == "openpgp":
            g = GnuPG(self.config)
            res = g.import_keys(result[keytype])
            if len(res["updated"]):
                self._managed_keys_add(result["address"], keytype)
            return res
        else:
            # We currently only support OpenPGP keys
            return False

    def _get_providerkey(self, domain):
        """
        Request a provider key for the appropriate domain.
        This is equivalent to get_key() with address=domain,
        except it should store the provider key in an 
        appropriate key store
        """
        pass

    def _verify_providerkey(self, domain):
        """
        ...
        """
        pass

    def _verify_result(self, result, signature):
        """
        Verify that the JSON result blob is correctly signed,
        and that the signature is from the correct provider key.
        """
        # No signature. See https://leap.se/code/issues/5340
        return True

    def _discover_server(self, address):
        """
        Automatically detect which nicknym server to query
        based on the address.
        """
        # TODO: Actually perform some form of lookup
        addr = address.split("@")
        addr.reverse()
        domain = addr[0]
        return "https://nicknym.%s:6425/" % domain

    def _audit_key(self, address, keytype, server):
        """
        Ask an alternative server for a key to verify that
        the same result is being provided.
        """
        result, signature = self._nickserver_get_key(address, keytype, server)
        if self._verify_result(result, signature):
            # TODO: verify that the result is acceptable
            pass
        return True

    def _managed_keys_add(self, address, keytype):
        try:
            data = self.config.load_pickle("nicknym.cache")
        except IOError:
            data = []
        data.append((address, keytype))
        data = list(set(data))
        self.config.save_pickle(data, "nicknym.cache")

    def _managed_keys_remove(self, address, keytype):
        try:
            data = self.config.load_pickle("nicknym.cache")
        except IOError:
            data = []
        data.remove((address, keytype))
        self.config.save_pickle(data, "nicknym.cache")

    def _get_managed_keys(self):
        try:
            return self.config.load_pickle("nicknym.cache")
        except IOError:
            return []


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


_plugins = PluginManager(builtin=__file__)
_plugins.register_commands(NicknymGetKey)
_plugins.register_commands(NicknymRefreshKeys)


if __name__ == "__main__":
    n = Nicknym()
    print n.get_key("varac@bitmask.net")
