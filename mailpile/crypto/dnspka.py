import DNS
import urllib2

from mailpile.crypto.gpgi import GnuPG

#
#  Support for DNS PKA (_pka) entries.
#  See http://www.gushi.org/make-dns-cert/HOWTO.html
#

class DNSPKALookup:
	def __init__(self):
		DNS.ParseResolvConf()
		self.req = DNS.Request(qtype="TXT")

	def lookup(self, address):
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
				return self._getkey(entry)

	def _getkey(self, entry):
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

		if fingerprint and not url:
			g = GnuPG()
			res = g.recv_key(fingerprint)
		elif url:
			r = urllib2.urlopen(url)
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

