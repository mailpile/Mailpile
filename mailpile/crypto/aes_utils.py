# This is a compatibility wrapper for using whatever AES library is
# handy. By default we just support Crypto.Cipher

from Crypto.Cipher import AES
from Crypto.Random.random import getrandbits

def aes_cbc_encrypt(key, iv, data):
    return AES.new(key, mode=AES.MODE_CBC, IV=iv).encrypt(data)

def aes_cbc_decrypt(key, iv, data):
    return AES.new(key, mode=AES.MODE_CBC, IV=iv).decrypt(data)
