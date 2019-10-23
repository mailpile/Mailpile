import hashlib
import ssl
import urllib
import urllib2

from mailpile.security import secure_urlget
from mailpile.commands import Command
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.crypto.keyinfo import get_keyinfo, MailpileKeyInfo
from mailpile.i18n import gettext
from mailpile.plugins import PluginManager
from mailpile.plugins.keylookup import LookupHandler
from mailpile.plugins.keylookup import register_crypto_key_lookup_handler

_ = lambda t: t


WKD_URL_FORMATS = (
        'https://openpgpkey.%(d)s/.well-known/openpgpkey/%(d)s/hu/%(l)s?%(q)s',
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
                'd': domain,  # FIXME: Should this be punycoded?
                'l': lpe,
                'q': urllib.urlencode({'l': lp})}


#  Support for Web Key Directory (WKD) lookup for keys.
#  See: https://wiki.gnupg.org/WKD and https://datatracker.ietf.org/doc/draft-koch-openpgp-webkey-service/
#
class WKDLookupHandler(LookupHandler):
    NAME = _("Web Key Directory")
    SHORTNAME = 'wkd'
    TIMEOUT = 12
    PRIORITY = 50  # WKD is better than keyservers and better than DNS
    PRIVACY_FRIENDLY = True  # These lookups can go over Tor
    SCORE = 5

    # People with really big keys are just going to have to publish in WKD
    # or something, unless or until the SKS keyservers get fixed somehow.
    MAX_KEY_SIZE = 1500000

    # Avoid lookups to certain domains. The rationale here is these are large
    # providers which are unlikely to implement WKD any time soon, so we would
    # rather not leak details of our activities to them. This list is a subset
    # of the list found here:
    #  - https://github.com/mailcheck/mailcheck/wiki/List-of-Popular-Domains
    DOMAIN_BLACKLIST = [
        "aol.com", "att.net", "comcast.net", "facebook.com", "gmail.com",
        "gmx.com", "googlemail.com", "google.com", "hotmail.com", "hotmail.co.uk",
        "mac.com", "me.com", "mail.com", "msn.com", "live.com", "sbcglobal.net",
        "verizon.net", "yahoo.com", "yahoo.co.uk", "email.com",
        "games.com", "gmx.net", "icloud.com", "iname.com", "inbox.com", "love.com",
        "outlook.com", "pobox.com", "rocketmail.com", "wow.com", "ygm.com",
        "ymail.com", "zoho.com", "zohomail.eu", "yandex.com", "bellsouth.net",
        "charter.net", "cox.net", "earthlink.net", "juno.com", "btinternet.com",
        "virginmedia.com", "blueyonder.co.uk", "freeserve.co.uk", "live.co.uk",
        "ntlworld.com", "o2.co.uk", "orange.net", "sky.com", "talktalk.co.uk",
        "tiscali.co.uk", "virgin.net", "wanadoo.co.uk", "bt.com", "sina.com",
        "sina.cn", "qq.com", "naver.com", "hanmail.net", "daum.net", "nate.com",
        "yahoo.co.jp", "yahoo.co.kr", "yahoo.co.id", "yahoo.co.in", "yahoo.com.sg",
        "yahoo.com.ph", "163.com", "yeah.net", "126.com", "21cn.com", "aliyun.com",
        "foxmail.com", "hotmail.fr", "live.fr", "laposte.net", "yahoo.fr",
        "wanadoo.fr", "orange.fr", "gmx.fr", "sfr.fr", "neuf.fr", "free.fr", "gmx.de",
        "hotmail.de", "live.de", "online.de", "t-online.de", "web.de", "yahoo.de",
        "libero.it", "virgilio.it", "hotmail.it", "aol.it", "tiscali.it", "alice.it",
        "live.it", "yahoo.it", "email.it", "tin.it", "poste.it", "teletu.it",
        "mail.ru", "rambler.ru", "yandex.ru", "ya.ru", "list.ru", "hotmail.be",
        "live.be", "skynet.be", "voo.be", "tvcablenet.be", "telenet.be",
        "hotmail.com.ar", "live.com.ar", "yahoo.com.ar", "fibertel.com.ar",
        "speedy.com.ar", "arnet.com.ar", "yahoo.com.mx", "live.com.mx", "hotmail.es",
        "hotmail.com.mx", "prodigy.net.mx", "yahoo.ca", "hotmail.ca", "bell.net",
        "shaw.ca", "sympatico.ca", "rogers.com", "yahoo.com.br", "hotmail.com.br",
        "outlook.com.br", "uol.com.br", "bol.com.br", "terra.com.br", "ig.com.br",
        "itelefonica.com.br", "r7.com", "zipmail.com.br", "globo.com", "globomail.com",
        "oi.com.br"]

    def __init__(self, *args, **kwargs):
        LookupHandler.__init__(self, *args, **kwargs)
        self.key_cache = { }

    def _score(self, key):
        return (self.SCORE, _('Found key in Web Key Directory'))

    def _lookup(self, address, strict_email_match=True):
        local, _, domain = address.partition("@")
        if domain.lower() in self.DOMAIN_BLACKLIST:
            # FIXME: Maybe make this dynamic; check for the WKD policy file and
            #        if it is present remove the provider from the blacklist.
            self.session.ui.debug(
                '[%s] Blacklisted domain, skipping: %s' % (self.NAME, domain))
            return {}

        # FIXMEs:
        #   - Check the spec and make sure we are doing the right thing when
        #     comes to redirects. Probably switch off. But Linus! They seem
        #     broken now, wah, wah, wah.
        #   - Check the policy file, if it doesn't exist don't leak the
        #     e-mail address to the server? Cache this? Counter-argument,
        #     shame if user has no policy file but has a published key.
        #   - Check content-type, because some sites return weird crap.

        local_part_encoded = _zbase_encode(
            hashlib.sha1(local.lower().encode('utf-8')).digest())
        error = None
        keyinfo = None
        for url in WebKeyDirectoryURLs(address):
            try:
                if 'keylookup' in self.session.config.sys.debug:
                    self.session.ui.debug('[%s] Fetching %s' % (self.NAME, url))
                key_data = secure_urlget(self.session, url,
                                         maxbytes=self.MAX_KEY_SIZE+1,
                                         timeout=int(self.TIMEOUT / 3))
                if key_data:
                    keyinfo = get_keyinfo(key_data,
                        key_source=(self.SHORTNAME, url),
                        key_info_class=MailpileKeyInfo
                        )[0]
                    error = None
                    break
                else:
                    error = 'Key not found'
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
            except (urllib2.URLError, ValueError, KeyError) as e:
                error = 'FAIL: %s' % e

        if not error and len(key_data) > self.MAX_KEY_SIZE:
            error = "Key too big (>%d bytes), ignoring" % self.MAX_KEY_SIZE
            if 'keylookup' in self.session.config.sys.debug:
                self.session.ui.debug(error)

        if error and 'keylookup' in self.session.config.sys.debug:
            self.session.ui.debug('[%s] Error: %s' % (self.NAME, error))
        if not error:
            self.key_cache[keyinfo["fingerprint"]] = key_data
        elif error[:3] in ('TLS', 'FAI', '404'):
            return {}  # Suppress these errors, they are common.
        else:
            raise ValueError(error)

        # FIXME: Key refreshes will need to know where this key came
        #        from, we should record this somewhere. Should WKD
        #        keys be considered ephemeral? What about revocations?
        #        What about signatures? What if we get back multiple
        #        keys/certs? What if we get back a revocation?

        return {keyinfo["fingerprint"]: keyinfo}

    def _getkey(self, email, keyinfo):
        # FIXME: Consider cleaning up the key before we import it, to
        #        get rid of signatures and UIDs we don't care about.
        data = self.key_cache.pop(keyinfo["fingerprint"])
        if data:
            return self._gnupg().import_keys(data, filter_uid_emails=[email])
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

