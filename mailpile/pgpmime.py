from email.parser import Parser
from GnuPGInterface import GnuPG


class PGPMimeParser(Parser):

  def parse_pgpmime(self, message):
    # FIXME: Walk the resulting message, if we find PGP/Mime signed parts,
    #        check the signature.  If we find PGP/Mime encrypted parts,
    #        decrypt and parse the contents.

    sig_count, sig_part, sig_sig, sig_alg = 0, None, None, 'SHA1'
    enc_count, enc_part, enc_ver = 0, None, None

    for part in message.walk():
      mimetype = part.get_content_type()

      if sig_count > 0:
        if sig_count == 1:
          sig_part = part
          sig_count = 2
        elif mimetype == 'application/pgp-signature':
          sig_sig = part.get_payload()
          sig_count = 0

          pgptext = ('-----BEGIN PGP SIGNED MESSAGE-----\nHash: %s\n\n%s%s'
                     ) % (sig_alg,
                          '\r\n'.join(sig_part.as_string().splitlines(False)),
                          sig_sig)
          gpg = GnuPG().run(['--verify'], create_fhs=['stdin', 'stderr'])
          gpg.handles['stdin'].write(pgptext)
          gpg.handles['stdin'].close()
          result = gpg.handles['stderr'].read().decode('utf-8')
          gpg.handles['stderr'].close()
          try:
            gpg.wait()
          except IOError:
            pass

          sig_part.openpgp_sig = result
          print result  # FIXME, delete this

      elif enc_count > 0:
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

