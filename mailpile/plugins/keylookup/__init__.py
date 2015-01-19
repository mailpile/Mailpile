import math
import traceback
from mailpile.commands import Command
from mailpile.crypto.gpgi import GnuPG
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils import ClearParseCache
from mailpile.plugins import PluginManager
from mailpile.util import *


__all__ = ['email_keylookup', 'nicknym', 'dnspka']

KEY_LOOKUP_HANDLERS = []


##[ Internal code, functions ]################################################

def register_crypto_key_lookup_handler(handler):
    if handler not in KEY_LOOKUP_HANDLERS:
        KEY_LOOKUP_HANDLERS.append(handler)
    KEY_LOOKUP_HANDLERS.sort(key=lambda h: (h.LOCAL and 0 or 1, h.PRIORITY))


def _score_validity(validity, local=False):
    if "r" in validity:
        return (-1000, _('Encryption key is revoked'))
    elif "d" in validity:
        return (-1000, _('Encryption key is disabled'))
    elif "e" in validity:
        return (-100, _('Encryption key has expired'))
    elif local and ("f" in validity or "u" in validity):
        return (50, _('Encryption key has been imported and verified'))
    return (0, '')


def _update_scores(key_id, key_info, known_keys_list):
    """Update scores and score explanations"""
    key_info["score"] = sum([score for source, (score, reason)
                             in key_info.get('scores', {}).iteritems()
                             if source != 'Known encryption keys'])

    # This is done here, not on the keychain lookup handler, in case
    # for some reason (e.g. UID changes on source keys) remote sources
    # suggest matches which our local search doesn't catch.
    if key_id in known_keys_list:
        score, reason = _score_validity(known_keys_list[key_id]["validity"],
                                        local=True)
        if score == 0:
            score += 9
            reason = _('Encryption key has been imported')

        key_info["on_keychain"] = True
        key_info['score'] += score
        key_info['scores']['Known encryption keys'] = [score, reason]

    if "keysize" in key_info:
        bits = int(key_info["keysize"])
        score = bits // 1024
        key_info['score'] += score

        if bits >= 4096: 
          key_strength = _('Encryption key is very strong')
        elif bits >= 3072: 
          key_strength = _('Encryption key is strong')
        elif bits >= 2048:
          key_strength = _('Encryption key is average')
        else: 
          key_strength = _('Encryption key is weak')

        key_info['scores']['Encryption key strength'] = [score, key_strength]

    sc, reason = max([(abs(score), reason)
                     for score, reason in key_info['scores'].values()])
    key_info['score_reason'] = '%s' % reason

    log_score = math.log(3 * abs(key_info['score']), 3)
    key_info['score_stars'] = (max(1, min(int(round(log_score)), 5))
                               * (-1 if (key_info['score'] < 0) else 1))


def _normalize_key(key_info):
    """Make sure expected attributes are on all keys"""
    if not key_info.get("uids"):
        key_info["uids"] = [{"name": "", "email": "", "comment": ""}]
    for uid in key_info["uids"]:
        uid["name"] = uid.get("name", _('Anonymous'))
        uid["email"] = uid.get("email", '')
        uid["comment"] = uid.get("comment", '')
    for key, default in [('on_keychain', False),
                         ('keysize', '0'),
                         ('keytype_name', 'unknown'),
                         ('created', '1970-01-01 00:00:00'),
                         ('fingerprint', 'FINGERPRINT_IS_MISSING'),
                         ('validity', '')]:
        if key not in key_info:
            key_info[key] = default


def lookup_crypto_keys(session, address,
                       event=None, allowremote=True, origins=None, get=None):
    known_keys_list = GnuPG(session and session.config or None).list_keys()
    found_keys = {}
    ordered_keys = []
    if origins:
        handlers = [h for h in KEY_LOOKUP_HANDLERS if h.NAME in origins]
    else:
        handlers = KEY_LOOKUP_HANDLERS
    ungotten = get and get[:] or []
    for handler in handlers:
        if get and not ungotten:
            # We have all the keys!
            break

        h = handler(session, known_keys_list)
        if not allowremote and not h.LOCAL:
            continue

        if event:
            ordered_keys.sort(key=lambda k: -k["score"])
            event.message = _('Searching for encryption keys in: %s') % _(h.NAME)
            event.private_data = {"result": ordered_keys,
                                  "runningsearch": h.NAME}
            session.config.event_log.log_event(event)

        try:
            # We allow for more time when importing keys
            timeout = h.TIMEOUT
            if ungotten:
                timeout *= 4

            # h.lookup will remove found keys from the wanted list,
            # but we have to watch out for the effects of timeouts.
            wanted = ungotten[:]
            results = RunTimed(timeout, h.lookup, address, get=wanted)
            ungotten[:] = wanted
        except (TimedOut, IOError, ValueError):
            if session.config.sys.debug:
                traceback.print_exc()
            results = {}

        for key_id, key_info in results.iteritems():
            if key_id in found_keys:
                old_scores = found_keys[key_id].get('scores', {})
                old_uids = found_keys[key_id].get('uids', [])[:]
                found_keys[key_id].update(key_info)
                if 'scores' in found_keys[key_id]:
                    found_keys[key_id]['scores'].update(old_scores)
                    # No need for an else, as old_scores will be empty

                # Merge in the old UIDs
                uid_emails = [u['email'] for u in key_info.get('uids', [])]
                if 'uids' not in found_keys[key_id]:
                    found_keys[key_id]['uids'] = []
                for uid in old_uids:
                    email = uid.get('email')
                    if email and email not in uid_emails:
                        found_keys[key_id]['uids'].append(uid)
            else:
                found_keys[key_id] = key_info
                found_keys[key_id]["origins"] = []
            found_keys[key_id]["origins"].append(h.NAME)
            _update_scores(key_id, found_keys[key_id], known_keys_list)
            _normalize_key(found_keys[key_id])

        # This updates and sorts ordered_keys in place. This will magically
        # also update the data on the viewable event, because Python.
        ordered_keys[:] = found_keys.values()
        ordered_keys.sort(key=lambda k: -k["score"])

    if event:
        event.private_data = {"result": ordered_keys, "runningsearch": False}
        session.config.event_log.log_event(event)
    return ordered_keys


##[ API endpoints / commands ]#################################################

class KeyLookup(Command):
    """Perform a key lookup"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/keylookup', 'crypto/keylookup',
        '<address> [<allowremote>]')
    HTTP_CALLABLE = ('GET',)
    HTTP_QUERY_VARS = {
        'address': 'The nick/address to find a encryption key for',
        'allowremote': 'Whether to permit remote key lookups (defaults to true)'
    }

    def command(self):
        if len(self.args) > 1:
            allowremote = self.args.pop()
        else:
            allowremote = self.data.get('allowremote', True)

        address = " ".join(self.data.get('address', self.args))
        result = lookup_crypto_keys(self.session, address, event=self.event,
                                    allowremote=allowremote)
        return self._success(_n('Found %d encryption key',
                                'Found %d encryption keys', 
                                len(result)) % len(result),
                             result=result)


class KeyImport(Command):
    """Import keys"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/keyimport', 'crypto/keyimport',
                      '<address> <fingerprint,...> <origins ...>')
    HTTP_CALLABLE = ('POST',)
    HTTP_POST_VARS = {
        'address': 'The nick/address to find an encryption key for',
        'fingerprints': 'List of fingerprints we want',
        'origins': 'List of origins to search'
    }

    def command(self):
        args = list(self.args)
        if args:
            address, fprints, origins = args[0], args[1].split(','), args[2:]
        else:
            address = self.data.get('address', [''])[0]
            fprints = self.data.get('fingerprints', [])
            origins = self.data.get('origins', [])
        assert(address or fprints or origins)

        result = lookup_crypto_keys(self.session, address,
                                    get=[f.strip() for f in fprints],
                                    origins=origins,
                                    event=self.event)
        if len(result) > 0:
            # Previous crypto evaluations may now be out of date, so we
            # clear the cache so users can see results right away.
            ClearParseCache(pgpmime=True)

        return self._success(_n('Imported %d encryption key',
                                'Imported %d encryption keys',
                                len(result)) % len(result),
                             result=result)


PluginManager(builtin=__file__).register_commands(KeyLookup, KeyImport)


##[ Basic lookup handlers ]###################################################

class LookupHandler:
    NAME = "NONE"
    TIMEOUT = 2
    PRIORITY = 10000
    LOCAL = False

    def __init__(self, session, known_keys_list):
        self.session = session
        self.known_keys = known_keys_list

    def _gnupg(self):
        return GnuPG(self.session and self.session.config or None)

    def _score(self, key):
        raise NotImplemented("Subclass and override _score")

    def _getkey(self, key):
        raise NotImplemented("Subclass and override _getkey")

    def _gk_succeeded(self, result):
        return 0 < (len(result.get('imported', [])) +
                    len(result.get('updated', [])))

    def _lookup(self, address):
        raise NotImplemented("Subclass and override _lookup")

    def lookup(self, address, get=None):
        all_keys = self._lookup(address)
        keys = {}
        for key_id, key_info in all_keys.iteritems():
            fprint = key_info.get('fingerprint', '')
            if (not get) or fprint in get:

                score, reason = self._score(key_info)
                if 'validity' in key_info:
                    vscore, vreason = _score_validity(key_info['validity'])
                    if abs(vscore) > abs(score):
                        reason = vreason
                    score += vscore

                key_info["score"] = score
                key_info['scores'] = {
                    self.NAME: [score, reason]
                }
                if get:
                    get.remove(fprint)
                    if self._gk_succeeded(self._getkey(key_info)):
                        keys[key_id] = key_info
                else:
                    keys[key_id] = key_info

        return keys

    def key_import(self, address):
        return True


class KeychainLookupHandler(LookupHandler):
    NAME = "GnuPG keychain"
    LOCAL = True
    PRIORITY = 0

    def _score(self, key):
        return (1, _('Found encryption key in keychain'))

    def _getkey(self, key):
        return False  # Already on keychain

    def _lookup(self, address):
        address = address.lower()
        results = {}
        for key_id, key_info in self.known_keys.iteritems():
            for uid in key_info.get('uids', []):
                if (address in uid.get('name', '').lower() or
                        address in uid.get('email', '').lower()):
                    results[key_id] = {}
                    for k in ('created', 'fingerprint', 'keysize',
                              'key_name', 'uids'):
                        if k in key_info:
                            results[key_id][k] = key_info[k]
        return results

    def _getkey(self, key):
        pass


class KeyserverLookupHandler(LookupHandler):
    NAME = "PGP Keyservers"
    LOCAL = False
    TIMEOUT = 20  # We know these are slow...
    PRIORITY = 200

    def _score(self, key):
        return (1, _('Found encryption key in keyserver'))

    def _lookup(self, address):
        return self._gnupg().search_key(address)

    def _getkey(self, key):
        return self._gnupg().recv_key(key['fingerprint'])


register_crypto_key_lookup_handler(KeychainLookupHandler)
register_crypto_key_lookup_handler(KeyserverLookupHandler)

# We do this down here, as that seems to make the Python module loader
# things happy enough with the circular dependencies...
from mailpile.plugins.keylookup.email_keylookup import EmailKeyLookupHandler
from mailpile.plugins.keylookup.dnspka import DNSPKALookupHandler
