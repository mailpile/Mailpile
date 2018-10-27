import math
import traceback
from mailpile.commands import Command
from mailpile.crypto.gpgi import GnuPG
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils.emails import ClearParseCache
from mailpile.plugins import PluginManager
from mailpile.plugins.vcard_gnupg import PGPKeysImportAsVCards
from mailpile.util import *
from mailpile.vcard import AddressInfo


__all__ = ['email_keylookup', 'nicknym', 'wkd']  # Disabled: dnspka

KEY_LOOKUP_HANDLERS = []


##[ Internal code, functions ]################################################

def register_crypto_key_lookup_handler(handler):
    if handler not in KEY_LOOKUP_HANDLERS:
        KEY_LOOKUP_HANDLERS.append(handler)
    KEY_LOOKUP_HANDLERS.sort(
        key=lambda h: (0 if h.LOCAL else 1, h.PRIORITY, -h.SCORE))


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


# FIXME: https://leap.se/en/docs/design/transitional-key-validation
#        ... provides a very structured ranking for keys coming from
#        different types of sources.  Check it!
def _update_scores(session, key_id, key_info, known_keys_list):
    """Update scores and score explanations"""

    # This is done here, potentially overriding the keychain lookup handler,
    # in case for some reason (e.g. UID changes on source keys) remote sources
    # suggest matches which our local search doesn't catch.
    if key_id in known_keys_list:
        score, reason = _score_validity(known_keys_list[key_id]["validity"],
                                        local=True)
        if score == 0:
            score = 9
            reason = _('Encryption key has been imported')

        key_info["on_keychain"] = True
        key_info['scores']['Known encryption keys'] = [score, reason]

    # FIXME: For this to work better, we need a list of signing subkeys.
    #        However, if a match is found then that counts, so we use it.
    if session:
        msgs = session.config.index.search(
            session, ['sig:' + key_id[-16:].lower()]).as_set()
        score = int(math.log(len(msgs) + 1, 2))
        if score:
            reason = _('Signature seen on %d messages') % len(msgs)
            key_info['scores']['Used to sign e-mail'] = [score, reason]

    if "keysize" in key_info:
        bits = int(key_info["keysize"])
        score = bits // 1024

        if bits >= 4096:
          key_strength = _('Encryption key is very strong')
        elif bits >= 3072:
          key_strength = _('Encryption key is strong')
        elif bits >= 2048:
          key_strength = _('Encryption key is good')
        else:
          key_strength = _('Encryption key is weak')

        key_info['scores']['Encryption key strength'] = [score, key_strength]

    key_info["score"] = sum([score for source, (score, reason)
                             in key_info.get('scores', {}).iteritems()])

    sc, reason = max([(abs(score), reason)
                     for score, reason in key_info['scores'].values()])
    key_info['score_reason'] = '%s' % reason

    log_score = math.log(3 * abs(key_info['score']), 3)
    key_info['score_stars'] = (max(1, min(int(round(log_score)), 5))
                               * (-1 if (key_info['score'] < 0) else 1))


def _normalize_key(session, key_info):
    """Make sure expected attributes are on all keys"""
    if not key_info.get("uids"):
        key_info["uids"] = [{"name": "", "email": "", "comment": ""}]
    if key_info.get("vcards") is None:
        key_info["vcards"] = {}
    for uid in key_info["uids"]:
        uid["name"] = uid.get("name", _('Anonymous'))
        uid["email"] = e = uid.get("email", '')
        uid["comment"] = uid.get("comment", '')
        if e and e not in key_info["vcards"]:
            vcard = session.config.vcards.get_vcard(e)
            if vcard:
                ai = AddressInfo(e, uid["name"], vcard=vcard)
                key_info["vcards"][e] = ai
    for key, default in [('on_keychain', False),
                         ('keysize', '0'),
                         ('keytype_name', 'unknown'),
                         ('created', '1970-01-01 00:00:00'),
                         ('fingerprint', 'FINGERPRINT_IS_MISSING'),
                         ('validity', '')]:
        if key not in key_info:
            key_info[key] = default


def lookup_crypto_keys(session, address,
                       event=None, strict_email_match=False, allowremote=True,
                       origins=None, get=None):
    known_keys_list = GnuPG(session and session.config or None).list_keys()
    found_keys = {}
    ordered_keys = []

    if origins:
        handlers = [h for h in KEY_LOOKUP_HANDLERS
                    if (h.NAME in origins) or (h.NAME.lower() in origins)]
    else:
        handlers = KEY_LOOKUP_HANDLERS

    ungotten = get and get[:] or []
    progress = [ ]

    for handler in handlers:
        if get and not ungotten:
            # We have all the keys!
            break

        try:
            h = handler(session, known_keys_list)
            if not allowremote and not h.LOCAL:
                continue

            if found_keys and (not h.PRIVACY_FRIENDLY) and (not origins):
                # We only try the privacy-hostile methods if we haven't
                # found any keys (unless origins were specified).
                if not ungotten:
                    continue

            progress.append(h.NAME)
            if event:
                ordered_keys.sort(key=lambda k: -k["score"])
                event.message = _('Searching for encryption keys in: %s'
                                  ) % _(h.NAME)
                event.private_data = {"result": ordered_keys,
                                      "progress": progress,
                                      "runningsearch": h.NAME}
                session.config.event_log.log_event(event)

            # We allow for more time when importing keys
            timeout = h.TIMEOUT
            if ungotten:
                timeout *= 4

            # h.lookup will remove found keys from the wanted list,
            # but we have to watch out for the effects of timeouts.
            wanted = ungotten[:]
            results = RunTimed(timeout, h.lookup, address,
                               strict_email_match=strict_email_match,
                               get=(wanted if (get is not None) else None))
            ungotten[:] = wanted
        except KeyboardInterrupt:
            raise
        except:
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
            _update_scores(session, key_id, found_keys[key_id], known_keys_list)
            _normalize_key(session, found_keys[key_id])

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
        'email': 'The address to find a encryption key for (strict)',
        'address': 'The nick or address to find a encryption key for (fuzzy)',
        'allowremote': 'Whether to permit remote key lookups (default=Yes)',
        'origins': 'Specify which origins to check (or * for all)'}

    def command(self):
        if len(self.args) > 1:
            allowremote = self.args.pop()
        else:
            allowremote = self.data.get('allowremote', ['Y'])[0]
            if allowremote.lower()[:1] in ('n', 'f'):
                allowremote = False

        origins = self.data.get('origins')
        if '*' in (origins or []):
            origins = [h.NAME for h in KEY_LOOKUP_HANDLERS]

        email = " ".join(self.data.get('email', []))
        address = " ".join(self.data.get('address', self.args))
        result = lookup_crypto_keys(self.session, email or address,
                                    strict_email_match=email,
                                    event=self.event,
                                    allowremote=allowremote,
                                    origins=origins)
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
        safe_assert(address or fprints or origins)

        result = lookup_crypto_keys(self.session, address,
                                    get=[f.strip() for f in fprints],
                                    origins=origins,
                                    event=self.event)

        if len(result) > 0:
            # Update the VCards!
            PGPKeysImportAsVCards(self.session,
                                  arg=[k['fingerprint'] for k in result]
                                  ).run()
            # Previous crypto evaluations may now be out of date, so we
            # clear the cache so users can see results right away.
            ClearParseCache(pgpmime=True)

        return self._success(_n('Imported %d encryption key',
                                'Imported %d encryption keys',
                                len(result)) % len(result),
                             result=result)


class KeyTofu(Command):
    """Import or refresh keys"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/keytofu', 'crypto/keytofu', '<emails>')
    HTTP_CALLABLE = ('POST',)
    HTTP_POST_VARS = {
        'email': 'E-mail addresses to find or update encryption keys for',
    }
    TOFU_ORIGINS = ['e-mail keys']
    TOFU_MIN_EMAILS = 3

    def _key_can_encrypt(self, gnupg, fingerprint):
        rc, data = gnupg.encrypt("hello", tokeys=[fingerprint])
        return (rc == 0)

    def _uses_crypto(self, idx, email):
        crypto = idx.search(self.session, ['from:' + email, 'has:crypto'])
        if len(crypto) < self.TOFU_MIN_EMAILS:
            return False
        recent = idx.search(self.session, ['from:' + email])
        recent = set(sorted(list(recent.as_set()))[-25:])
        crypto = crypto.as_set() & recent
        return (crypto >= self.TOFU_MIN_EMAILS)

    def _seen_enough_signatures(self, idx, email, keyinfo):
        fp = keyinfo['fingerprint'][-16:].lower()
        signed = idx.search(self.session, ['from:' + email, 'sig:' + fp])
        return (len(signed.as_set()) >= self.TOFU_MIN_EMAILS)

    def command(self):
        emails = set(list(self.args)) | set(self.data.get('email', []))
        if not emails:
            return self._success('Nothing Happened')

        idx = self._idx()
        gnupg = self._gnupg(dry_run=True)
        missing, old, status = [], {}, {}

        for email in emails:
            vc = self.session.config.vcards.get_vcard(email)
            fp = vc.pgp_key if vc else None
            if vc and fp:
                if self._key_can_encrypt(gnupg, fp):
                    old[email] = fp
                    status[email] = 'Key is already on our key-chain'
                else:
                    # FIXME: Should we remove the bad key from the vcard?
                    # FIXME: Should we blacklist the bad key?
                    missing.append(email)
                    status[email] = 'Obsolete key is on our key-chain'
            else:
                missing.append(email)
                status[email] = 'We have no key for this person'

        should_import = {}
        for email in missing:
            if self._uses_crypto(idx, email):
                keys = lookup_crypto_keys(self.session, email,
                                          origins=self.TOFU_ORIGINS,
                                          strict_email_match=True,
                                          event=self.event)
                for keyinfo in (keys or []):
                    if self._seen_enough_signatures(idx, email, keyinfo):
                        should_import[email] = keyinfo['fingerprint']
                        break
                if keys and 'email' not in should_import:
                    status[email] = 'Found keys, but none in active use'
            else:
                status[email] = 'Have not seen enough PGP messages'

        imported = {}
        for email, fingerprint in should_import.iteritems():
            keys = lookup_crypto_keys(
                self.session, email,
                get=[fingerprint],
                origins=self.TOFU_ORIGINS,
                strict_email_match=True,
                event=self.event)
            if keys:
                imported[email] = keys
                status[email] = 'Imported key!'
            else:
                status[email] = 'Failed to import key'

        for email in imported:
            if email in missing:
                missing.remove(email)

        if len(imported) > 0:
            # Update the VCards!
            fingerprints = []
            for keys in imported.values():
                fingerprints.extend([k['fingerprint'] for k in keys])
            PGPKeysImportAsVCards(self.session, arg=fingerprints).run()
            # Previous crypto evaluations may now be out of date, so we
            # clear the cache so users can see results right away.
            ClearParseCache(pgpmime=True)

        # i18n note: Not translating things here, since messages are not
        #            generally user-facing and we want to reduce load on
        #            our translators.
        return self._success('Evaluated key TOFU', result={
            'missing_keys': missing,
            'imported_keys': imported,
            'status': status,
            'on_keychain': old})


PluginManager(builtin=__file__).register_commands(
    KeyLookup, KeyImport, KeyTofu)


##[ Basic lookup handlers ]###################################################

class LookupHandler:
    NAME = "NONE"
    TIMEOUT = 2
    PRIORITY = 10000
    PRIVACY_FRIENDLY = False
    LOCAL = False
    SCORE = 0

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
        return (result and 0 < (len(result.get('imported', [])) +
                                len(result.get('updated', []))))

    def _lookup(self, address, strict_email_match=False):
        raise NotImplemented("Subclass and override _lookup")

    def lookup(self, address, strict_email_match=False, get=None):
        all_keys = self._lookup(address, strict_email_match=strict_email_match)
        keys = {}
        if get is not None:
            get = [unicode(g).upper() for g in get]
        for key_id, key_info in all_keys.iteritems():
            fprint = unicode(key_info.get('fingerprint', '')).upper()
            if (get is None) or (fprint and fprint in get):
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
                if get is not None:
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
    PRIVACY_FRIENDLY = True
    PRIORITY = 0
    SCORE = 8

    def _score(self, key):
        return (self.SCORE, _('Found encryption key in keychain'))

    def _getkey(self, key):
        return False  # Already on keychain

    def _lookup(self, address, strict_email_match):
        address = address.lower()
        results = {}
        for key_id, key_info in self.known_keys.iteritems():
            for uid in key_info.get('uids', []):
                if not strict_email_match:
                    match = (address in uid.get('name', '').lower() or
                             address in uid.get('email', '').lower())
                else:
                    match = (address == uid.get('email', '').lower())
                if match:
                    results[key_id] = {}
                    for k in ('created', 'fingerprint', 'keysize',
                              'key_name', 'uids'):
                        if k in key_info:
                            results[key_id][k] = key_info[k]
        return results


class KeyserverLookupHandler(LookupHandler):
    NAME = "PGP Keyservers"
    LOCAL = False
    TIMEOUT = 20  # We know these are slow...
    PRIVACY_FRIENDLY = False
    PRIORITY = 200
    SCORE = 1

    def _score(self, key):
        return (self.SCORE, _('Found encryption key in keyserver'))

    def _allowed_by_config(self):
        # FIXME: When direct keyserver contact works, change this.
        config = self.session.config
        return (
            config.sys.proxy.protocol in ('none', 'unknown', 'system')
            or config.sys.proxy.fallback)

    def _lookup(self, address, strict_email_match=False):
        # FIXME: We should probably just contact the keyservers directly.
        #
        # Queries look like this:
        #
        #    https://hkps.pool.sks-keyservers.net/pks/lookup?
        #        search=EMAIL&op=index&fingerprint=on&options=mr
        #
        if not self._allowed_by_config():
            return {}

        results = self._gnupg().search_key(address)
        if strict_email_match:
            for key in results.keys():
                match = [u for u in results[key].get('uids', [])
                         if u['email'].lower() == address]
                if not match:
                    del results[key]
        return results

    def _getkey(self, key):
        # FIXME: We should probably just contact the keyservers directly.
        #
        # Key downloads look like this:
        #
        #    https://hkps.pool.sks-keyservers.net/pks/lookup?
        #        search=0xFINGERPRINT&op=get&options=mr
        #
        if not self._allowed_by_config():
            return {}
        return self._gnupg().recv_key(key['fingerprint'])


register_crypto_key_lookup_handler(KeychainLookupHandler)
register_crypto_key_lookup_handler(KeyserverLookupHandler)

# We do this down here, as that seems to make the Python module loader
# things happy enough with the circular dependencies...
from mailpile.plugins.keylookup.email_keylookup import EmailKeyLookupHandler
from mailpile.plugins.keylookup.wkd import WKDLookupHandler
# Disabled: from mailpile.plugins.keylookup.dnspka import DNSPKALookupHandler
