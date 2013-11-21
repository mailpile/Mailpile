import os
import random
import threading

import mailpile.util
from mailpile.util import *


GLOBAL_POSTING_LIST = None

GLOBAL_POSTING_LOCK = threading.Lock()
GLOBAL_OPTIMIZE_LOCK = threading.Lock()


class PostingList(object):
    """A posting list is a map of search terms to message IDs."""

    CHARACTERS = 'abcdefghijklmnopqrstuvwxyz0123456789+_'

    MAX_SIZE = 60    # perftest gives: 75% below 500ms, 50% below 100ms
    HASH_LEN = 24

    @classmethod
    def _Optimize(cls, session, idx, force=False):
        flush_append_cache()

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
                    # FIXME: Remove invalid and deleted messages from
                    #        posting lists.
                    cls(session, fn, sig=fn).save()

        # Pass 2: While mergable pair exists: merge them!
        flush_append_cache()
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
                if (size < (1024 * postinglist_kb - (cls.HASH_LEN * 6))):
                    session.ui.mark('Pass 2: Merging %s into %s' % (fn, fnp))
                    fd = cached_open(os.path.join(postinglist_dir, fn), 'r')
                    fdp = cached_open(os.path.join(postinglist_dir, fnp), 'a')
                    try:
                        for line in fd:
                            fdp.write(line)
                    except:
                        flush_append_cache()
                        raise
                    finally:
                        fd.close()
                        os.remove(os.path.join(postinglist_dir, fn))

        flush_append_cache()
        filecount = 0
        for c in cls.CHARACTERS:
            filecount += len(os.listdir(session.config.postinglist_dir(c)))
        session.ui.mark('Optimized %s posting lists' % filecount)
        return filecount

    @classmethod
    def _Append(cls, session, word, mail_ids, compact=True, sig=None):
        config = session.config
        sig = sig or cls.WordSig(word, config)
        fd, fn = cls.GetFile(session, sig, mode='a')
        if (compact
        and (os.path.getsize(os.path.join(config.postinglist_dir(fn), fn))
                > (1024 * config.sys.postinglist_kb) - (cls.HASH_LEN * 6))
        and (random.randint(0, 50) == 1)):
            # This will compact the files and split out hot-spots, but we
            # only bother "once in a while" when the files are "big".
            fd.close()
            pls = cls(session, word, sig=sig)
            for mail_id in mail_ids:
                pls.append(mail_id)
            pls.save()
        else:
            # Quick and dirty append is the default.
            fd.write('%s\t%s\n' % (sig, '\t'.join(mail_ids)))

    @classmethod
    def Lock(cls, lock, method, *args, **kwargs):
        lock.acquire()
        try:
            return method(*args, **kwargs)
        finally:
            lock.release()

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
                    return (cached_open(fn, mode), sig)
            except (IOError, OSError):
                pass

            if len(sig) > 1:
                sig = sig[:-1]
            else:
                if 'r' in mode:
                    return (None, sig)
                else:
                    return (cached_open(fn, mode), sig)
        # Not reached
        return (None, None)

    def __init__(self, session, word, sig=None, config=None):
        self.config = config or session.config
        self.session = session
        self.sig = sig or self.WordSig(word, self.config)
        self.word = word
        self.WORDS = {self.sig: set()}
        self.lock = threading.Lock()
        self.load()

    def _parse_line(self, line):
        words = line.strip().split('\t')
        if len(words) > 1:
            if words[0] not in self.WORDS:
                self.WORDS[words[0]] = set()
            self.WORDS[words[0]] |= set(words[1:])

    def load(self):
        self.size = 0
        fd, self.filename = self.GetFile(self.session, self.sig)
        if fd:
            try:
                self.lock.acquire()
                self.size = decrypt_and_parse_lines(fd, self._parse_line)
            except ValueError:
                pass
            finally:
                fd.close()
                self.lock.release()

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
                    try:
                        fd = cached_open(outfile, mode)
                        fd.write(output)
                        return len(output)
                    finally:
                        if mode != 'a' and fd:
                            fd.close()
                elif os.path.exists(outfile):
                    os.remove(outfile)
                    flush_append_cache()
            except:
                self.session.ui.warning('%s' % (sys.exc_info(), ))
            return 0
        finally:
            if not locked:
                self.lock.release()

    def hits(self):
        return self.WORDS[self.sig]

    def append(self, eid):
        self.lock.acquire()
        try:
            if self.sig not in self.WORDS:
                self.WORDS[self.sig] = set()
            self.WORDS[self.sig].add(eid)
            return self
        finally:
            self.lock.release()

    def remove(self, eids):
        self.lock.acquire()
        try:
            for eid in eids:
                try:
                    self.WORDS[self.sig].remove(eid)
                except KeyError:
                    pass
            return self
        finally:
            self.lock.release()


class GlobalPostingList(PostingList):

    @classmethod
    def _Optimize(cls, session, idx, force=False, quick=False):
        pls = GlobalPostingList(session, '')
        count = 0
        keys = sorted(GLOBAL_POSTING_LIST.keys())
        for sig in keys:
            if (count % 50) == 0:
                session.ui.mark(('Updating search index... %d%% (%s)'
                                 ) % (count * 100 / len(keys), sig))
            pls.migrate(sig, compact=quick)
            count += 1
        pls.save()

        if quick:
            return count
        else:
            return PostingList._Optimize(session, idx, force=force)

    @classmethod
    def SaveFile(cls, session, prefix):
        return os.path.join(session.config.workdir, 'kw-journal.dat')

    @classmethod
    def GetFile(cls, session, sig, mode='r'):
        try:
            return (cached_open(cls.SaveFile(session, sig), mode),
                    'kw-journal.dat')
        except (IOError, OSError):
            return (None, 'kw-journal.dat')

    @classmethod
    def Append(cls, session, word, mail_ids, compact=True):
        super(GlobalPostingList, cls).Append(session, word, mail_ids,
                                             compact=compact)
        global GLOBAL_POSTING_LIST
        sig = cls.WordSig(word, session.config)
        if GLOBAL_POSTING_LIST is None:
            GLOBAL_POSTING_LIST = {}
        if sig not in GLOBAL_POSTING_LIST:
            GLOBAL_POSTING_LIST[sig] = set()
        for mail_id in mail_ids:
            GLOBAL_POSTING_LIST[sig].add(mail_id)

    def _fmt_file(self, prefix):
        return PostingList._fmt_file(self, 'ALL')

    def _compact(self, prefix, output, **kwargs):
        return prefix, output

    def load(self):
        self.filename = 'kw-journal.dat'
        global GLOBAL_POSTING_LIST
        if GLOBAL_POSTING_LIST:
            self.WORDS = GLOBAL_POSTING_LIST
        else:
            PostingList.load(self)
            GLOBAL_POSTING_LIST = self.WORDS

    def migrate(self, sig=None, compact=True):
        self.lock.acquire()
        try:
            sig = sig or self.sig
            if sig in self.WORDS and len(self.WORDS[sig]) > 0:
                PostingList.Append(self.session, sig, self.WORDS[sig],
                                                      sig=sig, compact=compact)
                del self.WORDS[sig]
        finally:
            self.lock.release()

    def remove(self, eids):
        PostingList(self.session, self.word,
                    sig=self.sig, config=self.config).remove(eids).save()
        return PostingList.remove(self, eids)

    def hits(self):
        return (self.WORDS.get(self.sig, set())
                | PostingList(self.session, self.word,
                              sig=self.sig, config=self.config).hits())
