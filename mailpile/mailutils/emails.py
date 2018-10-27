# vim: set fileencoding=utf-8 :
#
# FIXME: Refactor this monster into mailpile.mailutils.*
#
import base64
import copy
import email.header
import email.parser
import email.utils
import errno
import mailbox
import mimetypes
import os
import quopri
import random
import re
import StringIO
import threading
import traceback
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from mailpile.util import *
from platform import system
from urllib import quote, unquote
from datetime import datetime, timedelta

from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.mime import UnwrapMimeCrypto, MessageAsString
from mailpile.crypto.state import EncryptionInfo, SignatureInfo
from mailpile.eventlog import GetThreadEvent
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.vcard import AddressInfo
from mailpile.mailutils import *
from mailpile.mailutils.addresses import AddressHeaderParser
from mailpile.mailutils.generator import Generator
from mailpile.mailutils.html import extract_text_from_html, clean_html
from mailpile.mailutils.headerprint import HeaderPrints
from mailpile.mailutils.safe import safe_decode_hdr


GLOBAL_CONTENT_ID_LOCK = MboxLock()
GLOBAL_CONTENT_ID = random.randint(0, 0xfffffff)

def MakeContentID():
    global GLOBAL_CONTENT_ID
    with GLOBAL_CONTENT_ID_LOCK:
        GLOBAL_CONTENT_ID += 1
        GLOBAL_CONTENT_ID %= 0xfffffff
        return '%x' % GLOBAL_CONTENT_ID


def MakeBoundary():
    return '==%s==' % okay_random(30)


def MakeMessageID():
    # We generate a message-ID which is almost entirely random; we
    # include an element of the local time (give-or-take 36 hours)
    # to further reduce the odds of any collision.
    return '<%s%x@mailpile>' % (
        okay_random(40), time.time() // (3600*48))


def MakeMessageDate(ts=None):
    # Generate valid dates, but add some jitter to the seconds field
    # so we're not trivially leaking our exact time. We also avoid
    # leaking the time zone.
    return email.utils.formatdate(
        timeval=(ts or time.time()) + (random.randint(0, 60) - 30),
        localtime=False)


GLOBAL_PARSE_CACHE_LOCK = MboxLock()
GLOBAL_PARSE_CACHE = []

def ClearParseCache(cache_id=None, pgpmime=False, full=False):
    global GLOBAL_PARSE_CACHE
    with GLOBAL_PARSE_CACHE_LOCK:
        GPC = GLOBAL_PARSE_CACHE
        for i in range(0, len(GPC)):
            if (full or
                    (pgpmime and GPC[i][1]) or
                    (cache_id and GPC[i][0] == cache_id)):
                GPC[i] = (None, None, None)


def ParseMessage(fd, cache_id=None, update_cache=False,
                     pgpmime='all', config=None, event=None,
                     allow_weak_crypto=False):
    global GLOBAL_PARSE_CACHE
    if not GnuPG:
        pgpmime = False

    if cache_id is not None and not update_cache:
        with GLOBAL_PARSE_CACHE_LOCK:
            for cid, pm, message in GLOBAL_PARSE_CACHE:
                if cid == cache_id and pm == pgpmime:
                    return message

    if pgpmime:
        message = ParseMessage(fd, cache_id=cache_id, pgpmime=False,
                                   config=config)
        if message is None:
            return None
        if cache_id is not None:
            # Caching is enabled, let's not clobber the encrypted version
            # of this message with a fancy decrypted one.
            message = copy.deepcopy(message)
        def MakeGnuPG(*args, **kwargs):
            ev = event or GetThreadEvent()
            if ev and 'event' not in kwargs:
                kwargs['event'] = ev
            return GnuPG(config, *args, **kwargs)

        unwrap_attachments = ('all' in pgpmime or 'att' in pgpmime)
        UnwrapMimeCrypto(message,
            protocols={'openpgp': MakeGnuPG},
            unwrap_attachments=unwrap_attachments,
            require_MDC=(not allow_weak_crypto))

    else:
        try:
            if not hasattr(fd, 'read'):  # Not a file, is it a function?
                fd = fd()
            safe_assert(hasattr(fd, 'read'))
        except (TypeError, AssertionError):
            return None

        message = email.parser.Parser().parse(fd)
        msi = message.signature_info = SignatureInfo(bubbly=False)
        mei = message.encryption_info = EncryptionInfo(bubbly=False)
        for part in message.walk():
            part.signature_info = SignatureInfo(parent=msi)
            part.encryption_info = EncryptionInfo(parent=mei)

    if cache_id is not None:
        with GLOBAL_PARSE_CACHE_LOCK:
            # Keep 25 items, put new ones at the front
            GLOBAL_PARSE_CACHE[24:] = []
            GLOBAL_PARSE_CACHE[:0] = [(cache_id, pgpmime, message)]

    return message


def GetTextPayload(part):
    mimetype = part.get_content_type() or 'text/plain'
    cte = part.get('content-transfer-encoding', '').lower()
    if mimetype[:5] == 'text/' and cte == 'base64':
        # Mailing lists like to mess with text/plain parts, and Majordomo
        # in particular isn't aware of base64 encoding. Compensate!
        payload = part.get_payload(None, False) or ''
        parts = payload.split('\n--')
        try:
            parts[0] = base64.b64decode(parts[0])
        except TypeError:
            pass
        return '\n--'.join(parts)
    else:
        return part.get_payload(None, True) or ''


def ExtractEmails(string, strip_keys=True):
    emails = []
    startcrap = re.compile('^[\'\"<(]')
    endcrap = re.compile('[\'\">);]$')
    string = string.replace('<', ' <').replace('(', ' (')
    for w in [sw.strip() for sw in re.compile('[,\s]+').split(string)]:
        atpos = w.find('@')
        if atpos >= 0:
            while startcrap.search(w):
                w = w[1:]
            while endcrap.search(w):
                w = w[:-1]
            if w.startswith('mailto:'):
                w = w[7:]
                if '?' in w:
                    w = w.split('?')[0]
            if strip_keys and '#' in w[atpos:]:
                w = w[:atpos] + w[atpos:].split('#', 1)[0]
            # E-mail addresses are only allowed to contain ASCII
            # characters, so we just strip everything else away.
            emails.append(CleanText(w,
                                    banned=CleanText.WHITESPACE,
                                    replace='_').clean)
    return emails


def ExtractEmailAndName(string):
    email = (ExtractEmails(string) or [''])[0]
    name = (string
            .replace(email, '')
            .replace('<>', '')
            .replace('"', '')
            .replace('(', '')
            .replace(')', '')).strip()
    return email, (name or email)


def CleanHeaders(msg, copy_all=True, tombstones=False):
    clean_headers = []
    address_headers_lower = [h.lower() for h in Email.ADDRESS_HEADERS]
    for key, value in msg.items():
        lkey = key.lower()

        # Remove headers we don't want to expose
        if (lkey.startswith('x-mp-internal-') or
                lkey in ('bcc', 'encryption', 'attach-pgp-pubkey')):
            if tombstones:
                clean_headers.append((key, None))

        # Strip the #key part off any e-mail addresses:
        elif lkey in address_headers_lower:
            if '#' in value:
                clean_headers.append((key, re.sub(
                    r'(@[^<>\s#]+)#[a-fxA-F0-9]+([>,\s]|$)', r'\1\2', value)))
            elif copy_all:
                clean_headers.append((key, value))
        elif copy_all:
            clean_headers.append((key, value))

    return clean_headers


def CleanMessage(config, msg):
    replacements = CleanHeaders(msg, copy_all=False, tombstones=True)

    for key, val in replacements:
        del msg[key]
    for key, val in replacements:
        if val:
            msg[key] = val

    return msg


def PrepareMessage(config, msg,
                   sender=None, rcpts=None, events=None, bounce=False):
    msg = copy.deepcopy(msg)

    # Short circuit if this message has already been prepared.
    if ('x-mp-internal-sender' in msg and
            'x-mp-internal-rcpts' in msg and
            not bounce):
        return (sender or msg['x-mp-internal-sender'],
                rcpts or [r.strip()
                          for r in msg['x-mp-internal-rcpts'].split(',')],
                msg,
                events)

    crypto_policy = 'default'
    crypto_format = 'default'

    rcpts = rcpts or []
    if bounce:
        safe_assert(len(rcpts) > 0)

    # Iterate through headers to figure out what we want to do...
    need_rcpts = not rcpts
    for hdr, val in msg.items():
        lhdr = hdr.lower()
        if lhdr == 'from':
            sender = sender or val
        elif lhdr == 'encryption':
            crypto_policy = val
        elif need_rcpts and lhdr in ('to', 'cc', 'bcc'):
            rcpts += AddressHeaderParser(val).addresses_list(with_keys=True)

    # Are we sane?
    if not sender:
        raise NoFromAddressError()
    if not rcpts:
        raise NoRecipientError()

    # Are we encrypting? Signing?
    crypto_policy = crypto_policy.lower()
    if crypto_policy == 'default':
        crypto_policy = config.prefs.crypto_policy.lower()

    sender = AddressHeaderParser(sender)[0].address

    # FIXME: Shouldn't this be using config.get_profile instead?
    profile = config.vcards.get_vcard(sender)
    if profile:
        crypto_format = (profile.crypto_format or crypto_format).lower()
    if crypto_format == 'default':
        crypto_format = 'prefer_inline' if config.prefs.inline_pgp else ''

    # Extract just the e-mail addresses from the RCPT list, make unique
    rcpts, rr = [], rcpts
    for r in rr:
        for e in AddressHeaderParser(r).addresses_list(with_keys=True):
            if e not in rcpts:
                rcpts.append(e)

    # Bouncing disables all transformations, including crypto.
    if not bounce:
        # This is the BCC hack that Brennan hates!
        if config.prefs.always_bcc_self and sender not in rcpts:
            rcpts += [sender]

        # Add headers we require
        while 'date' in msg:
            del msg['date']
        msg['Date'] = MakeMessageDate()

        import mailpile.plugins
        plugins = mailpile.plugins.PluginManager()

        # Perform pluggable content transformations
        sender, rcpts, msg, junk = plugins.outgoing_email_content_transform(
            config, sender, rcpts, msg)

        # Perform pluggable encryption transformations
        sender, rcpts, msg, matched = plugins.outgoing_email_crypto_transform(
            config, sender, rcpts, msg,
            crypto_policy=crypto_policy,
            crypto_format=crypto_format,
            cleaner=lambda m: CleanMessage(config, m))

        if crypto_policy and (crypto_policy != 'none') and not matched:
            raise ValueError(_('Unknown crypto policy: %s') % crypto_policy)

    rcpts = set([r.rsplit('#', 1)[0] for r in rcpts])
    msg['x-mp-internal-readonly'] = str(int(time.time()))
    msg['x-mp-internal-sender'] = sender
    msg['x-mp-internal-rcpts'] = ', '.join(rcpts)
    return (sender, rcpts, msg, events)


class Email(object):
    """This is a lazy-loading object representing a single email."""

    def __init__(self, idx, msg_idx_pos,
                 msg_parsed=None, msg_parsed_pgpmime=(None, None),
                 msg_info=None, ephemeral_mid=None):
        self.index = idx
        self.config = idx.config
        self.msg_idx_pos = msg_idx_pos
        self.ephemeral_mid = ephemeral_mid
        self.reset_caches(msg_parsed=msg_parsed,
                          msg_parsed_pgpmime=msg_parsed_pgpmime,
                          msg_info=msg_info,
                          clear_parse_cache=False)

    def msg_mid(self):
        return self.ephemeral_mid or b36(self.msg_idx_pos)

    @classmethod
    def encoded_hdr(self, msg, hdr, value=None):
        hdr_value = value or (msg and msg.get(hdr)) or ''
        try:
            hdr_value.encode('us-ascii')
        except (UnicodeEncodeError, UnicodeDecodeError):
            if hdr.lower() in ('from', 'to', 'cc', 'bcc'):
                addrs = []
                for addr in [a.strip() for a in hdr_value.split(',')]:
                    name, part = [], []
                    words = addr.split()
                    for w in words:
                        if w[0] == '<' or '@' in w:
                            part.append((w, 'us-ascii'))
                        else:
                            name.append(w)
                    if name:
                        name = ' '.join(name)
                        try:
                            part[0:0] = [(name.encode('us-ascii'), 'us-ascii')]
                        except:
                            part[0:0] = [(name, 'utf-8')]
                        addrs.append(email.header.make_header(part).encode())
                hdr_value = ', '.join(addrs)
            else:
                parts = [(hdr_value, 'utf-8')]
                hdr_value = email.header.make_header(parts).encode()
        return hdr_value

    @classmethod
    def Create(cls, idx, mbox_id, mbx,
               msg_to=None, msg_cc=None, msg_bcc=None, msg_from=None,
               msg_subject=None, msg_text='', msg_references=None,
               msg_id=None, msg_atts=None, msg_headers=None,
               save=True, ephemeral_mid='not-saved', append_sig=True,
               use_default_from=True):
        msg = MIMEMultipart(boundary=MakeBoundary())
        msg.signature_info = msi = SignatureInfo(bubbly=False)
        msg.encryption_info = mei = EncryptionInfo(bubbly=False)
        msg_ts = int(time.time())

        if msg_from:
            from_email = AddressHeaderParser(unicode_data=msg_from)[0].address
            from_profile = idx.config.get_profile(email=from_email)
        elif use_default_from:
            from_profile = idx.config.get_profile()
            from_email = from_profile.get('email', None)
            from_name = from_profile.get('name', None)
            if from_email and from_name:
                msg_from = '%s <%s>' % (from_name, from_email)
        else:
            from_email = from_profile = from_name = None

        if msg_from:
            msg['From'] = cls.encoded_hdr(None, 'from', value=msg_from)

        msg['Date'] = MakeMessageDate(msg_ts)
        msg['Message-Id'] = msg_id or MakeMessageID()
        msg_subj = (msg_subject or '')
        msg['Subject'] = cls.encoded_hdr(None, 'subject', value=msg_subj)

        # Privacy trade-off: we want to help recipients do profiling and
        # discard poorly forged messages that are not from from Mailpile.
        # However, we don't want to leak too many details for privacy and
        # security reasons. So no: version or platform info, just the word
        # Mailpile. This will probably be obvious to a truly hostile
        # adversary anyway from other details.
        msg['User-Agent'] = 'Mailpile'

        ahp = AddressHeaderParser()
        norm = lambda a: ', '.join(sorted(list(set(ahp.normalized_addresses(
            addresses=a, with_keys=True, force_name=True)))))
        if msg_to:
            msg['To'] = cls.encoded_hdr(None, 'to', value=norm(msg_to))
        if msg_cc:
            msg['Cc'] = cls.encoded_hdr(None, 'cc', value=norm(msg_cc))
        if msg_bcc:
            msg['Bcc'] = cls.encoded_hdr(None, 'bcc', value=norm(msg_bcc))
        if msg_references:
            msg['In-Reply-To'] = msg_references[-1]
            msg['References'] = ', '.join(msg_references)

        if msg_text:
            try:
                msg_text.encode('us-ascii')
                charset = 'us-ascii'
            except (UnicodeEncodeError, UnicodeDecodeError):
                charset = 'utf-8'
            tp = MIMEText(msg_text, _subtype='plain', _charset=charset)
            tp.signature_info = SignatureInfo(parent=msi)
            tp.encryption_info = EncryptionInfo(parent=mei)
            msg.attach(tp)
            del tp['MIME-Version']

        for k, v in (msg_headers or []):
            msg[k] = v

        if msg_atts:
            for att in msg_atts:
                att = copy.deepcopy(att)
                att.signature_info = SignatureInfo(parent=msi)
                att.encryption_info = EncryptionInfo(parent=mei)
# Disabled for now.
#               if att.get('content-id') is None:
#                   att.add_header('Content-Id', MakeContentID())
                msg.attach(att)
                del att['MIME-Version']

        # Determine if we want to attach a PGP public key due to policy and
        # timing...
        if (idx.config.prefs.gpg_email_key and
                from_profile and
                'send_keys' in from_profile.get('crypto_format', 'none')):
            from mailpile.plugins.crypto_policy import CryptoPolicy
            addrs = ExtractEmails(norm(msg_to) + norm(msg_cc) + norm(msg_bcc))
            if CryptoPolicy.ShouldAttachKey(idx.config, emails=addrs):
                msg["Attach-PGP-Pubkey"] = "Yes"

        if save:
            msg_key = mbx.add(MessageAsString(msg))
            msg_to = msg_cc = []
            msg_ptr = mbx.get_msg_ptr(mbox_id, msg_key)
            msg_id = idx.get_msg_id(msg, msg_ptr)
            msg_idx, msg_info = idx.add_new_msg(msg_ptr, msg_id, msg_ts,
                                                msg_from, msg_to, msg_cc, 0,
                                                msg_subj, '', [])
            idx.set_conversation_ids(msg_info[idx.MSG_MID], msg,
                                     subject_threading=False)
            return cls(idx, msg_idx)
        else:
            msg_info = idx.edit_msg_info(idx.BOGUS_METADATA[:],
                                         msg_mid=ephemeral_mid or '',
                                         msg_id=msg['Message-ID'],
                                         msg_ts=msg_ts,
                                         msg_subject=msg_subj,
                                         msg_from=msg_from,
                                         msg_to=msg_to,
                                         msg_cc=msg_cc)
            return cls(idx, -1,
                       msg_info=msg_info,
                       msg_parsed=msg,
                       msg_parsed_pgpmime=('basic', msg),
                       ephemeral_mid=ephemeral_mid)

    def is_editable(self, quick=False):
        if self.ephemeral_mid:
            return True
        if not self.config.is_editable_message(self.get_msg_info()):
            return False
        if quick:
            return True
        return ('x-mp-internal-readonly' not in self.get_msg(pgpmime=False))

    MIME_HEADERS = ('mime-version', 'content-type', 'content-disposition',
                    'content-transfer-encoding')
    UNEDITABLE_HEADERS = ('message-id', ) + MIME_HEADERS
    MANDATORY_HEADERS = ('From', 'To', 'Cc', 'Bcc', 'Subject',
                         'Encryption', 'Attach-PGP-Pubkey')
    ADDRESS_HEADERS = ('From', 'To', 'Cc', 'Bcc', 'Reply-To')
    HEADER_ORDER = {
        'in-reply-to': -2,
        'references': -1,
        'date': 1,
        'from': 2,
        'subject': 3,
        'to': 4,
        'cc': 5,
        'bcc': 6,
        'encryption': 98,
        'attach-pgp-pubkey': 99,
    }

    def _attachment_aid(self, att):
        aid = att.get('aid')
        if not aid:
            cid = att.get('content-id')  # This comes from afar and might
                                         # be malicious, so check it.
            if (cid and
                    cid == CleanText(cid, banned=(CleanText.WHITESPACE +
                                                  CleanText.FS)).clean):
                aid = cid
            else:
                aid = 'part-%s' % att['count']
        return aid

    def get_editing_strings(self, tree=None, build_tree=True):
        if build_tree:
            tree = self.get_message_tree(want=['editing_strings'], tree=tree)

        strings = {
            'from': '', 'to': '', 'cc': '', 'bcc': '', 'subject': '',
            'encryption': '', 'attach-pgp-pubkey': '', 'attachments': {}
        }
        header_lines = []
        body_lines = []

        # We care about header order and such things...
        hdrs = dict([(h.lower(), h) for h in tree['headers'].keys()
                     if h.lower() not in self.UNEDITABLE_HEADERS])
        for mandate in self.MANDATORY_HEADERS:
            hdrs[mandate.lower()] = hdrs.get(mandate.lower(), mandate)
        keys = hdrs.keys()
        keys.sort(key=lambda k: (self.HEADER_ORDER.get(k.lower(), 99), k))
        lowman = [m.lower() for m in self.MANDATORY_HEADERS]
        lowadr = [m.lower() for m in self.ADDRESS_HEADERS]
        for hdr in [hdrs[k] for k in keys]:
            data = tree['headers'].get(hdr, '')
            lhdr = hdr.lower()
            if lhdr in lowadr and lhdr in lowman:
                adata = tree.get('addresses', {}).get(lhdr, None)
                if adata is None:
                    adata = AddressHeaderParser(data)
                strings[lhdr] = adata.normalized()
            elif lhdr in lowman:
                strings[lhdr] = unicode(data)
            else:
                header_lines.append(unicode('%s: %s' % (hdr, data)))

        for att in tree['attachments']:
            aid = self._attachment_aid(att)
            strings['attachments'][aid] = (att['filename'] or '(unnamed)')

        if not strings['encryption']:
            strings['encryption'] = unicode(self.config.prefs.crypto_policy)

        def _fixup(t):
            try:
                return unicode(t)
            except UnicodeDecodeError:
                return t.decode('utf-8')

        strings['headers'] = '\n'.join(header_lines).replace('\r\n', '\n')
        strings['body'] = unicode(''.join([_fixup(t['data'])
                                           for t in tree['text_parts']])
                                  ).replace('\r\n', '\n')

        return strings

    def get_editing_string(self, tree=None,
                                 estrings=None,
                                 attachment_headers=True,
                                 build_tree=True):
        if estrings is None:
            estrings = self.get_editing_strings(tree=tree,
                                                build_tree=build_tree)

        bits = [estrings['headers']] if estrings['headers'] else []
        for mh in self.MANDATORY_HEADERS:
            bits.append('%s: %s' % (mh, estrings[mh.lower()]))

        if attachment_headers:
            for aid in sorted(estrings['attachments'].keys()):
                bits.append('Attachment-%s: %s'
                            % (aid, estrings['attachments'][aid]))
        bits.append('')
        bits.append(estrings['body'])
        return '\n'.join(bits)

    def _update_att_name(self, part, filename):
        try:
            del part['Content-Disposition']
        except KeyError:
            pass
        part.add_header('Content-Disposition', 'attachment',
                        filename=filename)
        return part

    def _make_attachment(self, fn, msg, filedata=None):
        if filedata and fn in filedata:
            data = filedata[fn]
        else:
            if isinstance(fn, unicode):
                fn = fn.encode('utf-8')
            data = open(fn, 'rb').read()
        ctype, encoding = mimetypes.guess_type(fn)
        maintype, subtype = (ctype or 'application/octet-stream').split('/', 1)
        if maintype == 'image':
            att = MIMEImage(data, _subtype=subtype)
        else:
            att = MIMEBase(maintype, subtype)
            att.set_payload(data)
            encoders.encode_base64(att)
# Disabled for now.
#       att.add_header('Content-Id', MakeContentID())

        # FS paths are strings of bytes, should be represented as utf-8 for
        # correct header encoding.
        base_fn = os.path.basename(fn)
        if not isinstance(base_fn, unicode):
            base_fn = base_fn.decode('utf-8')

        att.add_header('Content-Disposition', 'attachment',
                       filename=self.encoded_hdr(None, 'file', base_fn))

        att.signature_info = SignatureInfo(parent=msg.signature_info)
        att.encryption_info = EncryptionInfo(parent=msg.encryption_info)
        return att

    def update_from_string(self, session, data, final=False):
        if not self.is_editable():
            raise NotEditableError(_('Message or mailbox is read-only.'))

        oldmsg = self.get_msg()
        if not data:
            outmsg = oldmsg

        else:
            newmsg = email.parser.Parser().parsestr(data.encode('utf-8'))
            outmsg = MIMEMultipart(boundary=MakeBoundary())
            outmsg.signature_info = SignatureInfo(bubbly=False)
            outmsg.encryption_info = EncryptionInfo(bubbly=False)

            # Copy over editable headers from the input string, skipping blanks
            for hdr in newmsg.keys():
                if hdr.startswith('Attachment-') or hdr == 'Attachment':
                    pass
                else:
                    encoded_hdr = self.encoded_hdr(newmsg, hdr)
                    if len(encoded_hdr.strip()) > 0:
                        if encoded_hdr == '!KEEP':
                            if hdr in oldmsg:
                                outmsg[hdr] = oldmsg[hdr]
                        else:
                            outmsg[hdr] = encoded_hdr

            # Copy over the uneditable headers from the old message
            for hdr in oldmsg.keys():
                if ((hdr.lower() not in self.MIME_HEADERS)
                        and (hdr.lower() in self.UNEDITABLE_HEADERS)):
                    outmsg[hdr] = oldmsg[hdr]

            # Copy the message text
            new_body = newmsg.get_payload().decode('utf-8')
            target_width = self.config.prefs.line_length
            if target_width >= 40 and 'x-mp-internal-no-reflow' not in newmsg:
                new_body = reflow_text(new_body, target_width=target_width)
            try:
                new_body.encode('us-ascii')
                charset = 'us-ascii'
            except (UnicodeEncodeError, UnicodeDecodeError):
                charset = 'utf-8'

            tp = MIMEText(new_body, _subtype='plain', _charset=charset)
            tp.signature_info = SignatureInfo(parent=outmsg.signature_info)
            tp.encryption_info = EncryptionInfo(parent=outmsg.encryption_info)
            outmsg.attach(tp)
            del tp['MIME-Version']

            # FIXME: Use markdown and template to generate fancy HTML part?

            # Copy the attachments we are keeping
            attachments = [h for h in newmsg.keys()
                           if h.lower().startswith('attachment')]
            if attachments:
                oldtree = self.get_message_tree(want=['attachments'])
                for att in oldtree['attachments']:
                    hdr = 'Attachment-%s' % self._attachment_aid(att)
                    if hdr in attachments:
                        outmsg.attach(self._update_att_name(att['part'],
                                                            newmsg[hdr]))
                        attachments.remove(hdr)

            # Attach some new files?
            for hdr in attachments:
                try:
                    att = self._make_attachment(newmsg[hdr], outmsg)
                    outmsg.attach(att)
                    del att['MIME-Version']
                except:
                    pass  # FIXME: Warn user that failed...

        # Save result back to mailbox
        if final:
            sender, rcpts, outmsg, ev = PrepareMessage(self.config, outmsg)
        return self.update_from_msg(session, outmsg)

    def update_from_msg(self, session, newmsg):
        if not self.is_editable():
            raise NotEditableError(_('Message or mailbox is read-only.'))

        if self.ephemeral_mid:
            self.reset_caches(clear_parse_cache=False,
                              msg_parsed=newmsg,
                              msg_parsed_pgpmime=('basic', newmsg),
                              msg_info=self.msg_info)

        else:
            mbx, ptr, fd = self.get_mbox_ptr_and_fd()
            fd.close()  # Windows needs this

            # OK, adding to the mailbox worked
            newptr = ptr[:MBX_ID_LEN] + mbx.add(MessageAsString(newmsg))
            self.update_parse_cache(newmsg)

            # Remove the old message...
            mbx.remove_by_ptr(ptr)

            # FIXME: We should DELETE the old version from the index first.

            # Update the in-memory-index
            mi = self.get_msg_info()
            mi[self.index.MSG_PTRS] = newptr
            self.index.set_msg_at_idx_pos(self.msg_idx_pos, mi)
            self.index.index_email(session, Email(self.index, self.msg_idx_pos))
            self.reset_caches(clear_parse_cache=False)

        return self

    def reset_caches(self,
                     msg_info=None,
                     msg_parsed=None, msg_parsed_pgpmime=(None, None),
                     clear_parse_cache=True):
        self.msg_info = msg_info
        self.msg_parsed = msg_parsed
        self.msg_parsed_pgpmime = msg_parsed_pgpmime
        if clear_parse_cache:
            self.clear_from_parse_cache()

    def update_parse_cache(self, newmsg):
        cache_id = self.get_cache_id()
        if cache_id:
            with GLOBAL_PARSE_CACHE_LOCK:
                GPC = GLOBAL_PARSE_CACHE
                for i in range(0, len(GPC)):
                    if GPC[i][0] == cache_id:
                        GPC[i] = (cache_id, False, newmsg)

    def clear_from_parse_cache(self):
        cache_id = self.get_cache_id()
        if cache_id:
            ClearParseCache(cache_id=cache_id)

    def delete_message(self, session, flush=True, keep=0):
        mi = self.get_msg_info()
        removed, failed, mailboxes = [], [], []
        kept = keep
        allow_deletion = session.config.prefs.allow_deletion
        for msg_ptr, mbox, fd in self.index.enumerate_ptrs_mboxes_fds(mi):
            try:
                if mbox:
                    try:
                        if keep > 0:
                            # Note: This will keep messages in the order of
                            # preference implemented by enumerate_ptrs_...
                            # FIXME: Allow more nuanced behaviour here.
                            mbox.get_file_by_ptr(msg_ptr)
                            keep -= 1
                        elif allow_deletion:
                            mbox.remove_by_ptr(msg_ptr)
                        else:
                            # FIXME: Allow deletion of local copies ONLY
                            raise ValueError("Deletion is forbidden")
                    except (KeyError, IndexError):
                        # Already gone!
                        pass
                    mailboxes.append(mbox)
                    removed.append(msg_ptr)
            except (IOError, OSError, ValueError, AttributeError) as e:
                failed.append(msg_ptr)
                print 'FIXME: Could not delete %s: %s' % (msg_ptr, e)

        if allow_deletion and not failed and not kept:
            self.index.delete_msg_at_idx_pos(session, self.msg_idx_pos,
                                             keep_msgid=False)
        if flush:
            for m in mailboxes:
                m.flush()
            return (not failed, [])
        else:
            return (not failed, mailboxes)

    def get_msg_info(self, field=None, uncached=False):
        if (uncached or not self.msg_info) and not self.ephemeral_mid:
            self.msg_info = self.index.get_msg_at_idx_pos(self.msg_idx_pos)
        if field is None:
            return self.msg_info
        else:
            return self.msg_info[field]

    def get_mbox_ptr_and_fd(self):
        mi = self.get_msg_info()
        for msg_ptr, mbox, fd in self.index.enumerate_ptrs_mboxes_fds(mi):
            if fd is not None:
                # FIXME: How do we know we have the right message?
                return mbox, msg_ptr, FixupForWith(fd)
        return None, None, None

    def get_file(self):
        return self.get_mbox_ptr_and_fd()[2]

    def get_msg_size(self):
        mbox, ptr, fd = self.get_mbox_ptr_and_fd()
        with fd:
            fd.seek(0, 2)
            return fd.tell()

    def get_metadata_kws(self):
        # FIXME: Track these somehow...
        return []

    def get_cache_id(self):
        if (self.msg_idx_pos >= 0) and not self.ephemeral_mid:
            return '%s/%s' % (self.index, self.msg_idx_pos)
        else:
            return None

    def _get_parsed_msg(self, pgpmime, update_cache=False):
        weak_crypto_max_age = self.config.prefs.weak_crypto_max_age
        allow_weak_crypto = False
        if weak_crypto_max_age > 0:
            ts = int(self.get_msg_info(self.index.MSG_DATE) or '0', 36)
            allow_weak_crypto = (ts < weak_crypto_max_age)
        return ParseMessage(self.get_file,
            cache_id=self.get_cache_id(),
            update_cache=update_cache,
            pgpmime=pgpmime,
            config=self.config,
            allow_weak_crypto=allow_weak_crypto,
            event=GetThreadEvent())

    def _update_crypto_state(self):
        if not (self.config.tags and
                self.msg_idx_pos >= 0 and
                self.msg_parsed_pgpmime[0] and
                self.msg_parsed_pgpmime[1] and
                not self.ephemeral_mid):
            return

        import mailpile.plugins.cryptostate as cs
        kw = cs.meta_kw_extractor(self.index,
                                  self.msg_mid(),
                                  self.msg_parsed_pgpmime[1],
                                  0, 0)  # msg_size, msg_ts

        # We do NOT want to update tags if we are getting back
        # a none/none state, as that can happen for the more
        # complex nested crypto-in-text messages, which a more
        # forceful parse of the message may have caught earlier.
        no_sig = self.config.get_tag('mp_sig-none')
        no_sig = no_sig and '%s:in' % no_sig._key
        no_enc = self.config.get_tag('mp_enc-none')
        no_enc = no_enc and '%s:in' % no_enc._key
        if no_sig not in kw or no_enc not in kw:
            msg_info = self.get_msg_info()
            msg_tags = msg_info[self.index.MSG_TAGS].split(',')
            msg_tags = sorted([t for t in msg_tags if t])

            # Note: this has the side effect of cleaning junk off
            #       the tag list, not just updating crypto state.
            def tcheck(tag_id):
                tag = self.config.get_tag(tag_id)
                return (tag and tag.slug[:6] not in ('mp_enc', 'mp_sig'))
            new_tags = sorted([t for t in msg_tags if tcheck(t)] +
                              [ti.split(':', 1)[0] for ti in kw
                               if ti.endswith(':in')])

            if msg_tags != new_tags:
                msg_info[self.index.MSG_TAGS] = ','.join(new_tags)
                self.index.set_msg_at_idx_pos(self.msg_idx_pos, msg_info)

    def get_msg(self, pgpmime='default', crypto_state_feedback=True):
        if pgpmime:
            if pgpmime == 'default':
                pgpmime = 'basic' if self.is_editable() else 'all'

            if self.msg_parsed_pgpmime[0] == pgpmime:
                result = self.msg_parsed_pgpmime[1]
            else:
                result = self._get_parsed_msg(pgpmime)
                self.msg_parsed_pgpmime = (pgpmime, result)

                # Post-parse, we want to make sure that the crypto-state
                # recorded on this message's metadata is up to date.
                if crypto_state_feedback:
                    self._update_crypto_state()
        else:
            if not self.msg_parsed:
                self.msg_parsed = self._get_parsed_msg(pgpmime)
            result = self.msg_parsed
        if not result:
            raise IndexError(_('Message not found'))
        return result

    def is_thread(self):
        return ((self.get_msg_info(self.index.MSG_THREAD_MID)) or
                (0 < len(self.get_msg_info(self.index.MSG_REPLIES))))

    def get(self, field, default=''):
        """Get one (or all) indexed fields for this mail."""
        field = field.lower()
        if field == 'subject':
            return self.get_msg_info(self.index.MSG_SUBJECT)
        elif field == 'from':
            return self.get_msg_info(self.index.MSG_FROM)
        else:
            raw = ' '.join(self.get_msg(pgpmime=False).get_all(field, default))
            return safe_decode_hdr(hdr=raw) or raw

    def get_sender(self):
        try:
            ahp = AddressHeaderParser(unicode_data=self.get('from'))
            return ahp[0].address
        except IndexError:
            return None

    def get_headerprints(self):
        return HeaderPrints(self.get_msg(pgpmime='basic'))

    def get_msg_summary(self):
        # We do this first to make sure self.msg_info is loaded
        msg_mid = self.get_msg_info(self.index.MSG_MID)
        return [
            msg_mid,
            self.get_msg_info(self.index.MSG_ID),
            self.get_msg_info(self.index.MSG_FROM),
            self.index.expand_to_list(self.msg_info),
            self.get_msg_info(self.index.MSG_SUBJECT),
            self.get_msg_info(self.index.MSG_BODY),
            self.get_msg_info(self.index.MSG_DATE),
            self.get_msg_info(self.index.MSG_TAGS).split(','),
            self.is_editable(quick=True)
        ]

    def _find_attachments(self, att_id, negative=False):
        msg = self.get_msg()
        count = 0
        for part in (msg.walk() if msg else []):
            mimetype = (part.get_content_type() or 'text/plain').lower()
            if mimetype.startswith('multipart/'):
                continue

            count += 1
            content_id = part.get('content-id', '')
            pfn = safe_decode_hdr(hdr=part.get_filename() or '')

            if (('*' == att_id)
                    or ('#%s' % count == att_id)
                    or ('part-%s' % count == att_id)
                    or (content_id == att_id)
                    or (mimetype == att_id)
                    or (pfn.lower().endswith('.%s' % att_id))
                    or (pfn == att_id)):
                if not negative:
                    yield (count, content_id, pfn, mimetype, part)
            elif negative:
                yield (count, content_id, pfn, mimetype, part)

    def add_attachments(self, session, filenames, filedata=None):
        if not self.is_editable():
            raise NotEditableError(_('Message or mailbox is read-only.'))
        msg = self.get_msg()
        for fn in filenames:
            att = self._make_attachment(fn, msg, filedata=filedata)
            msg.attach(att)
            del att['MIME-Version']
        return self.update_from_msg(session, msg)

    def remove_attachments(self, session, *att_ids):
        if not self.is_editable():
            raise NotEditableError(_('Message or mailbox is read-only.'))

        remove = []
        for att_id in att_ids:
            for count, cid, pfn, mt, part in self._find_attachments(att_id):
                remove.append(self._attachment_aid({
                    'msg_mid': self.msg_mid(),
                    'count': count,
                    'content-id': cid,
                    'filename': pfn,
                }))

        es = self.get_editing_strings()
        es['headers'] = None
        for k in remove:
            if k in es['attachments']:
                del es['attachments'][k]

        estring = self.get_editing_string(estrings=es)
        return self.update_from_string(session, estring)

    def extract_attachment(self, session, att_id, name_fmt=None, mode='get'):
        extracted = 0
        filename, attributes = '', {}
        for (count, content_id, pfn, mimetype, part
                ) in self._find_attachments(att_id):
            payload = part.get_payload(None, True) or ''
            attributes = {
                'msg_mid': self.msg_mid(),
                'count': count,
                'length': len(payload),
                'content-id': content_id,
                'filename': pfn,
            }
            attributes['aid'] = self._attachment_aid(attributes)
            if pfn:
                if '.' in pfn:
                    pfn, attributes['att_ext'] = pfn.rsplit('.', 1)
                    attributes['att_ext'] = attributes['att_ext'].lower()
                attributes['att_name'] = pfn
            if mimetype:
                attributes['mimetype'] = mimetype

            filesize = len(payload)
            if mode.startswith('inline'):
                attributes['data'] = payload
                session.ui.notify(_('Extracted attachment %s') % att_id)
            elif mode.startswith('preview'):
                attributes['thumb'] = True
                attributes['mimetype'] = 'image/jpeg'
                attributes['disposition'] = 'inline'
                thumb = StringIO.StringIO()
                if thumbnail(payload, thumb, height=250):
                    attributes['length'] = thumb.tell()
                    filename, fd = session.ui.open_for_data(
                        name_fmt=name_fmt, attributes=attributes)
                    thumb.seek(0)
                    fd.write(thumb.read())
                    fd.close()
                    session.ui.notify(_('Wrote preview to: %s') % filename)
                else:
                    session.ui.notify(_('Failed to generate thumbnail'))
                    raise UrlRedirectException('/static/img/image-default.png')
            else:
                WHITELIST = ('image/png',
                             'image/gif',
                             'image/jpeg',
                             'image/tiff',
                             'audio/mp3',
                             'audio/ogg',
                             'audio/x-wav',
                             'audio/mpeg',
                             'video/mpeg',
                             'video/ogg',
                             'application/pdf')
                if mode.startswith('get') and mimetype in WHITELIST:
                    # This allows the browser to (optionally) handle the
                    # content, instead of always forcing a download dialog.
                    attributes['disposition'] = 'inline'
                filename, fd = session.ui.open_for_data(
                    name_fmt=name_fmt, attributes=attributes)
                fd.write(payload)
                session.ui.notify(_('Wrote attachment to: %s') % filename)
                fd.close()
            extracted += 1

        if 0 == extracted:
            session.ui.notify(_('No attachments found for: %s') % att_id)
            return None, None
        else:
            return filename, attributes

    def get_message_tags(self):
        tids = self.get_msg_info(self.index.MSG_TAGS).split(',')
        return [self.config.get_tag(t) for t in tids]

    def get_message_tree(self, want=None, tree=None, pgpmime='default'):
        msg = self.get_msg(pgpmime=pgpmime)
        want = list(want) if (want is not None) else None
        tree = tree or {'_cleaned': []}
        tree['id'] = self.get_msg_info(self.index.MSG_ID)

        if want is not None:
            if 'editing_strings' in want or 'editing_string' in want:
                want.extend(['text_parts', 'headers', 'attachments',
                             'addresses'])

        for p in 'text_parts', 'html_parts', 'attachments':
            if want is None or p in want:
                tree[p] = []

        if (want is None or 'summary' in want) and 'summary' not in tree:
            tree['summary'] = self.get_msg_summary()

        if (want is None or 'tags' in want) and 'tags' not in tree:
            tree['tags'] = self.get_msg_info(self.index.MSG_TAGS).split(',')

        if (want is None or 'conversation' in want
                ) and 'conversation' not in tree:
            tree['conversation'] = {}
            conv_id = self.get_msg_info(self.index.MSG_THREAD_MID)
            if conv_id:
                conv_id = conv_id.split('/')[0]
                conv = Email(self.index, int(conv_id, 36))
                tree['conversation'] = convs = [conv.get_msg_summary()]
                for rid in conv.get_msg_info(self.index.MSG_REPLIES
                                             ).split(','):
                    if rid:
                        convs.append(Email(self.index, int(rid, 36)
                                           ).get_msg_summary())

        if (want is None or 'headerprints' in want):
            tree['headerprints'] = self.get_headerprints()

        if (want is None or 'headers' in want) and 'headers' not in tree:
            tree['headers'] = {}
            for hdr in msg.keys():
                tree['headers'][hdr] = safe_decode_hdr(msg, hdr)

        if (want is None or 'headers_lc' in want
                ) and 'headers_lc' not in tree:
            tree['headers_lc'] = {}
            for hdr in msg.keys():
                tree['headers_lc'][hdr.lower()] = safe_decode_hdr(msg, hdr)

        if (want is None or 'header_list' in want
                ) and 'header_list' not in tree:
            tree['header_list'] = [(k, safe_decode_hdr(msg, k, hdr=v))
                                   for k, v in msg.items()]

        if (want is None or 'addresses' in want
                ) and 'addresses' not in tree:
            address_headers_lower = [h.lower() for h in self.ADDRESS_HEADERS]
            tree['addresses'] = {}
            for hdr in msg.keys():
                hdrl = hdr.lower()
                if hdrl in address_headers_lower:
                    tree['addresses'][hdrl] = AddressHeaderParser(msg[hdr])

        # Note: count algorithm must match that used in extract_attachment
        #       above
        count = 0
        for part in msg.walk():
            crypto = {
                'signature': part.signature_info,
                'encryption': part.encryption_info,
            }

            mimetype = (part.get_content_type() or 'text/plain').lower()
            if (mimetype.startswith('multipart/')
                    or mimetype == "application/pgp-encrypted"):
                continue
            try:
                if (mimetype == "application/octet-stream"
                        and part.cryptedcontainer is True):
                    continue
            except:
                pass

            count += 1
            disposition = part.get('content-disposition', 'inline').lower()
            if (disposition[:6] == 'inline'
                    and mimetype.startswith('text/')):
                payload, charset = self.decode_payload(part)
                start = payload[:100].strip()

                if mimetype == 'text/html':
                    if want is None or 'html_parts' in want:
                        tree['html_parts'].append({
                            'charset': charset,
                            'type': 'html',
                            'data': clean_html(payload)
                        })

                elif want is None or 'text_parts' in want:
                    if start[:3] in ('<di', '<ht', '<p>', '<p ', '<ta', '<bo'):
                        payload = extract_text_from_html(payload)
                    # Ignore white-space only text parts, they usually mean
                    # the message is HTML only and we want the code below
                    # to try and extract meaning from it.
                    if (start or payload.strip()) != '':
                        text_parts = self.parse_text_part(payload, charset,
                                                          crypto)
                        tree['text_parts'].extend(text_parts)

            elif want is None or 'attachments' in want:
                filename_org = safe_decode_hdr(hdr=part.get_filename() or '')
                filename = CleanText(filename_org,
                                     banned=(CleanText.HTML +
                                             CleanText.CRLF + '\\/'),
                                     replace='_').clean
                att = {
                    'mimetype': mimetype,
                    'count': count,
                    'part': part,
                    'length': len(part.get_payload(None, True) or ''),
                    'content-id': part.get('content-id', ''),
                    'filename': filename,
                    'crypto': crypto
                }
                att['aid'] = self._attachment_aid(att)
                tree['attachments'].append(att)
                if filename_org != filename:
                    tree['_cleaned'].append('att: %s' % att['aid'])

        if want is None or 'text_parts' in want:
            if tree.get('html_parts') and not tree.get('text_parts'):
                html_part = tree['html_parts'][0]
                payload = extract_text_from_html(html_part['data'])
                text_parts = self.parse_text_part(payload,
                                                  html_part['charset'],
                                                  crypto)
                tree['text_parts'].extend(text_parts)

        if self.is_editable():
            if not want or 'editing_strings' in want:
                tree['editing_strings'] = self.get_editing_strings(
                    tree, build_tree=False)
            if not want or 'editing_string' in want:
                tree['editing_string'] = self.get_editing_string(
                    tree, build_tree=False)

        if want is None or 'crypto' in want:
            if 'crypto' not in tree:
                tree['crypto'] = {'encryption': msg.encryption_info,
                                  'signature': msg.signature_info}
            else:
                tree['crypto']['encryption'] = msg.encryption_info
                tree['crypto']['signature'] = msg.signature_info

        msg.signature_info.mix_bubbles()
        msg.encryption_info.mix_bubbles()
        return tree

    # FIXME: This should be configurable by the user, depending on where
    #        he lives and what kind of e-mail he gets.
    CHARSET_PRIORITY_LIST = ['utf-8', 'iso-8859-1']

    def decode_text(self, payload, charset='utf-8', binary=True):
        if charset:
            charsets = [charset] + [c for c in self.CHARSET_PRIORITY_LIST
                                    if charset.lower() != c]
        else:
            charsets = self.CHARSET_PRIORITY_LIST

        for charset in charsets:
            try:
                payload = payload.decode(charset)
                return payload, charset
            except (UnicodeDecodeError, TypeError, LookupError):
                pass

        if binary:
            return payload, '8bit'
        else:
            return _('[Binary data suppressed]\n'), 'utf-8'

    def decode_payload(self, part):
        charset = part.get_content_charset() or None
        return self.decode_text(GetTextPayload(part), charset=charset)

    def parse_text_part(self, data, charset, crypto):
        psi = crypto['signature']
        pei = crypto['encryption']
        current = {
            'type': 'bogus',
            'charset': charset,
            'crypto': {
                'signature': SignatureInfo(parent=psi),
                'encryption': EncryptionInfo(parent=pei)
            }
        }
        parse = []
        block = 'body'
        clines = []
        for line in data.splitlines(True):
            block, ltype = self.parse_line_type(line, block)
            if ltype != current['type']:

                # This is not great, it's a hack to move the preamble
                # before a quote section into the quote itself.
                if ltype == 'quote' and clines and '@' in clines[-1]:
                    current['data'] = ''.join(clines[:-1])
                    clines = clines[-1:]
                elif (ltype == 'quote' and len(clines) > 2
                        and '@' in clines[-2] and '' == clines[-1].strip()):
                    current['data'] = ''.join(clines[:-2])
                    clines = clines[-2:]
                else:
                    clines = []

                current = {
                    'type': ltype,
                    'data': ''.join(clines),
                    'charset': charset,
                    'crypto': {
                        'signature': SignatureInfo(parent=psi),
                        'encryption': EncryptionInfo(parent=pei)
                    }
                }
                parse.append(current)
            current['data'] += line
            clines.append(line)
        return parse

    BARE_QUOTE_STARTS = re.compile('(?i)^-+\s*Original Message.*-+$')
    GIT_DIFF_STARTS = re.compile('^diff --git a/.*b/')
    GIT_DIFF_LINE = re.compile('^([ +@-]|index |$)')

    def parse_line_type(self, line, block):
        # FIXME: Detect forwarded messages, ...

        if (block in ('body', 'quote', 'barequote')
                and line in ('-- \n', '-- \r\n', '- --\n', '- --\r\n')):
            return 'signature', 'signature'

        if block == 'signature':
            return block, block

        if block == 'barequote':
            return 'barequote', 'quote'

        stripped = line.rstrip()

        if stripped == GnuPG.ARMOR_BEGIN_SIGNED:
            return 'pgpbeginsigned', 'pgpbeginsigned'
        if block == 'pgpbeginsigned':
            if line.startswith('Hash: ') or stripped == '':
                return 'pgpbeginsigned', 'pgpbeginsigned'
            else:
                return 'pgpsignedtext', 'pgpsignedtext'
        if block == 'pgpsignedtext':
            if stripped == GnuPG.ARMOR_BEGIN_SIGNATURE:
                return 'pgpsignature', 'pgpsignature'
            else:
                return 'pgpsignedtext', 'pgpsignedtext'
        if block == 'pgpsignature':
            if stripped == GnuPG.ARMOR_END_SIGNATURE:
                return 'pgpend', 'pgpsignature'
            else:
                return 'pgpsignature', 'pgpsignature'

        if stripped == GnuPG.ARMOR_BEGIN_ENCRYPTED:
            return 'pgpbegin', 'pgpbegin'
        if block == 'pgpbegin':
            if ':' in line or stripped == '':
                return 'pgpbegin', 'pgpbegin'
            else:
                return 'pgptext', 'pgptext'
        if block == 'pgptext':
            if stripped == GnuPG.ARMOR_END_ENCRYPTED:
                return 'pgpend', 'pgpend'
            else:
                return 'pgptext', 'pgptext'

        if self.BARE_QUOTE_STARTS.match(stripped):
            return 'barequote', 'quote'

        if block == 'quote':
            if stripped == '':
                return 'quote', 'quote'
        if line.startswith('>'):
            return 'quote', 'quote'

        if self.GIT_DIFF_STARTS.match(stripped):
            return 'gitdiff', 'quote'

        if block == 'gitdiff':
            if self.GIT_DIFF_LINE.match(stripped):
                return 'gitdiff', 'quote'

        return 'body', 'text'

    WANT_MSG_TREE_PGP = ('text_parts', 'crypto')
    PGP_OK = {
        'pgpbeginsigned': 'pgpbeginverified',
        'pgpsignedtext': 'pgpverifiedtext',
        'pgpsignature': 'pgpverification',
        'pgpbegin': 'pgpbeginverified',
        'pgptext': 'pgpsecuretext',
        'pgpend': 'pgpverification',
    }

    def evaluate_pgp(self, tree, check_sigs=True, decrypt=False,
                                 crypto_state_feedback=True, event=None):
        if 'text_parts' not in tree:
            return tree

        pgpdata = []
        for part in tree['text_parts']:
            if 'crypto' not in part:
                part['crypto'] = {}

            ei = si = None
            if check_sigs:
                if part['type'] == 'pgpbeginsigned':
                    pgpdata = [part]
                elif part['type'] == 'pgpsignedtext':
                    pgpdata.append(part)
                elif part['type'] == 'pgpsignature':
                    pgpdata.append(part)
                    try:
                        gpg = GnuPG(self.config, event=event)
                        message = ''.join([p['data'].encode(p['charset'])
                                           for p in pgpdata])
                        si = gpg.verify(message)
                        pgpdata[0]['data'] = ''
                        pgpdata[1]['crypto']['signature'] = si
                        pgpdata[2]['data'] = ''

                    except Exception, e:
                        print e

            if decrypt:
                if part['type'] in ('pgpbegin', 'pgptext'):
                    pgpdata.append(part)
                elif part['type'] == 'pgpend':
                    pgpdata.append(part)

                    data = ''.join([p['data'] for p in pgpdata])
                    gpg = GnuPG(self.config, event=event)
                    si, ei, text = gpg.decrypt(data)

                    # FIXME: If the data is binary, we should provide some
                    #        sort of download link or maybe leave the PGP
                    #        blob entirely intact, undecoded.
                    text, charset = self.decode_text(text, binary=False)

                    pgpdata[1]['crypto']['encryption'] = ei
                    pgpdata[1]['crypto']['signature'] = si
                    if ei["status"] == "decrypted":
                        pgpdata[0]['data'] = ""
                        pgpdata[1]['data'] = text
                        pgpdata[2]['data'] = ""

            # Bubbling up!
            if (si or ei) and 'crypto' not in tree:
                tree['crypto'] = {'signature': SignatureInfo(bubbly=False),
                                  'encryption': EncryptionInfo(bubbly=False)}
            if si:
                si.bubble_up(tree['crypto']['signature'])
            if ei:
                ei.bubble_up(tree['crypto']['encryption'])

        # Cleanup, remove empty 'crypto': {} blocks.
        for part in tree['text_parts']:
            if not part['crypto']:
                del part['crypto']

        tree['crypto']['signature'].mix_bubbles()
        tree['crypto']['encryption'].mix_bubbles()
        if crypto_state_feedback:
            self._update_crypto_state()

        return tree

    def _decode_gpg(self, message, decrypted):
        header, body = message.replace('\r\n', '\n').split('\n\n', 1)
        for line in header.lower().split('\n'):
            if line.startswith('charset:'):
                return decrypted.decode(line.split()[1])
        return decrypted.decode('utf-8')


if __name__ == "__main__":
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
