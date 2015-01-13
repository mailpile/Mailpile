import os
import sys
import random
import struct
import threading
import traceback
import time

import mailpile.util
from mailpile.crypto.streamer import EncryptingStreamer
from mailpile.crypto.records import EncryptedDict
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


class EncryptedPostingLists(EncryptedDict):
    """
    This is a PostingList storage implementation based on the EncryptedDict.

    New entries are recorded to a special "incoming" dict which has a fixed
    capacity. When a PostingList either does not find a slot or its data
    grows too large, it and the neighboring entries are all migrated at once
    to a second long-term storage dict with "unlimited" capacity.

    When values are read from the EncryptedPostingList, values are read from
    both the incoming and long-term storage dicts and ORed together.

    The goal of this strategy is to ensure that the "hot spots" both for
    reads and writes end up in dicts that are small enough that the OS
    file system cache will accelerate most operations. The migration
    strategy ensures that values which hash to proximate buckets on
    disk get written to long term storage together, thus making efficient
    use of the underlying cache, read and write operations.

    FIXME/TODO:
       * Test the benefit of bitmask compression to reduce PL size
       * Make it possible to remove hits
    """
    DEFAULT_DIGEST_SIZE = 12  # Let 96 hash bits suffice. This buys us space
                              # for a third "hit" in the shards with the
                              # smallest key size, w/o needing to use the
                              # BlobStore. Two search terms hashing to the
                              # same value is not the end of the world.

    DEFAULT_BUCKET_SIZE = 3   # Our data sets are large and we expect to fill
                              # our tables over time, so use small buckets for
                              # long-term storage.

    INCOMING_BUCKET_SIZE = 5  # For incoming, we want to batch writes together
                              # which happens best with larger buckets.

    # These numbers are based on analysis of the keyword data from
    # Bjarni's 300k Mailpile.
    KEYWORDS_PER_MSG = 17      # Average unique keywords per message
    UP_TO_THREE_RATIO = 0.945  # How many fit in the minimal record size?
    HOT_SPOT_RATIO = 0.0006    # How many are seen in >= .1% of all mail?

    # Full stats:
    #    3      4876082      94.50%  100.00%   94.50%
    #    9       177887       3.45%    5.50%   97.95%
    #   27        60255       1.17%    2.05%   99.11%
    #   81        24441       0.47%    0.89%   99.59%
    #  243        11089       0.21%    0.41%   99.80%
    #  729         5041       0.10%    0.20%   99.90%
    # 2187         2942       0.06%    0.10%   99.96%
    # 6561         2040       0.04%    0.04%  100.00%

    def __init__(self, base_fn, key,
                 min_msgs=10000, max_msgs=1000000, cache_bytes=50*1024*1024,
                 overwrite=False):

        # How many hot-spots will we have at the max message size?
        self._hot_spot_count = (self.KEYWORDS_PER_MSG *
                                self.HOT_SPOT_RATIO *
                                max_msgs)

        # OK, these values are now known
        self._cache_bytes = cache_bytes
        self._shard_ratio = 2.0
        self._shard_size = max(self._hot_spot_count, cache_bytes // (2 * 66))

        # For incoming, we allocate 512 bytes of real disk space to each
        # key and set the size of the incoming hash to be half our cache
        # budget. We assume the other half goes to whatever's hot in the
        # long term storage (obviously there is no guarantee).
        self._incoming_key_size = 0.75 * 256 - 72
        self._incoming_shard_size = (cache_bytes // 256) // 2

        # Assuming we use a bitmap, how big will a hot-spot get?
        self._hot_spot_value_size = (self._incoming_key_size + 72) // 25 - 72

        # Roughly how many shards should we pre-create?
        min_shards = 1
        while (2 * self.KEYWORDS_PER_MSG * min_msgs >
                sum([self._keyfile_size(i) for i in range(0, min_shards)])):
            min_shards += 1

        # This is the basic long-term key store
        EncryptedDict.__init__(self, base_fn, key,
                               key_bytes=self.MIN_KEY_BYTES,
                               data_bytes=self._hot_spot_value_size,
                               shard_size=self._shard_size,
                               shard_ratio=self._shard_ratio,
                               min_shards=min_shards,
                               big_ratio=5,
                               overwrite=overwrite)

        # This is where recently scanned data goes; we set the ratios
        # to zero to limit this to a fixed size.
        self._incoming = EncryptedDict(base_fn + '-i', key,
                                       key_bytes=self._incoming_key_size,
                                       shard_size=self._incoming_shard_size,
                                       min_shards=1,
                                       digest_size=self.DEFAULT_DIGEST_SIZE,
                                       bucket_size=self.INCOMING_BUCKET_SIZE,
                                       big_ratio=0, shard_ratio=0)

    def _pack(self, hits, compress=False):
        data = ''.join(struct.pack('<I', v) for v in hits)
        # FIXME: Do the bitmask compression thing for longer lists?
        return data

    def _unpack(self, data):
        # FIXME: Do the bitmask decompression thing?
        return set(struct.unpack('<I', data[i:i+4])[0]
                   for i in range(0, len(data), 4))

    def _flush_records(self, key,
                       edict, kfi, keyset, pos, digest, value, records):
        vrpos = None
        for rpos, rdata in records:
            if rdata != edict._UNUSED:
                rdig = edict.rdata_digest(rdata)
                if rdig == digest:
                    vrpos, rval = rpos, value
                else:
                    rval = edict.rdata_value(rdata)

                try:
                    i1, (i2, lts_rdata) = self.load_digest_record(rdig)
                    lts_val = self._unpack(self.rdata_value(lts_rdata))
                except KeyError:
                    lts_val = set()

                hits = self._pack(self._unpack(rval) | lts_val)
                self.save_digest_record(rdig, hits)
                keyset[rpos] = edict._UNUSED
        if vrpos is not None:
            return vrpos
        else:
            return self.save_digest_record(rdig, value)

    def __setitem__(self, key, value):
        if isinstance(value, (int,)):
            value = set([value])
        elif isinstance(value, (list,)):
            value = set(value)
        else:
            assert(isinstance(value, (set,)))
        with self._lock:
            data = self._pack(self.get(key, set(), lts=False) | value)
            self._incoming.save_record(
                key, data, on_fail=lambda *a: self._flush_records(key, *a))

    def __getitem__(self, key, incoming=True, lts=True):
        rv = set()
        with self._lock:
            if incoming:
                rv |= self._unpack(self._incoming.get(key, ''))
            if lts:
                try:
                    rv |= self._unpack(EncryptedDict.__getitem__(self, key))
                except KeyError:
                    pass
        if len(rv) < 1:
            raise KeyError('Not found: %s' % key)
        return rv


if __name__ == '__main__':
    epl = EncryptedPostingLists('/tmp/test.aes', 'testing',
                                cache_bytes=10 * 1024*1024,
                                min_msgs=1000, max_msgs=100000,
                                overwrite=True)

    epl['hello'] = [1, 2, 3]

    t0 = time.time()
    for i in range(1000, 4333):
        epl['hello'] = i
        epl['world %s' % i] = i % 10
        epl['world %s' % (i % 30)] = i % 7
    t1 = time.time()
    print ('Wrote 9999 values in %.2f (%.5f ops/s %.5f s/op)'
           % (t1 - t0, 9999 / (t1 - t0), (t1 - t0) / 9999))

    hello = epl['hello']
    for i in range(1000, 4333):
        assert(i in hello)
    assert(1 in hello)
    assert(2 in hello)
    assert(3 in hello)

