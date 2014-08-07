from mailpile.i18n import gettext
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import (LookupHandler, 
    register_crypto_key_lookup_handler)
from mailpile.plugins.search import Search
from mailpile.mailutils import Email

import pgpdump

_ = lambda t: t


class EmailKeyLookupHandler(LookupHandler, Search):
    NAME = _("E-mail keys")
    PRIORITY = 5
    LOCAL = True

    def __init__(self, session, *args, **kwargs):
        LookupHandler.__init__(self, session, *args, **kwargs)
        Search.__init__(self, session)

    def _score(self, key):
        return (1, _('Found key in local e-mail'))

    def _lookup(self, address):
        results = {}
        terms = ["from:%s" % x for x in address.split('@')]
        terms.append("has:pgpkey")
        session, idx, _, _ = self._do_search(search=terms)
        for messageid in session.results:
            email = Email(self._idx(), messageid)
            attachments = email.get_message_tree("attachments")["attachments"]
            for part in attachments:
                if part["mimetype"] == "application/pgp-keys":
                    key = part["part"].get_payload(None, True)
                    results.update(self._get_keydata(key))

        return results

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
