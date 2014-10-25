# These are methods to do with MIME and crypto, implementing PGP/MIME.

import re
import StringIO
import email.parser

from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase

from mailpile.crypto.state import EncryptionInfo, SignatureInfo
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mail_generator import Generator

##[ Common utilities ]#########################################################

def Normalize(payload):
    # http://tools.ietf.org/html/rfc3156 says we must:
    #
    #   - use CRLF everywhere
    #   - strip trailing whitespace
    #   - end with a CRLF
    #
    # In particlar, the stripping of trailing whitespace seems (based on
    # experiments with mutt), to in practice mean "strip trailing whitespace
    # off the last line"...
    #
    text = re.sub(r'\r?\n', '\r\n', payload).rstrip(' \t')
    if not text.endswith('\r\n'):
        text += '\r\n'
    return text


def MessageAsString(part, unixfrom=False):
    buf = StringIO.StringIO()
    Generator(buf).flatten(part, unixfrom=unixfrom)
    return Normalize(buf.getvalue()).replace('--\r\n--', '--\r\n\r\n--')


class EncryptionFailureError(ValueError):
    pass


class SignatureFailureError(ValueError):
    pass


DEFAULT_CHARSETS = ['utf-8', 'iso-8859-1']


def _decode_text_part(part, payload, charsets=None):
    for cs in (c for c in ([part.get_content_charset() or None] +
                           (charsets or DEFAULT_CHARSETS)) if c):
        try:
            return cs, payload.decode(cs)
        except (UnicodeDecodeError, TypeError, LookupError):
            pass
    return '8bit', payload


def _update_text_payload(part, payload, charsets=None):
    if 'content-transfer-encoding' in part:
        # We want this recalculated by the charset setting below
        del part['content-transfer-encoding']
    charset, payload = _decode_text_part(part, payload, charsets=charsets)
    part.set_payload(payload, charset)


##[ Methods for unwrapping encrypted parts ]###################################

def UnwrapMimeCrypto(part, protocols=None, psi=None, pei=None, charsets=None):
    """
    This method will replace encrypted and signed parts with their
    contents and set part attributes describing the security properties
    instead.
    """
    part.signature_info = SignatureInfo(parent=psi)
    part.encryption_info = EncryptionInfo(parent=pei)
    mimetype = part.get_content_type()
    if part.is_multipart():

        # FIXME: Check the protocol. PGP? Something else?
        # FIXME: This is where we add hooks for other MIME encryption
        #        schemes, so route to callbacks by protocol.
        crypto_cls = protocols['openpgp']

        # Containers are by default not bubbly
        part.signature_info.bubbly = False
        part.encryption_info.bubbly = False

        if mimetype == 'multipart/signed':
            try:
                boundary = part.get_boundary()
                payload, signature = part.get_payload()

                # The Python get_payload() method likes to rewrite headers,
                # which breaks signature verification. So we manually parse
                # out the raw payload here.
                head, raw_payload, junk = part.as_string(
                    ).replace('\r\n', '\n').split('\n--%s\n' % boundary, 2)

                part.signature_info = crypto_cls().verify(
                    Normalize(raw_payload), signature.get_payload())
                part.signature_info.bubble_up(psi)

                # Reparent the contents up, removing the signature wrapper
                part.set_payload(payload.get_payload())
                for h in payload.keys():
                    del part[h]
                for h, v in payload.items():
                    part.add_header(h, v)

                # Try again, in case we just unwrapped another layer
                # of multipart/something.
                UnwrapMimeCrypto(part,
                                 protocols=protocols,
                                 psi=part.signature_info,
                                 pei=part.encryption_info,
                                 charsets=charsets)

            except (IOError, OSError, ValueError, IndexError, KeyError):
                part.signature_info = SignatureInfo()
                part.signature_info["status"] = "error"
                part.signature_info.bubble_up(psi)

        elif mimetype == 'multipart/encrypted':
            try:
                preamble, payload = part.get_payload()

                (part.signature_info, part.encryption_info, decrypted
                 ) = crypto_cls().decrypt(payload.as_string())
            except (IOError, OSError, ValueError, IndexError, KeyError):
                part.encryption_info = EncryptionInfo()
                part.encryption_info["status"] = "error"

            part.signature_info.bubble_up(psi)
            part.encryption_info.bubble_up(pei)

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
                UnwrapMimeCrypto(part,
                                 protocols=protocols,
                                 psi=part.signature_info,
                                 pei=part.encryption_info,
                                 charsets=charsets)

        # If we are still multipart after the above shenanigans (perhaps due
        # to an error state), recurse into our subparts and unwrap them too.
        elif part.is_multipart():
            for sp in part.get_payload():
                UnwrapMimeCrypto(sp,
                                 protocols=protocols,
                                 psi=part.signature_info,
                                 pei=part.encryption_info,
                                 charsets=charsets)

    elif mimetype == 'text/plain':
        return UnwrapPlainTextCrypto(part,
                                     protocols=protocols,
                                     psi=psi,
                                     pei=pei,
                                     charsets=charsets)

    else:
        # FIXME: This is where we would handle cryptoschemes that don't
        #        appear as multipart/...
        pass


    # Mix in our bubbles
    part.signature_info.mix_bubbles()
    part.encryption_info.mix_bubbles()

    # Bubble up!
    part.signature_info.bubble_up(psi)
    part.encryption_info.bubble_up(pei)


def UnwrapPlainTextCrypto(part, protocols=None, psi=None, pei=None,
                                charsets=None):
    """
    This method will replace encrypted and signed parts with their
    contents and set part attributes describing the security properties
    instead.
    """
    payload = part.get_payload(None, True).strip()
    si = SignatureInfo(parent=psi)
    ei = EncryptionInfo(parent=pei)
    for crypto_cls in protocols.values():
        crypto = crypto_cls()

        if (payload.startswith(crypto.ARMOR_BEGIN_ENCRYPTED) and
                payload.endswith(crypto.ARMOR_END_ENCRYPTED)):
            try:
                si, ei, text = crypto.decrypt(payload)
                _update_text_payload(part, text, charsets=charsets)
            except (IOError, OSError, ValueError, IndexError, KeyError):
                ei = EncryptionInfo()
                ei["status"] = "error"
            break

        elif (payload.startswith(crypto.ARMOR_BEGIN_SIGNED) and
                payload.endswith(crypto.ARMOR_END_SIGNED)):
            try:
                si = crypto.verify(payload)
            except (IOError, OSError, ValueError, IndexError, KeyError):
                si = SignatureInfo()
                si["status"] = "error"
            _update_text_payload(part, crypto.remove_armor(payload),
                                 charsets=charsets)
            break

    part.signature_info = si
    part.signature_info.bubble_up(psi)
    part.encryption_info = ei
    part.encryption_info.bubble_up(pei)


##[ Methods for encrypting and signing ]#######################################

class MimeWrapper:
    CONTAINER_TYPE = 'multipart/mixed'
    CONTAINER_PARAMS = ()

    def __init__(self, config, cleaner=None, sender=None, recipients=None):
        self.config = config
        self.sender = sender
        self.cleaner = cleaner
        self.recipients = recipients or []
        self.container = c = MIMEMultipart()
        c.set_type(self.CONTAINER_TYPE)
        c.signature_info = SignatureInfo(bubbly=False)
        c.encryption_info = EncryptionInfo(bubbly=False)
        if self.cleaner:
            self.cleaner(self.container)
        for pn, pv in self.CONTAINER_PARAMS:
            self.container.set_param(pn, pv)

    def crypto(self):
        return NotImplementedError("Please override me")

    def attach(self, part):
        c = self.container
        c.attach(part)

        if not hasattr(part, 'signature_info'):
            part.signature_info = SignatureInfo(parent=c.signature_info)
            part.encryption_info = EncryptionInfo(parent=c.encryption_info)
        else:
            part.signature_info.parent = c.signature_info
            part.signature_info.bubbly = True
            part.encryption_info.parent = c.encryption_info
            part.encryption_info.bubbly = True

        if self.cleaner:
            self.cleaner(part)
        del part['MIME-Version']
        return self

    def get_keys(self, people):
        return people

    def flatten(self, msg, unixfrom=False):
        return MessageAsString(msg, unixfrom=unixfrom)

    def get_only_text_part(self, msg):
        count = 0
        only_text_part = None
        for part in msg.walk():
            if part.is_multipart():
                continue
            count += 1
            if part.get_content_type() != 'text/plain' or count != 1:
                return False
            else:
                only_text_part = part
        return only_text_part

    def wrap(self, msg):
        for h in msg.keys():
            hl = h.lower()
            if not hl.startswith('content-') and not hl.startswith('mime-'):
                self.container[h] = msg[h]
                del msg[h]
            elif hl == 'mime-version':
                del msg[h]
        if hasattr(msg, 'signature_info'):
            self.container.signature_info = msg.signature_info
            self.container.encryption_info = msg.encryption_info
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

    def _update_crypto_status(self, part):
        part.signature_info.part_status = 'verified'

    def wrap(self, msg, prefer_inline=False):
        from_key = self.get_keys([self.sender])[0]

        if prefer_inline:
            prefer_inline = self.get_only_text_part(msg)

        if prefer_inline is not False:
            message_text = Normalize(prefer_inline.get_payload(None, True)
                                     .strip() + '\r\n\r\n')
            status, sig = self.crypto().sign(message_text,
                                             fromkey=from_key,
                                             clearsign=True,
                                             armor=True)
            if status == 0:
                _update_text_payload(prefer_inline, sig)
                self._update_crypto_status(prefer_inline)
                return msg

        else:
            MimeWrapper.wrap(self, msg)
            self.attach(msg)
            self.attach(self.sigblock)
            message_text = self.flatten(msg)
            status, sig = self.crypto().sign(message_text,
                                             fromkey=from_key, armor=True)
            if status == 0:
                self.sigblock.set_payload(sig)
                self._update_crypto_status(self.container)
                return self.container

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

    def _encrypt(self, message_text, tokeys=None, armor=False):
        return self.crypto().encrypt(message_text,
                                     tokeys=tokeys, armor=True)

    def _update_crypto_status(self, part):
        part.encryption_info.part_status = 'decrypted'

    def wrap(self, msg, prefer_inline=False):
        to_keys = set(self.get_keys(self.recipients + [self.sender]))

        if prefer_inline:
            prefer_inline = self.get_only_text_part(msg)

        if prefer_inline is not False:
            message_text = Normalize(prefer_inline.get_payload(None, True))
            status, enc = self._encrypt(message_text,
                                        tokeys=to_keys,
                                        armor=True)
            if status == 0:
                _update_text_payload(prefer_inline, enc)
                self._update_crypto_status(prefer_inline)
                return msg

        else:
            MimeWrapper.wrap(self, msg)
            del msg['MIME-Version']
            if self.cleaner:
                self.cleaner(msg)
            message_text = self.flatten(msg)
            status, enc = self._encrypt(message_text,
                                        tokeys=to_keys,
                                        armor=True)
            if status == 0:
                self.enc_data.set_payload(enc)
                self._update_crypto_status(self.enc_data)
                return self.container

        raise EncryptionFailureError(_('Failed to encrypt message!'))
