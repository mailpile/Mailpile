"""
Record-based AES encrypted data storage

This is a collection of modules designed to allow for easy Pythonic use
of encrypted data stores.

The basics are provided by EncryptedRecordStore, which defines the
on-disk storage format (largely compatible with RFC2822) and takes care
of the encryption and decryption of records.

The EncryptedBlobStore provides a subset of Pythonic list semantics,
extending EncryptedRecordStore to allow for arbitrarily sized elements
and splitting the storage accross multiple files to play nice with
backups, network-based storage and other environments where huge files
might be a problem.

The EncryptedDict provides a subset of Pythonic dict semantics, using a
mixture of the above two classes.

Notes:

1. A simple SHA256 digest is used to derive an AES key. This would not
   be considered sufficient for low entropy (human generated) keys.
2. All data storage is record based, which implies nontrivial amounts
   of disk space may be wasted. On the other hand, this is good for
   security as it obscures the size of the data being stored.
3. The EncryptedDict uses the encryption key as a salt to ensure the
   hashing is not predictable to an attacker. Again, low entropy keys
   should be avoided.
4. No provisions are made to make it possible to change keys.
5. No buffering or caching of any kind is done.
6. Deleting entries is NOT supported anywhere. Overwriting works.

Performance thoughts:

The key to performance of these algorithms will ultimately depend on how
well the OS caches data. In general we can help with that by encouraging
hot spots, trying to cluster frequently used values together. The other
way we can help is to minimize wasted space within the records
themselves, so the OS doesn't waste RAM caching junk.

For the metadata index, we expect hot spot clustering to focus around
recently received mail. The default sorts are by date and most of the
time users are reading or organizing recently received mail. So the OS
should have a relatively easy time effectively caching records for
current metadata.

The case for posting lists, which naturally live in an EncryptedDict is
different but also promising. In general, the keyword index will grow
linearly with the number of index messages; in particular each message
ID is unique and will generate one or more new keywords in the index.
Thus the keyword index will have a very long tail of rarely used, small
entries. The expected performance of such entries (reads and writes) is
dominated by the disk seeks times. For these entries, we can save at
least one disk seek by storing the values along with the keys, but that
is about all we can do.

Conversely, some keywords will have a very high frequency; for example
virtually all English language messages will contain the word "the".
These common keywords will become hot spots during the indexing process,
so causing them to cluster together will again let us play nice with the
operating system caches. A basic strategy for this is to allow larger
entries to bump smaller ones from the front of each hash bucket to later
stages, as entry size correlates with keyword popularity. Another
optimization which is out of scope for this module, is they should
compress well as they will contain long sequential runs of message IDs.

From a frequency point of view, the middle-of-the-road keywords barely
matter; 94% of all keywords match fewer than 5 messages, about 0.16%
match over 1000 messages. On average about 17 keywords are generated
per message.

Detailed search keyword stats:

  emails  keywords   __________ratios__________
       2   4551468    88.21%  100.00%   88.21%
       4    290686     5.63%   11.79%   93.84%
       8    150924     2.92%    6.16%   96.77%
      16     74239     1.44%    3.23%   98.21%
      32     38341     0.74%    1.79%   98.95%
      64     20552     0.40%    1.05%   99.35%
     128     13178     0.26%    0.65%   99.60%
     256      7731     0.15%    0.40%   99.75%
     512      4640     0.09%    0.25%   99.84%
    1024      2793     0.05%    0.16%   99.90%
    2048      2141     0.04%    0.10%   99.94%
   >2048      3084     0.06%    0.06%  100.00%
          (sample size: ~300k emails)

"""
import hashlib
import os
import struct
import time
import threading

from aes_utils import getrandbits, aes_cbc_encrypt, aes_cbc_decrypt

#aes_cbc_encrypt = lambda k, i, v: v
#aes_cbc_decrypt = lambda k, i, v: v


class _SimpleList(object):
    """Some syntactic sugar for listalikes"""
    def append(self, value):
        with self._lock:
            pos = len(self)
            self[pos] = value
        return pos

    def extend(self, values):
        for v in values:
            self.append(v)

    def __getslice__(self, i, j):
        return [self[v] for v in range(i, j)]

    def __iadd__(self, y):
        self.extend(y)

    def __iter__(self):
        return (self[v] for v in range(0, len(self)))

    def __reversed__(self):
        return (self[v] for v in reversed(range(0, len(self))))


class EncryptedRecordStore(_SimpleList):
    """
    This is an on-disk AES encrypted record storage. Data is written
    out base64 encoded, with 64 characters per line + CRLF, as that is
    likely to make it in and out of IMAP servers or other mail stores
    unchanged, while giving us a round multiple of what both AES and
    Base64 can handle without padding.
    """

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
            self._iv_seed = long(headers['iv-seed'], 16) + 10240020
            self._max_bytes = int(headers['record-size']) - (7 + 16) - 1
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
        if not isinstance(data, str):
            raise ValueError('Data must be a str')
        elif len(data) > self._MAX_DATA_SIZE:
            raise ValueError('Data too big for record')

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

        if encrypted == '':
            raise KeyError(pos)
        assert(len(encrypted) == self._RECORD_SIZE)

        iv, encrypted = encrypted[:16], encrypted[16:]
        plaintext, checksum = aes_cbc_decrypt(self._aes_key, iv, encrypted
                                              ).rsplit(':', 1)

        checksum = bytes(checksum.replace('\0', ''))
        if (len(checksum) < 6):
            raise ValueError('Checksum too short')
        if not hashlib.md5(plaintext).hexdigest().startswith(checksum):
            print 'bad data: %s' % plaintext
            raise ValueError('Checksum mismatch')

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


class EncryptedBlobStore(_SimpleList):
    """
    This is an on-disk variable-sized, sharded AES encrypted blob
    storage. It augments EncryptedRecordStore by placing bounds on
    how large each encrypted file will become and allows data blobs
    of arbitrary size by bumping "large" records to a secondary (or
    tertiary, ...) store.
    """

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

        self._lock = threading.RLock()

        self._shards = []
        self._load_next_shard()
        while os.path.exists(self._next_shardname()):
            self._load_next_shard()

        self._big_map = {}
        self._big_shard = None

    s0 = property(lambda self: self._shards[0])

    def _big(self):
        with self._lock:
            if self._big_shard is None:
                self._big_shard = EncryptedBlobStore(
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
        with self._lock:
            self._shards.append(EncryptedRecordStore(
                self._next_shardname(),
                self._key,
                max_bytes=self._max_bytes,
                overwrite=self._overwrite))

    def __getitem__(self, pos):
        shard, pos = pos // self._shard_size, pos % self._shard_size
        value = self._shards[shard][pos]
        if value.startswith(self._BIG_POINTER):
            self._big_map[pos] = int(value[len(self._BIG_POINTER):], 16)
            return self._big()[self._big_map[pos]]
        else:
            return value

    def __setitem__(self, pos, data):
        shard, pos = pos // self._shard_size, pos % self._shard_size
        with self._lock:
            while shard >= len(self._shards):
                self._load_next_shard()
        if len(data) > self.s0._MAX_DATA_SIZE:
            with self._lock:
                bpos = self._big_map.get(pos, len(self._big()))
                self._big()[bpos] = data
                self._big_map[pos] = bpos
                data = '%s%x' % (self._BIG_POINTER, bpos)
        self._shards[shard][pos] = data

    def __len__(self):
        with self._lock:
            return (self._shard_size * (len(self._shards) - 1) +
                    len(self._shards[-1]))

    def close(self):
        with self._lock:
            for s in self._shards:
                s.close()
            if self._big_shard is not None:
                self._big_shard.close()
            self._shards = []
            self._big_shard = None


class EncryptedDict(object):
    """
    This is a variable-sized, sharded AES encrypted dict. It uses
    EncryptedRecordStore for hashing and EncryptedBlobStore for values
    that do not fit alongside the keys. At the moment, data can be
    overwritten, but not deleted.

    TODO:
        - Grow the dict by adding keysets
        - Migrating "exciting" keys to the primary keyset
    """

    _BUCKET_SIZE = 5
    _DIGEST_SIZE = 16
    _UNUSED = '\0U'

    def __init__(self, base_fn, key,
                 key_bytes=50, data_bytes=400, big_ratio=5,
                 shard_size=100000, min_shards=1, shard_ratio=2.0,
                 overwrite=False):
        self._base_fn = base_fn
        self._key = key
        self._key_bytes = key_bytes
        self._shard_ratio = shard_ratio  # Growth ratio when expanding
        self._data_bytes = data_bytes
        self._shard_size = max(int(shard_size), 1024)
        self._big_ratio = float(big_ratio)
        self._overwrite = overwrite

        self._lock = threading.RLock()

        self.writes = []
        self.reads = []
        self._keys = []
        while (os.path.exists(self._next_keyfile()[0]) or
                len(self._keys) < min_shards):
            self._load_next_keys()
        self.reset_counters()

        self._values = EncryptedBlobStore(self._base_fn, self._key,
                                          max_bytes=data_bytes,
                                          shard_size=shard_size,
                                          big_ratio=big_ratio,
                                          overwrite=overwrite)

    def reset_counters(self):
        self.writes = [0 for keyset in self._keys]
        self.reads = [0 for keyset in self._keys]

    def _keyfile_size(self, kfi):
        return int(self._shard_size * (self._shard_ratio**kfi))

    def _keyfile_bytes(self, kfi):
        return self._key_bytes

    def _next_keyfile(self):
        pos = len(self._keys)
        return '%s-k-%s' % (self._base_fn, pos + 1), pos

    def _load_next_keys(self):
        with self._lock:
            kf, kfi = self._next_keyfile()
            kb = self._keyfile_bytes(kfi)
            ow = self._overwrite or not os.path.exists(kf)
            self._keys.append(EncryptedRecordStore(kf, self._key,
                                                   max_bytes=kb,
                                                   overwrite=ow))
            self.writes.append(0)
            self.reads.append(0)
            if ow:
                for i in range(0, self._keyfile_size(kfi)):
                    self._keys[kfi][i] = self._UNUSED
            return kfi, self._keys[kfi]

    def _offset_and_digest(self, key):
        digest = hashlib.sha256(self._key)
        digest.update(key)
        digest = digest.digest()[:self._DIGEST_SIZE]
        return struct.unpack('<L', digest[:4])[0], digest

    def load_records(self, keyset, count, pos, want=[]):
        values = []
        for inc in range(0, count):
            rpos = (pos + inc) % len(keyset)
            rval = keyset[rpos]
            values.append((rpos, rval))
            for w in want:
                if rval.startswith(w):
                    return values
        return values

    def load_record(self, key, want=None):
        pos, digest = self._offset_and_digest(key)
        if want is None:
            # Search for the unused marker, as well as the digest...
            want = [self._UNUSED]
        for kfi, keyset in enumerate(self._keys):
            records = self.load_records(keyset, self._BUCKET_SIZE, pos,
                                        want=want+[digest])
            if records[-1][1].startswith(digest):
                self.reads[kfi] += 1
                return (keyset, records[-1])
            elif records[-1][1] == self._UNUSED:
                # ...finding an unused marker means we can give up.
                break
        raise KeyError(key)

    def _try_save(self, keyset, pos, digest, value):
        records = self.load_records(keyset, self._BUCKET_SIZE, pos,
                                    want=[self._UNUSED, digest])
        if (records[-1][1] == self._UNUSED or
                records[-1][1].startswith(digest)):
            rpos, rdata = records[-1]
            record_data = digest + '=' + value
            if len(record_data) > keyset._MAX_DATA_SIZE:
                keyset[rpos] = '%s->%x' % (digest, self._values.append(value))
            else:
                keyset[rpos] = record_data
            return rpos
        else:
            return None

    def save_record(self, key, value):
        pos, digest = self._offset_and_digest(key)
        for kfi, keyset in enumerate(self._keys):
            rpos = self._try_save(keyset, pos, digest, value)
            if rpos is not None:
                self.writes[kfi] += 1
                return keyset, rpos

        # If we get this far, then we need to grow...
        kfi, keyset = self._load_next_keys()
        rpos = self._try_save(keyset, pos, digest, value)
        if rpos is not None:
            self.writes[kfi] += 1
            return keyset, rpos

        raise KeyError(key)

    def __setitem__(self, key, value):
        self.save_record(key, value)

    def __getitem__(self, key):
        keyset, (rpos, rdata) = self.load_record(key)
        if rdata[self._DIGEST_SIZE] == '=':
            return rdata[self._DIGEST_SIZE + 1:]
        elif rdata[self._DIGEST_SIZE:].startswith('->'):
            return self._values[int(rdata[self._DIGEST_SIZE + 2:], 16)]
        else:
            raise KeyError(key)

    def close(self):
        with self._lock:
            for s in self._keys:
                s.close()
            self._keys = []


if __name__ == '__main__':
    for size in (16, 50, 100, 200, 400, 800, 1600):
        er = EncryptedBlobStore('/tmp/tmp.aes', 'this is my secret key',
                                max_bytes=size, overwrite=True)
        print('Testing max_size=%d, real max=%d, lines=%d'
              % (size, er.s0._MAX_DATA_SIZE, er.s0._RECORD_LINES))
        for l in range(0, 20):
            er[l] = 'bjarni %s' % l
        for l in range(0, 20):
            assert(er[l] == 'bjarni %s' % l)
        assert(len(er) == 20)

    er = EncryptedBlobStore('/tmp/test.aes', 'this is my secret key',
                            max_bytes=512, big_ratio=4, overwrite=True)
    t0 = time.time()
    count = 10 * 1024 + 4321
    data = ('bjarni is a happy camper with plenty of stuff '
            'we must pad this with gibberish and make it '
            'a fair bit longer, so it makes a good test '
            'to say about this and that and the other') * 100
    for l in range(0, count):
        if (l % 1024) == 5:
            er[l] = data
        else:
            er[l] = data[:(l % 1024)]
    done = time.time()
    print ('10k record writes in %.2f (%.8f s/op)'
           % (done - t0, (done - t0) / count))
    assert(len(er) == count)

    t0 = time.time()
    for l in range(0, count):
        if (l % 1024) == 5:
            assert(er[l] == data)
        else:
            assert(er[l] == data[:(l % 1024)])

    done = time.time()
    print ('10k record reads in %.2f (%.8f s/op)'
           % (done - t0, (done - t0) / count))
    er.close()

    print 'Creating EncryptedDict...'
    ed = EncryptedDict('/tmp/test.aes', 'another secret key',
                       shard_size=(2*count), min_shards=2,
                       shard_ratio=2, overwrite=True)

    t0 = time.time()
    for i in range(0, count):
        ed[str(i)] = str(i)
    done = time.time()
    print ('10k dict writes in %.2f (%.8f s/op): %s'
           % (done - t0, (done - t0) / count, ed.writes))

    t0 = time.time()
    ed.reset_counters()
    for i in range(0, count):
        assert(ed[str(i)] == str(i))
    done = time.time()
    print ('10k dict reads in %.2f (%.8f s/op): %s'
           % (done - t0, (done - t0) / count, ed.reads))

