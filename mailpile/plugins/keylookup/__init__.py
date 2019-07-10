import copy
import math
import traceback
import ssl
import urllib
import urllib2
from mailpile.commands import Command
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.crypto import gpgi
from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.keyinfo import KeyUID, MailpileKeyInfo
from mailpile.crypto.autocrypt import get_minimal_PGP_key
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils.emails import ClearParseCache
from mailpile.plugins import PluginManager
from mailpile.plugins.vcard_gnupg import PGPKeysImportAsVCards
from mailpile.security import secure_urlget
from mailpile.util import *
from mailpile.vcard import AddressInfo, VCardLine, MailpileVCard


__all__ = ['email_keylookup', 'wkd']

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

        if score > 0 and key_info.is_pinned:
            score = 99
            reason = _('Encryption key has been imported and pinned')

        key_info.on_keychain = True
        key_info.scores['Known encryption keys'] = [score, reason]

    # FIXME: For this to work better, we need a list of signing subkeys.
    #        However, if a match is found then that counts, so we use it.
    if session:
        msgs = session.config.index.search(
            session, ['sig:' + key_id[-16:].lower()]).as_set()
        score = int(math.log(len(msgs) + 1, 2))
        if score:
            reason = _('Signature seen on %d messages') % len(msgs)
            key_info.scores['Used to sign e-mail'] = [score, reason]

    if key_info.keysize:
        bits = int(key_info.keysize)

        if key_info.keytype_name.startswith('Ed'):
            score = 4
        else:
            score = bits // 1024

        if score >= 4:
          key_strength = _('Encryption key is very strong')
        elif score >= 3:
          key_strength = _('Encryption key is strong')
        elif score >= 2:
          key_strength = _('Encryption key is strong enough')
        else:
          key_strength = _('Encryption key is weak')

        key_info.scores['Encryption key strength'] = [score, key_strength]

    key_info.score = sum(score for source, (score, reason)
                         in key_info.scores.iteritems())

    sc, reason = max([(abs(score), reason)
                     for score, reason in key_info['scores'].values()])
    key_info.score_reason = '%s' % reason

    log_score = math.log(3 * abs(key_info.score), 3)
    key_info.score_stars = (max(1, min(int(round(log_score)), 5))
                            * (-1 if (key_info['score'] < 0) else 1))


def _normalize_key(session, key_info):
    """Make sure expected attributes are on all keys"""
    if not key_info.uids:
        key_info.uids.append(KeyUID())
    for uid in key_info.uids:
        uid.name = uid.name or _('Anonymous')
        e = uid.email
        if e and e not in key_info.vcards:
            vcard = session.config.vcards.get_vcard(e)
            if vcard:
                ai = AddressInfo(e, uid.name, vcard=vcard)
                key_info.vcards[e] = ai
                if vcard.pgp_key == key_info.fingerprint:
                    key_info.is_preferred = True
                    if vcard.pgp_key_pinned:
                        key_info.is_pinned = True
    key_info.origins = list(set(key_info.origins))
    if not key_info.is_pinned:
        key_info.is_pinned = False
    if not key_info.is_preferred:
        key_info.is_preferred = False
    if not key_info.is_autocrypt:
        key_info.is_autocrypt = False


def _mailpile_key_list(gpgi_key_list):
    result = {}
    for info in gpgi_key_list.values():
        mki = MailpileKeyInfo.FromGPGI(info)
        result[mki.summary()] = mki
    return result


def lookup_crypto_keys(session, address,
                       event=None, strict_email_match=False, allowremote=True,
                       origins=None, get=None, vcard=None, only_good=False,
                       pin_key=False):
    found_keys = {}
    ordered_keys = []
    known_keys_list = _mailpile_key_list(
        GnuPG(session and session.config or None).list_keys())

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

        # FIXME: This merging of info about keys is probably misguided.
        for key_id, key_info in results.iteritems():
            if key_id in found_keys:
                old_scores = found_keys[key_id].scores
                old_uids = found_keys[key_id].uids
                found_keys[key_id].update(key_info)
                found_keys[key_id].scores.update(old_scores)

                # Merge in the old UIDs
                uid_emails = [u.email for u in key_info.uids]
                for uid in old_uids:
                    email = uid.email
                    if email and email not in uid_emails:
                        found_keys[key_id].uids.append(uid)
            else:
                found_keys[key_id] = key_info
            found_keys[key_id].origins.append(h.NAME)

        for key_id in found_keys.keys():
            _normalize_key(session, found_keys[key_id])
            _update_scores(session, key_id, found_keys[key_id], known_keys_list)

        # This updates and sorts ordered_keys in place. This will magically
        # also update the data on the viewable event, because Python.
        ordered_keys[:] = found_keys.values()
        ordered_keys.sort(key=lambda k: -k.score)

    if only_good:
        ordered_keys = [k for k in ordered_keys if k.score > 0]

    if get and vcard and ordered_keys:
        vcard.pgp_key = ordered_keys[0].fingerprint
        vcard.pgp_key_pinned = 'true' if pin_key else 'false'
        vcard.save()
        ordered_keys[0].is_preferred = True
        ordered_keys[0].is_pinned = pin_key
        for k in ordered_keys[1:]:
            k.is_preferred = k.is_pinned = False

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
        args = list(self.args)

        if len(args) > 1:
            allowremote = args.pop()
        else:
            allowremote = self.data.get('allowremote', ['Y'])[0]
        if allowremote.lower()[:1] in ('n', 'f'):
            allowremote = False

        origins = self.data.get('origins')
        if '*' in (origins or []):
            origins = [h.NAME for h in KEY_LOOKUP_HANDLERS]

        email = " ".join(self.data.get('email', []))
        address = " ".join(self.data.get('address', args))
        result = dict((k.summary(), k) for k in 
            lookup_crypto_keys(self.session, email or address,
                               strict_email_match=email,
                               event=self.event,
                               allowremote=allowremote,
                               origins=origins))

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
        'pinned': 'Pin this key?',
        'fingerprints': 'List of required fingerprints or key summary strings',
        'origins': 'List of origins to search'
    }

    def _get_or_create_vcard(self, address):
        vcard = self.session.config.vcards.get_vcard(address)
        if not vcard:
            vcard = MailpileVCard(
                VCardLine(name='email', value=address, type='pref'),
                VCardLine(name='kind', value='individual'),
                config=self.session.config)
            self.session.config.vcards.add_vcards(vcard)
        return vcard

    def command(self):
        args = list(self.args)
        if args:
            pin_key = False
            address, fprints, origins = args[0], args[1].split(','), args[2:]
        else:
            pin_key = self.data.get('pinned', [''])[0].lower()[:1] in ('y', 't')
            address = self.data.get('address', [''])[0]
            fprints = self.data.get('fingerprints', [])
            origins = self.data.get('origins', [])
        safe_assert(address or fprints or origins)

        result = lookup_crypto_keys(
            self.session, address,
            get=[f.strip() for f in fprints],
            pin_key=pin_key,
            vcard=self._get_or_create_vcard(address),
            origins=origins,
            event=self.event)

        if len(result) > 0:
            # Update the VCards!
            PGPKeysImportAsVCards(self.session,
                                  arg=[k['fingerprint'] for k in result]
                                  ).run()
                                  
            # The key was looked up based on the given address, so it must have
            # a user id containing that address, so when it is imported to
            # VCards, the VCard for that address will list the key.
            # The 'in_vcards' attribute is relevant to the given address only.
            for k in result:
                k['in_vcards'] = True
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
    TOFU_AUTOCRYPT_ORIGINS = ['e-mail keys']
    TOFU_OPENPGP_ORIGINS = ['e-mail keys', 'wkd']

    TOFU_AUTOCRYPT = 'autocrypt'
    TOFU_OPENPGP = 'openpgp'
    TOFU_MIN_EMAILS = 3
    TOFU_RECENT_EMAILS = 25

    def _key_can_encrypt(self, gnupg, fingerprint):
        rc, data = gnupg.encrypt("hello", tokeys=[fingerprint])
        return (rc == 0)

    def _uses_crypto(self, idx, email):
        session = self.session

        # FIXME: First, check the Autocrypt state DB.

        # No result? Ask the search-engine.
        threshold, emails = self.TOFU_MIN_EMAILS, self.TOFU_RECENT_EMAILS
        crypto = idx.search(session, ['from:' + email, 'has:crypto']).as_set()

        # We are confident a user is "using crypto" iff:
        #   1) their most recent e-mail had signs of crypto
        #   2) the were N crypto messages in their last M mails
        recent = sorted(list(idx.search(session, ['from:' + email]).as_set()))
        last1 = set(recent[-1:]) & crypto
        crypto &= set(recent[-emails:])
        return (
            self.TOFU_OPENPGP,
            self.TOFU_OPENPGP_ORIGINS,
            (last1 and len(crypto) >= threshold))

    def _seen_enough_signatures(self, idx, email, keyinfo):
        fp = keyinfo.fingerprint[-16:].lower()
        signed = idx.search(self.session, ['from:' + email, 'sig:' + fp])
        return (len(signed.as_set()) >= self.TOFU_MIN_EMAILS)

    def _seen_in_autocrypt(self, idx, email, keyinfo):
        fp = keyinfo.fingerprint.lower()
        has_ac = idx.search(
            self.session, ['from:' + email, 'has:autocrypt', 'pgpkey:' + fp])
        return (len(has_ac.as_set()) >= self.TOFU_MIN_AUTOCRYPT)

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
                if vc.pgp_key_pinned:
                    old[email] = fp
                    status[email] = 'Key is pinned'
                elif self._key_can_encrypt(gnupg, fp):
                    #
                    # FIXME: Autocrypt may want us to replace this key, even
                    #        if it's still usable...
                    #
                    old[email] = fp
                    status[email] = 'Key is already on our key-chain'
                else:
                    # FIXME: Should we remove the bad key from the vcard?
                    # FIXME: Should we blacklist the bad key?
                    # FIXME: Should this trigger a notification, per. #1869?
                    missing.append(email)
                    status[email] = 'Obsolete key is on our key-chain'
            else:
                missing.append(email)
                status[email] = 'We have no key for this person'

        should_import = {}
        for email in missing:
            crypto_type, origins, count = self._uses_crypto(idx, email)
            if count:
                keys = lookup_crypto_keys(self.session, email,
                                          origins=origins,
                                          strict_email_match=True,
                                          event=self.event,
                                          only_good=True)
                for keyinfo in (keys or []):
                    if crypto_type == self.TOFU_AUTOCRYPT:
                        if self._seen_in_autocrypt(idx, email, keyinfo):
                            should_import[email] = (keyinfo['fingerprint'],
                                                    origins)
                            break
                    if self._seen_enough_signatures(idx, email, keyinfo):
                        should_import[email] = (keyinfo['fingerprint'],
                                                origins)
                        break
                if keys and 'email' not in should_import:
                    status[email] = 'Found keys, but none in active use'
            else:
                status[email] = 'Have not seen enough PGP messages'

        imported = {}
        for email, (fingerprint, origins) in should_import.iteritems():
            keys = lookup_crypto_keys(
                self.session, email,
                get=[fingerprint],
                vcard=self.session.config.vcards.get_vcard(email),
                origins=origins,
                strict_email_match=True,
                event=self.event)
            if keys:
                # FIXME: This should trigger a notification, per. #1869
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

    def _getkey(self, email, key):
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
            fprint = unicode(key_info.fingerprint).upper()
            summary = key_info.summary()
            if (get is None) or (fprint and fprint in get) or (summary in get):
                score, reason = self._score(key_info)
                vscore, vreason = _score_validity(key_info['validity'])
                if abs(vscore) > abs(score):
                    reason = vreason
                score += vscore

                key_info.score = score
                key_info.scores = {
                    self.NAME: [score, reason]}

                if get is not None:
                    if fprint in get: get.remove(fprint)
                    if summary in get: get.remove(summary)
                    if self._gk_succeeded(self._getkey(address, key_info)):
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

    def _lookup(self, address, strict_email_match):
        address = address.lower()
        results = {}
        vcard = self.session.config.vcards.get_vcard(address)
        for key_id, key_info in self.known_keys.iteritems():
            match = False
            for uid in key_info.uids:
                if not strict_email_match:
                    match = (address in uid.name.lower() or
                             address in uid.email.lower())
                else:
                    match = (address == uid.email.lower())
                if match:
                    results[key_id] = key_info
                    break
            if vcard and (vcard.pgp_key == key_info.fingerprint) and not match:
                key_info.uids.append(
                    KeyUID(email=address, name=vcard.fn, comment='Mailpile'))
                results[key_id] = key_info
        return results

    def _getkey(self, email, key):
        # Returns dict like those returned by KeyserverLookupHandler._getkey()
        # and EmailKeyLookupHandler._getkey(). Even though the key is already
        # on the keychain, this is needed so KeyImport will create VCard(s)
        # from the key to indicate that it can be used for encrypting.

        if key['fingerprint'] in self.known_keys:
            return {'updated':[{'fingerprint':key['fingerprint']}]}
        else:
            return {}


class KeyserverLookupHandler(LookupHandler):
    NAME = "PGP Keyservers"
    LOCAL = False
    TIMEOUT = 30  # We know these are slow...
    PRIVACY_FRIENDLY = False
    PRIORITY = 200
    SCORE = 1

    # People with really big keys are just going to have to publish in WKD
    # or something, unless or until the SKS keyservers get fixed somehow.
    MAX_KEY_SIZE = 1500000

    # During testing, there were frequent HTTP gateway errors returned from
    # hkps.pool.sks-keyservers.net so sks-keyservers.net was added too.
    KEY_SERVER_BASE_URLS = [
        "https://sks-keyservers.net/pks/lookup",
        "https://hkps.pool.sks-keyservers.net/pks/lookup"]

    def _score(self, key):
        return (self.SCORE, _('Found encryption key in keyserver'))

    def _lookup_url(self, url_base, address):
        return "{}?{}".format(url_base, urllib.urlencode({
            "search": address,
            "op": "index",
            "fingerprint": "on",
            "options": "mr"}))

    def _lookup(self, address, strict_email_match=False):
        error = None
        for url_base in self.KEY_SERVER_BASE_URLS:
            url = self._lookup_url(url_base, address)
            if 'keylookup' in self.session.config.sys.debug:
                self.session.ui.debug('[%s] Fetching: %s' % (self.NAME, url))
            try:
                raw_result = secure_urlget(self.session, url,
                                           maxbytes=self.MAX_KEY_SIZE+1)
                error = None
                break
            except urllib2.HTTPError as e:
                error = str(e)
                if e.code == 404:
                    # If a server reports the key was not found, let's stop
                    # because the servers are supposed to be in sync.
                    break;
            except (IOError, urllib2.URLError, ssl.SSLError, ssl.CertificateError) as e:
                error = str(e)

        if not error and len(raw_result) > self.MAX_KEY_SIZE:
            error = "Response too big (>%d bytes), ignoring" % self.MAX_KEY_SIZE
            if 'keyservers' in self.session.config.sys.debug:
                self.session.ui.debug('[%s] %s' % (self.NAME, error))

        if error:
            if 'keylookup' in self.session.config.sys.debug:
                self.session.ui.debug('Error: %s' % error)
            if 'Error 404' in error:
                return {}
            raise ValueError(error)

        if 'keylookup' in self.session.config.sys.debug:
            self.session.ui.debug('[%s] DATA: %s' % (self.NAME, raw_result[:200]))
        results = _mailpile_key_list(
            self._gnupg().parse_hpk_response(raw_result.split('\n')))

        if strict_email_match:
            for key in results.keys():
                match = [u for u in results[key].uids
                         if u.email.lower() == address]
                if not match:
                    if 'keylookup' in self.session.config.sys.debug:
                        self.session.ui.debug('[%s] No UID for %s, ignoring key'
                                              % (self.NAME, address))
                    del results[key]

        if 'keylookup' in self.session.config.sys.debug:
            self.session.ui.debug('[%s] Results=%d' % (self.NAME, len(results)))

        return results

    def _getkey_url(self, url_base, email, key):
        fingerprint = '0x{}'.format(key['fingerprint'])
        params = {"search": fingerprint, "op": "get", "options": "mr"}
        return "{}?{}".format(url_base, urllib.urlencode(params))

    def _getkey(self, email, key):
        error = None
        for url_base in self.KEY_SERVER_BASE_URLS:
            url = self._getkey_url(url_base, email, key)
            if 'keylookup' in self.session.config.sys.debug:
                self.session.ui.debug('Fetching: %s' % url)
            try:
                key_data = secure_urlget(self.session, url,
                                         maxbytes=self.MAX_KEY_SIZE+1)
                error = None
                break
            except urllib2.HTTPError as e:
                error = e
                if e.code == 404:
                    # If a server reports the key was not found, let's stop
                    # because the servers are supposed to be in sync.
                    break;
            except (IOError, urllib2.URLError, ssl.SSLError, ssl.CertificateError) as e:
                error = e

        if len(key_data) > self.MAX_KEY_SIZE and not error:
            error = "Key too big (>%d bytes), ignoring" % self.MAX_KEY_SIZE
            if 'keylookup' in self.session.config.sys.debug:
                self.session.ui.debug(error)

        if error:
            raise ValueError(str(error))

        return self._gnupg().import_keys(key_data)


class VerifyingKeyserverLookupHandler(KeyserverLookupHandler):
    NAME = "keys.OpenPGP.org"
    PRIVACY_FRIENDLY = False
    LOCAL = False
    TIMEOUT = 15
    PRIORITY = 75  # Better than SKS keyservers and better than DNS
    SCORE = 5      # Treat these as valid as WKD, yay e-mail vetting!

    KEY_SERVER_BASE_URLS = [
        "http://zkaan2xfbuxia2wpf7ofnkbz6r5zdbbvxbunvp5g2iebopbfc4iqmbad.onion/pks/lookup",
        "https://keys.openpgp.org/pks/lookup"]

    def _lookup_url(self, url_base, address):
        # This deliberately avoids any escaping of the e-mail address; k.o.o.
        # can't handle such things at the moment.
        return "{}?op=index&options=mr&search={}".format(url_base, address)

    def _score(self, key):
        return (self.SCORE, _('Found encryption key in keys.OpenPGP.org'))


register_crypto_key_lookup_handler(KeychainLookupHandler)
register_crypto_key_lookup_handler(KeyserverLookupHandler)
register_crypto_key_lookup_handler(VerifyingKeyserverLookupHandler)

# We do this down here, as that seems to make the Python module loader
# things happy enough with the circular dependencies...
from mailpile.plugins.keylookup.email_keylookup import EmailKeyLookupHandler
from mailpile.plugins.keylookup.wkd import WKDLookupHandler
# Disabled: from mailpile.plugins.keylookup.dnspka import DNSPKALookupHandler
