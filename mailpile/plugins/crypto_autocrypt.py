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
from mailpile.util import sha1b64

_plugins = PluginManager(builtin=__file__)


##[ Begin borrowed code ... ]################################################
#
# Based on:
#
# https://github.com/mailencrypt/inbome/blob/master/src/inbome/parse.py

def parse_autocrypt_headervalue(value, optional_attrs=[]):
    result_dict = {}
    for x in value.split(";"):
        kv = x.split("=", 1)
        name = kv[0].strip()
        value = kv[1].strip()
        if name == "addr":
            result_dict["addr"] = value
        elif name == "keydata":
            keydata_base64 = "".join(value.split())
            keydata = base64.b64decode(keydata_base64)
            result_dict["keydata"] = keydata
        elif name == "prefer-encrypted":
            result_dict["prefer-encrypted"] = value

    if "keydata" not in result_dict:
        # found no keydata, ignoring header
        return {}

    if "addr" not in result_dict:
        # found no e-mail address, ignoring header
        return {}

    if "prefer-encrypted" not in result_dict:
        result_dict["prefer-encrypted"] = "nopreference"

    if result_dict.get("prefer-encrypted") not in ("mutual", "nopreference"):
        result_dict["prefer-encrypted"] = "nopreference"

    return result_dict


def extract_autocrypt_header(msg, to=None, optional_attrs=None):
    all_results = []
    for inb in msg.get_all("AutoCrypt"):
        res = parse_autocrypt_headervalue(inb, optional_attrs)
        print("Res:", res)
        if res and (not to or res['addr'] == to):
            all_results.append(res)

    # Return parsed header iff we found exactly one.
    if len(all_results) == 1:
        return all_results[0]
    elif len(all_results) > 1:
        # TODO: Handle gossip here.
        return {}

    # FIXME: The AutoCrypt spec talks about synthesizing headers from other
    #        details. That would make sense if AutoCrypt was our primary
    # mechanism, but we're not really there yet. Needs more thought.

    return {}


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
    INIT_ORDER = ('key', 'ts-message-date', 'prefer-encrypted',
                  'count', 'mid', 'ts-last-seen')

    def __init__(self, to,
                 key=None, ts_message_date=None, prefer_encrypted=None,
                 count=1, mid=None, ts_last_seen=None):
        self['to'] = to
        self['ts-message-date'] = ts_message_date or int(time.time())
        self['ts-last-seen'] = ts_last_seen or self['ts-message-date']
        self['key'] = key  # Signature of key data (not key itself)
        self['mid'] = mid  # MID of most recent message with this key.
        self['count'] = count  # How many times have we seen this key?
        self['prefer-encrypted'] = prefer_encrypted

    def should_encrypt(self):
        #
        # Note: This differs from the AutoCrypt recommendations in that,
        #       we've added a counter which lets us further slow things
        #       down and reduce false-start encryption.
        #
        # FIXME: Does that break the simplicity of the mental model? Bad idea?
        #
        if self['prefer-encrypted'] and self['count'] > 1:
            return True
        if self['prefer-encrypted'] is None and self['count'] > 5:
            return True
        return False

    def save_to(self, db):
        db[self['to']] = [self[k] for k in self.INIT_ORDER]
        return self

    @classmethod
    def Load(cls, db, to):
        return cls(to, *db[to])


def AutoCrypt_process_email(config, msg, msg_mid, msg_ts, sender_email,
                            autocrypt_header=None):
    autocrypt_header = autocrypt_header or extract_autocrypt_header(
        msg, to=sender_email, optional_attrs=( ))

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
        pe = autocrypt_header.get('prefer-encrypted')

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
                    existing['prefer-encrypted'] = pe

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
                return AutoCryptRecord(to,
                                       key=key, ts=ts, prefer_encrypted=pe,
                                       mid=mid)

        except (TypeError, KeyError):
            pass

        # Create a new record, yay!
        record = AutoCryptRecord(to,
                                 key=key, ts_message_date=ts,
                                 prefer_encrypted=pe, mid=mid)

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
    SYNOPSIS = (None, 'crypto/autocrypt/peers', 'crypto/autocrypt/peers')
    HTTP_CALLABLE = ('POST', )

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)

        db = get_AutoCrypt_DB(config)['state']

        return self._success(_("Found %d peers") % len(db), db)


def extract_pgp_key_keywords(key_data):
    # FIXME: pgpdump!
    # FIXME: It's unclear what the goal was here.
    return set([])


def autocrypt_meta_kwe(index, msg_mid, msg, msg_size, msg_ts, body_info=None):
    keywords = set([])

    # We always tell the search index about AutoCrypt messages and keys,
    # whether "the experiment" is enabled by the user or not.
    config = index.config

    if 'autocrypt' in msg:
        sender = ExtractEmails(msg['from'])[0]
        autocrypt_header = extract_autocrypt_header(
            msg, to=sender, optional_attrs=( ))

        if autocrypt_header:
            keywords.add('autocrypt:has')
            key_data = autocrypt_header.get('key')
            if key_data:
                keywords |= extract_pgp_key_keywords(key_data)

            AutoCrypt_process_email(config, msg, msg_mid, msg_ts, sender,
                                    autocrypt_header=autocrypt_header)

            save_AutoCrypt_DB(config)

    return keywords


class AutoCryptTxf(EmailTransform):
    """
    This is an outgoing email content transform for adding autocrypt headers.
    """
    def TransformOutgoing(self, sender, rcpts, msg, **kwargs):
        matched = False
        keydata = None
        sender_keyid = None

        gnupg = GnuPG(self.config, event=GetThreadEvent())
        profile = self._get_sender_profile(sender, kwargs)
        if profile['vcard'] is not None:
            sender_keyid = profile['vcard'].pgp_key
            data = gnupg.get_pubkey(sender_keyid)
            keydata = base64.b64encode(data)

        if keydata:
            msg["Autocrypt"] = "addr=%s; prefer-encrypt=mutual; keydata=%s" % (sender, keydata)
            matched = True

        return sender, rcpts, msg, matched, True

_plugins.register_commands(AutoCryptSearch, AutoCryptForget, AutoCryptParse, AutoCryptPeers)
_plugins.register_meta_kw_extractor('autocrypt', autocrypt_meta_kwe)
_plugins.register_outgoing_email_content_transform('550_autocrypt', AutoCryptTxf)
