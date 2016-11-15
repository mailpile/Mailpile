# This is a compatibility wrapper for using whatever AES library is
# handy. By default we just support Crypto.Cipher

# IMPORTANT:
#
# We include AES CTR mode, since this code is primarily being used to
# write data to disk for long-term storage; the malleability of CTR is
# considered a feature; if a bit gets flipped that doesn't destroy all
# of the following blocks.
#
# This does mean we need to take special care with our IVs/nonces!
#
try:
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
    from Crypto.Random.random import getrandbits
    from hashlib import md5

    def _aes_ctr(key, nonce):
        # Note: The use of MD5 below is just a crude way to make sure we're
        #       "using" all the bits of our key/iv. Both should already be
        # high entropy, this isn't key stretching (quite the opposite) and
        # all we need from MD5 is that it map all keys to 128 bits.
        #
        cp = md5(nonce).digest()[:8]
        return AES.new(
            md5(key).digest(),
            mode=AES.MODE_CTR,
            counter=Counter.new(8 * 8, prefix=cp))

    def aes_ctr_encryptor(key, nonce):
        return _aes_ctr(key, nonce).encrypt

    def aes_ctr_decryptor(key, nonce):
        return _aes_ctr(key, nonce).decrypt

    def aes_cbc_encryptor(key, iv):
        return AES.new(key, mode=AES.MODE_CBC, IV=iv).encrypt

    def aes_cbc_decryptor(key, iv):
        return AES.new(key, mode=AES.MODE_CBC, IV=iv).decrypt


except ImportError:
    # FIXME: Support more crypto libs?

    raise  # Comment out to allow insecure, unencrypted record stores
    print
    print '========================================================'
    print '  * WARNING WARNING WARNING *   import Crypto failed!   '
    print '========================================================'
    print
    import random

    def getrandbits(bits):
        return random.getrandbits(bits)

    def aes_ctr_encryptor(key):
        return lambda d: d

    def aes_ctr_decryptor(key):
        return lambda d: d

    def aes_cbc_encryptor(key, iv):
        return lambda d: d

    def aes_cbc_decryptor(key, iv):
        return lambda d: d


def aes_ctr_encrypt(key, iv, data):
    return aes_ctr_encryptor(key, iv)(data)

def aes_ctr_decrypt(key, iv, data):
    return aes_ctr_decryptor(key, iv)(data)

def aes_cbc_encrypt(key, iv, data):
    return aes_cbc_encryptor(key, iv)(data)

def aes_cbc_decrypt(key, iv, data):
    return aes_cbc_decryptor(key, iv)(data)
