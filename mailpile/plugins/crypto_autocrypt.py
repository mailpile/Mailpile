# This file contains Autocrypt application logic: state database,
# persistance, integration with Mailpile itself.
#
# Lower level code lives in mailpile.crypto.autocrypt, and some logic
# has also leaked into mailpile.crypto.gpgi and mailpile.crypto.mime.
#
"""
Usage examples and doctests for internal logic:

>>> import time
>>> state_db = {}
>>> cfg = None
>>> email = 'bre@mailpile.is'

# Seed our fake state DB with some data, verify it's sane.
>>> acr = AutocryptRecord(email, key_sig='123', prefer_encrypt='mutual')
>>> (time.time() - acr.last_seen_ts) // 10
0.0
>>> (time.time() - acr.autocrypt_ts) // 10
0.0
>>> acr.float_ratio()  # Ratio of messages with Autocrypt?
1.0
>>> acr.save_to(state_db) is not None
True
>>> state_db[email][0]
'123'
>>> AutocryptRecord.Load(state_db, email).key_sig
'123'

# Unknown e-mails, give None as a recommendation.
>>> str(autocrypt_recommendation(cfg,'foo@example.org', state_db=state_db))
'None'

# If prefer-encrypt is Mutual, we usually recommend encrypting...
>>> str(autocrypt_recommendation(cfg, email, state_db=state_db))
'encrypt (key=123)'

# Recommendations change if we haven't seen any Autocrypt headers for
# over 35 days or if we no longer have a key.
>>> acr.autocrypt_ts -= (36 * 24 * 3600)
>>> acr.save_to(state_db) and None
>>> str(autocrypt_recommendation(cfg, email, state_db=state_db))
'discourage (key=123)'
>>> acr.key_sig = None
>>> acr.save_to(state_db) and None
>>> str(autocrypt_recommendation(cfg, email, state_db=state_db))
'disable'

"""
import base64
import copy
import datetime
import re
import time
import traceback
import urllib2
from email import encoders
from email.mime.base import MIMEBase

import mailpile.security as security
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.commands import Command
from mailpile.crypto.autocrypt import *
from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.gpgi import OpenPGPMimeSigningWrapper
from mailpile.crypto.gpgi import OpenPGPMimeEncryptingWrapper
from mailpile.crypto.gpgi import OpenPGPMimeSignEncryptWrapper
from mailpile.crypto.mime import UnwrapMimeCrypto, MessageAsString
from mailpile.crypto.state import EncryptionInfo, SignatureInfo
from mailpile.eventlog import GetThreadEvent
from mailpile.mailutils.emails import Email, ExtractEmails, ClearParseCache
from mailpile.mailutils.emails import MakeContentID
from mailpile.plugins import PluginManager, EmailTransform
from mailpile.plugins.crypto_policy import register_crypto_policy
from mailpile.plugins.vcard_gnupg import PGPKeysImportAsVCards
from mailpile.plugins.search import Search
from mailpile.plugins.keylookup import register_crypto_key_lookup_handler
from mailpile.plugins.keylookup.email_keylookup import get_pgp_key_keywords
from mailpile.plugins.keylookup.email_keylookup import EmailKeyLookupHandler
from mailpile.util import sha1b64


##[ The Autocrypt State Database logic ]#####################################

# FIXME: This really should be a record store, not an in-memory dict
def save_Autocrypt_DB(config):
    if config.autocrypt_db:
        config.save_pickle(config.autocrypt_db, 'autocrypt_db')


def get_Autocrypt_DB(config):
    if not config.real_hasattr('autocrypt_db'):
        try:
            db = config.load_pickle('autocrypt_db')
        except (IOError, EOFError):
            db = {'state': {}}
        config.real_setattr('autocrypt_db', db)
    return config.autocrypt_db


class AutocryptRecord(object):
    RATIO_MAX = 10000.0  # Force calculations to be floats
    RATIO_INIT = 10000
    RATIO_WINDOW = 100
    INIT_ORDER = ('key_sig', 'autocrypt_ts', 'prefer_encrypt',
                  'key_count', 'mid', 'last_seen_ts', 'seen_count',
                  'imported_ts', 'key_ratio', 'key_info')

    def __init__(self, to,
                 key_sig=None, autocrypt_ts=None, prefer_encrypt=None,
                 key_count=None, mid=None, last_seen_ts=None,
                 seen_count=None, imported_ts=None, key_ratio=None,
                 key_info=None):
        if '@' not in to:
            raise ValueError('To must be an e-mail address')
        self.autocrypt_ts = int(key_sig and (autocrypt_ts or time.time()) or 0)
        self.prefer_encrypt = prefer_encrypt or ''
        self.key_sig = key_sig or ''
        self.key_count = int(key_count or (key_sig and 1) or 0)
        self.to = to
        self.mid = mid or ''
        self.last_seen_ts = int(last_seen_ts or autocrypt_ts or time.time())
        self.seen_count = int(seen_count or 1)
        self.imported_ts = (imported_ts or 0)
        self.key_ratio = (key_ratio or (self.RATIO_INIT if key_sig else 0))
        self.key_info = key_info or ''

    def float_ratio(self):
        return (self.key_ratio / self.RATIO_MAX)

    def update_ratio(self, have_key=True):
        window = float(min(self.seen_count, self.RATIO_WINDOW))
        oratio = self.key_ratio
        self.key_ratio = int(self.RATIO_MAX * (
            ((self.key_ratio / self.RATIO_MAX) * (window-1) / window) +
            ((1.0 if have_key else 0) / window)))
        return (oratio != self.key_ratio)

    def should_encrypt(self):
        return (
            self.key_sig and
            self.prefer_encrypt == 'mutual' and
            self.autocrypt_ts == self.last_seen_ts)

    def as_list(self):
        return [self.__getattribute__(k) for k in self.INIT_ORDER]

    def as_dict(self):
        return dict(
            (k, self.__getattribute__(k))
            for k in (['to'] + list(self.INIT_ORDER)))

    def as_text(self):
        return '%s' % self.as_dict()

    def save_to(self, db):
        db[canonicalize_email(self.to)] = self.as_list()
        return self

    @classmethod
    def Load(cls, db, to, _raise=KeyError):
        try:
            return cls(to, *db[canonicalize_email(to)])
        except (KeyError, AttributeError, TypeError):
            if _raise is None:
                return None
            else:
                raise _raise('Not Found')


def autocrypt_process_email(config, msg, msg_mid, msg_ts, sender_email,
                            autocrypt_header=None, save_DB=False):
    """
    Process an e-mail, updating the Autocrypt state database as appropriate.
    If the state database has changed, return the new state. Otherwise None.
    """
    if not config.prefs.key_tofu.autocrypt:
        return None

    db = get_Autocrypt_DB(config)['state']
    changed = False
    try:
        existing = AutocryptRecord.Load(db, sender_email)
    except KeyError:
        existing = None

    # Trying keep the DB Small: we don't store full keys, just hashes
    # of them. When or if we actually decide to use the key it must
    # either be findable in e-mail (not deleted) or in a keychain.
    # Since Autocrypt is opportunistic, missing some chances to encrypt
    # is by definition acceptable! We also deliberately do not use
    # the key fingerprint here, as we would still like to detect and
    # capture updates when subkeys or UIDs change.
    try:
        # Note: Fails if the sender_email doesn't match the addr= attribte.
        autocrypt_header = (
            autocrypt_header or
            extract_autocrypt_header(msg, to=sender_email))

        if autocrypt_header:
            to = autocrypt_header['addr']
            pe = autocrypt_header.get('prefer-encrypt')
            key_data = autocrypt_header['keydata']
            key_sig = sha1b64(key_data).strip()
            # FIXME: Do we need to handle gossip headers here? If the way
            #        we handle keys using keytofu and the search engine is
            #        compatible with Autocrypt, then maybe no...?
        else:
            to = pe = key_data = key_sig = None

        # Note: This algorithm differs from the update algorithm described in
        #       the Autocrypt Level 1 spec, because we're also updating a
        # counter that tells us how often we've seen a particular key.

        # New entry or no-op; short circuit
        if existing is None:
            if key_sig:
                existing = AutocryptRecord(to,
                    key_sig=key_sig,
                    autocrypt_ts=msg_ts,
                    prefer_encrypt=pe,
                    mid=msg_mid)
                changed = True
                return existing  # Will save in `finally` block
            else:
                return None

        # Always update last-seen timestamp and seen counter
        if existing.mid != msg_mid:
            existing.seen_count += 1
            changed = True
        if existing.last_seen_ts < msg_ts:
            existing.last_seen_ts = msg_ts
            changed = True

        # Same key: Update counts and policy/timestamp if newer
        if existing.key_sig == key_sig:
            if existing.mid != msg_mid:
                if existing.autocrypt_ts < msg_ts:
                    existing.autocrypt_ts = msg_ts
                    existing.prefer_encrypt = pe
                    existing.mid = msg_mid
                existing.key_count += 1
                changed = True

        # Different key: If newer than what's on file, update
        if key_sig and existing.autocrypt_ts < msg_ts:
            existing.autocrypt_ts = msg_ts
            existing.key_sig = key_sig
            existing.mid = msg_mid
            existing.prefer_encrypt = pe
            existing.key_count = 1
            existing.imported_ts = 0
            changed = True

        # Update our estimated ratio of how many mails have Autocrypt
        if existing:
            if existing.update_ratio(have_key=(key_sig is not None)):
                changed = True

        # If we made changes, return the current state. Else, None.
        return (existing if changed else None)

    except (TypeError, KeyError):
        traceback.print_exc()
        changed = False
        return None

    finally:
        if changed and (existing is not None):
            existing.save_to(db)
            if save_DB:
                save_Autocrypt_DB(config)


def autocrypt_recommendation(config, email, re_encrypted=False, state_db=None):
    """
    Returns an Autocrypt Level 1 recommendation for a given e-mail address.
    If the e-mail is not in the Autocrypt database, returns None.
    """
    db = state_db or get_Autocrypt_DB(config)['state']
    try:
        acr = AutocryptRecord.Load(db, email)
    except KeyError:
        acr = None

    # Not found in the Autocrypt DB, we have no opinion.
    if not acr:
        return None

    # Notes:
    #
    #  - Checking whether keys are usable for encryption (expired, revoked)
    #    is handled by mailpile.plugins.keylookup.KeyTofu; our Autocrypt
    #    recommendations assume all that keys are usable.
    #
    #  - We are not handling Gossip here at all, but Gossip is handled
    #    by Mailpile's fallback heuristics since Autocrypt Gossip headers
    #    are considered as a source of keys to import when requested.
    #
    # This simplifies the logic somewhat.

    # Determine if encryption is possible; short-circuit if not.
    if not acr.key_sig:
        return AutocryptRecommendation(AutocryptRecommendation.DISABLE)

    # Phase 1: Preliminary recommendation
    if acr.last_seen_ts - (35 * 24 * 3600) > acr.autocrypt_ts:
        rec = AutocryptRecommendation.DISCOURAGE
    else:
        rec = AutocryptRecommendation.ENABLE

    # Phase 2: Final recommendation
    if re_encrypted or (
            (rec == AutocryptRecommendation.ENABLE) and
            ('mutual' == acr.prefer_encrypt)):
        rec = AutocryptRecommendation.ENCRYPT

    return AutocryptRecommendation(rec, key_sig=acr.key_sig)


def autocrypt_policy_checker(session, profile, emails):
    AR = AutocryptRecommendation
    acrs = []
    baseline = 'sign' if ('S' in profile.crypto_format) else 'none'

    if 'E' not in profile.crypto_format:
        return (baseline, AR.ENABLE if profile.pgp_key else AR.DISABLE)

    for email in (e for e in emails if e != profile.email):
        acrs.append(autocrypt_recommendation(session.config, email))
        if acrs[-1] is None:
            return (baseline, AR.DISABLE)

    policy = AR.Synchronize(*acrs)
    return (
        'sign-encrypt' if (policy == AR.ENCRYPT) else baseline,
        policy)


##[ Autocrypt integration and API commands ]###################################

class AutocryptSearch(Command):
    """Search for the Autocrypt database."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/search', 'crypto/autocrypt/search', '<emails>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {'q': 'emails'}

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                r = self.result
                return '\n'.join(["%s: %s (should_encrypt=%s)" % (
                                      to,
                                      r[to].as_dict(),
                                      r[to].should_encrypt())
                                  for to in sorted(r.keys())])
            else:
                return _("No results")

    def command(self):
        args = list(self.args)
        for q in self.data.get('q', []):
            args.extend(q.split())

        db = get_Autocrypt_DB(self.session.config)['state']
        results = dict((e, AutocryptRecord.Load(db, e))
                       for e in args if canonicalize_email(e) in db)

        if results:
            return self._success(_("Found %d results") % len(results.keys()),
                                 results)
        else:
            return self._error(_("Not found"), results)


class AutocryptForget(Command):
    """Forget all Autocrypt state for a list of e-mail address."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/forget', 'crypto/autocrypt/forget', '<emails>')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {'email': 'emails'}

    def command(self):
        args = list(self.args)
        args.extend(self.data.get('email', []))

        forgot = []
        db = get_Autocrypt_DB(self.session.config)['state']
        for e in args:
            if e in db:
                del db[e]
                forgot.append(e)

        if forgot:
            save_Autocrypt_DB(self.session.config)
            return self._success(_("Forgot %d recipients") % len(forgot),
                                 forgot)
        else:
            return self._error(_("Not found"))


class AutocryptParse(Command):
    """Parse the Autocrypt header from a message (or messages)."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/parse', 'crypto/autocrypt/parse', '<emails>')
    HTTP_CALLABLE = ('POST', )

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        updated = []
        args = list(self.args)
        for e in [Email(idx, i) for i in self._choose_messages(args)]:
            autocrypt_meta_kwe(
                idx, e.msg_mid(), e.get_msg(), None,
                int(e.get_msg_info(e.index.MSG_DATE), 36),
                update_cb=lambda u, k: updated.append((u, k)),
                save_DB=False)

        updated = [(u[0].as_dict(), sorted(list(u[1])))
                   for u in updated if u[0] is not None]
        if updated:
            save_Autocrypt_DB(config)

        return self._success("Updated %d records" % len(updated), updated)


class AutocryptPeers(Command):
    """List known Autocrypt Peers and their state."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/peers', 'crypto/autocrypt/peers', None)
    HTTP_CALLABLE = ('POST', )

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if not self.result:
                return _("No results")
            return '\n'.join([
                AutocryptRecord.Load(self.result, r).as_text()
                for r in self.result])

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)

        db = get_Autocrypt_DB(config)['state']

        return self._success(_("Found %d peers") % len(db), db)


def autocrypt_meta_kwe(index, msg_mid, msg, msg_size, msg_ts,
                       body_info=None, update_cb=None, save_DB=True):
    """
    This extracts search keywords from the Autocrypt headers, and
    updates the Autocrypt state database as a side-effect.
    """
    keywords = set([])
    config = index.config
    if not config.prefs.key_tofu.autocrypt:
        return keywords

    mimetype = (msg.get_content_type() or '').lower()
    if mimetype not in AUTOCRYPT_IGNORE_MIMETYPES:
        autocrypt_header = sender = None

        senders = ExtractEmails(msg['from'] or '')  # FIXME: Shitty parser?
        if len(senders) == 1:
            sender = senders[0]
            autocrypt_header = extract_autocrypt_header(msg, to=sender)

        if autocrypt_header:
            keywords.add('pgp:has')
            keywords.add('autocrypt:has')
            key_data = autocrypt_header.get('keydata')
            if key_data:
                keywords |= set(get_pgp_key_keywords(key_data))

            for gh in extract_autocrypt_gossip_headers(msg):
                key_data = gh.get('keydata')
                if key_data:
                    keywords.add('autocrypt-gossip:has')
                    keywords |= set(get_pgp_key_keywords(key_data))

        update = autocrypt_process_email(config, msg, msg_mid, msg_ts, sender,
                                         autocrypt_header=autocrypt_header,
                                         save_DB=save_DB)
        if update_cb is not None:
            update_cb(update, keywords)

    return keywords


class AutocryptTxf(EmailTransform):
    """
    This is an outgoing email content transform for adding autocrypt headers.

    Note: This transform relies on Memory Hole code elsewhere to correctly
    obscure Gossip headers. Plugin/hook priorities must be set accordingly.
    """
    def TransformOutgoing(self, sender, rcpts, msg, **kwargs):
        matched = False
        keydata = mutual = sender_keyid = key_binary = None

        gnupg = GnuPG(self.config, event=GetThreadEvent())
        profile = self._get_sender_profile(sender, kwargs)
        vcard = profile['vcard']
        if vcard is not None:
            crypto_format = vcard.crypto_format
            sender_keyid = vcard.pgp_key
            if sender_keyid and 'autocrypt' in crypto_format:
                key_binary = gnupg.get_minimal_key(key_id=sender_keyid,
                                                   user_id=sender,
                                                   armor=False)

            if key_binary:
                mutual = 'E' in crypto_format.split('+')[0].split(':')[-1]
                msg["Autocrypt"] = make_autocrypt_header(
                    sender, key_binary, prefer_encrypt_mutual=mutual)

                if 'encrypt' in msg.get('Encryption', '').lower():
                    gossip_list = []
                    for rcpt in rcpts:
                        # FIXME: Check if any of the recipients are in the BCC
                        #        header; omit their keys if so?
                        try:
                            # This *should* always succeed: if we are encrypting,
                            # then the key we encrypt to should already be in
                            # the keychain.
                            if '#' in rcpt:
                                rcpt, rcpt_keyid = rcpt.split('#')
                            else:
                                # This happens when composing in the CLI.
                                rcpt_keyid = rcpt
                            if (rcpt != sender) and rcpt_keyid:
                                kb = gnupg.get_minimal_key(key_id=rcpt_keyid,
                                                           user_id=rcpt,
                                                           armor=False)
                                if kb:
                                    gossip_list.append(make_autocrypt_header(
                                        rcpt, kb, prefix='Autocrypt-Gossip'))
                        except (ValueError, IndexError):
                            pass
                    if len(gossip_list) > 1:
                        # No point gossiping peoples keys back to them alone.
                        for hdr in gossip_list:
                            msg.add_header('Autocrypt-Gossip', hdr)

                matched = True

        return sender, rcpts, msg, matched, True


class AutocryptKeyLookupHandler(EmailKeyLookupHandler):
    NAME = _("Autocrypt")
    PRIORITY = 4
    TIMEOUT = 25  # 5 seconds per message we are willing to parse
    LOCAL = True
    PRIVACY_FRIENDLY = True
    SCORE = 1

    def __init__(self, session, *args, **kwargs):
        EmailKeyLookupHandler.__init__(self, session, *args, **kwargs)

    def _score(self, key):
        return (self.SCORE, _('Found key using Autocrypt'))

    def _db_and_acr(self, address):
        db = get_Autocrypt_DB(self.session.config)['state']
        try:
            return db, AutocryptRecord.Load(db, address)
        except KeyError:
            return db, None

    def _getkey(self, email, keyinfo):
        db, acr = self._db_and_acr(email)
        if acr:
            rv = EmailKeyLookupHandler._getkey(self, email, keyinfo)
            if self._gk_succeeded(rv):
                acr.imported_ts = int(time.time())
                acr.save_to(db)
                save_Autocrypt_DB(self.session.config)
            return rv
        else:
            raise ValueError('Not found in Autocrypt DB: %s' % email)

    def _lookup(self, address, strict_email_match=False):
        config, ui = self.session.config, self.session.ui
        results = {}
        if not (address and config.prefs.key_tofu.autocrypt):
            return results

        db, acr = self._db_and_acr(address)
        if acr is None or not acr.key_sig or not acr.mid:
            return results

        # Note: Autocrypt gossip is handled by the normal e-mail lookups
        for key_info, raw_key in self._get_message_keys(int(acr.mid, 36),
                autocrypt=True, autocrypt_gossip=False, attachments=False):
            key_sig = sha1b64(raw_key).strip()
            if key_sig == acr.key_sig:
                fp = key_info.fingerprint
                results[fp] = results[key_sig] = copy.copy(key_info)
                self.key_cache[fp] = self.key_cache[key_sig] = raw_key
                if 'keylookup' in config.sys.debug:
                    ui.debug('Got key from =%s: %s' % (acr.mid, key_sig,))
            elif 'keylookup' in config.sys.debug:
                ui.debug('Key sig %s != %s' % (key_sig, acr.key_sig))

        return results


if __name__ == "__main__":
    import sys
    import doctest

    results = doctest.testmod(optionflags=doctest.ELLIPSIS)
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)

else:
    _plugins = PluginManager(builtin=__file__)

    _plugins.register_meta_kw_extractor('autocrypt', autocrypt_meta_kwe)
    _plugins.register_commands(
        AutocryptSearch,
        AutocryptForget,
        AutocryptParse,
        AutocryptPeers)
    register_crypto_key_lookup_handler(AutocryptKeyLookupHandler)
    register_crypto_policy('autocrypt', autocrypt_policy_checker)

    # Note: we perform our transformations BEFORE the GnuPG transformations
    # (prio 500), so the memory hole transformation can take care of hiding
    # the Autocrypt-Gossip headers.
    _plugins.register_outgoing_email_content_transform(
        '400_autocrypt', AutocryptTxf)
