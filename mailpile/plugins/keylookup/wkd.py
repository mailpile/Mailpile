import hashlib
import ssl
import urllib
import urllib2

from mailpile.commands import Command
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.crypto.keyinfo import get_keyinfo, MailpileKeyInfo
from mailpile.i18n import gettext
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import LookupHandler
from mailpile.plugins.keylookup import register_crypto_key_lookup_handler

_ = lambda t: t


WKD_URL_FORMATS = (
        'https://openpgpkey.%(d)s/.well-known/%(d)s/openpgpkey/hu/%(l)s?%(q)s',
        'https://%(d)s/.well-known/openpgpkey/hu/%(l)s?%(q)s')

ALPHABET = "ybndrfg8ejkmcpqxot1uwisza345h769"
SHIFT = 5
MASK = 31


#  Encodes data using ZBase32 encoding
#  See: https://tools.ietf.org/html/rfc6189#section-5.1.6
#
def _zbase_encode(data):
    if len(data) == 0:
        return ""
    buffer = ord(data[0])
    index = 1
    bitsLeft = 8
    result = ""
    while bitsLeft > 0 or index < len(data):
        if bitsLeft < SHIFT:
            if index < len(data):
                buffer = buffer << 8
                buffer = buffer | (ord(data[index]) & 0xFF)
                bitsLeft = bitsLeft + 8
                index = index + 1
            else:
                pad = SHIFT - bitsLeft
                buffer = buffer << pad
                bitsLeft = bitsLeft + pad
        bitsLeft = bitsLeft - SHIFT
        result = result + ALPHABET[MASK & (buffer >> bitsLeft)]
    return result


def WebKeyDirectoryURLs(address, plusmagic=True):
    local, _, domain = address.partition("@")
    encoded_parts = [(local, _zbase_encode(
        hashlib.sha1(local.lower().encode('utf-8')).digest()))]
    if plusmagic and '+' in local:
        local = local.split('+')[0]
        encoded_parts.append((local, _zbase_encode(
            hashlib.sha1(local.lower().encode('utf-8')).digest())))
    for lp, lpe in encoded_parts:
        for urlfmt in WKD_URL_FORMATS:
            yield urlfmt % {
                'd': domain,
                'l': lpe,
                'q': urllib.urlencode({'l': lp})}


#  Support for Web Key Directory (WKD) lookup for keys.
#  See: https://wiki.gnupg.org/WKD and https://datatracker.ietf.org/doc/draft-koch-openpgp-webkey-service/
#
class WKDLookupHandler(LookupHandler):
    NAME = _("Web Key Directory")
    SHORTNAME = 'wkd'
    TIMEOUT = 10
    PRIORITY = 50  # WKD is better than keyservers and better than DNS
    PRIVACY_FRIENDLY = True  # These lookups can go over Tor
    SCORE = 5

    def __init__(self, *args, **kwargs):
        LookupHandler.__init__(self, *args, **kwargs)
        self.key_cache = { }

    def _score(self, key):
        return (self.SCORE, _('Found key in Web Key Directory'))

    def _lookup(self, address, strict_email_match=True):
        local, _, domain = address.partition("@")
        local_part_encoded = _zbase_encode(
            hashlib.sha1(local.lower().encode('utf-8')).digest())

        error = None
        for url in WebKeyDirectoryURLs(address):
            try:
                if 'keylookup' in self.session.config.sys.debug:
                    self.session.ui.debug('[%s] Fetching %s' % (self.NAME, url))
                with ConnBroker.context(need=[ConnBroker.OUTGOING_HTTPS]):
                    result = urllib2.urlopen(url).read()
                error = None
                break
            except urllib2.HTTPError as e:
                if e.code == 404 and '+' not in address:
                    error = '404: %s' % e
                    # Since we are testing openpgpkey.* first, if we actually get a
                    # valid response back we should treat that as authoritative and
                    # not waste cycles checking the bare domain too.
                    break
                else:
                    error = str(e)
            except ssl.CertificateError as e:
                error = 'TLS: %s' % e
            except urllib2.URLError as e:
                error = 'FAIL: %s' % e

        if error and 'keylookup' in self.session.config.sys.debug:
            self.session.ui.debug('[%s] Error: %s' % (self.NAME, error))
        if not error:
            keyinfo = get_keyinfo(result, key_info_class=MailpileKeyInfo)[0]
            self.key_cache[keyinfo["fingerprint"]] = result
        elif error[:3] in ('TLS', 'FAI', '404'):
            return {}  # Suppress these errors, they are common.
        else:
            raise ValueError(error)

        return {keyinfo["fingerprint"]: keyinfo}

    def _getkey(self, email, keyinfo):
        # FIXME: Consider cleaning up the key before we import it, to
        #        get rid of signatures and UIDs we don't care about.
        data = self.key_cache.pop(keyinfo["fingerprint"])
        if data:
            return self._gnupg().import_keys(data)
        else:
            raise ValueError("Key not found")


class GetWebKeyDirectoryURLs(Command):
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/wkd/urls', None, '<emails>')

    def command(self):
        return self._success(_("Generated WKD URLs"),
            dict((addr, list(WebKeyDirectoryURLs(addr))) for addr in self.args))


_ = gettext

_plugins = PluginManager(builtin=__file__)
_plugins.register_commands(GetWebKeyDirectoryURLs)

register_crypto_key_lookup_handler(WKDLookupHandler)

