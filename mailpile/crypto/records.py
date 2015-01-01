import hashlib
import os
import struct
import time
import threading

from aes_utils import getrandbits, aes_cbc_encrypt, aes_cbc_decrypt


class EncryptedRecordShard(object):
    # This is an AES encrypted record storage. Data is written out base64
    # encoded, with 64 characters per line + CRLF, as that is likely to
    # make it in and out of IMAP servers or other mail stores unchanged,
    # while giving us a round multiple of what both AES and Base64 can
    # handle without padding.

    _HEADER = ('X-Mailpile-Encrypted-Records: v1\r\n'
               'From: Mailpile <encrypted@mailpile.is>\r\n'
               'Subject: %(filename)s\r\n'
               'cipher: aes-256-cbc\r\n'
               'record-size: %(record_size)d\r\n'
               'iv-seed: %(ivs)s\r\n'
               '\r\n')

    def __init__(self, fn, key, max_bytes=400, overwrite=False):
        key_hash = bytes(hashlib.sha256(key.decode('utf-8')).digest())

        self._NEWLINE = '\r\n'
        self._max_bytes = max_bytes
        self._calculate_constants()

        self._iv_seed = getrandbits(48)
        self._iv_seed_random = '%x' % getrandbits(64)
        self._aes_key = key_hash[:16]
        self._header_data = {
            'record_size': self._RECORD_SIZE,
            'filename': fn,
            'ivs': '%12.12x' % self._iv_seed
        }
        self._lock = threading.RLock()

        try:
            self._fd = open(fn, 'wb+' if overwrite else 'rb+')
        except (OSError, IOError):
            self._fd = open(fn, 'wb+')

        if not self._parse_header():
            self._write_header()
        assert(max_bytes <= self._max_bytes)

    def _calculate_constants(self):
        # Calculate our constants! Magic numbers:
        #  - 48 is how much data fits in 64 byte of base64
        #  - 16 is the size of the IV
        #  - 7 is the minimum size of our checksum
        self._RECORD_LINES = max(1, int((self._max_bytes + 7 + 16) / 48) + 1)
        self._RECORD_SIZE = self._RECORD_LINES * 48
        self._MAX_DATA_SIZE = self._RECORD_SIZE - (7 + 16)
        self._RECORD_LINE_BYTES = 64
        self._ZERO_RECORD = '\0' * self._RECORD_SIZE
        self._RECORD_BYTES =  self._RECORD_LINES * (self._RECORD_LINE_BYTES +
                                                    len(self._NEWLINE))

    def _parse_header(self):
        self._fd.seek(0)
        try:
            header = self._fd.read(len(self._HEADER % self._header_data) + 1024)
            if not header:
                return False

            if '\n' in header and self._NEWLINE not in header:
                self._NEWLINE = '\n'
            header = header.split(self._NEWLINE + self._NEWLINE)[0]
            headers = dict(hl.strip().split(': ', 1)
                           for hl in header.splitlines())

            self._header_skip = len(header) + len(self._NEWLINE) * 2
            self._iv_seed = long(headers['iv-seed'], 16) + 1024000
            self._max_bytes = int(headers['record-size']) - (7 + 16)
            self._header_data = {
                'record_size': int(headers['record-size']),
                'filename': headers['Subject'],
                'ivs': headers['iv-seed']
            }
            self._calculate_constants()
            return True

        except IOError:
            return False
        except (KeyError, ValueError, AssertionError):
            import traceback
            traceback.print_exc()
            return False

    def _write_header(self):
        with self._lock:
            self._header_data['ivs'] = '%12.12x' % self._iv_seed
            header = self._HEADER % self._header_data
            self._fd.seek(0)
            self._fd.write(header)
            self._header_skip = len(header)

    def close(self):
        self._write_header()
        self._fd.close()

    def _iv(self, pos):
        # Here we generate an IV that should never repeat: the first 6 bytes
        # are derived from a random counter created at program startup, the
        # rest is pseudorandom crap.
        with self._lock:
            self._iv_seed += 1
            self._iv_seed %= 0x1000000000000L
            if (self._iv_seed % 123456) == 0:
                self._write_header()

            self._iv_seed_random = hashlib.sha512(self._iv_seed_random
                                                  ).digest()

        iv = bytes(struct.pack('<Q', self._iv_seed)[:6] +
                   self._iv_seed_random)

        return iv[:16]

    def save_record(self, pos, data):
        assert(len(data) < self._MAX_DATA_SIZE)

        iv = self._iv(pos)

        # We're using MD5 as a checksum here to detect corruption.
        cks = hashlib.md5(data).hexdigest()

        # We use the checksum as padding, where we are guaranteed by the
        # assertion above to have room for at least 6 nybbles of the MD5.
        record = (data + ':' + cks + self._ZERO_RECORD)[:self._RECORD_SIZE]
        encrypted = (iv + aes_cbc_encrypt(self._aes_key, iv, record)
                     ).encode('base64').replace('\n', '')

        with self._lock:
            self._fd.seek(self._header_skip + pos * self._RECORD_BYTES)
            for i in range(0, self._RECORD_LINES):
                self._fd.write(encrypted[i * self._RECORD_LINE_BYTES :
                                         (i+1) * self._RECORD_LINE_BYTES])
                self._fd.write(self._NEWLINE)

    def load_record(self, pos):
        with self._lock:
            self._fd.seek(self._header_skip + pos * self._RECORD_BYTES)
            encrypted = self._fd.read(self._RECORD_BYTES).decode('base64')
        iv, encrypted = encrypted[:16], encrypted[16:]

        plaintext, checksum = aes_cbc_decrypt(self._aes_key, iv, encrypted
                                              ).rsplit(':', 1)

        checksum = bytes(checksum.replace('\0', ''))
        assert(len(checksum) >= 6)
        assert(hashlib.md5(plaintext).hexdigest().startswith(checksum))

        return plaintext

    def __getitem__(self, pos):
        return self.load_record(pos)

    def __setitem__(self, pos, data):
        return self.save_record(pos, data)

    def __len__(self):
        with self._lock:
            self._fd.seek(0, 2)
            size = self._fd.tell()
        return (size - self._header_skip) // self._RECORD_BYTES


class EncryptedRecordStore(object):
  
    _BIG_POINTER = '\0B->'

    def __init__(self, base_fn, key,
                 max_bytes=400, shard_size=50000, big_ratio=10,
                 overwrite=False):
        self._base_fn = base_fn
        self._key = key
        self._max_bytes = max(max_bytes, 50)
        self._shard_size = max(int(shard_size), 1024)
        self._big_ratio = float(big_ratio)
        self._overwrite = overwrite

        self._shards = []
        self._load_next_shard()
        while os.path.exists(self._next_shardname()):
            self._load_next_shard()

        self._big_map = {}
        self._big_shard = None

    s0 = property(lambda self: self._shards[0])

    def _big(self):
        if self._big_shard is None:
            self._big_shard = EncryptedRecordStore(
                '%s-b' % self._base_fn,
                self._key,
                max_bytes=self._max_bytes * self._big_ratio,
                shard_size=self._shard_size / self._big_ratio,
                big_ratio=self._big_ratio,
                overwrite=self._overwrite)
        return self._big_shard

    def _next_shardname(self):
        return '%s-%s' % (self._base_fn, len(self._shards) + 1)

    def _load_next_shard(self):
        self._shards.append(EncryptedRecordShard(self._next_shardname(),
                                                 self._key,
                                                 max_bytes=self._max_bytes,
                                                 overwrite=self._overwrite))

    def __getitem__(self, pos):
        shard, pos = pos // self._shard_size, pos % self._shard_size
        value = self._shards[shard][pos]
        if value.startswith(self._BIG_POINTER):
            self._big_map[pos] = int(data[len(self._BIG_POINTER):], 16)
            return self._big()[self._big_map[pos]]
        else:
            return value

    def __setitem__(self, pos, data):
        shard, pos = pos // self._shard_size, pos % self._shard_size
        while shard >= len(self._shards):
            self._load_next_shard()
        if len(data) >= self.s0._MAX_DATA_SIZE:
            bpos = self._big_map.get(pos, len(self._big()))
            self._big()[bpos] = data
            self._big_map[pos] = bpos
            data = '%s%x' % (len(self._BIG_POINTER), bpos)
        self._shards[shard][pos] = data

    def __len__(self):
        return (self._shard_size * (len(self._shards) - 1) +
                len(self._shards[-1]))

    def close(self):
        for s in self._shards:
            s.close()
        if self._big_shard is not None:
            self._big_shard.close()


if __name__ == '__main__':
    for size in (16, 50, 100, 200, 400, 800, 1600):
        er = EncryptedRecordStore('/tmp/tmp.aes', 'this is my secret key',
                                  max_bytes=size, overwrite=True)
        print('Testing max_size=%d, real max=%d, lines=%d'
              % (size, er.s0._MAX_DATA_SIZE, er.s0._RECORD_LINES))
        for l in range(0, 20):
            er[l] = 'bjarni %s' % l
        for l in range(0, 20):
            assert(er[l] == 'bjarni %s' % l)
        assert(len(er) == 20)

    er = EncryptedRecordStore('test.aes', 'this is my secret key', 740,
                              big_ratio=4, overwrite=True)
    t0 = time.time()
    count = 100 * 1024 + 4321
    for l in range(0, count):
        data = ('bjarni is a happy camper with plenty of stuff '
                'we must pad this with gibberish and make it '
                'a fair bit longer, so it makes a good test '
                'to say about this and that and the other')
        if (l % 1024) == 5:
            data = data * 74
        er[l % 1024 ] = data
    done = time.time()
    print ('100k record writes in %.2f (%.8f s/op)'
           % (done - t0, (done - t0) / count))
    assert(len(er) == 1024)

    t0 = time.time()
    for l in range(0, count):
        er[l % 1024]

    done = time.time()
    print ('100k record reads in %.2f (%.8f s/op)'
           % (done - t0, (done - t0) / count))
    er.close()
