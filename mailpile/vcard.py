# This is a very simplistic Contact class based on VCard 4.0

import random
from mailpile.util import *
import httplib
import base64
from lxml import etree


class SimpleVCard(dict):
  VCARD_OTHER_KEYS = {
    'AGENT': '',
    'CLASS': '',
    'EXPERTISE': '',
    'HOBBY': '',
    'INTEREST': '',
    'LABEL': '',
    'MAILER': '',
    'NAME': '',
    'ORG-DIRECTORY': '',
    'PROFILE': '',
    'SORT-STRING': '',
  }
  VCARD4_KEYS = {
    'ADR': '', 'ANNIVERSARY': '',
    'BDAY': '',
    'CALADRURI': '', 'CALURI': '', 'CATEGORIES': '', 'CLIENTPIDMAP': '',
    'EMAIL': '',
    'FBURL': '',
    'FN': '',
    'GENDER': '', 'GEO': '',
    'IMPP': '',
    'KEY': '', 'KIND': '',
    'LANG': '', 'LOGO': '',
    'MEMBER': '',
    'N': '', 'NICKNAME': '', 'NOTE': '',
    'ORG': '',
    'PHOTO': '', 'PRODID': '',
    'RELATED': '', 'REV': '', 'ROLE': '',
    'SOUND': '', 'SOURCE': '',
    'TEL': '', 'TITLE': '', 'TZ': '',
    'UID': '', 'URL': '',
    'XML': '',
  }

  def __init__(self):
    dict.__init__(self)
    self.filename = None
    self.gpg_recipient = lambda self: None
    self.version = '4.0'
    self.order = []

  def __getitem__(self, key):
    return dict.__getitem__(self, key.upper())

  def __setitem__(self, key, val):
    key = key.upper()
    if not (key.startswith('X-')
        or  key in self.VCARD4_KEYS
        or  key in self.VCARD_OTHER_KEYS):
      raise ValueError('Not a valid vCard key: %s' % key)
    if key not in self.order:
      self.order.append(key)
    if type(val) in (type(list()), type(set())):
      while key in self.order:
        self.order.remove(key)
      self.order.extend([key for v in val])
      dict.__setitem__(self, key, val)
    else:
      if key in self:
        dict.__getitem__(self, key)[0][0] = val
      else:
        dict.__setitem__(self, key, [[val, []]])

  def __str__(self):
    if self.kind == 'individual':
      return 'Contact: %s <%s>' % (self.fn, self.email)
    elif self.kind == 'group':
      return 'Group: %s (%s = %s)' % (self.fn, self.nickname,
                                ','.join([e[0] for e in self.get('EMAIL', [])]))
    else:
      return '%s: %s (%s)' % (self.kind, self.fn, self.nickname)

  fn = property(lambda self: self.get('FN', [[None]])[0][0],
                lambda self, v: self.__setitem__('FN', v))
  kind = property(lambda self: self.get('KIND', [[None]])[0][0] or 'individual',
                  lambda self, v: self.__setitem__('KIND', v))
  members = property(lambda self: [(m[0].startswith('mailto:') and m[0][7:]
                                                                or m[0]).lower()
                                   for m in self.get('MEMBER', [])])
  nickname = property(lambda self: self.get('NICKNAME', [[None]])[0][0],
                      lambda self, v: self.__setitem__('KIND', v))

  def _getset_email(self, newemail=None):
    first = None
    for pair in self.get('EMAIL', []):
      first = first or pair
      for a in pair[1]:
        if 'PREF' in a.upper():
          first = pair
    if newemail is not None:
      if first:
        first[0] = newemail
      else:
        self['EMAIL'] = newemail
        return self['EMAIL']
    return first or [None, []]

  email = property(lambda self: self._getset_email()[0],
                   lambda self, v: self._getset_email(v)[0])

  def _random_uid(self):
    if 'X-MAILPILE-RID' not in self:
      crap = '%s %s' % (self.email, random.randint(0, 0x1fffffff))
      self['X-MAILPILE-RID'] = b64w(sha1b64(crap)).lower()
    return self['X-MAILPILE-RID'][0][0]
  random_uid = property(_random_uid)

  def as_jCard(self):
    # FIXME: Needs type info and attributes.
    card = [[key.lower(), {}, "text", self[key][0][0]] for key in self.order]
    stream = ["vcardstream", ["vcard", card]]
    return stream

  def as_mpCard(self):
    return dict([(key, self[key][0][0]) for key in self.order])

  def as_xCard(self):
    # FIXME: Render as an xCard
    raise Exception('Unimplemented')

  def as_vCard(self):
    def _rotated_vcf(key):
      data = self[key].pop(0)
      self[key].append(data)
      return '%s:%s' % (';'.join([key] + data[1]), data[0])
    return '\r\n'.join([
      'BEGIN:VCARD',
      'VERSION:%s' % self.version,
    ] + [
      # The _rotated_vcf lets us rotate through the values in order
      # and we should end up with everything back in its original state.
      (_rotated_vcf(k)) for k in self.order
    ] + [
      'END:VCARD',
      ''
    ])

  def load(self, filename=None, data=None):
    if data:
      lines = [l.strip() for l in data.strip().splitlines()]
    else:
      self.filename = filename or self.filename
      lines = []
      decrypt_and_parse_lines(open(self.filename, 'rb'),
                              lambda l: lines.append(l.strip()))
      while lines and not lines[-1]:
        lines.pop(-1)

    if (not lines.pop(0).upper() == 'BEGIN:VCARD'
    or  not lines.pop(-1).upper() == 'END:VCARD'):
      print '%s' % lines
      raise ValueError('Not a valid VCard')

    for line in lines:
      attrs, data = line.split(':', 1)
      attrs = attrs.split(';')
      key = attrs.pop(0)
      if key == 'VERSION':
        self.version = data
      elif key not in ('BEGIN:VCARD', 'VERSION', 'END:VCARD'):
        if not key in self:
          self[key] = []
        self.order.append(key)
        self[key].append([data, attrs])

    return self

  def save(self, filename=None, gpg_recipient=None):
    filename = filename or self.filename
    if filename:
      fd = gpg_open(filename, gpg_recipient or self.gpg_recipient(), 'wb')
      fd.write(self.as_vCard().encode('utf-8'))
      fd.close()
      return self
    else:
      raise ValueError('Save to what file?')



class DAVClient:
  def __init__(self, host, port=None, username=None, password=None, protocol='https'):
    if not port:
      if protocol == 'https':    port = 443
      elif protocol == 'http':   port = 80
      else: raise Exception("Can't determine port from protocol. Please specifiy a port.")
    self.cwd = "/"
    self.baseurl = "%s://%s:%d" % (protocol, host, port)
    self.host = host
    self.port = port
    self.protocol = protocol
    self.username = username
    self.password = password
    if username and password:
      self.auth = base64.encodestring('%s:%s' % (username, password)).replace('\n', '')
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
      raise Exception("HTTP %d: %s\n(%s %s)\n>>>%s<<<" % (self.last_status, self.last_statusmessage, method, url, self.last_body))
    return self.last_status, self.last_statusmessage, self.last_headers, self.last_body

  def options(self, url):
    status, msg, header, resbody = self.request(url, "OPTIONS")
    return header["allow"].split(", ")



class CardDAV(DAVClient):
  def __init__(self, host, url, port=None, username=None, password=None, protocol='https'):
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
    card = SimpleVCard()
    card.load(data=resbody)
    return card

  def put_vcard(self, url, vcard):
    raise Exception('Unimplemented')

  def list_vcards(self):
    status, msg, header, resbody = self.request(self.url, "PROPFIND", {}, {})
    tr = etree.fromstring(resbody)
    cardurls = [x.text for x in tr.xpath("/d:multistatus/d:response/d:href", namespaces={"d": "DAV:"}) if x.text not in ("", None) and x.text[-3:] == "vcf"]
    return cardurls


