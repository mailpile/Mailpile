#coding:utf-8
import base64
import httplib
import sys
import re
import getopt
from lxml import etree

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.vcard import *
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)


class DAVClient:
    def __init__(self, host,
                 port=None, username=None, password=None, protocol='https'):
        if not port:
            if protocol == 'https':
                port = 443
            elif protocol == 'http':
                port = 80
            else:
                raise Exception("Can't determine port from protocol. "
                                "Please specifiy a port.")
        self.cwd = "/"
        self.baseurl = "%s://%s:%d" % (protocol, host, port)
        self.host = host
        self.port = port
        self.protocol = protocol
        self.username = username
        self.password = password
        if username and password:
            self.auth = base64.encodestring('%s:%s' % (username, password)
                                            ).replace('\n', '')
        else:
            self.auth = None

    def request(self, url, method, headers={}, body=""):
        if self.protocol == "https":
            req = httplib.HTTPSConnection(self.host, self.port)
            # FIXME: Verify HTTPS certificate
        else:
            req = httplib.HTTPConnection(self.host, self.port)

        req.putrequest(method, url)
        req.putheader("Host", self.host)
        req.putheader("User-Agent", "Mailpile")
        if self.auth:
            req.putheader("Authorization", "Basic %s" % self.auth)

        for key, value in headers.iteritems():
            req.putheader(key, value)

        req.endheaders()
        req.send(body)
        res = req.getresponse()

        self.last_status = res.status
        self.last_statusmessage = res.reason
        self.last_headers = dict(res.getheaders())
        self.last_body = res.read()

        if self.last_status >= 300:
            raise Exception(("HTTP %d: %s\n(%s %s)\n>>>%s<<<"
                             ) % (self.last_status, self.last_statusmessage,
                                  method, url, self.last_body))
        return (self.last_status, self.last_statusmessage,
                self.last_headers, self.last_body)

    def options(self, url):
        status, msg, header, resbody = self.request(url, "OPTIONS")
        return header["allow"].split(", ")


class CardDAV(DAVClient):
    def __init__(self, host, url,
                 port=None, username=None, password=None, protocol='https'):
        DAVClient.__init__(self, host, port, username, password, protocol)
        self.url = url

        if not self._check_capability():
            raise Exception("No CardDAV support on server")

    def cd(self, url):
        self.url = url

    def _check_capability(self):
        result = self.options(self.url)
        return "addressbook" in self.last_headers["dav"].split(", ")

    def get_vcard(self, url):
        status, msg, header, resbody = self.request(url, "GET")
        card = MailpileVCard()
        card.load(data=resbody)
        return card

    def put_vcard(self, url, vcard):
        raise Exception('Unimplemented')

    def list_vcards(self):
        stat, msg, hdr, resbody = self.request(self.url, "PROPFIND", {}, {})
        tr = etree.fromstring(resbody)
        urls = [x.text for x in tr.xpath("/d:multistatus/d:response/d:href",
                                         namespaces={"d": "DAV:"})
                if x.text not in ("", None) and x.text[-3:] == "vcf"]
        return urls


class CardDAVImporter(VCardImporter):
    REQUIRED_PARAMETERS = ["host", "url"]
    OPTIONAL_PARAMETERS = ["port", "username", "password", "protocol"]
    FORMAT_NAME = "CardDAV Server"
    FORMAT_DESCRIPTION = "CardDAV HTTP contact server."
    SHORT_NAME = "carddav"
    CONFIG_RULES = {
        'host': ('Host name', 'hostname', None),
        'port': ('Port number', int, None),
        'url': ('CardDAV URL', 'url', None),
        'protcol': ('Connection protocol', 'string', 'https'),
        'password': ('CardDAV URL', 'url', None),
        'username': ('CardDAV URL', 'url', None)
    }

    def get_contacts(self):
        self.carddav = CardDAV(host, url, port, username, password, protocol)
        results = []
        cards = self.carddav.list_vcards()
        for card in cards:
            results.append(self.carddav.get_vcard(card))

        return results

    def filter_contacts(self, terms):
        pass


_plugins.register_vcard_importers(CardDAVImporter)
