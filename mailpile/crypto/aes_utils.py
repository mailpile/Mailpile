from __future__ import print_function
# This is a compatibility wrapper for using whatever AES library is handy.
# By default we support Cryptography and pyCrypto, with a preference for
# Cryptography.

# IMPORTANT:
#
# We currently only implement AES CTR mode, since this code is primarily
# being used to write data to disk for long-term storage; the malleability
# of CTR is considered a feature; if a bit gets flipped that doesn't destroy
# all of the following blocks.
#
# This does mean we need to take special care with our IVs/nonces!
#
import os
import struct
from hashlib import md5


def make_cryptography_utils():
    import os
    import cryptography.hazmat.backends
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    def _aes_ctr(key, nonce):
        # Notes:
        #
        # The funky business with the prefixed nonce is because the first
        # iteration of this code used pycrypto's Crypto.Util.Counter with
        # the prefix argument. Cryptography doesn't have such a counter API,
        # but if we carefully set the nonce we can achieve compatibility.
        #
        # The MD5 digests save the caller from having to know our internal
        # size requirements; AES wants 128, we just mix all the bits we're
        # given. We expect the input to already be strongly random (so MD5's
        # weaknesses shouldn't matter), but it may of the wrong size.
        #
        hashed_key = md5(key).digest()
        prefixed_nonce = md5(nonce).digest()[:8] + '\0\0\0\0\0\0\0\1'
        return Cipher(
            algorithms.AES(hashed_key),
            modes.CTR(prefixed_nonce),
            backend=cryptography.hazmat.backends.default_backend())

    def aes_ctr_encryptor(key, nonce):
        return _aes_ctr(key, nonce).encryptor().update

    def aes_ctr_decryptor(key, nonce):
        return _aes_ctr(key, nonce).decryptor().update

    return aes_ctr_encryptor, aes_ctr_decryptor


def make_pycrypto_utils():
    from Crypto.Cipher import AES
    from Crypto.Util import Counter

    def _nonce_as_int(nonce):
        i1, i2, i3, i4 = struct.unpack(">IIII", nonce)
        return (i1 << 96 | i2 << 64 | i3 << 32 | i4)

    def _aes_ctr(key, nonce):
        # Notes:
        #
        # A previous iteration of this code used the Counter with a prefix,
        # which limited us to 2**64 iterations. This has been change to just
        # set an initial value and allow wraparound.
        #
        # The MD5 digests save the caller from having to know our internal
        # size requirements; AES wants 128, we just mix all the bits we're
        # given. We expect the input to already be strongly random (so MD5's
        # weaknesses shouldn't matter), but it may of the wrong size.
        #
        hashed_key = md5(key).digest()
        prefixed_nonce = md5(nonce).digest()[:8] + '\0\0\0\0\0\0\0\1'
        counter = Counter.new(128, initial_value=_nonce_as_int(prefixed_nonce))
        return AES.new(hashed_key, mode=AES.MODE_CTR, counter=counter)

    def aes_ctr_encryptor(key, nonce):
        return _aes_ctr(key, nonce).encrypt

    def aes_ctr_decryptor(key, nonce):
        return _aes_ctr(key, nonce).decrypt

    return aes_ctr_encryptor, aes_ctr_decryptor


def make_dummy_utils():
    def aes_ctr_encryptor(key):
        return lambda d: d

    def aes_ctr_decryptor(key):
        return lambda d: d

    return aes_ctr_encryptor, aes_ctr_decryptor


##############################################################################

try:
    aes_ctr_encryptor, aes_ctr_decryptor = make_cryptography_utils()
except ImportError:
    try:
        aes_ctr_encryptor, aes_ctr_decryptor = make_pycrypto_utils()
    except ImportError:
        raise ImportError("Please pip install cryptography (or pycrypto)")


def getrandbits(count):
    bits = os.urandom(count // 8)
    rint = 0
    while bits:
        rint = (rint << 8) | struct.unpack("B", bits[0])[0]
        bits = bits[1:]
    return rint

def aes_ctr_encrypt(key, iv, data):
    return aes_ctr_encryptor(key, iv)(data)

def aes_ctr_decrypt(key, iv, data):
    return aes_ctr_decryptor(key, iv)(data)


if __name__ == "__main__":
    import base64

    bogus_key = "01234567890abcdef"
    bogus_nonce = "this is a bogus nonce that is bogus"
    hello = "hello world"

    results = []
    for name, backend in (('Cryptography', make_cryptography_utils),
                          ('pyCrypto', make_pycrypto_utils)):
        aes_ctr_encryptor, aes_ctr_decryptor = backend()

        ct1 = aes_ctr_encryptor(bogus_key, bogus_nonce)(hello)
        results.append((name, base64.b64encode(ct1)))

        ct2 = aes_ctr_encrypt(bogus_key, bogus_nonce, hello)
        results.append((name, base64.b64encode(ct2)))

        assert(aes_ctr_decrypt(bogus_key, bogus_nonce, ct1) ==
               aes_ctr_decryptor(bogus_key, bogus_nonce)(ct1) ==
               hello)


    # Make sure all the results are the same
    okay = True
    r1 = results[0]
    for result in results[1:]:
        if r1[1] != result[1]:
            print('%s != %s' % (r1, result))
            okay = False
    assert(okay)

    # This verifies we can decrypt some snippets of data that were
    # generated with a previous iteration of mailpile.crypto.streamer
    from mailpile.util import sha512b64 as genkey
    legacy_data = "part two, yeaaaah\n"
    legacy_nonce = "2c1c43936034cae20eef86d961cb6570"
    legacy_key = genkey("test key", legacy_nonce)[:32].strip()
    legacy_ct = base64.b64decode("D+lBOPrtV+amUCAtoFPCzxsZ")
    decrypted = aes_ctr_decrypt(legacy_key, legacy_nonce, legacy_ct)
    assert(legacy_data == decrypted)

    print("ok")
