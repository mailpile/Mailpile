import datetime
import time
import copy

from mailpile.crypto.autocrypt import *
from mailpile.crypto.keyinfo import get_keyinfo, MailpileKeyInfo
from mailpile.i18n import gettext
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import LookupHandler
from mailpile.plugins.keylookup import register_crypto_key_lookup_handler
from mailpile.plugins.search import Search
from mailpile.mailutils.emails import Email


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


class EmailKeyLookupHandler(LookupHandler, Search):
    NAME = _("E-mail keys")
    SHORTNAME = 'e-mail'
    PRIORITY = 5
    TIMEOUT = 25  # 5 seconds per message we are willing to parse
    LOCAL = True
    PRIVACY_FRIENDLY = True
    SCORE = 1

    def __init__(self, session, *args, **kwargs):
        LookupHandler.__init__(self, session, *args, **kwargs)
        Search.__init__(self, session)

        global GLOBAL_KEY_CACHE
        self.key_cache = GLOBAL_KEY_CACHE
        _PRUNE_GLOBAL_KEY_CACHE()

    def _score(self, key):
        return (self.SCORE, _('Found key in local e-mail'))

    def _lookup(self, address, strict_email_match=False):
        results = {}
        canon_address = canonicalize_email(address)
        terms = ['from:%s' % address, 'has:pgpkey', '+pgpkey:%s' % address]
        session, idx = self._do_search(search=terms)
        deadline = time.time() + (0.75 * self.TIMEOUT)
        for messageid in session.results[:5]:
            for key_info, raw_key in self._get_message_keys(
                    messageid, autocrypt=False, autocrypt_gossip=True):
                if strict_email_match:
                    match = [u for u in key_info.uids
                             if canonicalize_email(u.email) == canon_address]
                    if not match:
                        continue
                fp = key_info.fingerprint
                results[fp] = copy.copy(key_info)
                self.key_cache[fp] = raw_key
            if len(results) > 5 or time.time() > deadline:
                break
        return results

    def _getkey(self, email, keyinfo):
        data = self.key_cache.get(keyinfo.fingerprint)
        if data:
            if keyinfo.is_autocrypt and email:
                data = get_minimal_PGP_key(data, user_id=email, binary_out=True)[0]
            return self._gnupg().import_keys(data)
        else:
            raise ValueError("Key not found")

    def _get_message_keys(self, messageid,
                          autocrypt=True, autocrypt_gossip=True,
                          attachments=True):
        keys = self.key_cache.get(messageid, [])
        if not keys:
            email = Email(self._idx(), messageid)

            # First we check the Autocrypt headers
            loop_count = 0
            msg = email.get_msg(pgpmime='all')
            ac_headers = []
            if autocrypt:
                ac_headers.append(extract_autocrypt_header(msg))
            if autocrypt_gossip:
                ac_headers.extend(extract_autocrypt_gossip_headers(msg))
            for ach in ac_headers:
                loop_count += 1
                if 'keydata' in ach:
                    for keyinfo in get_keyinfo(ach['keydata'],
                                               autocrypt_header=ach,
                                               key_info_class=MailpileKeyInfo):
                        keyinfo.is_autocrypt = True
                        keyinfo.is_gossip = (loop_count > 1)
                        keys.append((keyinfo, ach['keydata']))

            # Then go looking at the attachments
            atts = []
            if attachments:
                atts.extend(email.get_message_tree(want=["attachments"]
                                                   )["attachments"])
            for part in atts:
                if len(keys) > 100:  # Just to set some limit...
                    break
                if _might_be_pgp_key(part["filename"], part["mimetype"]):
                    key = part["part"].get_payload(None, True)
                    for keyinfo in get_keyinfo(key,
                                               key_info_class=MailpileKeyInfo):
                        keys.append((keyinfo, key))
            self.key_cache[messageid] = keys
        return keys


def get_pgp_key_keywords(data):
    kws = []
    for keyinfo in get_keyinfo(data):
        for uid in keyinfo.uids:
            if uid.email:
                kws.append('%s:pgpkey' % uid.email.lower())
        fingerprint = keyinfo.fingerprint.lower()
        kws.append('pgpkey:has')
        kws.append('%s:pgpkey' % fingerprint)
        kws.append('%s:pgpkey' % fingerprint[-16:])
        for sk in keyinfo.subkeys:
           kws.append('%s:pgpkey' % sk.fingerprint)
           kws.append('%s:pgpkey' % sk.fingerprint[-16:])
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
