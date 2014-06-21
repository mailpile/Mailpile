import DNS
import urllib2

from mailpile.crypto.gpgi import GnuPG
from mailpile.plugins.keylookup import LookupHandler, register_crypto_key_lookup_handler

#
#  Support for DNS PKA (_pka) entries.
#  See http://www.gushi.org/make-dns-cert/HOWTO.html
#

class DNSPKALookupHandler(LookupHandler):
    NAME = "DNS PKA records"

    def __init__(self):
        DNS.ParseResolvConf()
        self.req = DNS.Request(qtype="TXT")

    def _score(self, key):
        return 9

    def _lookup(self, address):
        """
        >>> from mailpile.crypto.dnspka import *
        >>> d = DNSPKALookup()
        >>> res = d.lookup("smari@immi.is")
        >>> res["result"]["count"] == 1
        """
        dom = address.replace("@", "._pka.")
        result = self.req.req(dom)
        for res in result.answers:
            if res["typename"] != "TXT":
                continue
            for entry in res["data"]:
                return self._keyinfo(entry)

        return {}

    def _keyinfo(self, entry):
        pkaver = None
        fingerprint = None
        url = None

        for stmt in entry.split(";"):
            key, value = stmt.split("=", 1)
            if key == "v":
                pkaver = value
            elif key == "fpr":
                fingerprint = value
            elif key == "uri":
                url = value

        if pkaver != "pka1":
            raise ValueError("We only know how to deal with pka version 1")

        return {fingerprint: {"fingerprint": fingerprint, "url": url, "pkaver": pkaver}}

    def _getkey(self, key):
        if key["fingerprint"] and not key["url"]:
            g = GnuPG()
            res = g.recv_key(key["fingerprint"])
        elif key["url"]:
            r = urllib2.urlopen(key["url"])
            result = r.readlines()
            start = 0
            end = len(result)
            # Hack to deal with possible HTML results from keyservers:
            for i in range(len(result)):
                if result[i].startswith("-----BEGIN PGP"):
                    start = i
                elif result[i].startswith("-----END PGP"):
                    end = i
            result = "".join(result[start:end])
            g = GnuPG()
            res = g.import_keys(result)
            return res
        else:
            raise ValueError("Need a fingerprint or a URL")


register_crypto_key_lookup_handler(DNSPKALookupHandler)
