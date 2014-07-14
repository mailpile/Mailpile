import os
import random
import threading
import time
from gettext import gettext as _

import mailpile.util
from mailpile.util import *


GLOBAL_POSTING_LIST = None
GLOBAL_POSTING_LOCK = TracedRLock()
GLOBAL_OPTIMIZE_LOCK = TracedLock()


# FIXME: Create a tiny cache for PostingList objects, so we can start
#        encrypting them.  We should have a read-cache of moderate size,
# and a one-element write cache which only writes to disk when a PostingList
# gets evicted OR the cache in its entirety is flushed. Due to how keywords
# are grouped into posting lists and the fact that they are flushed to
# disk in sorted order, this should be enough to group everything together
# that can actually be grouped.


class PostingList(object):
    """A posting list is a map of search terms to message IDs."""

    CHARACTERS = 'abcdefghijklmnopqrstuvwxyz0123456789+_'

    MAX_SIZE = 60    # perftest gives: 75% below 500ms, 50% below 100ms
    HASH_LEN = 24

    @classmethod
    def _Optimize(cls, session, idx, force=False):
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
                    compact = (os.path.getsize(fn_path) > max_size and
                               random.randint(0, 50) == 1)
                if fd:
                    with fd:
                        if not compact:
                            fd.write('%s\t%s\n' % (sig, '\t'.join(mail_ids)))
                            return
            except IOError:
                print 'OMGWTF: compact=%s %s / %s' % (compact, fn_path, fd)
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
                       obfuscate=config.prefs.obfuscate_index)

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
        self.word = word
        self.WORDS = {self.sig: set()}
        self.lock = TracedRLock()
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
        if fd:
            try:
                self.lock.acquire()
                self.size = 0
                decrypt_and_parse_lines(fd, self._parse_lines, self.config)
            except ValueError:
                pass
            finally:
                self.lock.release()
                fd.close()

    def _fmt_file(self, prefix):
        output = []
        self.session.ui.mark('Formatting prefix %s' % unicode(prefix))
        for word in self.WORDS.keys():
            data = self.WORDS.get(word, [])
            if ((prefix == 'ALL' or word.startswith(prefix))
                    and len(data) > 0):
                output.append(('%s\t%s\n'
                               ) % (word, '\t'.join(['%s' % x for x in data])))
        return ''.join(output)

    def _compact(self, prefix, output, locked=False):
        while ((len(output) > 1024 * self.config.sys.postinglist_kb) and
               (len(prefix) < self.HASH_LEN)):
            biggest = self.sig
            for word in self.WORDS:
                if (len(self.WORDS.get(word, []))
                        > len(self.WORDS.get(biggest, []))):
                    biggest = word
            if len(biggest) > len(prefix):
                biggest = biggest[:len(prefix) + 1]
                self.save(prefix=biggest, mode='a', locked=locked)
                for key in [k for k in self.WORDS if k.startswith(biggest)]:
                    del self.WORDS[key]
                output = self._fmt_file(prefix)
        return prefix, output

    def save(self, prefix=None, compact=True, mode='w', locked=False):
        if not locked:
            self.lock.acquire()
        try:
            prefix = prefix or self.filename
            output = self._fmt_file(prefix)
            if compact:
                prefix, output = self._compact(prefix, output, locked=True)
            try:
                outfile = self.SaveFile(self.session, prefix)
                self.session.ui.mark('Writing %d bytes to %s' % (len(output),
                                                                 outfile))
                if output:
                    with open(outfile, mode) as fd:
                        fd.write(output)
                        return len(output)
                elif os.path.exists(outfile):
                    os.remove(outfile)
            except:
                self.session.ui.warning('%s' % (sys.exc_info(), ))
            return 0
        finally:
            if not locked:
                self.lock.release()

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


GLOBAL_GPL_LOCK = TracedRLock()


class GlobalPostingList(PostingList):

    @classmethod
    def _Optimize(cls, session, idx, force=False, lazy=False, quick=False):
        count = 0
        global GLOBAL_POSTING_LIST
        if (GLOBAL_POSTING_LIST
                and (not lazy or len(GLOBAL_POSTING_LIST) > 40*1024)):
            keys = sorted(GLOBAL_POSTING_LIST.keys())
            pls = GlobalPostingList(session, '')
            for sig in keys:
                if (count % 97) == 0:
                    session.ui.mark(('Updating search index... %d%% (%s)'
                                     ) % (count * 100 / len(keys), sig))
                elif (count % 17) == 0:
                    play_nice_with_threads()

                # If we're doing a full optimize later, we disable the
                # compaction here. Otherwise it follows the normal
                # rules (compacts as necessary).
                pls._migrate(sig, compact=quick)
                count += 1
                if mailpile.util.QUITTING:
                    break
            pls.save()

        if quick or mailpile.util.QUITTING:
            return count
        else:
            return PostingList._Optimize(session, idx, force=force)

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
            global GLOBAL_POSTING_LIST
            sig = cls.WordSig(word, session.config)
            if GLOBAL_POSTING_LIST is None:
                GLOBAL_POSTING_LIST = {}
            if sig not in GLOBAL_POSTING_LIST:
                GLOBAL_POSTING_LIST[sig] = set()
            for mail_id in mail_ids:
                GLOBAL_POSTING_LIST[sig].add(mail_id)

    def __init__(self, *args, **kwargs):
        with GLOBAL_GPL_LOCK:
            PostingList.__init__(self, *args, **kwargs)
            self.lock = GLOBAL_GPL_LOCK

    def _fmt_file(self, prefix):
        return PostingList._fmt_file(self, 'ALL')

    def _compact(self, prefix, output, **kwargs):
        return prefix, output

    def load(self):
        with self.lock:
            self.filename = 'kw-journal.dat'
            global GLOBAL_POSTING_LIST
            if GLOBAL_POSTING_LIST:
                self.WORDS = GLOBAL_POSTING_LIST
            else:
                PostingList.load(self)
                GLOBAL_POSTING_LIST = self.WORDS

    def _migrate(self, sig=None, compact=True):
        with self.lock:
            sig = sig or self.sig
            if sig in self.WORDS and len(self.WORDS[sig]) > 0:
                PostingList.Append(self.session, sig, self.WORDS[sig],
                                   sig=sig, compact=compact)
                del self.WORDS[sig]

    def remove(self, eids):
        PostingList(self.session, self.word,
                    sig=self.sig, config=self.config).remove(eids).save()
        return PostingList.remove(self, eids)

    def hits(self):
        return (self.WORDS.get(self.sig, set())
                | PostingList(self.session, self.word,
                              sig=self.sig, config=self.config).hits())
