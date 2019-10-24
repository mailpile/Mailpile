from __future__ import print_function
# Copyright (C) 2018 Jack Dodds & Mailpile ehf.
# This code is part of Mailpile and is hereby released under the
# Gnu Affero Public Licence v.3 - see ../../COPYING and ../../AGPLv3.txt.
#
"""
This file contains low-level Autocrypt code: constants, parsing, etc.

The higher level application logic (state database, persistance etc.) is
mostly in mailpile.plugins.crypto_autocrypt, but inevitably some has
leaked into mailpile.crypto.gpgi and mailpile.crypto.mime.

Examples (and doctests):


# Canonicalize e-mail addresses according to Autocrypt conventions
>>> canonicalize_email('BrE@maILPile.is')
'bre@mailpile.is'


# Parse the Autocrypt header
>>> ach = 'addr=bre@mailpile.is; _a=b; _c=d; keydata=aGVsbG8='
>>> hv = parse_autocrypt_headervalue(ach, optional_attrs=['_a'])
>>> hv['addr']
'bre@mailpile.is'
>>> hv['keydata']
'hello'
>>> hv['_a']
'b'
>>> hv.get('_c') is None
True
>>> hv.get('prefer-encrypt') is None
True

# Invalid autocrypt headers return {}
>>> parse_autocrypt_headervalue('addr=bre@mailpile.is')
{}
>>> parse_autocrypt_headervalue('keydata=aGVsbG8=')
{}
>>> parse_autocrypt_headervalue('unknown=attribute; ' + ach)
{}

# Invalid prefer-encrypt values just get ignored
>>> hv = parse_autocrypt_headervalue('prefer-encrypt=bogus; ' + ach)
>>> hv.get('prefer-encrypt') is None
True
>>> hv = parse_autocrypt_headervalue('prefer-encrypt=mutual; ' + ach)
>>> hv.get('prefer-encrypt') == 'mutual'
True


# Generate a valid Autocrypt header
>>> make_autocrypt_header('bre@mailpile.is', 'hello', prefer_encrypt_mutual=True)
'addr=bre@mailpile.is; prefer-encrypt=mutual; keydata=aGVsbG8='


# Autocrypt setup-codes are used to secure our PGP keys
>>> generate_autocrypt_setup_code(random_data='fake random garbage data')
'1189-1868-6510-5211-5608-1629-1262-5635-4164'
>>> len(generate_autocrypt_setup_code())
44
>>> generate_autocrypt_setup_code() != generate_autocrypt_setup_code()
True


# AutocryptRecommendations combine a key and a policy of what to do
>>> ar = AutocryptRecommendation('disable')
>>> ar.policy
'disable'
>>> ar.key_sig is None
True

# Combining recommendations for multiple parties has specific rules
>>> ar2 = AutocryptRecommendation('encrypt', key_sig='12345')
>>> AutocryptRecommendation.Synchronize(ar, ar2)
'disable'
>>> str(ar2)
'disable'

# Not just anything is a valid recommendation
>>> ar2.policy = 'bogus'
Traceback (most recent call last):
   ...
ValueError: Invalid Autocrypt policy: bogus


"""
import base64
import datetime
import os
import pgpdump
import struct
import time


AUTOCRYPT_IGNORE_MIMETYPES = ('multipart/report', )


def canonicalize_email(address):
    try:
        localpart, domain = address.split('@')
    except (ValueError, AttributeError):
        # Just return invalid e-mails unchanged, there is no sensible way
        # to canonicalize such a thing.
        return address

    # FIXME: Ensure domain is ASCII, if not, punycode it
    domain = domain.lower()

    # FIXME: Ensure we're using the "empty locale"
    localpart = localpart.lower()

    # NOTE: We deliberately do not strip plussed parts or perform any other
    #       normalization of the localpart beyond lowercasing. This is both
    # to comply with the Autocrypt Level 1 spec, but also because being able
    # to use plussed parts to allow differing cryptographic identities to
    # share the same e-mail account is something power users like to do.

    return '%s@%s' % (localpart, domain)


def parse_autocrypt_headervalue(value, optional_attrs=None):
    # Based on:
    #
    # https://github.com/mailencrypt/inbome/blob/master/src/inbome/parse.py
    """
    Parse an AutoCrypt header. Will return an empty dict if parsing fails.

    Optional attributes may be added to the result dictionary, but only the ones
    listed in optional_attrs (a list or dict); others are ignored.
    """
    result_dict = {}
    try:
        for x in value.split(";"):
            kv = x.split("=", 1)
            name = kv[0].strip()
            value = kv[1].strip()
            if name in ("addr", "prefer-encrypt"):
                result_dict[name] = value
            elif name == "keydata":
                keydata_base64 = "".join(value.split())
                keydata = base64.b64decode(keydata_base64)
                result_dict[name] = keydata
            elif name[:1] == '_':
                if optional_attrs and name in optional_attrs:
                    result_dict[name] = value
            else:
                # Unknown value detected, refuse to parse any further
                return {}
    except (ValueError, TypeError, IndexError):
        return {}

    if "keydata" not in result_dict:
        # found no keydata, ignoring header
        return {}

    if "addr" not in result_dict:
        # found no e-mail address, ignoring header
        return {}
    else:
        result_dict["addr"] = canonicalize_email(result_dict["addr"])

    if result_dict.get("prefer-encrypt") not in ("mutual", None):
        # Invalid prefer-encrypt value; treat as nopreference
        del result_dict['prefer-encrypt']

    return result_dict


def extract_autocrypt_header(msg, to=None, optional_attrs=None):
    # Autocrypt requires there only be one From header
    froms = msg.get_all("From") or []
    if len(froms) != 1:
        return {}

    # Extract the from address for comparisons below. We compare the
    # canonicalized versions, which is not the strictest interpretation
    # of the spec, but feels like a reasonable balance here.
    from mailpile.mailutils.addresses import AddressHeaderParser
    from_addrs = AddressHeaderParser(froms[0])
    if len(from_addrs) != 1:
        return {}
    from_addr = canonicalize_email(from_addrs[0].address)

    to = canonicalize_email(to) if to else None
    all_results = []
    for inb in (msg.get_all("Autocrypt") or []):
        res = parse_autocrypt_headervalue(inb, optional_attrs=optional_attrs)
        if res:
            if ((not to or canonicalize_email(res['addr']) == to) and
                    (canonicalize_email(res['addr']) == from_addr)):
                all_results.append(res)

    # Return parsed header iff we found exactly one.
    if len(all_results) == 1:
        return all_results[0]
    else:
        return {}


def extract_autocrypt_gossip_headers(msg, to=None, optional_attrs=None):
    to = canonicalize_email(to) if to else None
    all_results = []
    for inb in (msg.get_all("Autocrypt-Gossip") or []):
        res = parse_autocrypt_headervalue(inb, optional_attrs=optional_attrs)
        if res and (not to or res['addr'] == to):
            all_results.append(res)

    return all_results


def make_autocrypt_header(addr, binary_key,
                          prefer_encrypt_mutual=False, prefix='Autocrypt'):
    prefix = '%s: ' % prefix
    pem = ' prefer-encrypt=mutual;' if prefer_encrypt_mutual else ''
    hdr = '%saddr=%s;%s keydata=' % (prefix, addr, pem)
    for c in base64.b64encode(binary_key).strip():
        if (len(hdr) % 78) == 0: hdr += ' '
        hdr += c
    return hdr[len(prefix):]


def generate_autocrypt_setup_code(random_data=None):
    """
    Generate a passphrase/setup-code compliant with Autocrypt Level 1.

    From the spec: An Autocrypt Level 1 MUA MUST generate a Setup Code as
    UTF-8 string of 36 numeric characters, divided into nine blocks of four,
    separated by dashes. The dashes are part of the secret code and there
    are no spaces. This format holds about 119 bits of entropy. It is
    designed to be unambiguous, pronounceable, script-independent (Chinese,
    Cyrillic etc.), easily input on a mobile device and split into blocks
    that are easily kept in short term memory.
    """
    random_data = random_data or os.urandom(16)  # 16 bytes = 128 bits entropy
    ints = struct.unpack('>4I', random_data[:16])
    ival = ints[0] + (ints[1] << 32) + (ints[2] << 64) + (ints[3] << 96)
    blocks = []
    while len(blocks) < 9:
        blocks.append('%4.4d' % (ival % 10000))
        ival //= 10000
    return '-'.join(blocks)


# FIXME: Add a with_signing_subkeys=True, implement. This deviates
#        from the Autocrypt spec, because Autocrypt says nothing about
#        signatures. But we're almost always signing our mail, and w/o
#        the subkeys the signatures cannot be checked.
def UNUSED_get_minimal_PGP_key(keydata,
                               user_id=None, subkey_id=None, binary_out=False):
    """
    Accepts a PGP key (armored or binary) and returns a minimal PGP key
    containing exactly five packets (base64 or binary) defining a
    primary key, a single user id with one self-signature, and a
    single encryption subkey with one self-signature. Such a five packet
    key MUST be used in Autocrypt headers (Level 1 Spec section 2.1.1).
    The unrevoked user id with newest unexpired self-signature and the
    unrevoked encryption-capable subkey with newest unexpired
    self-signature are selected from the input key.
    If user_id is provided, a user id containing that string will be
    selected if there is one, otherwise any user id will be accepted.
    If subkey_id is specified, only a subkey with that id will be selected.

    Along with the new key, the selected user id and subkey id are returned.
    Returns None if there is a failure.
    """
    def _get_int4(data, offset):
        '''Pull four bytes from data at offset and return as an integer.'''
        return ((data[offset] << 24) + (data[offset + 1] << 16) +
                (data[offset + 2] << 8) + data[offset + 3])

    def _exp_time(creation_time, exp_time_subpacket_data):

        life_s = _get_int4(exp_time_subpacket_data, 0)
        if not life_s:
            return 0
        return packet.creation_time + datetime.timedelta( seconds = life_s)

    def _pgp_header(type, body_length):

        if body_length < 192:
            return bytearray([type+0xC0, body_length])
        elif body_length < 8384:
            return bytearray([type+0xC0, (body_length-192)//256+192,
                                                 (body_length-192)%256])
        else:
            return bytearray([type+0xC0, 255,
                    body_length//(1<<24), body_length//(1<<16) % 256,
                    body_length//1<<8 % 256, body_length % 256])

    pri_key = None
    u_id = None
    u_id_sig = None
    u_id_match = False
    s_key = None
    s_key_sig = None
    user_id = canonicalize_email(user_id) if user_id else None
    now = datetime.datetime.utcfromtimestamp(time.time())

    if '-----BEGIN PGP PUBLIC KEY BLOCK-----' in keydata:
        packet_iter = pgpdump.AsciiData(keydata).packets()
    else:
        packet_iter = pgpdump.BinaryData(keydata).packets()

    try:
        packet = next(packet_iter)
    except:
        packet = None

    while packet:

        if packet.raw == 6 and pri_key:     # Primary key must be the first
            break                           # and only the first packet.
        elif packet.raw != 6 and not pri_key:
            break

        elif packet.raw == 6:               # Primary Public-Key Packet
            pri_key = packet

        elif packet.raw == 13:              # User ID Packet
            u_id_try = packet
            u_id_sig_try = None
            u_id_try_match = (
                not user_id or (user_id == canonicalize_email(u_id_try.user)))

            # Accept a nonmatching u_id IFF no other u_id matches.
            if u_id_match and not u_id_try_match:
                u_id_try = None

            for packet in packet_iter:
                if packet.raw != 2:         # Signature Packet
                    break
                elif not u_id_try:
                    continue
                                            # User ID certification
                elif packet.raw_sig_type in (0x10, 0x11, 0x12, 0x13, 0x1F):
                    if (pri_key.fingerprint.endswith(packet.key_id) and
                            (not packet.expiration_time or
                                packet.expiration_time > now) and
                            (not u_id_sig_try or
                                u_id_sig_try.creation_time
                                    < packet.creation_time)):
                        u_id_sig_try = packet
                                            # Certification revocation
                elif packet.raw_sig_type == 0x30:
                    if pri_key.fingerprint.endswith(packet.key_id):
                        u_id_try = None
                        u_id_sig_try = None

            # Select unrevoked user id with newest unexpired self-signature
            if u_id_try and u_id_sig_try and (
                    not u_id or not u_id_sig or
                    u_id_try_match and not u_id_match or
                    u_id_sig_try.creation_time >= u_id_sig.creation_time):
                u_id = u_id_try
                u_id_sig = u_id_sig_try
                u_id_match = u_id_try_match
            continue    # Skip next(packet_iter) - for has done it.

        elif packet.raw == 14:              # Public-Subkey Packet
            s_key_try = packet
            s_key_sig_try = None

            # Honour a request for specific subkey and check for expiry.
            if ((subkey_id and not s_key_try.fingerprint.endswith(subkey_id))
                    or (s_key_try.expiration_time and
                        s_key_try.expiration_time < now)):
                s_key_try = None

            for packet in packet_iter:
                if packet.raw != 2:         # Signature Packet
                    break
                elif not s_key_try:
                    continue
                                            # Subkey Binding Signature
                elif packet.raw_sig_type == 0x18:
                    packet.key_expire_time = None
                    if (pri_key.fingerprint.endswith(packet.key_id) and
                            not packet.expiration_time or
                            packet.expiration_time >= now):
                        can_encrypt = True  # Assume encrypt -- FIXME
                        for subpacket in packet.subpackets:
                            if subpacket.subtype == 9:  # Key expiration
                                packet.key_expire_time = _exp_time(
                                    packet.creation_time, subpacket.data)
                            elif subpacket.subtype == 27:   # Key flags
                                can_encrypt |= subpacket.data[0] & 0x0C
                        if can_encrypt and (not packet.key_expire_time or
                                            packet.key_expire_time >= now):
                            s_key_sig_try = packet
                                            # Subkey revocation signature
                elif packet.raw_sig_type == 0x28:
                    if pri_key.fingerprint.endswith(packet.key_id):
                        s_key_try = None
                        s_key_sig_try = None

            # Select unrevoked encryption-capable subkey with newest
            # unexpired self-signature (ignores newness of key itself).
            if s_key_try and s_key_sig_try and (not s_key_sig or
                    s_key_sig_try.creation_time >= s_key_sig.creation_time):
                s_key = s_key_try
                s_key_sig = s_key_sig_try
            continue    # Skip next(packet_iter) - for has done it.

        try:
            packet = next(packet_iter)
        except:
            packet = None

    if not(pri_key and u_id and u_id_sig and s_key and s_key_sig):
        return '', None, None

    newkey = (
        _pgp_header(pri_key.raw, len(pri_key.data)) + pri_key.data +
        _pgp_header(u_id.raw, len(u_id.data)) + u_id.data +
        _pgp_header(u_id_sig.raw, len(u_id_sig.data)) + u_id_sig.data +
        _pgp_header(s_key.raw, len(s_key.data)) + s_key.data +
        _pgp_header(s_key_sig.raw, len(s_key_sig.data)) + s_key_sig.data )

    if not binary_out:
        newkey = base64.b64encode(newkey)

    return newkey, u_id.user, s_key.key_id


class AutocryptRecommendation(object):
    DISABLE    = "disable"
    DISCOURAGE = "discourage"
    ENABLE     = "enable"
    ENCRYPT    = "encrypt"

    ORDERED_POLICIES = (DISABLE, DISCOURAGE, ENABLE, ENCRYPT)

    def __init__(self, policy, key_sig=None):
        self.key_sig = self._policy = None
        self.set_recommendation(policy, key_sig)

    def __str__(self):
        if self.policy in (self.DISABLE,):
            return self.policy
        return "%s (key=%s)" % (self.policy, self.key_sig)

    @classmethod
    def Synchronize(cls, *recommendations):
        """
        This will synchronize a set of Autocrypt recommendations to whatever
        the lowest common denomitor is, and then return that policy.
        """
        if not recommendations:
            return cls.DISABLE
        lowest_common_policy = cls.ORDERED_POLICIES[min(
            cls.ORDERED_POLICIES.index(r.policy) for r in recommendations)]
        for r in recommendations:
            r.policy = lowest_common_policy
        return lowest_common_policy

    def set_recommendation(self, policy, key_sig=None):
        if policy not in self.ORDERED_POLICIES:
            raise ValueError('Invalid Autocrypt policy: %s' % policy)
        if policy != self.DISABLE and key_sig is None and self.key_sig is None:
            raise ValueError('Policy %s requires a key' % policy)
        self._policy = policy
        if key_sig is not None:
            self.key_sig = key_sig

    policy = property(lambda self: self._policy, set_recommendation)


if __name__ == "__main__":
    import sys
    import doctest

    results = doctest.testmod(optionflags=doctest.ELLIPSIS)
    print('%s' % (results, ))
    if results.failed:
        sys.exit(1)
