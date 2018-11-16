import hashlib
import ssl
import urllib
import urllib2

from mailpile.conn_brokers import Master as ConnBroker
from mailpile.crypto.keydata import get_keydata
from mailpile.i18n import gettext
from mailpile.plugins.keylookup import LookupHandler
from mailpile.plugins.keylookup import register_crypto_key_lookup_handler

ALPHABET = "ybndrfg8ejkmcpqxot1uwisza345h769"
SHIFT = 5
MASK = 31

#
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

_ = lambda t: t

#
#  Support for Web Key Directory (WKD) lookup for keys.
#  See: https://wiki.gnupg.org/WKD and https://datatracker.ietf.org/doc/draft-koch-openpgp-webkey-service/
#
class WKDLookupHandler(LookupHandler):
    NAME = _("Web Key Directory")
    TIMEOUT = 10
    PRIORITY = 50  # WKD is better than keyservers and better than DNS
    PRIVACY_FRIENDLY = True  # These lookups can go over Tor
    SCORE = 5

    URL_FORMATS = (
        'https://openpgpkey.%(d)s/.well-known/%(d)s/openpgpkey/hu/%(l)s?%(q)s',
        'https://%(d)s/.well-known/openpgpkey/hu/%(l)s?%(q)s')

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
        for urlfmt in self.URL_FORMATS:
            url = urlfmt % {
                'd': domain,
                'l': local_part_encoded,
                'q': urllib.urlencode({'l': local})}

            try:
                with ConnBroker.context(need=[ConnBroker.OUTGOING_HTTPS]):
                    r = urllib2.urlopen(url)
                error = None
                break
            except (urllib2.URLError, ssl.CertificateError):
                error = 'TLS'  # Wrong TLS keys are common. :-(
            except urllib2.HTTPError as e:
                if e.code == 404:
                    error = '404'
                    # Since we are testing openpgpkey.* first, if we actually get a
                    # valid response back we should treat that as authoritative and
                    # not waste cycles checking the bare domain too.
                    break
                else:
                    error = str(e)

        if not error:
            result = r.read()
            keydata = get_keydata(result)[0]
            self.key_cache[keydata["fingerprint"]] = result
        elif error in ('TLS', '404'):
            return {}  # Suppress these errors, they are common.
        else:
            raise ValueError(error)

        return {keydata["fingerprint"]: keydata}

    def _getkey(self, keydata):
        data = self.key_cache.pop(keydata["fingerprint"])
        if data:
            return self._gnupg().import_keys(data)
        else:
            raise ValueError("Key not found")


_ = gettext
register_crypto_key_lookup_handler(WKDLookupHandler)
