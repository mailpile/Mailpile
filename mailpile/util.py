# coding: utf-8
#
# Misc. utility functions for Mailpile.
#
import cgi
import datetime
import hashlib
import inspect
import locale
import random
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

THREAD_LOCAL = threading.local()

RID_COUNTER = 0
RID_COUNTER_LOCK = threading.Lock()

MAIN_PID = os.getpid()
DEFAULT_PORT = 33411

WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]'
                         ':\"|;`\'\\\<\>\?,\.\/\-]{2,}')

# These next two variables are important for reducing hot-spots in the
# search index and polluting it with spammy results. But adding too many
# terms here makes searches fail, so we need to be careful. Also, the
# spam classifier won't see these things. So again, careful...
STOPLIST = set(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                'a', 'an', 'and', 'any', 'are', 'as', 'at',
                'but', 'by', 'can', 'div', 'do', 'for', 'from',
                'has', 'hello', 'hi', 'i', 'in', 'if', 'is', 'it',
                'mailto', 'me', 'my',
                'og', 'of', 'on', 'or', 'p', 're', 'span', 'so',
                'that', 'the', 'this', 'td', 'to', 'tr',
                'was', 'we', 'were', 'you'])

BORING_HEADERS = ('received', 'received-spf', 'date',
                  'content-type', 'content-disposition', 'mime-version',
                  'list-archive', 'list-help', 'list-unsubscribe',
                  'dkim-signature', 'domainkey-signature')

# For the spam classifier, if these headers are missing a special
# note is made of that in the message keywords.
EXPECTED_HEADERS = ('from', 'to', 'subject', 'date', 'message-id')

# Different attachment types we create keywords for during indexing
ATT_EXTS = {
    'audio': ['aiff', 'aac', 'mid', 'midi', 'mp3', 'mp2', '3gp', 'wav'],
    'code': ['c', 'cpp', 'c++', 'css', 'cxx',
             'h', 'hpp', 'h++', 'html', 'hxx', 'py', 'php', 'pl', 'rb',
             'java', 'js', 'xml'],
    'crypto': ['asc', 'pgp', 'key'],
    'data': ['cfg', 'csv', 'gz', 'json', 'log', 'sql', 'rss', 'tar',
             'tgz', 'vcf', 'xls', 'xlsx'],
    'document': ['csv', 'doc', 'docx', 'htm', 'html', 'md',
                 'odt', 'ods', 'odp', 'ps', 'pdf', 'ppt', 'pptx', 'psd',
                 'txt', 'xls', 'xlsx', 'xml'],
    'font': ['eot', 'otf', 'pfa', 'pfb', 'gsf', 'pcf', 'ttf', 'woff'],
    'image': ['bmp', 'eps', 'gif', 'ico', 'jpeg', 'jpg',
              'png', 'ps', 'psd', 'svg', 'svgz', 'tiff', 'xpm'],
    'video': ['avi', 'divx'],
}
ATT_EXTS['media'] = (ATT_EXTS['audio'] + ATT_EXTS['font'] +
                     ATT_EXTS['image'] + ATT_EXTS['video'])

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

UNI_BOX_FLIPS = [
    (u'\u250c', u'\u2514'), (u'\u250d', u'\u2515'), (u'\u250e', u'\u2516'),
    (u'\u250f', u'\u2517'), (u'\u2510', u'\u2518'), (u'\u2511', u'\u2519'),
    (u'\u2512', u'\u251a'), (u'\u2513', u'\u251b'), (u'\u251d', u'\u251f'),
    (u'\u2521', u'\u2522'), (u'\u2526', u'\u2527'), (u'\u2529', u'\u252a'),
    (u'\u252c', u'\u2534'), (u'\u252d', u'\u2535'), (u'\u252e', u'\u2536'),
    (u'\u252f', u'\u2537'), (u'\u2530', u'\u2538'), (u'\u2531', u'\u2539'),
    (u'\u2532', u'\u253a'), (u'\u2533', u'\u253b'), (u'\u2543', u'\u2545'),
    (u'\u2544', u'\u2546'), (u'\u2547', u'\u2548'), (u'\u2552', u'\u2558'),
    (u'\u2553', u'\u2559'), (u'\u2554', u'\u255a'), (u'\u2555', u'\u255b'),
    (u'\u2556', u'\u255c'), (u'\u2557', u'\u255d'), (u'\u2564', u'\u2567'),
    (u'\u2565', u'\u2568'), (u'\u2566', u'\u2569'), (u'\u256d', u'\u2570'),
    (u'\u256e', u'\u256f'), (u'\u2571', u'\u2572'), (u'\u2575', u'\u2577'),
    (u'\u2579', u'\u257a'), (u'\u257d', u'\u257f')
]
UNI_BOX_FLIP = dict(UNI_BOX_FLIPS + [(b, a) for a, b in UNI_BOX_FLIPS])


##[ Lock debugging tools ]##################################################

def WhereAmI(start=1):
    stack = inspect.stack()
    return '%s' % '->'.join(
        ['%s:%s' % ('/'.join(stack[i][1].split('/')[-2:]), stack[i][2])
         for i in reversed(range(start, len(stack)-1))])


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


class JobPostponingException(Exception):
    seconds = 300


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


def thread_context_push(**kwargs):
    if not hasattr(THREAD_LOCAL, 'context'):
        THREAD_LOCAL.context = []
    THREAD_LOCAL.context.append(kwargs)


def thread_context():
    return THREAD_LOCAL.context if hasattr(THREAD_LOCAL, 'context') else []


def thread_context_pop():
    if hasattr(THREAD_LOCAL, 'context'):
        THREAD_LOCAL.context.pop(-1)


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


def flip_unicode_boxes(text):
    return ''.join(UNI_BOX_FLIP.get(c, c) for c in text)


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


def string_to_intlist(text):
    """Converts a string into an array of integers"""
    try:
        return [ord(c) for c in text.encode('utf-8')]
    except (UnicodeEncodeError, UnicodeDecodeError):
        return [ord(c) for c in text]


def intlist_to_string(intlist):
    chars = ''.join([chr(c) for c in intlist])
    try:
        return chars.decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return chars


def truthy(txt, default=False, special=None):
    try:
        # Floats are fun! :-P
        return (abs(float(txt)) >= 0.00001)
    except (ValueError, TypeError):
        pass

    txt = unicode(txt).lower()
    if special is not None and txt in special:
        return special[txt]
    elif txt in ('n', 'no', 'false', 'off'):
        return False
    elif txt in ('y', 'yes', 'true', 'on'):
        return True
    elif txt in (_('false'), _('no'), _('off')):
        return False
    elif txt in (_('true'), _('yes'), _('on')):
        return True
    else:
        return default


def randomish_uid():
    """
    Generate a weakly random unique ID. Might not actually be unique.
    Leaks the time; uniqueness depends on time moving forward and not
    being invoked too rapidly.
    """
    with RID_COUNTER_LOCK:
        global RID_COUNTER
        RID_COUNTER += 1
        RID_COUNTER %= 0x1000
        return '%3.3x%7.7x%x' % (random.randint(0, 0xfff),
                                 time.time() // 16,
                                 RID_COUNTER)


def okay_random(length, *seeds):
    """
    Generate a psuedo-random string, mixing some seed data with os.urandom().
    The mixing is "just in case" os.urandom() is lame for some unfathomable
    reason. This is hopefully all overkill.
    """
    secret = ''
    while len(secret) < length:
        # Generate unpredictable bytes from the base64 alphabet
        secret += sha512b64(os.urandom(128 + length * 2),
                            '%s' % time.time(),
                            '%x' % random.randint(0, 0xffffffff),
                            *seeds)
        # Strip confusing characters and truncate
        secret = CleanText(secret, banned=CleanText.NONALNUM + 'O01l\n \t'
                           ).clean[:length]
    return secret


def split_secret(secret, recipients, pad_to=24):
    while len(secret) < pad_to:
        secret += '\x00'
    as_bytes = string_to_intlist(secret)
    parts = []
    while len(parts) < recipients-1:
        parts.append(string_to_intlist(os.urandom(len(as_bytes))))
    last = []
    parts.append(last)
    for i in range(0, len(as_bytes)):
        c = as_bytes[i]
        for j in range(0, recipients-1):
            c ^= parts[j][i]
        last.append(c & 0xff)
    return [':'.join(['%2.2x' % x for x in p]) for p in parts]


def merge_secret(parts):
    parts = [[int(c, 16) for c in p.split(':')] for p in parts]
    secret = []
    for i in range(0, len(parts[0])):
        c = parts[0][i]
        for j in range(1, len(parts)):
            c ^= parts[j][i]
        secret.append(c & 0xff)
    while secret[-1] == 0:
        secret[-1:] = []
    return intlist_to_string(secret)


REFLOW_PROSE_START = re.compile(r'\S*\w+')
REFLOW_NONBLANK = re.compile(r'\S')

def reflow_text(text, quoting=False, target_width=65):
    """
    Reflow text so lines are roughly of a uniform length suitable for
    reading or replying. Tries to detect whether the text has already
    been manually formatted and preserve unmodified in such cases.

    >>> test_string = (('abcd efgh ijkl mnop ' + ('q' * 72) + ' ') * 2)[:-1]
    >>> print reflow_text(test_string)
    abcd efgh ijkl mnop
    qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
    abcd efgh ijkl mnop
    qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq

    >>> print reflow_text('> ' + ('q' * 72))
    > qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq

    The function should be stable:

    >>> reflow_text(test_string) == reflow_text(reflow_text(test_string))
    True
    """
    if quoting:
        target_width -= 2
    inlines = text.splitlines()
    outlines = []
    def line_length(l, word):
        return sum(len(w) for w in l) + len(l) + len(word)
    while inlines:
        thisline = inlines.pop(0)
        if (re.match(REFLOW_PROSE_START, thisline)
                and not thisline.endswith('  ')
                and len(thisline) > target_width-10):
            # This line looks like the beginning of a paragraph, go get
            # the rest of the paragraph for reflowing...
            para = thisline.strip().split()
            while (inlines
                    and not inlines[0].endswith('  ')
                    and re.match(REFLOW_PROSE_START, inlines[0])):
                para += inlines.pop(0).strip().split()

            # Once we have the full paragraph, reflow using target width
            paralines = [[]]
            for word in para:
               if line_length(paralines[-1], word) <= target_width:
                   paralines[-1].append(word)
               elif 0 == len(paralines[-1]):
                   paralines[-1].append(word)
               else:
                   paralines.append([word])
            outlines.extend([' '.join(l) for l in paralines])

        else:
            # Not a paragraph, just preserve this line unchanged
            outlines.append(thisline)

    return '\n'.join(outlines)


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
            else:
                return _('%d mins') % minutes_ago
        elif hours_ago < 2:
            return _('%d hour') % hours_ago
        else:
            return _('%d hours') % hours_ago
    elif days_ago < 2:
        return _(ts.strftime('%A'))  #return _('%d day') % days_ago
    elif days_ago < 7:
        return _(ts.strftime('%A'))  #return _('%d days') % days_ago
    elif days_ago < 366:
        return _(ts.strftime("%b")) + ts.strftime(" %d")
    else:
        return _(ts.strftime("%b")) + ts.strftime(" %d %Y")

_translate_these = [_('Monday'), _('Mon'), _('Tuesday'), _('Tue'),
                    _('Wednesday'), _('Wed'), _('Thursday'), _('Thu'),
                    _('Friday'), _('Fri'), _('Saturday'), _('Sat'),
                    _('Sunday'), _('Sun'),
                    _('January'), _('Jan'), _('February'), _('Feb'),
                    _('March'), _('Mar'), _('April'), _('Apr'),
                    _('May'), _('June'), _('Jun'),
                    _('July'), _('Jul'), _('August'), _('Aug'),
                    _('September'), _('Sep'), _('October'), _('Oct'),
                    _('November'), _('Nov'), _('December'), _('Dec')]


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
    >>> friendly_number(10230)
    '10k'
    >>> friendly_number(12341234, decimals=1)
    '12.3M'
    >>> friendly_number(1024000000, base=1024, suffix='iB')
    '977MiB'
    """
    count = 0
    number = float(number)
    while number > base and count < len(powers):
        number /= base
        count += 1
    if decimals:
        fmt = '%%.%df%%s%%s' % decimals
    else:
        number = round(number)
        fmt = '%d%s%s'
    return fmt % (number, powers[count], suffix)


def decrypt_and_parse_lines(fd, parser, config,
                            newlines=False, decode='utf-8',
                            passphrase=None,
                            _raise=IOError, error_cb=None):
    import mailpile.crypto.streamer as cstrm
    symmetric_key = config and config.master_key or 'missing'
    passphrase_reader = (passphrase.get_reader()
                         if (passphrase is not None) else
                         (config.passphrases['DEFAULT'].get_reader()
                          if (config is not None) else None))

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
                    gpg_pass=passphrase_reader) as pdsfd:
                _parser(pdsfd)
                if not pdsfd.verify(_raise=_raise) and error_cb:
                    error_cb(fd.tell())
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
    try:
        return unicode(obj)
    except:
        return "COMPLEXBLOB"

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


def play_nice(niceness):
    if hasattr(os, 'nice'):
        os.nice(niceness)


def play_nice_with_threads(sleep=True, weak=False, deadline=None):
    """
    Long-running batch jobs should call this now and then to pause
    their activities in case there are other threads that would like to
    run. Recent user activity increases the delay significantly, to
    hopefully make the app more responsive when it is in use.
    """
    if weak or threading.activeCount() < 4:
        time.sleep(0)
        return 0

    deadline = (time.time() + 5) if (deadline is None) else deadline
    while True:
        activity_threshold = (180 - time.time() + LAST_USER_ACTIVITY) / 120
        delay = max(0.001, min(0.1, 0.1 * activity_threshold))
        if not sleep:
            break

        # This isn't just about sleeping, this is also basically a hack
        # to release the GIL and let other threads run.
        if LIVE_USER_ACTIVITIES < 1:
            time.sleep(delay)
        else:
            time.sleep(max(delay, 0.250))

        if QUITTING or LIVE_USER_ACTIVITIES < 1:
            break
        if time.time() > deadline:
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
    NONPATH = ''.join([chr(c) for c in (set(range(32, 127)) -
                                        set(range(ord('0'), ord('9') + 1)) -
                                        set(range(ord('a'), ord('z') + 1)) -
                                        set(range(ord('A'), ord('Z') + 1)) -
                                        set([ord('_'), ord('/')]))])

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


def monkey_patch(org_func, wrapper):
    """
    A utility to help with monkey patching, returns a new function where
    org_func has been wrapped by the given wrapper.

    >>> foo = monkey_patch(lambda a: a + 1, lambda o, a: o(a + 100))
    >>> foo(1)
    102
    """
    def wrap(*args, **kwargs):
        return wrapper(org_func, *args, **kwargs)
    return wrap


# If 'python util.py' is executed, start the doctest unittest
if __name__ == "__main__":
    import doctest
    import sys
    result = doctest.testmod()
    print '%s' % (result, )
    if result.failed:
        sys.exit(1)
