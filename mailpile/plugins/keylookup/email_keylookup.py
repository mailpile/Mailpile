import time

from mailpile.i18n import gettext
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import (LookupHandler, 
    register_crypto_key_lookup_handler)
from mailpile.plugins.search import Search
from mailpile.mailutils import Email

import pgpdump


_ = lambda t: t
GLOBAL_KEY_CACHE = {}


class EmailKeyLookupHandler(LookupHandler, Search):
    NAME = _("E-mail keys")
    PRIORITY = 5
    TIMEOUT = 25  # 5 seconds per message we are willing to parse
    LOCAL = True

    def __init__(self, session, *args, **kwargs):
        LookupHandler.__init__(self, session, *args, **kwargs)
        Search.__init__(self, session)

    def _score(self, key):
        return (1, _('Found key in local e-mail'))

    def _lookup(self, address):
        results = {}
        terms = ['from:%s' % address, 'has:pgpkey']
        session, idx, _, _ = self._do_search(search=terms)
        deadline = time.time() + (0.75 * self.TIMEOUT)
        for messageid in session.results[:5]:
            for key in self._get_keys(messageid):
                results.update(self._get_keydata(key))
            if len(results) > 5 or time.time() > deadline:
                break
        return results

    def _get_keys(self, messageid):
        global GLOBAL_KEY_CACHE
        if len(GLOBAL_KEY_CACHE) > 50:
            GLOBAL_KEY_CACHE = {}

        keys = GLOBAL_KEY_CACHE.get(messageid, [])
        if not keys:
            email = Email(self._idx(), messageid)
            attachments = email.get_message_tree("attachments")["attachments"]
            for part in attachments:
                if part["mimetype"] == "application/pgp-keys":
                    keys.append(part["part"].get_payload(None, True))
                    if len(keys) > 5:  # Just to set some limit...
                        break
            GLOBAL_KEY_CACHE[messageid] = keys
        return keys

    def _get_keydata(self, data):
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
                results[curfp]["uids"].append({"name": m.user_name, 
                    "email": m.user_email})

        return results


register_crypto_key_lookup_handler(EmailKeyLookupHandler)

def has_pgpkey_data_kw_extractor(index, msg, mimetype, filename, part, loader):
    if mimetype == "application/pgp-keys":
        return ['pgpkey:has']
    return []

_plugins = PluginManager(builtin=__file__)
_plugins.register_data_kw_extractor('pgpkey', has_pgpkey_data_kw_extractor)
_ = gettext
