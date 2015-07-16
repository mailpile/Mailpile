import struct
import time
import zlib

from mailpile.util import *


def PackIntSet(ints):
    if len(ints) > 15:
        return '\xff\xff\xff\xff' + zlib.compress(intlist_to_bitmask(ints))
    else:
        return struct.pack('<' + 'I' * len(ints), *ints)


def UnpackIntSet(data):
    if len(data) > 13 and data[:4] == '\xff\xff\xff\xff':
        return set(bitmask_to_intlist(zlib.decompress(data[4:])))
    else:
        return set(struct.unpack('<' + 'I' * (len(data)//4), data))


def PackLongList(longs):
    packed = struct.pack('<' + 'q' * len(longs), *longs)
    if (len(packed) > 8 * 15) or (longs[0] == 0xffffffffffffffffL):
        return ('\xff\xff\xff\xff\xff\xff\xff\xff' + zlib.compress(packed))
    else:
        return packed


def UnpackLongList(data):
    if len(data) > 17 and data[:8] == '\xff\xff\xff\xff\xff\xff\xff\xff':
        data = zlib.decompress(data[8:])
    return list(struct.unpack('<' + 'q' * (len(data)//8), data))


class StorageBackedData(object):
    """
    This lovely hack exposes the full API of a Python set or list, but any
    writes get flushed to a storage backend and the initial state is loaded
    from the same.

    It is NOT SAFE to ever have more than one of these for a given backend
    as they will not stay in sync. Since most methods are proxies, using
    set method on a backed list will fail and vice-versa.
    """
    def __init__(self, storage, skey):
        self._storage = storage
        self._skey = skey
        self._load()
        self.last_save = time.time()
        self.auto_save = True
        self.interval = -1
        self.dirty = False

    def _pack(self, data): raise NotImplemented()
    def _unpack(self, data): raise NotImplemented()

    def load(self):
        try:
            self._obj = self._unpack(self._storage[self._skey])
        except (KeyError, IndexError):
            self._obj = self._unpack('')

    def save(self, maybe=False):
        if not maybe or self.dirty:
            self._storage[self._skey] = self._pack(self._obj)
            self.dirty = False

    def _dirty_maybe_save(self):
        self.dirty = True
        if self.auto_save:
            if (self.interval < 1 or
                    self.last_save < time.time() - self.interval):
                self.save()

    def _r(self, method, *args, **kwargs):
        return getattr(self._obj, method)(*args, **kwargs)

    def _w(self, method, *args, **kwargs):
        rv = getattr(self._obj, method)(*args, **kwargs)
        self._dirty_maybe_save()
        return rv

    def _iw(self, method, *args, **kwargs):
        self._obj = getattr(self._obj, method)(*args, **kwargs)
        self._dirty_maybe_save()
        return self
 
    def __and__(s, *a, **kw): return s._r('__and__', *a, **kw)
    def __cmp__(s, *a, **kw): return s._r('__cmp__', *a, **kw)
    def __contains__(s, *a, **kw): return s._r('__contains__', *a, **kw)
    def __eq__(s, *a, **kw): return s._r('__eq__', *a, **kw)
    def __ge__(s, *a, **kw): return s._r('__ge__', *a, **kw)
    def __getitem__(s, *a, **kw): return s._r('__getitem__', *a, **kw)
    def __getslice__(s, *a, **kw): return s._r('__getslice__', *a, **kw)
    def __gt__(s, *a, **kw): return s._r('__gt__', *a, **kw)
    def __iter__(s, *a, **kw): return s._r('__iter__', *a, **kw)
    def __le__(s, *a, **kw): return s._r('__le__', *a, **kw)
    def __len__(s, *a, **kw): return s._r('__len__', *a, **kw)
    def __lt__(s, *a, **kw): return s._r('__lt__', *a, **kw)
    def __mul__(s, *a, **kw): return s._r('__mul__', *a, **kw)
    def __ne__(s, *a, **kw): return s._r('__ne__', *a, **kw)
    def __or__(s, *a, **kw): return s._r('__or__', *a, **kw)
    def __rand__(s, *a, **kw): return s._r('__rand__', *a, **kw)
    def __reduce__(s, *a, **kw): return s._r('__reduce__', *a, **kw)
    def __repr__(s, *a, **kw): return s._r('__repr__', *a, **kw)
    def __reversed__(s, *a, **kw): return s._r('__reversed__', *a, **kw)
    def __rmul__(s, *a, **kw): return s._r('__rmul__', *a, **kw)
    def __rsub__(s, *a, **kw): return s._r('__rsub__', *a, **kw)
    def __rxor__(s, *a, **kw): return s._r('__rxor__', *a, **kw)
    def __sizeof__(s, *a, **kw): return s._r('__sizeof__', *a, **kw)
    def __sub__(s, *a, **kw): return s._r('__sub__', *a, **kw)
    def __xor__(s, *a, **kw): return s._r('__xor__', *a, **kw)
    def copy(s, *a, **kw): return s._r('copy', *a, **kw)
    def count(s, *a, **kw): return s._r('count', *a, **kw)
    def difference(s, *a, **kw): return s._r('difference', *a, **kw)
    def index(s, *a, **kw): return s._r('index', *a, **kw)
    def intersection(s, *a, **kw): return s._r('intersection', *a, **kw)
    def isdisjoint(s, *a, **kw): return s._r('isdisjoint', *a, **kw)
    def issubset(s, *a, **kw): return s._r('issubset', *a, **kw)
    def issuperset(s, *a, **kw): return s._r('issuperset', *a, **kw)
    def union(s, *a, **kw): return s._r('union', *a, **kw)

    def symmetric_difference(s, *a, **kw):
        return s._r('symmetric_difference', *a, **kw)

    def __iadd__(s, *a, **kw): return s._iw('__iadd__', *a, **kw)
    def __iand__(s, *a, **kw): return s._iw('__iand__', *a, **kw)
    def __imul__(s, *a, **kw): return s._iw('__imul__', *a, **kw)
    def __ior__(s, *a, **kw): return s._iw('__ior__', *a, **kw)
    def __isub__(s, *a, **kw): return s._iw('__isub__', *a, **kw)
    def __ixor__(s, *a, **kw): return s._iw('__ixor__', *a, **kw)

    def __delitem__(s, *a, **kw): return s._w('__delitem__', *a, **kw)
    def __delslice__(s, *a, **kw): return s._w('__delslice__', *a, **kw)
    def __setitem__(s, *a, **kw): return s._w('__setitem__', *a, **kw)
    def __setslice__(s, *a, **kw): return s._w('__setslice__', *a, **kw)
    def add(s, *a, **kw): return s._w('add', *a, **kw)
    def append(s, *a, **kw): return s._w('append', *a, **kw)
    def clear(s, *a, **kw): return s._w('clear', *a, **kw)
    def discard(s, *a, **kw): return s._w('discard', *a, **kw)
    def extend(s, *a, **kw): return s._w('extend', *a, **kw)
    def insert(s, *a, **kw): return s._w('insert', *a, **kw)
    def pop(s, *a, **kw): return s._w('pop', *a, **kw)
    def remove(s, *a, **kw): return s._w('remove', *a, **kw)
    def reverse(s, *a, **kw): return s._w('reverse', *a, **kw)
    def sort(s, *a, **kw): return s._w('sort', *a, **kw)
    def update(s, *a, **kw): return s._w('update', *a, **kw)

    def difference_update(s, *a, **kw):
        return s._w('difference_update', *a, **kw)
    def intersection_update(s, *a, **kw):
        return s._w('intersection_update', *a, **kw)
    def symmetric_difference_update(s, *a, **kw):
        return s._w('symmetric_difference_update', *a, **kw)


class StorageBackedSet(StorageBackedData):
    def _pack(self, data): return PackIntSet(data)
    def _unpack(self, data): return UnpackIntSet(data)


class StorageBackedLongs(StorageBackedData):
    def _pack(self, data): return PackLongList(data)
    def _unpack(self, data): return UnpackLongList(data)
