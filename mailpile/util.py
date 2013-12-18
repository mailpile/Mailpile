# coding: utf-8
#
# Misc. utility functions for Mailpile.
#
import cgi
import datetime
import hashlib
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

try:
    import Image
except:
    Image = None


global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER, APPEND_FD_CACHE_SIZE
global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT, QUITTING


QUITTING = False

DEFAULT_PORT = 33411

WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]'
                         ':\"|;\'\\\<\>\?,\.\/\-]{2,}')

STOPLIST = set(['an', 'and', 'are', 'as', 'at', 'by', 'for', 'from',
                'has', 'http', 'in', 'is', 'it', 'mailto', 'og', 'or',
                're', 'so', 'the', 'to', 'was'])

BORING_HEADERS = ('received', 'date',
                  'content-type', 'content-disposition', 'mime-version',
                  'dkim-signature', 'domainkey-signature', 'received-spf')

B64C_STRIP = '\n='

B64C_TRANSLATE = string.maketrans('/', '_')

B64W_TRANSLATE = string.maketrans('/+', '_-')

STRHASH_RE = re.compile('[^0-9a-z]+')

B36_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


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


def sha1b64(s):
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
    return _hash(hashlib.sha1, [s]).digest().encode('base64')


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
    if not number:
        return B36_ALPHABET[0]
    base36 = []
    while number:
        number, i = divmod(number, 36)
        base36.append(B36_ALPHABET[i])
    return ''.join(reversed(base36))


def elapsed_datetime(timestamp):
    """
    Return "X days ago" style relative dates for recent dates.
    """
    ts = datetime.date.fromtimestamp(timestamp)
    days_ago = (datetime.date.today() - ts).days

    if days_ago < 1:
        return _('today')
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


GPG_BEGIN_MESSAGE = '-----BEGIN PGP MESSAGE'
GPG_END_MESSAGE = '-----END PGP MESSAGE'


def decrypt_gpg(lines, fd):
    for line in fd:
        lines.append(line)
        if line.startswith(GPG_END_MESSAGE):
            break

    gpg = subprocess.Popen(['gpg', '--batch'],
                                                 stdin=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 stdout=subprocess.PIPE)
    lines = gpg.communicate(input=''.join(lines))[0].splitlines(True)
    if gpg.wait() != 0:
        raise AccessError("GPG was unable to decrypt the data.")

    return lines


def decrypt_and_parse_lines(fd, parser):
    size = 0
    for line in fd:
        size += len(line)
        if line.startswith(GPG_BEGIN_MESSAGE):
            for line in decrypt_gpg([line], fd):
                parser(line.decode('utf-8'))
        else:
            parser(line.decode('utf-8'))
    return size


def gpg_open(filename, recipient, mode):
    fd = open(filename, mode)
    if recipient and ('a' in mode or 'w' in mode):
        gpg = subprocess.Popen(['gpg', '--batch', '-aer', recipient],
                               stdin=subprocess.PIPE,
                               stdout=fd)
        return gpg.stdin
    return fd


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


# Indexing messages is an append-heavy operation, and some files are
# appended to much more often than others.  This implements a simple
# LRU cache of file descriptors we are appending to.
APPEND_FD_CACHE = {}
APPEND_FD_CACHE_SIZE = 500
APPEND_FD_CACHE_ORDER = []
APPEND_FD_CACHE_LOCK = threading.Lock()


def flush_append_cache(ratio=1, count=None, lock=True):
    try:
        if lock:
            APPEND_FD_CACHE_LOCK.acquire()
        drop = count or int(ratio * len(APPEND_FD_CACHE_ORDER))
        for fn in APPEND_FD_CACHE_ORDER[:drop]:
            try:
                APPEND_FD_CACHE[fn].close()
                del APPEND_FD_CACHE[fn]
            except KeyError:
                pass
        APPEND_FD_CACHE_ORDER[:drop] = []
    finally:
        if lock:
            APPEND_FD_CACHE_LOCK.release()


def cached_open(filename, mode):
    try:
        APPEND_FD_CACHE_LOCK.acquire()
        if mode == 'a':
            fd = None
            if filename in APPEND_FD_CACHE:
                APPEND_FD_CACHE_ORDER.remove(filename)
                fd = APPEND_FD_CACHE[filename]
            if not fd or fd.closed:
                if len(APPEND_FD_CACHE) > APPEND_FD_CACHE_SIZE:
                    flush_append_cache(count=1, lock=False)
                try:
                    fd = APPEND_FD_CACHE[filename] = open(filename, 'a')
                except (IOError, OSError):
                    # Too many open files?    Close a bunch and try again.
                    flush_append_cache(ratio=0.3, lock=False)
                    fd = APPEND_FD_CACHE[filename] = open(filename, 'a')
            APPEND_FD_CACHE_ORDER.append(filename)
            return fd
        else:
            if filename in APPEND_FD_CACHE:
                fd = APPEND_FD_CACHE[filename]
                try:
                    if 'w' in mode or '+' in mode:
                        del APPEND_FD_CACHE[filename]
                        APPEND_FD_CACHE_ORDER.remove(filename)
                        fd.close()
                    else:
                        fd.flush()
                except (ValueError, IOError):
                    pass
            return open(filename, mode)
    finally:
        APPEND_FD_CACHE_LOCK.release()


def play_nice_with_threads():
    """
    Long-running batch jobs should call this now and then to pause
    their activities if there are other threads that would like to
    run. This is a bit of a hack!
    """
    delay = max(0, 0.01 * (threading.activeCount() - 2))
    if delay:
        time.sleep(delay)
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
    image.thumbnail([x, y], Image.ANTIALIAS)
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


# If 'python util.py' is executed, start the doctest unittest
if __name__ == "__main__":
    import doctest
    import sys
    if doctest.testmod().failed:
        sys.exit(1)
