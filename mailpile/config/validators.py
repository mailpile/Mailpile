import os
import socket
import re

try:
    import win_inet_pton
except ImportError:
    pass

from urlparse import urlparse

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as n
from mailpile.util import *


def BoolCheck(value):
    """
    Convert common yes/no strings into boolean values.

    >>> BoolCheck('yes')
    True
    >>> BoolCheck('no')
    False

    >>> BoolCheck('true')
    True
    >>> BoolCheck('false')
    False

    >>> BoolCheck('on')
    True
    >>> BoolCheck('off')
    False

    >>> BoolCheck('wiggle')
    Traceback (most recent call last):
        ...
    ValueError: Invalid boolean: wiggle
    """
    bool_val = truthy(value, default=None)
    if bool_val is None:
        raise ValueError(_('Invalid boolean: %s') % value)
    return bool_val


def SlugCheck(slug, allow=''):
    """
    Verify that a string is a valid URL slug.

    >>> SlugCheck('_Foo-bar.5')
    '_foo-bar.5'

    >>> SlugCheck('Bad Slug')
    Traceback (most recent call last):
        ...
    ValueError: Invalid URL slug: Bad Slug

    >>> SlugCheck('Bad/Slug')
    Traceback (most recent call last):
        ...
    ValueError: Invalid URL slug: Bad/Slug
    """
    if not slug == CleanText(unicode(slug),
                             banned=(CleanText.NONDNS.replace(allow, ''))
                             ).clean:
        raise ValueError(_('Invalid URL slug: %s') % slug)
    return slug.lower()


def SlashSlugCheck(slug):
    """
    Verify that a string is a valid URL slug (slashes allowed).

    >>> SlashSlugCheck('Okay/Slug')
    'okay/slug'
    """
    return SlugCheck(slug, allow='/')


def RouteProtocolCheck(proto):
    """
    Verify that the protocol is actually a protocol.
    (FIXME: Should reference a list of registered protocols...)

    >>> RouteProtocolCheck('SMTP')
    'smtp'
    """
    proto = str(proto).strip().lower()
    if proto not in ("smtp", "smtptls", "smtpssl", "local"):
        raise ValueError(_('Invalid message delivery protocol: %s') % proto)
    return proto

def DnsNameValid(dnsname):
    """
    Tests whether a string is a valid dns name, returns a boolean value
    """
    if not dnsname or not DNSNAME_RE.match(dnsname):
        return False
    else:
        return True

def HostNameValid(host):
    """
    Tests whether a string is a valid host-name, return a boolean value

    >>> HostNameValid("127.0.0.1")
    True

    >>> HostNameValid("::1")
    True

    >>> HostNameValid("localhost")
    True

    >>> HostNameValid("22.45")
    False
    """
    valid = False
    for attr in ["AF_INET","AF_INET6"]:
        try:
            socket.inet_pton(socket.__getattribute__(attr), host)
            valid = True
            break
        except (socket.error):
            pass
    if not valid:
        # the host is not an IP so check if its a hostname i.e. 'localhost' or 'site.com'
        if not host or (not DnsNameValid(host) and not ALPHA_RE.match(host)):
            return False
        else:
            return True
    else:
        return True

def HostNameCheck(host):
    """
    Verify that a string is a valid host-name, return it lowercased.

    >>> HostNameCheck('foo.BAR.baz')
    'foo.bar.baz'

    >>> HostNameCheck('127.0.0.1')
    '127.0.0.1'

    >>> HostNameCheck('not/a/hostname')
    Traceback (most recent call last):
        ...
    ValueError: Invalid hostname: not/a/hostname
    """
    # Check DNS, IPv4, and finally IPv6
    if not HostNameValid(host):
        raise ValueError(_('Invalid hostname: %s') % host)
    return str(host).lower()


def B36Check(b36val):
    """
    Verify that a string is a valid path base-36 integer.

    >>> B36Check('Aa')
    'aa'

    >>> B36Check('.')
    Traceback (most recent call last):
        ...
    ValueError: invalid ...
    """
    int(b36val, 36)
    return str(b36val).lower()


def NotUnicode(string):
    """
    Make sure a string is NOT unicode.
    """
    if isinstance(string, unicode):
        string = string.encode('utf-8')
    if not isinstance(string, str):
        return str(string)
    return string


def PathCheck(path):
    """
    Verify that a string is a valid path, make it absolute.

    >>> PathCheck('/etc/../')
    '/'

    >>> PathCheck('/no/such/path')
    Traceback (most recent call last):
        ...
    ValueError: File/directory does not exist: /no/such/path
    """
    if isinstance(path, unicode):
        path = path.encode('utf-8')
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise ValueError(_('File/directory does not exist: %s') % path)
    return os.path.abspath(path)


def WebRootCheck(path):
    """
    Verify that a string is a valid web root path, normalize the slashes.

    >>> WebRootCheck('/')
    ''

    >>> WebRootCheck('/foo//bar////baz//')
    '/foo/bar/baz'

    >>> WebRootCheck('/foo/$%!')
    Traceback (most recent call last):
        ...
    ValueError: Invalid web root: /foo/$%!
    """
    p = re.sub('/+', '/', '/%s/' % path)[:-1]
    if (p != CleanText(p, banned=CleanText.NONPATH).clean):
        raise ValueError('Invalid web root: %s' % path)
    return p


def FileCheck(path=None):
    """
    Verify that a string is a valid path to a file, make it absolute.

    >>> FileCheck('/etc/../etc/passwd')
    '/etc/passwd'

    >>> FileCheck('/')
    Traceback (most recent call last):
        ...
    ValueError: Not a file: /
    """
    if path in (None, 'None', 'none', ''):
        return None
    path = PathCheck(path)
    if not os.path.isfile(path):
        raise ValueError(_('Not a file: %s') % path)
    return path


def DirCheck(path=None):
    """
    Verify that a string is a valid path to a directory, make it absolute.

    >>> DirCheck('/etc/../')
    '/'

    >>> DirCheck('/etc/passwd')
    Traceback (most recent call last):
        ...
    ValueError: Not a directory: /etc/passwd
    """
    if path in (None, 'None', 'none', ''):
        return None
    path = PathCheck(path)
    if not os.path.isdir(path):
        raise ValueError(_('Not a directory: %s') % path)
    return path


def NewPathCheck(path):
    """
    Verify that a string is a valid path to a directory, make it absolute.

    >>> NewPathCheck('/magic')
    '/magic'

    >>> NewPathCheck('/no/such/path/magic')
    Traceback (most recent call last):
        ...
    ValueError: File/directory does not exist: /no/such/path
    """
    PathCheck(os.path.dirname(path))
    return os.path.abspath(path)

def UrlCheck(url):
    """
    Verify that a url parsed string has a valid uri scheme

    >>> UrlCheck("http://mysite.com")
    'http://mysite.com'

    >>> UrlCheck("/not-valid.net")
    Traceback (most recent call last):
        ...
    ValueError: Not a valid url: ...

    >>> UrlCheck("tallnet://some-host.com")
    Traceback (most recent call last):
        ...
    ValueError: Not a valid url: tallnet://some-host.com
    """
    uri = urlparse(url)
    if not uri.scheme in URI_SCHEMES:
        raise ValueError(_("Not a valid url: %s") % url)
    else:
        return url

def EmailCheck(email):
    """
    Verify that a string is a valid email

    >>> EmailCheck("test@test.com")
    'test@test.com'
    """
    if not EMAIL_RE.match(email):
        raise ValueError(_("Not a valid e-mail: %s") % email)
    return email


def GPGKeyCheck(value):
    """
    Strip a GPG fingerprint of all spaces, make sure it seems valid.
    Will also accept e-mail addresses, for legacy reasons.

    >>> GPGKeyCheck('User@Foo.com')
    'User@Foo.com'

    >>> GPGKeyCheck('1234 5678 abcd EF00')
    '12345678ABCDEF00'

    >>> GPGKeyCheck('12345678')
    '12345678'

    >>> GPGKeyCheck('B906 EA4B 8A28 15C4 F859  6F9F 47C1 3F3F ED73 5179')
    'B906EA4B8A2815C4F8596F9F47C13F3FED735179'

    >>> GPGKeyCheck('B906 8A28 15C4 F859  6F9F 47C1 3F3F ED73 5179')
    Traceback (most recent call last):
        ...
    ValueError: Not a GPG key ID or fingerprint

    >>> GPGKeyCheck('B906 8X28 1111 15C4 F859  6F9F 47C1 3F3F ED73 5179')
    Traceback (most recent call last):
        ...
    ValueError: Not a GPG key ID or fingerprint
    """
    value = value.replace(' ', '').replace('\t', '').strip()
    if value in ('!CREATE', '!PASSWORD'):
        return value
    try:
        if len(value) not in (8, 16, 40):
            raise ValueError(_('Not a GPG key ID or fingerprint'))
        if re.match(r'^[0-9A-F]+$', value.upper()) is None:
            raise ValueError(_('Not a GPG key ID or fingerprint'))
    except ValueError:
        try:
            return EmailCheck(value)
        except ValueError:
            raise ValueError(_('Not a GPG key ID or fingerprint'))
    return value.upper()


class IgnoreValue(Exception):
    pass


def IgnoreCheck(data):
    raise IgnoreValue()


if __name__ == "__main__":
    import doctest
    import sys
    result = doctest.testmod(optionflags=doctest.ELLIPSIS)
    print '%s' % (result, )
    if result.failed:
        sys.exit(1)
