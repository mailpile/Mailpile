# This is a very simplistic VCard 4.0 class with no sanity checks.

class SimpleVCard(dict):
  FILENAME = None
  VERSION = 4.0
  ORDER = []

  def __getitem__(self, key):
    return dict.__getitem__(self, key.upper())

  def __setitem__(self, key, val):
    key = key.upper()
    if key not in self.ORDER:
      self.ORDER.append(key)
    if type(val) == type(list()):
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

  email = property(lambda self: self.get('EMAIL', [[None]])[0][0],
                   lambda self, v: self.__setitem__('EMAIL', v))

  def _rotated_vcf(self, key):
    data = self[key].pop(0)
    self[key].append(data)
    return '%s:%s' % (';'.join([key] + data[1]), data[0])

  def as_vcf(self):
    return '\r\n'.join([
      'BEGIN:VCARD',
      'VERSION:%s' % self.VERSION,
    ] + [
      # The _rotated_vcf lets us rotate through the values in order
      # and we should end up with everything back in its original state.
      (self._rotated_vcf(k)) for k in self.ORDER
    ] + [
      'END:VCARD',
      ''
    ])

  def load(self, filename=None):
    self.FILENAME = filename or self.FILENAME
    data = open(self.FILENAME, 'rb').read().decode('utf-8')
    lines = [l.strip() for l in data.strip().splitlines()]
    if (not lines.pop(0).upper() == 'BEGIN:VCARD'
    or  not lines.pop(-1).upper() == 'END:VCARD'):
      raise ValueError('Not a valid VCard')

    for line in lines:
      attrs, data = line.split(':', 1)
      attrs = attrs.split(';')
      key = attrs.pop(0)
      if key == 'VERSION':
        self.VERSION = data
      elif key not in ('BEGIN:VCARD', 'VERSION', 'END:VCARD'):
        self.ORDER.append(key)
        if not key in self:
          self[key] = []
        self[key].append([data, attrs]) 
    return self

  def save(self, filename=None):
    fd = open(filename or self.FILENAME, 'wb')
    fd.write(self.as_vcf().encode('utf-8'))
    fd.close()
    return self

