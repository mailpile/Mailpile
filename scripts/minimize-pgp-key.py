#!/usr/bin/python
#
# Standalone script for minimizing PGP keys, using the same logic as
# we use for Autocrypt.
#
from mailpile.crypto.autocrypt import get_minimal_PGP_key
import os

if __name__ == "__main__":
    default_file = os.path.dirname(os.path.abspath(__file__))
    default_file = os.path.abspath(default_file + '/../tests/data/pub.key')

    print
    print 'Default key file:', default_file
    print

    key_file_path = raw_input('Enter key file path or <Enter> for default: ')
    if key_file_path == '':
        key_file_path = default_file

    user_id = raw_input('Enter email address: ')
    if user_id == '':
        user_id = None

    subkey_id = raw_input('Enter subkey_id: ')
    if subkey_id == '':
        subkey_id = None

    with open(key_file_path, 'r') as keyfile:
        keydata = bytearray( keyfile.read() )

    print 'Key length:', len(keydata)

    newkey, u, i = get_minimal_PGP_key(
        keydata, user_id=user_id, subkey_id=subkey_id, binary_out=True)

    print 'User ID:', u
    print 'Subkey ID:', i
    print 'Minimal key length:', len(newkey)
    key_file_path += '.min.gpg'
    print 'Minimal key output file:', key_file_path

    with open(key_file_path, 'w') as keyfile:
        keyfile.write(newkey)
