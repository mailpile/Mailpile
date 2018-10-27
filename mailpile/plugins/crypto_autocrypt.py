import base64
import datetime
import re
import time
import urllib2
from email import encoders
from email.mime.base import MIMEBase

import mailpile.security as security
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.commands import Command
from mailpile.crypto.autocrypt_utils import *
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
from mailpile.plugins.vcard_gnupg import PGPKeysImportAsVCards
from mailpile.plugins.search import Search
from mailpile.plugins.keylookup.email_keylookup import get_pgp_key_keywords
from mailpile.util import sha1b64

_plugins = PluginManager(builtin=__file__)


##[ Misc. AutoCrypt-related API commands ]####################################


# FIXME: This really should be a record store, not an in-memory dict
def save_AutoCrypt_DB(config):
    if config.autocrypt_db:
        config.save_pickle(config.autocrypt_db, 'autocrypt_db')


def get_AutoCrypt_DB(config):
    if not config.real_hasattr('autocrypt_db'):
        try:
            db = config.load_pickle('autocrypt_db')
        except (IOError, EOFError):
            db = {'state': {}}
        config.real_setattr('autocrypt_db', db)
    return config.autocrypt_db


class AutoCryptRecord(dict):
    INIT_ORDER = ('key', 'ts-message-date', 'prefer-encrypt',
                  'count', 'mid', 'ts-last-seen')

    def __init__(self, to,
                 key=None, ts_message_date=None, prefer_encrypt=None,
                 count=1, mid=None, ts_last_seen=None):
        self['to'] = to
        self['ts-message-date'] = ts_message_date or int(time.time())
        self['ts-last-seen'] = ts_last_seen or self['ts-message-date']
        self['key'] = key  # Signature of key data (not key itself)
        self['mid'] = mid  # MID of most recent message with this key.
        self['count'] = count  # How many times have we seen this key?
        self['prefer-encrypt'] = prefer_encrypt

    def should_encrypt(self):
        return (self['prefer-encrypt'] == 'mutual')

    def save_to(self, db):
        db[self['to']] = [self[k] for k in self.INIT_ORDER]
        return self

    @classmethod
    def Load(cls, db, to):
        return cls(to, *db[to])


def AutoCrypt_process_email(config, msg, msg_mid, msg_ts, sender_email,
                            autocrypt_header=None):
    autocrypt_header = (
        autocrypt_header or
        extract_autocrypt_header(msg, to=sender_email))
    gossip_headers = extract_autocrypt_gossip_headers(msg, to=sender_email)

    db = get_AutoCrypt_DB(config)['state']
    if autocrypt_header:
        ts = msg_ts
        to = autocrypt_header['addr']
        mid = msg_mid
        key_data = autocrypt_header['keydata']

        # Trying to save RAM: we don't store full keys, just hashes of
        # them. When or if we actually decide to use the key it must
        # either be findable in e-mail (not deleted) or in a keychain.
        # Since AutoCrypt is opportunistic, missing some chances to encrypt
        # is by definition acceptable! We also deliberately do not use
        # the key fingerprint here, as we would still like to detect and
        # capture updates when subkeys change.
        key = sha1b64(key_data).strip()
        pe = autocrypt_header.get('prefer-encrypt')

        try:
            existing = AutoCryptRecord.Load(db, to)
            if existing['key'] == key and existing['mid'] != mid:
                # This is the same key! Count it.
                existing['count'] += 1

                # If and only if this header is newer than what we have on
                # file: update some of our attributes.
                if existing['ts-last-seen'] < ts:
                    existing['ts-last-seen'] = ts
                    existing['mid'] = mid
                    existing['prefer-encrypt'] = pe

                # If it's old and provides us with an earlier date for
                # the "origin" of this key, make note of that as well.
                elif existing['ts-message-date'] > ts:
                    existing['ts-message-date'] = ts

                # Add the raw key data (for use downstream), save, return.
                return existing.save_to(db)

            elif existing['ts-last-seen'] >= ts:
                if existing['ts-message-date'] < ts:
                    # FIXME: This is evidence sender has multiple clients
                    # doing AutoCrypt at once. That's a problem! We might
                    # want to make a note of this and do something about it.
                    # This is a point to discuss with the AutoCrypt group.
                    pass

                # Header is older than what we already have on file, ignore!
                # But... return the parsed record, even if this is a no-op.
                # This allows the keyword extractor to use the data, at
                # the expense of things seeming more exciting than they
                # really are when run manually.
                return AutoCryptRecord(
                     to, key=key, ts=ts, prefer_encrypt=pe, mid=mid)

        except (TypeError, KeyError):
            pass

        # Create a new record, yay!
        record = AutoCryptRecord(
            to, key=key, ts_message_date=ts, prefer_encrypt=pe, mid=mid)

        return record.save_to(db)

    # If we get this far, we have no valid AutoCrypt header (new or old).
    # Remove address from our database to save resources. We don't care
    # about the null states at the moment.
    if sender_email in db:
        del db[sender_email]
        return False

    return None


##[ AutoCrypt debugging and API commands ]#####################################

class AutoCryptSearch(Command):
    """Search for the AutoCrypt database."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/search', 'crypto/autocrypt/search', '<emails>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {'q': 'emails'}

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                r = self.result
                return '\n'.join(["%s: %s (%s)" % (
                                      to, r[to], r[to].should_encrypt())
                                  for to in sorted(r.keys())])
            else:
                return _("No results")

    def command(self):
        args = list(self.args)
        for q in self.data.get('q', []):
            args.extend(q.split())

        db = get_AutoCrypt_DB(self.session.config)['state']
        results = dict((e, AutoCryptRecord.Load(db, e))
                       for e in args if e in db)

        if results:
            return self._success(_("Found %d results") % len(results.keys()),
                                 results)
        else:
            return self._error(_("Not found"), results)


class AutoCryptForget(Command):
    """Forget all AutoCrypt state for a list of e-mail address."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/forget', 'crypto/autocrypt/forget', '<emails>')
    HTTP_CALLABLE = ('POST', )
    HTTP_QUERY_VARS = {'email': 'emails'}

    def command(self):
        args = list(self.args)
        args.extend(self.data.get('email', []))

        forgot = []
        changes = 0
        db = get_AutoCrypt_DB(self.session.config)['state']
        for e in args:
            if e in db:
                changes += 1
                del db[e]
                forgot.append(e)

        if changes:
            save_AutoCrypt_DB(self.session.config)
            return self._success(_("Forgot %d recipients") % changes, forgot)
        else:
            return self._error(_("Not found"))


class AutoCryptParse(Command):
    """Parse the AutoCrypt header from a message (or messages)."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/parse', 'crypto/autocrypt/parse', '<emails>')
    HTTP_CALLABLE = ('POST', )

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)

        emails = [Email(idx, i) for i in self._choose_messages(args)]
        db = get_AutoCrypt_DB(config)['state']
        updated = []

        for e in emails:
            msg = e.get_msg()
            if 'autocrypt' in msg:
                sender = e.get_sender()
                update = AutoCrypt_process_email(
                    config, e.get_msg(), e.msg_mid(),
                    int(e.get_msg_info(e.index.MSG_DATE), 36), sender)
                if update is not None:
                    # Note: update==False means an entry was removed, which
                    #       is an interesting event!
                    updated.append(sender)

        if updated:
            save_AutoCrypt_DB(config)

        return self._success("Updated %d records" % len(updated), updated)


class AutoCryptPeers(Command):
    """List known AutoCrypt Peers and their state."""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/autocrypt/peers', 'crypto/autocrypt/peers', None)
    HTTP_CALLABLE = ('POST', )

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)

        db = get_AutoCrypt_DB(config)['state']

        return self._success(_("Found %d peers") % len(db), db)


def autocrypt_meta_kwe(index, msg_mid, msg, msg_size, msg_ts, body_info=None):
    keywords = set([])
    config = index.config

    if 'autocrypt' in msg:
        sender = ExtractEmails(msg['from'])[0]
        autocrypt_header = extract_autocrypt_header(msg, to=sender)

        if autocrypt_header:
            keywords.add('pgp:has')
            keywords.add('autocrypt:has')
            key_data = autocrypt_header.get('keydata')
            if key_data:
                keywords |= set(get_pgp_key_keywords(key_data))

            AutoCrypt_process_email(config, msg, msg_mid, msg_ts, sender,
                                    autocrypt_header=autocrypt_header)

            save_AutoCrypt_DB(config)

    return keywords


class AutoCryptTxf(EmailTransform):
    """
    This is an outgoing email content transform for adding autocrypt headers.

    Note: This transform relies on Memory Hole code elsewhere to correctly obscure
    the Gossip headers. Priorities must be set accordingly.
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
                                                   user_id=sender)

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
                                                           user_id=rcpt)
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


_plugins.register_meta_kw_extractor('autocrypt', autocrypt_meta_kwe)
_plugins.register_commands(
    AutoCryptSearch,
    AutoCryptForget,
    AutoCryptParse,
    AutoCryptPeers)

# Note: we perform our transformations BEFORE the GnuPG transformations
# (prio 500), so the memory hole transformation can take care of hiding
# the Autocrypt-Gossip headers.
_plugins.register_outgoing_email_content_transform(
    '400_autocrypt', AutoCryptTxf)
