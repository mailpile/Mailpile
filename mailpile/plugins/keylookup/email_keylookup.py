import datetime
import time
import copy
from pgpdump.utils import PgpdumpException

from mailpile.crypto.autocrypt_utils import *
from mailpile.i18n import gettext
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import LookupHandler
from mailpile.plugins.keylookup import register_crypto_key_lookup_handler
from mailpile.plugins.search import Search
from mailpile.mailutils.emails import Email

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


def _get_keydata(data, include_subkeys=False):
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

    if include_subkeys:
        return results
    else:
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
            for key_info, raw_key in self._get_message_keys(messageid):
                if strict_email_match:
                    match = [u for u in key_info.get('uids', [])
                             if (u['email'] or '').lower() == address]
                    if not match:
                        continue
                fp = key_info["fingerprint"]
                results[fp] = copy.copy(key_info)
                self.key_cache[fp] = raw_key
            if len(results) > 5 or time.time() > deadline:
                break
        return results

    def _getkey(self, keydata):
        data = self.key_cache.get(keydata["fingerprint"])
        if data:
            return self._gnupg().import_keys(data)
        else:
            raise ValueError("Key not found")

    def _get_message_keys(self, messageid):
        keys = self.key_cache.get(messageid, [])
        if not keys:
            email = Email(self._idx(), messageid)

            # First we check the Autocrypt headers
            msg = email.get_msg(pgpmime='all')
            for ach in ([extract_autocrypt_header(msg)] +
                        extract_autocrypt_gossip_headers(msg)):
                if 'keydata' in ach:
                    for keydata in _get_keydata(ach['keydata']):
                        keys.append((keydata, ach['keydata']))

            # Then go looking at the attachments
            attachments = email.get_message_tree(want=["attachments"]
                                                 )["attachments"]
            for part in attachments:
                if len(keys) > 100:  # Just to set some limit...
                    break
                if _might_be_pgp_key(part["filename"], part["mimetype"]):
                    key = part["part"].get_payload(None, True)
                    for keydata in _get_keydata(key, include_subkeys=False):
                        keys.append((keydata, key))
            self.key_cache[messageid] = keys
        return keys


def get_pgp_key_keywords(key_data):
    kws = []
    data = _get_keydata(key_data, include_subkeys=True)
    if data:
        kws += ['pgpkey:has']
        for keydata in data:
            for uid in keydata.get('uids', []):
                if uid.get('email'):
                    kws.append('%s:pgpkey' % uid['email'].lower())
            fingerprint = keydata["fingerprint"].lower()
            kws.append('%s:pgpkey' % fingerprint)
            kws.append('%s:pgpkey' % fingerprint[-16:])
    return kws


def has_pgpkey_data_kw_extractor(index, msg, mimetype, filename, part, loader,
                                 body_info=None, **kwargs):
    kws = []
    if _might_be_pgp_key(filename, mimetype):
        new_kws = get_pgp_key_keywords(part.get_payload(None, True))
        if new_kws:
            body_info['pgp_key'] = filename
            kws += new_kws
    return kws


register_crypto_key_lookup_handler(EmailKeyLookupHandler)
_plugins.register_data_kw_extractor('pgpkey', has_pgpkey_data_kw_extractor)
_ = gettext
