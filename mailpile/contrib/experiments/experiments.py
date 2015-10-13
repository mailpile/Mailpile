import copy
import re
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText

from mailpile.crypto.state import SignatureInfo, EncryptionInfo
from mailpile.plugins import EmailTransform
from mailpile.mailutils import CleanHeaders
from mailpile.util import *


##[ Crypto experiments ]######################################################

def _AddCryptoState(part, src=None):
    part.signature_info = src.signature_info if src else SignatureInfo()
    part.encryption_info = src.encryption_info if src else EncryptionInfo()
    return part


def _CopyAsMultipart(msg, callback, cleaner):
    m = _AddCryptoState(MIMEMultipart())
    m.set_type('multipart/mixed')
    if cleaner:
        cleaner(m)

    for hdr, value in msg.items():
        hdrl = hdr.lower()
        if not hdrl.startswith('content-') and not hdrl.startswith('mime-'):
            m[hdr] = value
            del msg[hdr]
        elif hdrl == 'mime-version':
            del msg[hdrl]
    callback('headers', m, msg)

    def att(part):
        if hasattr(part, 'signature_info'):
            part.signature_info.parent = m.signature_info
            part.encryption_info.parent = m.encryption_info
        m.attach(part)
        callback('part', m, part)
    if msg.is_multipart() and msg.get_content_type() == 'multipart/mixed':
        for part in msg.get_payload():
            att(part)
    else:
        att(msg)
    callback('payload', m, msg)

    return m


class EmailCryptoTxf(EmailTransform):
    """This is a set of email encryption experiments"""

    # Different methods. True is for backwards compatibility, => 'attach'
    TRANSFORM_STYLES = ('true', 'attach', 'mime')

    # Header protection ignores these...
    DKG_IGNORED_HEADERS = ['mime-version', 'content-type']

    # When encrypting, we may want to replace or strip certain
    # headers from the unprotected header. We also make sure some
    # of the protected headers are visible to the recipient, in
    # an inline part instead of an attachment.
    DKG_VISIBLE_HEADERS = ['subject', 'from', 'to', 'cc']
    DKG_REPLACED_HEADERS = {
        'subject': lambda s: 'Encrypted Message',
    }
    DKG_STRIPPED_HEADERS = ['openpgp']

    def DkgHeaderTransformOutgoing(self, msg, crypto_policy, cleaner,
                                   transform_style):
        visible, invisible = Message(), Message()

        if 'encrypt' in crypto_policy:
            for hdr, val in CleanHeaders(msg):
                hdrl = hdr.lower()

                if hdrl in self.DKG_VISIBLE_HEADERS:
                    visible[hdr] = val
                elif hdrl not in self.DKG_IGNORED_HEADERS:
                    invisible[hdr] = val

                if hdrl in self.DKG_REPLACED_HEADERS:
                    del msg[hdr]
                    msg[hdr] = self.DKG_REPLACED_HEADERS[hdrl](val)
                elif hdrl in self.DKG_STRIPPED_HEADERS:
                    del msg[hdr]

        elif 'sign' in crypto_policy:
            for hdr, val in CleanHeaders(msg):
                if hdr.lower() not in self.DKG_IGNORED_HEADERS:
                    invisible[hdr] = val

        else:
            return msg

        def copy_callback_attach(stage, msg, part):
            if stage == 'headers' and visible.keys():
                part = _AddCryptoState(MIMEText(visible.as_string(),
                                                'rfc822-headers'))
                part.set_param('protected-headers',
                               'v1,%s' % msg['Message-ID'])
                part['Content-Disposition'] = 'inline'
                del part['MIME-Version']
                msg.attach(part)
                return part

            elif stage == 'payload' and invisible.keys():
                part = _AddCryptoState(MIMEText(invisible.as_string(),
                                                'rfc822-headers'))
                part.set_param('protected-headers',
                               'v1,%s' % msg['Message-ID'])
                part['Content-Disposition'
                     ] = 'attachment; filename=Secure_Headers.txt'
                del part['MIME-Version']
                msg.attach(part)
                return part

            return None

        def copy_callback_mime(stage, msg, part):
            if stage == 'headers':
                new_part = copy_callback_attach(stage, msg, part)
                if new_part:
                    for key in invisible.keys():
                        new_part[key] = invisible[key]
                        del invisible[key]

            elif stage in ('payload', 'part') and invisible.keys():
                for key in invisible.keys():
                    part[key] = invisible[key]
                    del invisible[key]

        if transform_style == 'mime':
            return _CopyAsMultipart(msg, copy_callback_mime, cleaner)
        else:
            return _CopyAsMultipart(msg, copy_callback_attach, cleaner)

    def DkgHeaderTransformIncoming(self, msg):
        # FIXME: Parse incoming message/rfc822-headers parts, migrate
        #        back to public header. Somehow annotate which are secure
        #        and which are not.
        return msg


    ##[ Transform hooks follow ]##############################################

    def TransformOutgoing(self, sender, rcpt, msg,
                          crypto_policy='none',
                          cleaner=lambda m: m,
                          **kwargs):
        txf_continue = True
        txf_matched = False

        txf_style = self.config.prefs.get('experiment_dkg_hdrs', 'off').lower()
        if txf_style in self.TRANSFORM_STYLES:
            msg = self.DkgHeaderTransformOutgoing(msg, crypto_policy, cleaner,
                                                  txf_style)
            txf_matched = True

        return sender, rcpt, msg, txf_matched, txf_continue

    def TransformIncoming(self, msg, **kwargs):
        txf_continue = True
        txf_matched = False

        if self.config.prefs.experiment_dkg_hdrs is True:
            msg = self.DkgHeaderTransformIncoming(msg)
            txf_matched = True

        return msg, txf_matched, txf_continue


##[ Keyword experiments ]#####################################################

RE_QUOTES = re.compile(r'^(>\s*)+')
RE_CLEANPARA = re.compile(r'[>"\*\'\s]')

def paragraph_id_extractor(index, msg, ctype, textpart, **kwargs):
    """Create search index terms to identify paragraphs."""
    kws = set([])
    try:
        if not ctype == 'text/plain':
            return kws
        if not index.config.prefs.get('experiment_para_kws'):
            return kws

        para = {'text': '', 'qlevel': 0}
        def end_para():
            txt = para.get('text', '')
            if (len(txt) > 60 and
                    not ('unsubscribe' in txt and 'http' in txt) and
                    not ('@lists' in txt or '/mailman/' in txt) and
                    not (txt.endswith(':'))):
                txt = re.sub(RE_CLEANPARA, '', txt)[-120:]
#               print 'PARA: %s' % txt
                kws.add('%s:p' % md5_hex(txt))
            para.update({'text': '', 'qlevel': 0})

        for line in textpart.splitlines():
            if line in ('-- ', '- -- ', '- --'):
                return kws

            # Find the quote markers...
            markers = re.match(RE_QUOTES, line)
            ql = len((markers.group(0) if markers else '').strip())

            # Paragraphs end when...
            if ((ql == 0 and line.endswith(':')) or  # new quote starts
                    (ql != para['qlevel']) or        # quote level changes
                    (ql == len(line)) or             # blank lines
                    (line[:2] == '--')):             # on -- dividers
                end_para()

            para['qlevel'] = ql
            if not line[:2] in ('--', ):
                para['text'] += line
        end_para()
    except: # AttributeError:
        import traceback
        traceback.print_exc()
        pass
    return kws
