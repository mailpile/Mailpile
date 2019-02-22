import os
import sys
import random
import threading
import traceback
import time

import mailpile.util
from mailpile.crypto.streamer import EncryptingStreamer
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


NEW_POSTING_LIST = True

GLOBAL_POSTING_LOCK = PListRLock()
GLOBAL_OPTIMIZE_LOCK = PListLock()

GLOBAL_GPL_LOCK = PListRLock()
GLOBAL_GPL = None

PLC_CACHE_LOCK = PListLock()
PLC_CACHE = {}

TIMERS = {
    'render': 0,
    'save': 0,
    'save_count': 0,
    'load': 0,
    'load_count': 0,
}

# These are special keys in the Global Posting List that never
# get migrated into the search index itself.
# Note: To avoid conflicts, these keys should be in all caps.
GPL_MSGID_TRACKER = '_MAX_MSGID_'
GPL_NEVER_MIGRATE = (GPL_MSGID_TRACKER, )


def PLC_CACHE_FlushAndClean(session, min_changes=0, keep=5, runtime=None):
    def save(plc):
        job_name = _('Save PLC %s') % plc.sig
        session.ui.mark(job_name)
        session.config.save_worker.do(session, job_name, plc.save)
        play_nice_with_threads()

    def remove(ts, plc):
        with PLC_CACHE_LOCK:
            if plc.sig in PLC_CACHE and ts == PLC_CACHE[plc.sig][0]:
               del PLC_CACHE[plc.sig]

    startt = int(time.time())
    expire = startt - max(30, 300 - len(PLC_CACHE))
    savets = startt - 15

    def time_up():
        return (runtime and startt + runtime < time.time())

    with PLC_CACHE_LOCK:
        plc_cache = sorted(PLC_CACHE.values())

    for ts, plc in plc_cache[:-keep]:
        if plc.changes:
            save(plc)
        remove(ts, plc)
        if time_up():
            return

    for ts, plc in plc_cache[-keep:]:
        if (plc.changes > min_changes) or (plc.changes and ts < savets):
            save(plc)
        if ts < expire:
            remove(ts, plc)
        if time_up():
            return


class PostingListContainer(object):
    """A container for posting lists mapping search terms to message IDs."""

    MAX_ITEMS = int((60 * 1024) / 5)  # Target size of about 60KB
    MAX_HASH_LEN = 24

    @classmethod
    def Load(cls, session, sig, uncached_cb=None):
        fn, sig = cls._GetFilenameAndSig(session.config, sig)
        plc = None
        with PLC_CACHE_LOCK:
            if sig in PLC_CACHE:
                PLC_CACHE[sig][0] = int(time.time())
                plc = PLC_CACHE[sig][1]
        if plc is None:
            plc = cls(session, sig)  # Unlocked: stalled loads would deadlock
            with PLC_CACHE_LOCK:
                PLC_CACHE[sig] = [int(time.time()), plc]
            if uncached_cb:
               uncached_cb()
        # We return the cached version no matter what, in case a race above
        # had us loading the same posting-list twice: we want to be sure
        # calling code gets the shared object.
        with PLC_CACHE_LOCK:
            return PLC_CACHE[sig][1]

    def __init__(self, session, sig, fd=None):
        self.session = session
        self.config = session.config

        self.lock = PListRLock()
        self.sig = sig
        self.fd = fd
        self.words = {sig: set()}

        self.changes = 0
        self._load()

    def get(self, sig, default=None):
        return self.words.get(sig, default)

    def add(self, *args, **kwargs):
        with self.lock:
            return self._unlocked_add(*args, **kwargs)

    def remove(self, *args, **kwargs):
        with self.lock:
            self.changed = True
            return self._unlocked_remove(*args, **kwargs)

    def _deleted_set(self):
        # FIXME!
        return set()

    def save(self, split=True):
        if not self.changes:
            return

        if split and len(self.words) > 1:
            with self.lock:
                for plc in self._splits():
                    plc.save(split=False)
            return

        t = [time.time()]
        encryption_key = self.config.get_master_key()
        outfile = self._SaveFile(self.config, self.sig)
        with self.lock:
            # Optimizing for fast loads, so deletion only happens on save.
            del_set = self._deleted_set()
            output = '\n'.join('\t'.join(l) for l
                               in ([sig] + [str(v) for v in (values-del_set)]
                                   for sig, values in self.words.iteritems())
                               if len(l) > 1)
            t.append(time.time())

            if not output:
                try:
                    os.remove(outfile)
                except OSError:
                    pass
            elif self.config.prefs.encrypt_index and encryption_key:
                subj = self.config.mailpile_path(outfile)
                with EncryptingStreamer(encryption_key,
                                        delimited=False,
                                        dir=self.config.tempfile_dir(),
                                        header_data={'subject': subj},
                                        name='PLC/%s' % self.sig) as fd:
                    fd.write(output.encode('utf-8'))
                    fd.save(outfile)
            else:
                with open(outfile, 'wb') as fd:
                    fd.write(output)

            t.append(time.time())
            self.changes = 0

        if len(t) == 3:
            TIMERS['render'] += t[1] - t[0]
            TIMERS['save'] += t[2] - t[1]
            TIMERS['save_count'] += 1

    def _splits(self):
        splits = [self]
        if len(self.sig) < self.MAX_HASH_LEN:
            total, sums = 0, {}
            for sig, values in self.words.iteritems():
                total += len(values)
                if len(values) >= (self.MAX_ITEMS / 2):
                    nsig = sig[:self.MAX_HASH_LEN]
                else:
                    nsig = sig[:len(self.sig)+1]
                if nsig in sums:
                    sums[nsig] += len(values)
                else:
                    sums[nsig] = len(values)

            while total > self.MAX_ITEMS and sums:
                skeys = sums.keys()
                skeys.sort(key=lambda k: -sums[k])
                nsig = skeys[0]
                total -= sums[nsig]
                del sums[nsig]
                try:
                    fn = self._SaveFile(self.config, nsig)
                    if not os.path.exists(fn):
                        open(fn, 'w').close()

                    plc = PostingListContainer(self.session, nsig)
                    for sig in list(self.words.keys()):
                        if sig.startswith(nsig):
                            plc.add(sig, self.words[sig])
                            del self.words[sig]
                    splits.append(plc)
                except (OSError, IOError):
                    pass

        return splits

    def _load(self):
        t0 = time.time()
        if not self.fd:
            fn, self.sig = self._GetFilenameAndSig(self.config, self.sig)
            try:
                self.fd = open(fn, 'rb')
            except (IOError, OSError):
                return
        with self.lock, self.fd:
            try:
                decrypt_and_parse_lines(self.fd,
                                        self._unlocked_parse_lines,
                                        self.config)
                self.changes = 0
            except (ValueError, IOError):
                self.session.ui.warning('load(%s) %s'
                                        % (self.sig, sys.exc_info()))
                if self.config.sys.debug:
                    traceback.print_exc()
        self.fd = None
        TIMERS['load'] += time.time() - t0
        TIMERS['load_count'] += 1

    def _unlocked_parse_lines(self, lines):
        for line in lines:
            words = line.strip().split('\t')
            if len(words) > 1:
                self._unlocked_add(words[0], words[1:])

    def _unlocked_add(self, sig, values):
        wset = set(values)
        self.changes += len(wset)
        if sig in self.words:
            self.words[sig] |= wset
        else:
            self.words[sig] = wset

    def _unlocked_remove(self, sig, values):
        wset = set(values)
        self.changes += len(wset)
        if sig in self.words:
            self.words[sig] -= wset
            if not self.words[sig]:
                del self.words[sig]

    @classmethod
    def _SaveFile(cls, config, sig):
        return os.path.join(config.postinglist_dir(sig), sig)

    @classmethod
    def _GetFilenameAndSig(cls, config, sig):
        """Find and the closest matching posting list container file"""
        sig = sig[:cls.MAX_HASH_LEN]
        while len(sig) > 0:
            fn = cls._SaveFile(config, sig)
            try:
                if os.path.exists(fn):
                    return (fn, sig)
            except (IOError, OSError):
                pass

            if len(sig) > 1:
                sig = sig[:-1]
            else:
                return (fn, sig)

        # Not reached
        return (None, None)


class NewPostingList(object):
    """A posting list is a map of search terms to message IDs."""

    HASH_LEN = 24

    @classmethod
    def Append(cls, session, word, values, compact=False, sig=None):
        sig = sig or cls._WordSig(word, session.config)
        PostingListContainer.Load(session, sig).add(sig, values)

    @classmethod
    def Optimize(cls, session, index, lazy=False, quick=False):
        threshold = (quick or lazy) and 250 or 50
        PLC_CACHE_FlushAndClean(session, min_changes=threshold)

    def __init__(self, session, word):
        self.config = session.config
        self.session = session
        if word:
            self.word = word
            self.sig = self._WordSig(word, self.config)
            self.plc = PostingListContainer.Load(self.session, self.sig)

    def hits(self):
        return self.plc.get(self.sig) or set()

    def append(self, *eids):
        self.plc.add(self.sig, eids)
        return self

    def remove(self, eids):
        self.plc.remove(self.sig, eids)
        return self

    @classmethod
    def _WordSig(cls, word, config):
        return strhash(word, cls.HASH_LEN,
                       obfuscate=((config.prefs.obfuscate_index or
                                   config.prefs.encrypt_index) and
                                  config.get_master_key()))


##############################################################################

class OldPostingList(object):
    """A posting list is a map of search terms to message IDs."""

    CHARACTERS = 'abcdefghijklmnopqrstuvwxyz0123456789+_'

    MAX_SIZE = 60    # perftest gives: 75% below 500ms, 50% below 100ms
    HASH_LEN = 24

    @classmethod
    def _Optimize(cls, session, idx, force=False):
        return  # Disabled, this is incompatible with new posting lists!

        postinglist_kb = session.config.sys.postinglist_kb

        # Pass 1: Compact all files that are 90% or more of our target size
        for c in cls.CHARACTERS:
            postinglist_dir = session.config.postinglist_dir(c)
            for fn in sorted(os.listdir(postinglist_dir)):
                if mailpile.util.QUITTING:
                    break
                filesize = os.path.getsize(os.path.join(postinglist_dir, fn))
                if force or (filesize > 900 * postinglist_kb):
                    session.ui.mark('Pass 1: Compacting >%s<' % fn)
                    play_nice_with_threads()
                    with GLOBAL_POSTING_LOCK:
                        # FIXME: Remove invalid and deleted messages from
                        #        posting lists.
                        cls(session, fn, sig=fn).save()

        # Pass 2: While mergable pair exists: merge them!
        for c in cls.CHARACTERS:
            postinglist_dir = session.config.postinglist_dir(c)
            files = [n for n in os.listdir(postinglist_dir) if len(n) > 1]
            files.sort(key=lambda a: -len(a))
            for fn in files:
                if mailpile.util.QUITTING:
                    break
                size = os.path.getsize(os.path.join(postinglist_dir, fn))
                fnp = fn[:-1]
                while not os.path.exists(os.path.join(postinglist_dir, fnp)):
                    fnp = fnp[:-1]
                size += os.path.getsize(os.path.join(postinglist_dir, fnp))
                if (fnp and
                    size < (1024 * postinglist_kb - (cls.HASH_LEN * 6))):
                    session.ui.mark('Pass 2: Merging %s into %s' % (fn, fnp))
                    play_nice_with_threads()
                    try:
                        GLOBAL_POSTING_LOCK.acquire()
                        path_fn = os.path.join(postinglist_dir, fn)
                        path_fnp = os.path.join(postinglist_dir, fnp)
                        with open(path_fn, 'r') as fd:
                            with open(path_fnp, 'a') as fdp:
                                for line in fd:
                                    fdp.write(line)
                    finally:
                        try:
                            os.remove(os.path.join(postinglist_dir, fn))
                        except (OSError, IOError):
                            pass
                        GLOBAL_POSTING_LOCK.release()

        filecount = 0
        for c in cls.CHARACTERS:
            filecount += len(os.listdir(session.config.postinglist_dir(c)))
        session.ui.mark('Optimized %s posting lists' % filecount)
        return filecount

    @classmethod
    def _Append(cls, session, word, mail_ids, compact=True, sig=None):
        config = session.config
        sig = sig or cls.WordSig(word, config)

        fd = None
        while fd is None:
            fd, fn = cls.GetFile(session, sig, mode='a')
            fn_path = cls.SaveFile(session, fn)
            try:
                # The code below will compact the files and split out hot-spots,
                # but we only bother "once in a while" when the files are "big".
                if compact:
                    max_size = ((1024 * config.sys.postinglist_kb) -
                                (cls.HASH_LEN * 6))
                    if (os.path.getsize(fn_path) > max_size and
                            random.randint(0, 50) == 1):
                        break
                if fd:
                    with fd:
                        fd.write('%s\t%s\n' % (sig, '\t'.join(mail_ids)))
                        return
            except IOError:
                print ('RETRY: APPEND(compact=%s, %s, %s) %s'
                       % (compact, fn_path, fd, sys.exc_info()))
                time.sleep(0.2)
                fd = None

        # OK, compactinate!
        pls = cls(session, word, sig=sig)
        for mail_id in mail_ids:
            pls.append(mail_id)
        pls.save()

    @classmethod
    def Lock(cls, lock, method, *args, **kwargs):
        with lock:
            return method(*args, **kwargs)

    @classmethod
    def Optimize(cls, *args, **kwargs):
        return cls.Lock(GLOBAL_OPTIMIZE_LOCK, cls._Optimize, *args, **kwargs)

    @classmethod
    def Append(cls, *args, **kwargs):
        return cls.Lock(GLOBAL_POSTING_LOCK, cls._Append, *args, **kwargs)

    @classmethod
    def WordSig(cls, word, config):
        return strhash(word, cls.HASH_LEN,
                       obfuscate=((config.prefs.obfuscate_index or
                                   config.prefs.encrypt_index) and
                                  config.get_master_key()))

    @classmethod
    def SaveFile(cls, session, prefix):
        return os.path.join(session.config.postinglist_dir(prefix), prefix)

    @classmethod
    def GetFile(cls, session, sig, mode='r'):
        sig = sig[:cls.HASH_LEN]
        while len(sig) > 0:
            fn = cls.SaveFile(session, sig)
            try:
                if os.path.exists(fn):
                    return (open(fn, mode), sig)
            except (IOError, OSError):
                pass

            if len(sig) > 1:
                sig = sig[:-1]
            else:
                if 'r' in mode:
                    return (None, sig)
                else:
                    return (open(fn, mode), sig)
        # Not reached
        return (None, None)

    def __init__(self, session, word, sig=None, config=None):
        self.config = config or session.config
        self.session = session
        self.sig = sig or self.WordSig(word, self.config)
        self.size = 0
        self.word = word
        self.WORDS = {self.sig: set()}
        self.lock = PListRLock()
        self.load()

    def _parse_lines(self, lines):
        for line in lines:
            self.size += len(line)
            words = line.strip().split('\t')
            if len(words) > 1:
                wset = set(words[1:])
                if words[0] in self.WORDS:
                    self.WORDS[words[0]] |= wset
                else:
                    self.WORDS[words[0]] = wset

    def load(self):
        fd, self.filename = self.GetFile(self.session, self.sig)
        if not fd:
            return
        with self.lock, fd:
            try:
                self.size = 0
                decrypt_and_parse_lines(fd, self._parse_lines, self.config)
            except (ValueError, IOError):
                self.session.ui.warning('load(%s) %s'
                                        % (self.filename, sys.exc_info()))

    def _fmt_file(self, prefix):
        output = []
        self.session.ui.mark('Formatting prefix %s' % unicode(prefix))
        for word in self.WORDS.keys():
            data = self.WORDS.get(word, [])
            if ((prefix == 'ALL' or word.startswith(prefix))
                    and len(data) > 0):
                output.append(('%s\t%s\n'
                               ) % (word, '\t'.join(['%s' % x for x in data])))
        play_nice_with_threads(weak=True)
        return ''.join(output)

    def _compact(self, prefix, output):
        while ((len(output) > 1024 * self.config.sys.postinglist_kb) and
               (len(prefix) < self.HASH_LEN)):
            with self.lock:
                biggest = self.sig
                for word in self.WORDS:
                    if (len(self.WORDS.get(word, []))
                            > len(self.WORDS.get(biggest, []))):
                        biggest = word
                if len(biggest) > len(prefix):
                    biggest = biggest[:len(prefix) + 1]
                    self.save(prefix=biggest, mode='ab')
                    for key in [k for k in self.WORDS
                                if k.startswith(biggest)]:
                        del self.WORDS[key]
                    output = self._fmt_file(prefix)
        return prefix, output

    def save(self, prefix=None, compact=True, mode='wb'):
        with self.lock:
            prefix = prefix or self.filename
            output = self._fmt_file(prefix)
            if compact:
                prefix, output = self._compact(prefix, output)
            try:
                outfile = self.SaveFile(self.session, prefix)
                self.session.ui.mark('Writing %d bytes to %s' % (len(output),
                                                                 outfile))
                if output:
                    if self.config.prefs.encrypt_index:
                        encryption_key = self.config.get_master_key()
                        with EncryptingStreamer(encryption_key,
                                                delimited=True,
                                                dir=self.config.tempfile_dir(),
                                                name='PostingList') as efd:
                            efd.write(output.encode('utf-8'))
                            efd.save(outfile, mode=mode)
                    else:
                        with open(outfile, mode) as fd:
                            fd.write(output)
                    return len(output)
                elif os.path.exists(outfile):
                    os.remove(outfile)
            except:
                self.session.ui.warning('%s=>%s' % (outfile, sys.exc_info(),))
            return 0

    def hits(self):
        return self.WORDS[self.sig]

    def append(self, eid):
        with self.lock:
            if self.sig not in self.WORDS:
                self.WORDS[self.sig] = set()
            self.WORDS[self.sig].add(eid)
            return self

    def remove(self, eids):
        with self.lock:
            for eid in eids:
                try:
                    self.WORDS[self.sig].remove(eid)
                except KeyError:
                    pass
            return self


class GlobalPostingList(OldPostingList):

    @classmethod
    def _Optimize(cls, session, idx,
                  force=False, lazy=False, quick=False, ratio=1.0, runtime=0):

        # Record the largest known msg_mid here so it doesn't get lost
        cls.UpdateMaxMsgMid(session, [b36(cls.GetMaxMsgIdxPos())])

        starttime = time.time()
        count = 0
        global GLOBAL_GPL
        if (GLOBAL_GPL and (not lazy or len(GLOBAL_GPL) > 5*1024)):
            # Processing keys in order is more efficient, as it lets things
            # accumulate in the PLC_CACHE.
            keys = sorted(GLOBAL_GPL.keys())
            if ratio:
                keyn = int(len(keys) * ratio)
                start = random.randint(0, len(keys))
                # This lets the selection wrap around to the beginning,
                # so we don't have a bias against writing out the first
                # keys compared with the others.
                keys += keys
                keys = keys[start:start+keyn]

            pls = GlobalPostingList(session, '')
            for sig in keys:
                if (count % 7) == 0:
                    PLC_CACHE_FlushAndClean(session, min_changes=100000)
                if (count % 97) == 0:
                    session.ui.mark(('Updating search index... %d%% (%s)'
                                     ) % (count * 100 / len(keys), sig))

                # If we're doing a full optimize later, we disable the
                # compaction here. Otherwise it follows the normal
                # rules (compacts as necessary).
                pls._migrate(sig, compact=quick)
                count += 1
                if mailpile.util.QUITTING:
                    break
                if runtime and starttime + (0.80 * runtime) < time.time():
                    break
            PLC_CACHE_FlushAndClean(session)
            pls.save()

        if quick or mailpile.util.QUITTING:
            return count
        else:
            return OldPostingList._Optimize(session, idx, force=force)

    @classmethod
    def SaveFile(cls, session, prefix):
        return os.path.join(session.config.workdir, 'kw-journal.dat')

    @classmethod
    def GetFile(cls, session, sig, mode='r'):
        try:
            return (open(cls.SaveFile(session, sig), mode),
                    'kw-journal.dat')
        except (IOError, OSError):
            return (None, 'kw-journal.dat')

    @classmethod
    def _Append(cls, session, word, mail_ids, compact=True):
        super(GlobalPostingList, cls)._Append(session, word, mail_ids,
                                              compact=compact)
        with GLOBAL_GPL_LOCK:
            global GLOBAL_GPL
            sig = cls.WordSig(word, session.config)
            if GLOBAL_GPL is None:
                GLOBAL_GPL = {}
            if sig not in GLOBAL_GPL:
                GLOBAL_GPL[sig] = set()
            for mail_id in mail_ids:
                GLOBAL_GPL[sig].add(mail_id)

    @classmethod
    def GetMaxMsgIdxPos(cls):
        with GLOBAL_GPL_LOCK:
            return cls._unlocked_GetMaxMsgIdxPos()

    @classmethod
    def _unlocked_GetMaxMsgIdxPos(cls):
        global GLOBAL_GPL
        try:
            max_idx = 0
            for hits in GLOBAL_GPL.values():
                if hits:
                    max_idx = max(max_idx, max(int(id, 36) for id in hits))
            return max_idx
        except:
            return 0

    @classmethod
    def UpdateMaxMsgMid(cls, session, msg_mids):
        if len(msg_mids) == 0:
            return
        try:
            msg_idx_pos = max(int(id, 36) for id in msg_mids)
        except:
            return

        global GLOBAL_GPL
        with GLOBAL_GPL_LOCK:
            max_msg_idx_pos = max(
                int(id, 36)
                for id in GLOBAL_GPL.get(GPL_MSGID_TRACKER, set(['0'])))
            if max_msg_idx_pos and msg_idx_pos <= max_msg_idx_pos:
                return

            if GLOBAL_GPL is None:
                GLOBAL_GPL = {}
            GLOBAL_GPL[GPL_MSGID_TRACKER] = [b36(msg_idx_pos)]

        super(GlobalPostingList, cls)._Append(
            session, '', GLOBAL_GPL[GPL_MSGID_TRACKER],
            sig=GPL_MSGID_TRACKER, compact=False)

    def __init__(self, *args, **kwargs):
        with GLOBAL_GPL_LOCK:
            OldPostingList.__init__(self, *args, **kwargs)
            self.lock = GLOBAL_GPL_LOCK

    def _fmt_file(self, prefix):
        return OldPostingList._fmt_file(self, 'ALL')

    def _compact(self, prefix, output, **kwargs):
        return prefix, output

    def load(self):
        with self.lock:
            self.filename = 'kw-journal.dat'
            global GLOBAL_GPL
            if GLOBAL_GPL:
                self.WORDS = GLOBAL_GPL
            else:
                OldPostingList.load(self)
                GLOBAL_GPL = self.WORDS

    def _migrate(self, sig=None, compact=True):
        with self.lock:
            sig = sig or self.sig
            if sig in GPL_NEVER_MIGRATE:
                return
            if sig in self.WORDS and len(self.WORDS[sig]) > 0:
                PostingList.Append(self.session, sig, self.WORDS[sig],
                                   sig=sig, compact=compact)
                del self.WORDS[sig]

    def remove(self, eids):
        PostingList(self.session, self.word).remove(eids).save()
        return OldPostingList.remove(self, eids)

    def hits(self):
        return (self.WORDS.get(self.sig, set())
                | PostingList(self.session, self.word).hits())


if NEW_POSTING_LIST:
    PostingList = NewPostingList
else:
    PostingList = OldPostingList
