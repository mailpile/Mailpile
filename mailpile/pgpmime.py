import tempfile

from email.parser import Parser
from GnuPGInterface import GnuPG


class PGPMimeParser(Parser):

  def parse_pgpmime(self, message):
    sig_count, sig_part, sig_alg = 0, None, 'SHA1'
    enc_count, enc_part, enc_ver = 0, None, None

    for part in message.walk():
      mimetype = part.get_content_type()

      if sig_count > 0:
        if sig_count == 1:
          sig_part = part
          sig_count = 2
        elif mimetype == 'application/pgp-signature':
          sig_count = 0

          sig = tempfile.NamedTemporaryFile()
          sig.write(part.get_payload())
          sig.flush()
          msg = '\r\n'.join(sig_part.as_string().splitlines(False))+'\r\n'

          gpg = GnuPG().run(['--utf8-strings', '--verify', sig.name, '-'],
                            create_fhs=['stdin', 'stderr'])
          gpg.handles['stdin'].write(msg)
          gpg.handles['stdin'].close()
          result = gpg.handles['stderr'].read().decode('utf-8')
          gpg.handles['stderr'].close()
          try:
            gpg.wait()
            sig_part.openpgp = ('verified', result)
          except IOError:
            sig_part.openpgp = ('signed', result)

      elif enc_count > 0:
        # FIXME: Decrypt and parse!
        pass

      elif mimetype == 'multipart/signed':
        sig_alg = part.get_param('micalg', 'pgp-sha1').split('-')[1].upper()
        sig_count = 1

      elif mimetype == 'multipart/encrypted':
        enc_count = 1

  def parse(self, fp, headersonly=False):
    message = Parser.parse(self, fp, headersonly=headersonly)
    self.parse_pgpmime(message)
    return message

