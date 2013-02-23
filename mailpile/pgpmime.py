import tempfile

from email.parser import Parser
from GnuPGInterface import GnuPG


class PGPMimeParser(Parser):

  def parse_pgpmime(self, message):
    sig_count, sig_parts, sig_alg = 0, [], 'SHA1'
    enc_count, enc_parts, enc_ver = 0, [], None

    for part in message.walk():
      mimetype = part.get_content_type()

      if (sig_count > 1) and (mimetype == 'application/pgp-signature'):
        sig = tempfile.NamedTemporaryFile()
        sig.write(part.get_payload())
        sig.flush()
        msg = '\r\n'.join(sig_parts[0].as_string().splitlines(False))+'\r\n'

        result = None
        try:
          gpg = GnuPG().run(['--utf8-strings', '--verify', sig.name, '-'],
                            create_fhs=['stdin', 'stderr'])
          gpg.handles['stdin'].write(msg)
          gpg.handles['stdin'].close()
          result = gpg.handles['stderr'].read().decode('utf-8')
          gpg.wait()
          summary = ('verified', result)
        except IOError:
          summary = ('signed', result or 'Error running GnuPG')

        for sig_part in sig_parts:
          sig_part.openpgp = summary

        # Reset!
        sig_count, sig_parts = 0, []

      elif sig_count > 0:
          sig_parts.append(part)
          sig_count += 1

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

