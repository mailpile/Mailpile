from mailpile.crypto.gpgi import GnuPG
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import LookupHandler, register_crypto_key_lookup_handler
from mailpile.commands import Action

import pgpdump


class EmailKeyLookupHandler(LookupHandler):
    NAME = "E-mail keys"

    def _score(self, key):
        return 

    def _lookup(self, address):
        results = {}
        cmdres = Action(self.session, "search", ["from:%s" % address, "has:pgpkey"])
        print cmdres.as_dict()
        print "Found %d messages matching." % cmdres["result"]["stats"]["total"]
        for messageid in cmdres["result"]["thread_ids"]:
            email = Email(idx, list(eids)[0])
            for part in email.walk():
                if part.get_content_type == "application/pgp-keys":
                    results.update(self._get_keydata(part))

        return results

    def _get_keydata(self, part):
        data = part.get_payload()
        results = {}
        try:
            if "-----BEGIN" in data:
                ak = pgpdump.AsciiData(data)
            else:
                ak = pgpdump.BinaryData(data)
        except TypeError:
            return []

        curfp = None
        for m in ak.packets():
            if isinstance(m, pgpdump.packet.PublicKeyPacket):
                curfp = m.fingerprint
                results[curfp] = {
                    "fingerprint": m.fingerprint,
                    "expires": m.expiration_time,
                    "created": m.datetime,
                    "uids": [],
                }
            if isinstance(m, pgpdump.packet.UserIDPacket):
                results[curfp]["uids"].append({"name": m.user_name, "email": m.user_email})

        return results

register_crypto_key_lookup_handler(EmailKeyLookupHandler)

def has_pgpkey_data_kw_extractor(index, msg, mimetype, filename, part, loader):
    if mimetype == "application/pgp-keys":
        return ['pgpkey:has']
    return []

_plugins = PluginManager(builtin=__file__)
_plugins.register_data_kw_extractor('pgpkey', has_pgpkey_data_kw_extractor)
