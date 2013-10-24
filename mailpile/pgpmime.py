import tempfile

from email.parser import Parser
from email.message import Message
import StringIO
import re

from gpgi import *


class PGPMimeParser(Parser):

  def parse_pgpmime(self, message):
    sig_count, sig_parts, sig_alg = 0, [], 'SHA1'
    enc_count, enc_parts, enc_ver = 0, [], None

    for part in message.walk():
      mimetype = part.get_content_type()
      if (sig_count > 1) and (mimetype == 'application/pgp-signature'):
        sig = part.get_payload()
        msg = '\r\n'.join(sig_parts[0].as_string().splitlines(False))+'\r\n'

        result = None
        gpg = GnuPG()
        status = gpg.verify(msg, sig)

        for sig_part in sig_parts:
          sig_part.openpgp_signature = status

        # Reset!
        sig_count, sig_parts = 0, []

      elif sig_count > 0:
          sig_parts.append(part)
          sig_count += 1

      elif enc_count > 0 and (mimetype == 'application/octet-stream'):
        # FIXME: Decrypt and parse!
        crypt = tempfile.NamedTemporaryFile()
        crypt.write(part.get_payload())
        crypt.flush()
        msg = '\r\n'.join(part.as_string().splitlines(False))+'\r\n'

        result = None
        gpg = GnuPG()
        result = gpg.decrypt(msg)
        summary = ('decrypted', result)
        s = StringIO.StringIO()
        s.write(result)
        m = Parser().parse(s)
        m = Message()
        m.set_payload(result)
        part.set_payload([m])

        for enc_part in enc_parts:
          enc_part.openpgp_decrypt = summary

        # Reset!
        enc_count, enc_parts = 0, []
      elif mimetype == 'multipart/signed':
        sig_alg = part.get_param('micalg', 'pgp-sha1').split('-')[1].upper()
        sig_count = 1

      elif mimetype == 'multipart/encrypted':
        enc_count = 1

  def parse(self, fp, headersonly=False):
    message = Parser.parse(self, fp, headersonly=headersonly)
    self.parse_pgpmime(message)
    return message

