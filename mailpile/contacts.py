# This is a very simplistic Contact class based on VCard 4.0

import random

from mailpile.util import *


class Contact(dict):
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
    return '%s <%s>' % (self.fn, self.email)

  fn = property(lambda self: self.get('FN', [[None]])[0][0],
                lambda self, v: self.__setitem__('FN', v))

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
    # FIXME: Render as a jCard
    raise Exception('Unimplemented')

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

