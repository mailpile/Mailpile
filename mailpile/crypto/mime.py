# These are methods to do with MIME and crypto, implementing PGP/MIME.

import re
import StringIO
import email.parser

from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase

from mailpile.crypto.state import EncryptionInfo, SignatureInfo
from mailpile.mail_generator import Generator

##[ Common utilities ]#########################################################

def Normalize(payload):
    return re.sub(r'\r?\n', '\r\n', payload)


class EncryptionFailureError(ValueError):
    pass


class SignatureFailureError(ValueError):
    pass


##[ Methods for unwrapping encrypted parts ]###################################

def UnwrapMimeCrypto(part, protocols=None, si=None, ei=None):
    """
    This method will replace encrypted and signed parts with their
    contents and set part attributes describing the security properties
    instead.
    """
    part.signature_info = si or SignatureInfo()
    part.encryption_info = ei or EncryptionInfo()
    mimetype = part.get_content_type()
    if part.is_multipart():

        # FIXME: Check the protocol. PGP? Something else?
        # FIXME: This is where we add hooks for other MIME encryption
        #        schemes, so route to callbacks by protocol.
        crypto_cls = protocols['openpgp']

        if mimetype == 'multipart/signed':
            try:
                gpg = crypto_cls()
                boundary = part.get_boundary()
                payload, signature = part.get_payload()

                # The Python get_payload() method likes to rewrite headers,
                # which breaks signature verification. So we manually parse
                # out the raw payload here.
                head, raw_payload, junk = part.as_string(
                    ).replace('\r\n', '\n').split('\n--%s\n' % boundary, 2)

                part.signature_info = gpg.verify(
                    Normalize(raw_payload), signature.get_payload())

                # Reparent the contents up, removing the signature wrapper
                part.set_payload(payload.get_payload())
                for h in payload.keys():
                    del part[h]
                for h, v in payload.items():
                    part.add_header(h, v)

                # Try again, in case we just unwrapped another layer
                # of multipart/something.
                return UnwrapMimeCrypto(part,
                                        protocols=protocols,
                                        si=part.signature_info,
                                        ei=part.encryption_info)

            except (IOError, OSError, ValueError, IndexError, KeyError):
                part.signature_info = SignatureInfo()
                part.signature_info["status"] = "error"

        elif mimetype == 'multipart/encrypted':
            try:
                gpg = crypto_cls()
                preamble, payload = part.get_payload()

                (part.signature_info, part.encryption_info, decrypted
                 ) = gpg.decrypt(payload.as_string())
            except (IOError, OSError, ValueError, IndexError, KeyError):
                part.encryption_info = EncryptionInfo()
                part.encryption_info["status"] = "error"

            if part.encryption_info['status'] == 'decrypted':
                newpart = email.parser.Parser().parse(
                    StringIO.StringIO(decrypted))

                # Reparent the contents up, removing the encryption wrapper
                part.set_payload(newpart.get_payload())
                for h in newpart.keys():
                    del part[h]
                for h, v in newpart.items():
                    part.add_header(h, v)

                # Try again, in case we just unwrapped another layer
                # of multipart/something.
                return UnwrapMimeCrypto(part,
                                        protocols=protocols,
                                        si=part.signature_info,
                                        ei=part.encryption_info)

        # If we are still multipart after the above shenanigans, recurse
        # into our subparts and unwrap them too.
        if part.is_multipart():
            for subpart in part.get_payload():
                UnwrapMimeCrypto(subpart,
                                 protocols=protocols,
                                 si=part.signature_info,
                                 ei=part.encryption_info)

    else:
        # FIXME: This is where we would handle cryptoschemes that don't
        #        appear as multipart/...
        pass


##[ Methods for encrypting and signing ]#######################################

class MimeWrapper:
    CONTAINER_TYPE = 'multipart/mixed'
    CONTAINER_PARAMS = ()
    CRYTPO_CLASS = None

    def __init__(self, config, cleaner=None, sender=None, recipients=None):
        self.config = config
        self.crypto = self.CRYPTO_CLASS()
        self.sender = sender
        self.cleaner = cleaner
        self.recipients = recipients or []
        self.container = MIMEMultipart()
        self.container.set_type(self.CONTAINER_TYPE)
        for pn, pv in self.CONTAINER_PARAMS:
            self.container.set_param(pn, pv)

    def attach(self, part):
        self.container.attach(part)
        if self.cleaner:
            self.cleaner(part)
        del part['MIME-Version']
        return self

    def get_keys(self, people):
        return people

    def flatten(self, msg, unixfrom=False):
        buf = StringIO.StringIO()
        Generator(buf).flatten(msg, unixfrom=unixfrom, linesep='\r\n')
        return buf.getvalue()

    def wrap(self, msg):
        for h in msg.keys():
            hl = h.lower()
            if not hl.startswith('content-') and not hl.startswith('mime-'):
                self.container[h] = msg[h]
                del msg[h]
        return self.container


class MimeSigningWrapper(MimeWrapper):
    CONTAINER_TYPE = 'multipart/signed'
    CONTAINER_PARAMS = ()
    SIGNATURE_TYPE = 'application/x-signature'
    SIGNATURE_DESC = 'Abstract Digital Signature'

    def __init__(self, *args, **kwargs):
        MimeWrapper.__init__(self, *args, **kwargs)

        self.sigblock = MIMEBase(*self.SIGNATURE_TYPE.split('/'))
        self.sigblock.set_param("name", "signature.asc")
        for h, v in (("Content-Description", self.SIGNATURE_DESC),
                     ("Content-Disposition",
                      "attachment; filename=\"signature.asc\"")):
            self.sigblock.add_header(h, v)

    def wrap(self, msg):
        MimeWrapper.wrap(self, msg)
        self.attach(msg)
        self.attach(self.sigblock)

        message_text = Normalize(self.flatten(msg))
        from_key = self.get_keys([self.sender])[0]
        status, sig = self.crypto.sign(message_text,
                                       fromkey=from_key, armor=True)
        if status == 0:
            self.sigblock.set_payload(sig)
            return self.container
        else:
            raise SignatureFailureError(_('Failed to sign message!'))


class MimeEncryptingWrapper(MimeWrapper):
    CONTAINER_TYPE = 'multipart/encrypted'
    CONTAINER_PARAMS = ()
    ENCRYPTION_TYPE = 'application/x-encrypted'
    ENCRYPTION_VERSION = 0

    def __init__(self, *args, **kwargs):
        MimeWrapper.__init__(self, *args, **kwargs)

        self.version = MIMEBase(*self.ENCRYPTION_TYPE.split('/'))
        self.version.set_payload('Version: %s\n' % self.ENCRYPTION_VERSION)
        for h, v in (("Content-Disposition", "attachment"), ):
            self.version.add_header(h, v)

        self.enc_data = MIMEBase('application', 'octet-stream')
        for h, v in (("Content-Disposition",
                      "attachment; filename=\"msg.asc\""), ):
            self.enc_data.add_header(h, v)

        self.attach(self.version)
        self.attach(self.enc_data)

    def wrap(self, msg):
        MimeWrapper.wrap(self, msg)

        del msg['MIME-Version']
        if self.cleaner:
            self.cleaner(msg)
        message_text = Normalize(self.flatten(msg))

        to_keys = set(self.get_keys(self.recipients + [self.sender]))
        status, enc = self.crypto.encrypt(message_text,
                                          tokeys=to_keys, armor=True)
        if status == 0:
            self.enc_data.set_payload(enc)
            return self.container
        else:
            raise EncryptionFailureError(_('Failed to sign message!'))
