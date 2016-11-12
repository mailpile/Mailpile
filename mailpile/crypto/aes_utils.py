# This is a compatibility wrapper for using whatever AES library is
# handy. By default we just support Crypto.Cipher

try:
    from Crypto.Cipher import AES
    from Crypto.Random.random import getrandbits

    def aes_cbc_encrypt(key, iv, data):
        return AES.new(key, mode=AES.MODE_CBC, IV=iv).encrypt(data)

    def aes_cbc_decrypt(key, iv, data):
        return AES.new(key, mode=AES.MODE_CBC, IV=iv).decrypt(data)

except ImportError:
    # FIXME: Support more crypto libs?

    raise  # Comment out to allow insecure, unencrypted record stores
    print
    print '========================================================'
    print '  * WARNING WARNING WARNING *   import Crypto failed!   '
    print '========================================================'
    print

    def getrandbits(bits):
        return 0

    def aes_cbc_encrypt(key, iv, data):
        return data

    def aes_cbc_decrypt(key, iv, data):
        return data
