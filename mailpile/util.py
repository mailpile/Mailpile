# coding: utf-8
#
# Misc. utility functions for Mailpile.
#
import cgi
import datetime
import hashlib
import inspect
import locale
import re
import subprocess
import os
import sys
import string
import tempfile
import threading
import time
import StringIO
from distutils import spawn

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.safe_popen import Popen, PIPE


try:
    from PIL import Image
except:
    Image = None


global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT, QUITTING


TESTING = False
QUITTING = False
LAST_USER_ACTIVITY = 0
LIVE_USER_ACTIVITIES = 0

MAIN_PID = os.getpid()
DEFAULT_PORT = 33411

WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]'
                         ':\"|;\'\\\<\>\?,\.\/\-]{2,}')

PROSE_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]'
                          ':\"|;\'\\\<\>\?,\.\/\-]{1,}')

STOPLIST = set(['an', 'and', 'are', 'as', 'at', 'by', 'for', 'from',
                'has', 'i', 'in', 'is', 'it',
                'mailto', 'me',
                'og', 'or', 're', 'so', 'the', 'to', 'was', 'you'])

BORING_HEADERS = ('received', 'date',
                  'content-type', 'content-disposition', 'mime-version',
                  'dkim-signature', 'domainkey-signature', 'received-spf')

EXPECTED_HEADERS = ('from', 'to', 'subject', 'date')

B64C_STRIP = '\r\n='

B64C_TRANSLATE = string.maketrans('/', '_')

B64W_TRANSLATE = string.maketrans('/+', '_-')

STRHASH_RE = re.compile('[^0-9a-z]+')

ALPHA_RE  = re.compile("\A[a-zA-Z]+\Z")
EMAIL_RE = re.compile("\A.+@.+\Z")
DNSNAME_RE = re.compile("\A([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,32}\Z")

B36_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'

RE_LONG_LINE_SPLITTER = re.compile('([^\n]{,72}) ')

# see: http://www.iana.org/assignments/uri-schemes/uri-schemes.xhtml
# currently we just use common ones
PERMANENT_URI_SCHEMES = set([
  "data", "file", "ftp", "gopher", "http", "https", "imap",
  "jabber", "mailto", "news", "telnet", "tftp", "ws", "wss"
])
PROVISIONAL_URI_SCHEMES = set([
  "bitcoin", "chrome", "cvs", "feed", "git", "irc", "magnet",
  "sftp", "smtp", "ssh", "steam", "svn"
])
URI_SCHEMES = PERMANENT_URI_SCHEMES.union(PROVISIONAL_URI_SCHEMES)

def WhereAmI(start=1):
    stack = inspect.stack()
    return '%s' % '->'.join(
        ['%s:%s' % ('/'.join(stack[i][1].split('/')[-2:]), stack[i][2])
         for i in reversed(range(start, len(stack)-1))])


##[ Lock debugging tools ]##################################################

def _TracedLock(what, *a, **kw):
    lock = what(*a, **kw)

    class Wrapper:
        def acquire(self, *args, **kwargs):
            if self.locked():
                print '==!== Waiting for %s at %s' % (str(lock), WhereAmI(2))
            return lock.acquire(*args, **kwargs)
        def release(self, *args, **kwargs):
            return lock.release(*args, **kwargs)
        def __enter__(self, *args, **kwargs):
            if self.locked():
                print '==!== Waiting for %s at %s' % (str(lock), WhereAmI(2))
            return lock.__enter__(*args, **kwargs)
        def __exit__(self, *args, **kwargs):
            return lock.__exit__(*args, **kwargs)
        def _is_owned(self, *args, **kwargs):
            return lock._is_owned(*args, **kwargs)
        def locked(self, *args, **kwargs):
            acquired = False
            try:
                acquired = lock.acquire(False)
                return (not acquired)
            finally:
                if acquired:
                    lock.release()

    return Wrapper()


def TracedLock(*args, **kwargs):
    return _TracedLock(threading.Lock, *args, **kwargs)


def TracedRLock(*args, **kwargs):
    return _TracedLock(threading.RLock, *args, **kwargs)


TracedLocks = (TracedLock, TracedRLock)
UnTracedLocks = (threading.Lock, threading.RLock)

# Replace with as necessary TracedLocks to track down deadlocks.
EventLock, EventRLock = UnTracedLocks
ConfigLock, ConfigRLock = UnTracedLocks
CryptoLock, CryptoRLock = UnTracedLocks
UiLock, UiRLock = UnTracedLocks
WorkerLock, WorkerRLock = UnTracedLocks
MboxLock, MboxRLock = UnTracedLocks
SearchLock, SearchRLock = UnTracedLocks
PListLock, PListRLock = UnTracedLocks
VCardLock, VCardRLock = UnTracedLocks
MSrcLock, MSrcRLock = UnTracedLocks

##############################################################################


class WorkerError(Exception):
    pass


class UsageError(Exception):
    pass


class AccessError(Exception):
    pass


class UrlRedirectException(Exception):
    """An exception indicating we need to redirecting to another URL."""
    def __init__(self, url):
        Exception.__init__(self, 'Should redirect to: %s' % url)
        self.url = url


class MultiContext:
    def __init__(self, contexts):
        self.contexts = contexts or []

    def __enter__(self, *args, **kwargs):
        for ctx in self.contexts:
            ctx.__enter__(*args, **kwargs)
        return self

    def __exit__(self, *args, **kwargs):
        raised = []
        for ctx in reversed(self.contexts):
            try:
                ctx.__exit__(*args, **kwargs)
            except Exception as e:
                raised.append(e)
        if raised:
            raise raised[0]


def FixupForWith(obj):
    if not hasattr(obj, '__enter__'):
        obj.__enter__ = lambda: obj
    if not hasattr(obj, '__exit__'):
        obj.__exit__ = lambda a, b, c: True
    return obj


def b64c(b):
    """
    Rewrite a base64 string:
        - Remove LF and = characters
        - Replace slashes by underscores

    >>> b64c("abc123456def")
    'abc123456def'
    >>> b64c("\\na/=b=c/")
    'a_bc_'
    >>> b64c("a+b+c+123+")
    'a+b+c+123+'
    """
    return string.translate(b, B64C_TRANSLATE, B64C_STRIP)


def b64w(b):
    """
    Rewrite a base64 string by replacing
    "+" by "-" (e.g. for URLs).

    >>> b64w("abc123456def")
    'abc123456def'
    >>> b64w("a+b+c+123+")
    'a-b-c-123-'
    """
    return string.translate(b, B64W_TRANSLATE, B64C_STRIP)


def escape_html(t):
    """
    Replace characters that have a special meaning in HTML
    by their entity equivalents. Return the replaced
    string.

    >>> escape_html("Hello, Goodbye.")
    'Hello, Goodbye.'
    >>> escape_html("Hello<>World")
    'Hello&lt;&gt;World'
    >>> escape_html("<&>")
    '&lt;&amp;&gt;'

    Keyword arguments:
    t -- The string to escape
    """
    return cgi.escape(t)


def _hash(cls, data):
    h = cls()
    for s in data:
        if isinstance(s, unicode):
            h.update(s.encode('utf-8'))
        else:
            h.update(s)
    return h


def sha1b64(*data):
    """
    Apply the SHA1 hash algorithm to a string
    and return the base64-encoded hash value

    >>> sha1b64("Hello")
    '9/+ei3uy4Jtwk1pdeF4MxdnQq/A=\\n'

    >>> sha1b64(u"Hello")
    '9/+ei3uy4Jtwk1pdeF4MxdnQq/A=\\n'

    Keyword arguments:
    s -- The string to hash
    """
    return _hash(hashlib.sha1, data).digest().encode('base64')


def sha512b64(*data):
    """
    Apply the SHA512 hash algorithm to a string
    and return the base64-encoded hash value

    >>> sha512b64("Hello")[:64]
    'NhX4DJ0pPtdAJof5SyLVjlKbjMeRb4+sf933+9WvTPd309eVp6AKFr9+fz+5Vh7p'
    >>> sha512b64(u"Hello")[:64]
    'NhX4DJ0pPtdAJof5SyLVjlKbjMeRb4+sf933+9WvTPd309eVp6AKFr9+fz+5Vh7p'

    Keyword arguments:
    s -- The string to hash
    """
    return _hash(hashlib.sha512, data).digest().encode('base64')


def md5_hex(*data):
    return _hash(hashlib.md5, data).hexdigest()


def strhash(s, length, obfuscate=None):
    """
    Create a hash of

    >>> strhash("Hello", 10)
    'hello9_+ei'
    >>> strhash("Goodbye", 5, obfuscate="mysalt")
    'voxpj'

    Keyword arguments:
    s -- The string to be hashed
    length -- The length of the hash to create.
                        Might be limited by the hash method
    obfuscate -- None to disable SHA512 obfuscation,
                             or a salt to append to the string
                             before hashing
    """
    if obfuscate:
        hashedStr = b64c(sha512b64(s, obfuscate).lower())
    else:  # Don't obfuscate
        hashedStr = re.sub(STRHASH_RE, '', s.lower())[:(length - 4)]
        while len(hashedStr) < length:
            hashedStr += b64c(sha1b64(s)).lower()
    return hashedStr[:length]


def b36(number):
    """
    Convert a number to base36

    >>> b36(2701)
    '231'
    >>> b36(12345)
    '9IX'
    >>> b36(None)
    '0'

    Keyword arguments:
    number -- An integer to convert to base36
    """
    if not number or number < 0:
        return B36_ALPHABET[0]
    base36 = []
    while number:
        number, i = divmod(number, 36)
        base36.append(B36_ALPHABET[i])
    return ''.join(reversed(base36))


def split_long_lines(text):
    """
    Split long lines of text into shorter ones, ignoring ascii art.

    >>> test_string = (('abcd efgh ijkl mnop ' + ('q' * 72) + ' ') * 2)[:-1]
    >>> print split_long_lines(test_string)
    abcd efgh ijkl mnop
    qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
    abcd efgh ijkl mnop
    qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq

    >>> print split_long_lines('> ' + ('q' * 72))
    > qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq

    The function should be stable:

    >>> split_long_lines(test_string) == split_long_lines(
    ...                                    split_long_lines(test_string))
    True
    """
    lines = text.splitlines()
    for i in range(0, len(lines)):
        buffered, done = [], False
        while (not done and
               len(lines[i]) > 72 and
               re.match(PROSE_REGEXP, lines[i])):
            n = re.sub(RE_LONG_LINE_SPLITTER, '\\1\n', lines[i], 1
                       ).split('\n')
            if len(n) == 1:
                done = True
            else:
                buffered.append(n[0])
                lines[i] = n[1]
        if buffered:
            lines[i] = '\n'.join(buffered + [lines[i]])
    return '\n'.join(lines)


def elapsed_datetime(timestamp):
    """
    Return "X days ago" style relative dates for recent dates.
    """
    ts = datetime.datetime.fromtimestamp(timestamp)
    elapsed = datetime.datetime.today() - ts
    days_ago = elapsed.days
    hours_ago, remainder = divmod(elapsed.seconds, 3600)
    minutes_ago, seconds_ago = divmod(remainder, 60)

    if days_ago < 1:
        if hours_ago < 1:
            if minutes_ago < 3:
                return _('now')
            elif minutes_ago >= 3:
                return _('%d mins') % minutes_ago
        elif hours_ago < 2:
            return _('%d hour') % hours_ago
        else:
            return _('%d hours') % hours_ago
    elif days_ago < 2:
        return _('%d day') % days_ago
    elif days_ago < 7:
        return _('%d days') % days_ago
    elif days_ago < 366:
        return ts.strftime("%b %d")
    else:
        return ts.strftime("%b %d %Y")


def friendly_datetime(timestamp):
    date = datetime.date.fromtimestamp(timestamp)
    return date.strftime("%b %d, %Y")


def friendly_time(timestamp):
    date = datetime.datetime.fromtimestamp(timestamp)
    return date.strftime("%H:%M")


def friendly_number(number, base=1000, decimals=0, suffix='',
                    powers=['', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']):
    """
    Format a number as friendly text, using common suffixes.

    >>> friendly_number(102)
    '102'
    >>> friendly_number(10240)
    '10k'
    >>> friendly_number(12341234, decimals=1)
    '12.3M'
    >>> friendly_number(1024000000, base=1024, suffix='iB')
    '976MiB'
    """
    count = 0
    number = float(number)
    while number > base and count < len(powers):
        number /= base
        count += 1
    if decimals:
        fmt = '%%.%df%%s%%s' % decimals
    else:
        fmt = '%d%s%s'
    return fmt % (number, powers[count], suffix)


def decrypt_and_parse_lines(fd, parser, config,
                            newlines=False, decode='utf-8',
                            _raise=IOError):
    import mailpile.crypto.streamer as cstrm
    symmetric_key = config and config.master_key or 'missing'

    if not newlines:
        if decode:
            _parser = lambda ll: parser((l.rstrip('\r\n').decode(decode)
                                         for l in ll))
        else:
            _parser = lambda ll: parser((l.rstrip('\r\n') for l in ll))
    elif decode:
        _parser = lambda ll: parser((l.decode(decode) for l in ll))
    else:
        _parser = parser

    for line in fd:
        if cstrm.PartialDecryptingStreamer.StartEncrypted(line):
            with cstrm.PartialDecryptingStreamer(
                    [line], fd,
                    name='decrypt_and_parse',
                    mep_key=symmetric_key,
                    gpg_pass=(config.gnupg_passphrase.get_reader()
                              if config else None)) as pdsfd:
                _parser(pdsfd)
                pdsfd.verify(_raise=_raise)
        else:
            _parser([line])



# This is a hack to deal with the fact that Windows sometimes won't
# let us delete files right away because it thinks they are still open.
# Any failed removal just gets queued up for later.
#
PENDING_REMOVAL = []
PENDING_REMOVAL_LOCK = threading.Lock()

def safe_remove(filename=None):
    with PENDING_REMOVAL_LOCK:
        if filename:
            PENDING_REMOVAL.append(filename)
        for fn in PENDING_REMOVAL[:]:
            try:
                os.remove(fn)
                PENDING_REMOVAL.remove(fn)
            except (OSError, IOError):
                pass
        return (filename and filename not in PENDING_REMOVAL)


def backup_file(filename, backups=5, min_age_delta=0):
    if os.path.exists(filename):
        if os.stat(filename).st_mtime >= time.time() - min_age_delta:
            return

        for ver in reversed(range(1, backups)):
            bf = '%s.%d' % (filename, ver)
            if os.path.exists(bf):
                nbf = '%s.%d' % (filename, ver+1)
                if os.path.exists(nbf):
                    os.remove(nbf)
                os.rename(bf, nbf)
        os.rename(filename, '%s.1' % filename)


def json_helper(obj):
    if isinstance(obj, datetime.datetime):
        return str(obj)


class GpgWriter(object):
    def __init__(self, gpg):
        self.fd = gpg.stdin
        self.gpg = gpg

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def write(self, data):
        self.fd.write(data)

    def close(self):
        self.fd.close()
        self.gpg.wait()


def dict_merge(*dicts):
    """
    Merge one or more dicts into one.

    >>> d = dict_merge({'a': 'A'}, {'b': 'B'}, {'c': 'C'})
    >>> sorted(d.keys()), sorted(d.values())
    (['a', 'b', 'c'], ['A', 'B', 'C'])
    """
    final = {}
    for d in dicts:
        final.update(d)
    return final


def play_nice_with_threads(sleep=True):
    """
    Long-running batch jobs should call this now and then to pause
    their activities in case there are other threads that would like to
    run. Recent user activity increases the delay significantly, to
    hopefully make the app more responsive when it is in use.
    """
    threads = threading.activeCount() - 3
    if threads < 1:
        return 0

    lc = 0
    while True:
        activity_threshold = (300 - time.time() + LAST_USER_ACTIVITY) / 300
        delay = (max(0, 0.002 * threads) +
                 max(0, min(0.10, 0.400 * activity_threshold)))
        if not sleep:
            break

        # This isn't just about sleeping, this is also basically a hack
        # to release the GIL and let other threads run.
        time.sleep(delay)

        lc += 1
        if QUITTING or LIVE_USER_ACTIVITIES < 1 or lc > 10:
            break

    return delay


def thumbnail(fileobj, output_fd, height=None, width=None):
    """
    Generates a thumbnail image , which should be a file,
    StringIO, or string, containing a PIL-supported image.
    FIXME: Failure modes unmanaged.

    Keyword arguments:
    fileobj -- Either a StringIO instance, a file object or
                         a string (containing the image) to
                         read the source image from
    output_fd -- A file object or filename, or StringIO to
    """
    if not Image:
        # If we don't have PIL, we just return the supplied filename in
        # the hopes that somebody had the good sense to extract the
        # right attachment to that filename...
        return None

    # Ensure the source image is either a file-like object or a StringIO
    if (not isinstance(fileobj, (file, StringIO.StringIO))):
        fileobj = StringIO.StringIO(fileobj)

    image = Image.open(fileobj)

    # defining the size
    if height is None and width is None:
        raise Exception("Must supply width or height!")
    # If only one coordinate is given, calculate the
    # missing one in order to make the thumbnail
    # have the same proportions as the source img
    if height and not width:
        x = height
        y = int((float(height) / image.size[0]) * image.size[1])
    elif width and not height:
        y = width
        x = int((float(width) / image.size[1]) * image.size[0])
    else:  # We have both sizes
        y = width
        x = height
    try:
        image.thumbnail([x, y], Image.ANTIALIAS)
    except IOError:
        return None

    # If saving an optimized image fails, save it unoptimized
    # Keep the format (png, jpg) of the source image
    try:
        image.save(output_fd, format=image.format, quality=90, optimize=1)
    except:
        image.save(output_fd, format=image.format, quality=90)

    return image


class CleanText:
    """
    This is a helper class for aggressively cleaning text, dumbing it
    down to just ASCII and optionally forbidding some characters.

    >>> CleanText(u'clean up\\xfe', banned='up ').clean
    'clean'
    >>> CleanText(u'clean\\xfe', replace='_').clean
    'clean_'
    >>> CleanText(u'clean\\t').clean
    'clean\\t'
    >>> str(CleanText(u'c:\\\\l/e.an', banned=CleanText.FS))
    'clean'
    >>> CleanText(u'c_(l e$ a) n!', banned=CleanText.NONALNUM).clean
    'clean'
    """
    FS = ':/.\'\"\\'
    CRLF = '\r\n'
    WHITESPACE = '\r\n\t '
    NONALNUM = ''.join([chr(c) for c in (set(range(32, 127)) -
                                         set(range(ord('0'), ord('9') + 1)) -
                                         set(range(ord('a'), ord('z') + 1)) -
                                         set(range(ord('A'), ord('Z') + 1)))])
    NONDNS = ''.join([chr(c) for c in (set(range(32, 127)) -
                                       set(range(ord('0'), ord('9') + 1)) -
                                       set(range(ord('a'), ord('z') + 1)) -
                                       set(range(ord('A'), ord('Z') + 1)) -
                                       set([ord('-'), ord('_'), ord('.')]))])
    NONVARS = ''.join([chr(c) for c in (set(range(32, 127)) -
                                        set(range(ord('0'), ord('9') + 1)) -
                                        set(range(ord('a'), ord('z') + 1)) -
                                        set([ord('_')]))])

    def __init__(self, text, banned='', replace=''):
        self.clean = str("".join([i if (((ord(i) > 31 and ord(i) < 127) or
                                         (i in self.WHITESPACE)) and
                                        i not in banned) else replace
                                  for i in (text or '')]))

    def __str__(self):
        return str(self.clean)

    def __unicode__(self):
        return unicode(self.clean)


def HideBinary(text):
    try:
        text.decode('utf-8')
        return text
    except UnicodeDecodeError:
        return '[BINARY DATA, %d BYTES]' % len(text)


class TimedOut(IOError):
    """We treat timeouts as a particular type of IO error."""
    pass


class RunTimedThread(threading.Thread):
    def __init__(self, name, func):
        threading.Thread.__init__(self, target=func)
        self.name = name
        self.daemon = True

    def run_timed(self, timeout):
        self.start()
        self.join(timeout=timeout)
        if self.isAlive() or QUITTING:
            raise TimedOut('Timed out: %s' % self.name)


def RunTimed(timeout, func, *args, **kwargs):
    result, exception = [], []
    def work():
        try:
            result.append(func(*args, **kwargs))
        except:
            et, ev, etb = sys.exc_info()
            exception.append((et, ev, etb))
    RunTimedThread(func.__name__, work).run_timed(timeout)
    if exception:
        t, v, tb = exception[0]
        raise t, v, tb
    return result[0]


class DebugFileWrapper(object):
    def __init__(self, dbg, fd):
        self.fd = fd
        self.dbg = dbg

    def __getattribute__(self, name):
        if name in ('fd', 'dbg', 'write', 'flush', 'close'):
            return object.__getattribute__(self, name)
        else:
            self.dbg.write('==(%d.%s)\n' % (self.fd.fileno(), name))
            return object.__getattribute__(self.fd, name)

    def write(self, data, *args, **kwargs):
        self.dbg.write('<=(%d.write)= %s\n' % (self.fd.fileno(),
                                               HideBinary(data).rstrip()))
        return self.fd.write(data, *args, **kwargs)

    def flush(self, *args, **kwargs):
        self.dbg.write('==(%d.flush)\n' % self.fd.fileno())
        return self.fd.flush(*args, **kwargs)

    def close(self, *args, **kwargs):
        self.dbg.write('==(%d.close)\n' % self.fd.fileno())
        return self.fd.close(*args, **kwargs)


# If 'python util.py' is executed, start the doctest unittest
if __name__ == "__main__":
    import doctest
    import sys
    result = doctest.testmod()
    print '%s' % (result, )
    if result.failed:
        sys.exit(1)
