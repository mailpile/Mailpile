import datetime
import time
import copy
from pgpdump.utils import PgpdumpException

from mailpile.i18n import gettext
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import LookupHandler
from mailpile.plugins.keylookup import register_crypto_key_lookup_handler
from mailpile.plugins.search import Search
from mailpile.mailutils import Email

import pgpdump


_ = lambda t: t
_plugins = PluginManager(builtin=__file__)


GLOBAL_KEY_CACHE = {}


def _PRUNE_GLOBAL_KEY_CACHE():
    global GLOBAL_KEY_CACHE
    for k in GLOBAL_KEY_CACHE.keys()[10:]:
        del GLOBAL_KEY_CACHE[k]


PGP_KEY_SUFFIXES = ('pub', 'asc', 'key', 'pgp')

def _might_be_pgp_key(filename, mimetype):
    filename = (filename or '').lower()
    return ((mimetype == "application/pgp-keys") or
            (filename.lower().split('.')[-1] in PGP_KEY_SUFFIXES and
             'encrypted' not in filename and
             'signature' not in filename))


def _get_creation_time(m):
    """Compatibility shim, for differing versions of pgpdump"""
    try:
        return m.creation_time
    except AttributeError:
        try:
            return m.datetime
        except AttributeError:
            return datetime.datetime(1970, 1, 1, 00, 00, 00)


def _get_keydata(data):
    results = []
    try:
        if "-----BEGIN" in data:
            ak = pgpdump.AsciiData(data)
        else:
            ak = pgpdump.BinaryData(data)
        packets = list(ak.packets())
    except (TypeError, IndexError, PgpdumpException):
        return []

    now = time.time()
    for m in packets:
        try:
            if isinstance(m, pgpdump.packet.PublicKeyPacket):
                size = str(int(1.024 *
                               round(len('%x' % (m.modulus or 0)) / 0.256)))
                validity = ('e'
                            if (0 < (int(m.expiration_time or 0)) < now)
                            else '')
                results.append({
                    "fingerprint": m.fingerprint,
                    "created": _get_creation_time(m),
                    "validity": validity,
                    "keytype_name": (m.pub_algorithm or '').split()[0],
                    "keysize": size,
                    "uids": [],
                })
            if isinstance(m, pgpdump.packet.UserIDPacket) and results:
                # FIXME: This used to happen with results=[], does that imply
                #        UIDs sometimes come before the PublicKeyPacket?
                results[-1]["uids"].append({"name": m.user_name,
                                            "email": m.user_email})
        except (TypeError, AttributeError, KeyError, IndexError, NameError):
            import traceback
            traceback.print_exc()

    # This will only return keys that have UIDs
    return [k for k in results if k['uids']]


class EmailKeyLookupHandler(LookupHandler, Search):
    NAME = _("E-mail keys")
    PRIORITY = 5
    TIMEOUT = 25  # 5 seconds per message we are willing to parse
    LOCAL = True

    def __init__(self, session, *args, **kwargs):
        LookupHandler.__init__(self, session, *args, **kwargs)
        Search.__init__(self, session)

        global GLOBAL_KEY_CACHE
        self.key_cache = GLOBAL_KEY_CACHE
        _PRUNE_GLOBAL_KEY_CACHE()

    def _score(self, key):
        return (1, _('Found key in local e-mail'))

    def _lookup(self, address, strict_email_match=False):
        results = {}
        address = address.lower()
        terms = ['from:%s' % address, 'has:pgpkey', '+pgpkey:%s' % address]
        session, idx = self._do_search(search=terms)
        deadline = time.time() + (0.75 * self.TIMEOUT)
        for messageid in session.results[:5]:
            for key_data in self._get_keys(messageid):
                if strict_email_match:
                    match = [u for u in key_data.get('uids', [])
                             if (u['email'] or '').lower() == address]
                    if not match:
                        continue
                results[key_data["fingerprint"]] = copy.copy(key_data)
            if len(results) > 5 or time.time() > deadline:
                break
        return results

    def _getkey(self, keydata):
        data = self.key_cache.get(keydata["fingerprint"])
        if data:
            return self._gnupg().import_keys(data)
        else:
            raise ValueError("Key not found")

    def _get_keys(self, messageid):
        keys = self.key_cache.get(messageid, [])
        if not keys:
            email = Email(self._idx(), messageid)
            attachments = email.get_message_tree(want=["attachments"]
                                                 )["attachments"]
            for part in attachments:
                if _might_be_pgp_key(part["filename"], part["mimetype"]):
                    key = part["part"].get_payload(None, True)
                    for keydata in _get_keydata(key):
                        keys.append(keydata)
                        self.key_cache[keydata["fingerprint"]] = key
                    if len(keys) > 5:  # Just to set some limit...
                        break
            self.key_cache[messageid] = keys
        return keys


def has_pgpkey_data_kw_extractor(index, msg, mimetype, filename, part, loader,
                                 body_info=None, **kwargs):
    kws = []
    if _might_be_pgp_key(filename, mimetype):
        data = _get_keydata(part.get_payload(None, True))
        for keydata in data:
            for uid in keydata.get('uids', []):
                if uid.get('email'):
                    kws.append('%s:pgpkey' % uid['email'].lower())
        if data:
            body_info['pgp_key'] = filename
            kws += ['pgpkey:has']

    # FIXME: If this is a PGP key, make all the key IDs searchable so
    #        we can find this file again later! Searching by e-mail is lame.
    #        This is issue #655 ?

    return kws


register_crypto_key_lookup_handler(EmailKeyLookupHandler)
_plugins.register_data_kw_extractor('pgpkey', has_pgpkey_data_kw_extractor)
_ = gettext
