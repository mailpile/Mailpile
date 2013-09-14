import tempfile

from email.parser import Parser
from email.message import Message
from GnuPGInterface import GnuPG
import StringIO
import re


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
          if not result:
            summary = ('signed', 'Error running GnuPG')
          else:
            reslines = [g.split("gpg: ")[1] for g in result.strip().split("\n")]
            matchgr = re.match(".*made (.*) using (.*) key ID ([a-zA-Z0-9]{8}).*", reslines[0])
            keyid = matchgr.groups()[2]
            keytype = matchgr.groups()[1]
            datetime = matchgr.groups()[0]

            # FIXME: This should understand what kind of UI we have.
            summary = ('signed', "Signed %s with %s key 0x%s (<a onclick=\"mailpile.gpgrecvkey('%s');\">fetch key</a>)"
              % (datetime, keytype, keyid, keyid))

        for sig_part in sig_parts:
          sig_part.openpgp = summary

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
        try:
          gpg = GnuPG().run(['--utf8-strings', '--decrypt'],
                            create_fhs=['stdin', 'stdout', 'stderr'])
          gpg.handles['stdin'].write(msg)
          gpg.handles['stdin'].close()
          result = gpg.handles['stdout'].read().decode('utf-8')
          gpg.wait()
          summary = ('decrypted', result)
          # part.attach(result)
          s = StringIO.StringIO()
          s.write(result)
          m = Parser().parse(s)
          m = Message()
          m.set_payload(result)
          part.set_payload([m])
          # print part.__module__
          # enc_parts.append(part)
        except IOError:
          if not result:
            summary = ('encrypted', 'Error running GnuPG')
          else:
            #reslines = [g.split("gpg: ")[1] for g in result.strip().split("\n")]
            #matchgr = re.match(".*made (.*) using (.*) key ID ([a-zA-Z0-9]{8}).*", reslines[0])
            #keyid = matchgr.groups()[2]
            #keytype = matchgr.groups()[1]
            #datetime = matchgr.groups()[0]

            # FIXME: This should understand what kind of UI we have.
            summary = ('encrypted', result)

        for enc_part in enc_parts:
          enc_part.openpgp = summary

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

