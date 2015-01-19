#!/usr/bin/python

from Crypto.Cipher import AES
from Crypto.Random.random import getrandbits
import hashlib
import struct
import time


class EncryptedRecordStore(object):
    # This is an AES encrypted record storage. Data is written out base64
    # encoded, with 64 characters per line + CRLF, as that is likely to
    # make it in and out of IMAP servers or other mail stores unchanged,
    # while giving us a round multiple of what both AES and Base64 can
    # handle without padding.

    HEADER = ('X-Mailpile-Encrypted-Records: v1\r\n'
              'From: Mailpile <encrypted@mailpile.is>\r\n'
              'Subject: %(filename)s\r\n'
              'cipher: aes-256-cbc\r\n'
              'record-size: %(record_size)d\r\n'
              'iv-seed: %(ivs)s\r\n'
              '\r\n')

    def __init__(self, fn, key, max_bytes=400, overwrite=False):
        key_hash = bytes(hashlib.sha256(key.decode('utf-8')).digest())

        self.NEWLINE = '\r\n'
        self.max_bytes = max_bytes
        self.calculate_constants()

        self.iv_seed = getrandbits(48)
        self.iv_seed_random = '%x' % getrandbits(64)
        self.aes_key = key_hash[:16]
        self.header_data = {
            'record_size': self.RECORD_SIZE,
            'filename': fn,
            'ivs': '%12.12x' % self.iv_seed
        }

        try:
            self.fd = open(fn, 'wb+' if overwrite else 'rb+')
        except (OSError, IOError):
            self.fd = open(fn, 'wb+')

        if not self.parse_header():
            self.write_header()
        assert(max_bytes <= self.max_bytes)

    def calculate_constants(self):
        # Calculate our constants! Magic numbers:
        #  - 48 is how much data fits in 64 byte of base64
        #  - 16 is the size of the IV
        #  - 7 is the minimum size of our checksum
        self.RECORD_LINES = max(1, int((self.max_bytes + 7 + 16) / 48) + 1)
        self.RECORD_SIZE = self.RECORD_LINES * 48
        self.MAX_DATA_SIZE = self.RECORD_SIZE - (7 + 16)
        self.RECORD_LINE_BYTES = 64
        self.ZERO_RECORD = '\0' * self.RECORD_SIZE
        self.RECORD_BYTES =  self.RECORD_LINES * (self.RECORD_LINE_BYTES +
                                                  len(self.NEWLINE))

    def parse_header(self):
        self.fd.seek(0)
        try:
            header = self.fd.read(len(self.HEADER % self.header_data) + 1024)
            if not header:
                return False

            if '\n' in header and self.NEWLINE not in header:
                self.NEWLINE = '\n'
            header = header.split(self.NEWLINE + self.NEWLINE)[0]
            headers = dict(hl.strip().split(': ', 1)
                           for hl in header.splitlines())

            self.header_skip = len(header) + len(self.NEWLINE) * 2
            self.iv_seed = long(headers['iv-seed'], 16) + 1024000
            self.max_bytes = int(headers['record-size']) - (7 + 16)
            self.header_data = {
                'record_size': int(headers['record-size']),
                'filename': headers['Subject'],
                'ivs': headers['iv-seed']
            }
            self.calculate_constants()
            return True

        except IOError:
            return False
        except (KeyError, ValueError, AssertionError):
            import traceback
            traceback.print_exc()
            return False

    def write_header(self):
        self.header_data['ivs'] = '%12.12x' % self.iv_seed
        header = self.HEADER % self.header_data
        self.fd.seek(0)
        self.fd.write(header)
        self.header_skip = len(header)

    def close(self):
        self.write_header()
        self.fd.close()

    def _iv(self, pos):
        # Here we generate an IV that should never repeat: the first 6 bytes
        # are derived from a random counter created at program startup, the
        # rest is pseudorandom crap.
        self.iv_seed += 1
        self.iv_seed %= 0x1000000000000L
        if (self.iv_seed % 123456) == 0:
            self.write_header()

        self.iv_seed_random = hashlib.sha512(self.iv_seed_random).digest()
        iv = bytes(struct.pack('<Q', self.iv_seed)[:6] +
                   self.iv_seed_random)

        return iv[:16]

    def save_record(self, pos, data):
        assert(len(data) < self.MAX_DATA_SIZE)

        iv = self._iv(pos)
        aes = AES.new(self.aes_key, mode=AES.MODE_CBC, IV=iv)

        # We're using MD5 as a checksum here to detect corruption.
        cks = hashlib.md5(data).hexdigest()

        # We use the checksum as padding, where we are guaranteed by the
        # assertion above to have room for at least 6 nybbles of the MD5.
        record = (data + ':' + cks + self.ZERO_RECORD)[:self.RECORD_SIZE]
        encrypted = (iv + aes.encrypt(record)).encode('base64')
        encrypted = encrypted.replace('\n', '')

        self.fd.seek(self.header_skip + pos * self.RECORD_BYTES)
        for i in range(0, self.RECORD_LINES):
            self.fd.write(encrypted[i * self.RECORD_LINE_BYTES :
                                    (i+1) * self.RECORD_LINE_BYTES])
            self.fd.write(self.NEWLINE)

    def load_record(self, pos):
        self.fd.seek(self.header_skip + pos * self.RECORD_BYTES)
        encrypted = self.fd.read(self.RECORD_BYTES).decode('base64')
        iv, encrypted = encrypted[:16], encrypted[16:]

        aes = AES.new(self.aes_key, mode=AES.MODE_CBC, IV=iv)
        plaintext, checksum = aes.decrypt(encrypted).rsplit(':', 1)

        checksum = bytes(checksum.replace('\0', ''))
        assert(len(checksum) >= 6)
        assert(hashlib.md5(plaintext).hexdigest().startswith(checksum))

        return plaintext


for size in (16, 50, 100, 200, 400, 800, 1600):
    er = EncryptedRecordStore('/tmp/tmp.aes', 'this is my secret key',
                              max_bytes=size, overwrite=True)
    print('Testing max_size=%d, real max=%d, lines=%d'
          % (size, er.MAX_DATA_SIZE, er.RECORD_LINES))
    for l in range(0, 20):
        er.save_record(l, 'bjarni %s' % l)
    for l in range(0, 20):
        assert(er.load_record(l) == 'bjarni %s' % l)

er = EncryptedRecordStore('test.aes', 'this is my secret key', 740)
t0 = time.time()
count = 100 * 1024 + 4321
for l in range(0, count):
    er.save_record(l % 1024, 'bjarni is a happy camper with plenty of stuff '
                             'we must pad this with gibberish and make it '
                             'a fair bit longer, so it makes a good test '
                             'to say about this and that and the other')
done = time.time()
print ('100k record writes in %.2f (%.8f s/op)'
       % (done - t0, (done - t0) / count))

t0 = time.time()
for l in range(0, count):
    er.load_record(l % 1024)
done = time.time()
print ('100k record reads in %.2f (%.8f s/op)'
       % (done - t0, (done - t0) / count))
er.close()
