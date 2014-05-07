import base64
import copy
import email.header
import email.parser
import email.utils
import errno
import lxml.html
import mailbox
import mimetypes
import os
import quopri
import re
import StringIO
import threading
import traceback
from gettext import gettext as _
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from lxml.html.clean import Cleaner
from mailpile.util import *
from platform import system
from urllib import quote, unquote

from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.gpgi import OpenPGPMimeSigningWrapper
from mailpile.crypto.gpgi import OpenPGPMimeEncryptingWrapper
from mailpile.crypto.mime import UnwrapMimeCrypto
from mailpile.crypto.state import EncryptionInfo, SignatureInfo
from mailpile.mail_generator import Generator
from mailpile.vcard import AddressInfo


MBX_ID_LEN = 4  # 4x36 == 1.6 million mailboxes


class NotEditableError(ValueError):
    pass


class NoFromAddressError(ValueError):
    pass


class NoRecipientError(ValueError):
    pass


class InsecureSmtpError(ValueError):
    pass


class NoSuchMailboxError(OSError):
    pass


def ParseMessage(fd, pgpmime=True):
    message = email.parser.Parser().parse(fd)
    if pgpmime and GnuPG:
        UnwrapMimeCrypto(message, protocols={
            'openpgp': GnuPG
        })
    else:
        for part in message.walk():
            part.signature_info = SignatureInfo()
            part.encryption_info = EncryptionInfo()
    return message


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


def MessageAsString(part, unixfrom=False):
    buf = StringIO.StringIO()
    Generator(buf).flatten(part, unixfrom=unixfrom, linesep='\r\n')
    return buf.getvalue()


def CleanMessage(config, msg):
    replacements = []
    for key, value in msg.items():
        lkey = key.lower()

        # Remove headers we don't want to expose
        if (lkey.startswith('x-mp-internal-') or
                lkey in ('bcc', 'encryption')):
            replacements.append((key, None))

        # Strip the #key part off any e-mail addresses:
        elif lkey in ('to', 'from', 'cc'):
            if '#' in value:
                replacements.append((key, re.sub(
                    r'(@[^<>\s#]+)#[a-fxA-F0-9]+([>,\s]|$)', r'\1\2', value)))

    for key, val in replacements:
        del msg[key]
    for key, val in replacements:
        if val:
            msg[key] = val

    return msg


def PrepareMessage(config, msg, sender=None, rcpts=None, events=None):
    msg = copy.deepcopy(msg)

    # Short circuit if this message has already been prepared.
    if 'x-mp-internal-sender' in msg and 'x-mp-internal-rcpts' in msg:
        return (sender or msg['x-mp-internal-sender'],
                rcpts or [r.strip()
                          for r in msg['x-mp-internal-rcpts'].split(',')],
                msg,
                events)

    crypto_policy = config.prefs.crypto_policy.lower()
    rcpts = rcpts or []

    # Iterate through headers to figure out what we want to do...
    need_rcpts = not rcpts
    for hdr, val in msg.items():
        lhdr = hdr.lower()
        if lhdr == 'from':
            sender = sender or val
        elif lhdr == 'encryption':
            crypto_policy = val.lower()
        elif need_rcpts and lhdr in ('to', 'cc', 'bcc'):
            rcpts += ExtractEmails(val, strip_keys=False)

    # Are we sane?
    if not sender:
        raise NoFromAddressError()
    if not rcpts:
        raise NoRecipientError()

    # Are we encrypting? Signing?
    if crypto_policy == 'default':
        crypto_policy = config.prefs.crypto_policy

    # This is the BCC hack that Brennan hates!
    rcpts += [sender]

    sender = ExtractEmails(sender, strip_keys=False)[0]
    sender_keyid = None
    if config.prefs.openpgp_header:
        try:
            gnupg = GnuPG()
            seckeys = dict([(x["email"], y["fingerprint"])
                            for y in gnupg.list_secret_keys().values()
                            for x in y["uids"]])
            sender_keyid = seckeys[sender]
        except:
            pass

    rcpts, rr = [sender], rcpts
    for r in rr:
        for e in ExtractEmails(r, strip_keys=False):
            if e not in rcpts:
                rcpts.append(e)

    # Add headers we require
    if 'date' not in msg:
        msg['Date'] = email.utils.formatdate()

    if sender_keyid and config.prefs.openpgp_header:
        msg["OpenPGP"] = "id=%s; preference=%s" % (sender_keyid,
                                                   config.prefs.openpgp_header)

    if 'openpgp' in crypto_policy:

        # FIXME: Make a more efficient sign+encrypt wrapper

        cleaner = lambda m: CleanMessage(config, m)
        if 'sign' in crypto_policy:
            msg = OpenPGPMimeSigningWrapper(config,
                                            sender=sender,
                                            cleaner=cleaner,
                                            recipients=rcpts).wrap(msg)
        if 'encrypt' in crypto_policy:
            msg = OpenPGPMimeEncryptingWrapper(config,
                                               sender=sender,
                                               cleaner=cleaner,
                                               recipients=rcpts).wrap(msg)

    rcpts = set([r.rsplit('#', 1)[0] for r in rcpts])
    msg['x-mp-internal-readonly'] = str(int(time.time()))
    msg['x-mp-internal-sender'] = sender
    msg['x-mp-internal-rcpts'] = ', '.join(rcpts)
    return (sender, rcpts, msg, events)


MUA_HEADERS = ('date', 'from', 'to', 'cc', 'subject', 'message-id', 'reply-to',
               'mime-version', 'content-disposition', 'content-type',
               'user-agent', 'list-id', 'list-subscribe', 'list-unsubscribe',
               'x-ms-tnef-correlator', 'x-ms-has-attach')
DULL_HEADERS = ('in-reply-to', 'references')


def HeaderPrintHeaders(message):
    """Extract message headers which identify the MUA."""
    headers = [k for k, v in message.items()]

    # The idea here, is that MTAs will probably either prepend or append
    # headers, not insert them in the middle. So we strip things off the
    # top and bottom of the header until we see something we are pretty
    # comes from the MUA itself.
    while headers and headers[0].lower() not in MUA_HEADERS:
        headers.pop(0)
    while headers and headers[-1].lower() not in MUA_HEADERS:
        headers.pop(-1)

    # Finally, we return the "non-dull" headers, the ones we think will
    # uniquely identify this particular mailer and won't vary too much
    # from message-to-message.
    return [h for h in headers if h.lower() not in DULL_HEADERS]


def HeaderPrint(message):
    """Generate a fingerprint from message headers which identifies the MUA."""
    return b64w(sha1b64('\n'.join(HeaderPrintHeaders(message)))).lower()


class Email(object):
    """This is a lazy-loading object representing a single email."""

    def __init__(self, idx, msg_idx_pos,
                 msg_parsed=None, msg_parsed_pgpmime=None,
                 msg_info=None, ephemeral_mid=None):
        self.index = idx
        self.config = idx.config
        self.msg_idx_pos = msg_idx_pos
        self.ephemeral_mid = ephemeral_mid
        self.reset_caches(msg_parsed=msg_parsed,
                          msg_parsed_pgpmime=msg_parsed_pgpmime,
                          msg_info=msg_info)

    def msg_mid(self):
        return self.ephemeral_mid or b36(self.msg_idx_pos)

    @classmethod
    def encoded_hdr(self, msg, hdr, value=None):
        hdr_value = value or (msg and msg.get(hdr)) or ''
        try:
            hdr_value.encode('us-ascii')
        except:
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
               msg_subject=None, msg_text=None, msg_references=None,
               save=True, ephemeral_mid='not-saved'):
        msg = MIMEMultipart()
        msg.signature_info = SignatureInfo()
        msg.encryption_info = EncryptionInfo()
        msg_ts = int(time.time())
        if not msg_from:
            msg_from = idx.config.get_profile().get('email', None)
            from_name = idx.config.get_profile().get('name', None)
            if msg_from and from_name:
                msg_from = '%s <%s>' % (from_name, msg_from)
        if not msg_from:
            raise NoFromAddressError()
        msg['From'] = cls.encoded_hdr(None, 'from', value=msg_from)
        msg['Date'] = email.utils.formatdate(msg_ts)
        msg['Message-Id'] = email.utils.make_msgid('mailpile')
        msg_subj = (msg_subject or '')
        msg['Subject'] = cls.encoded_hdr(None, 'subject', value=msg_subj)
        if msg_to:
            msg['To'] = cls.encoded_hdr(None, 'to',
                                        value=', '.join(set(msg_to)))
        if msg_cc:
            msg['Cc'] = cls.encoded_hdr(None, 'cc',
                                        value=', '.join(set(msg_cc)))
        if msg_bcc:
            msg['Bcc'] = cls.encoded_hdr(None, 'bcc',
                                         value=', '.join(set(msg_bcc)))
        if msg_references:
            msg['In-Reply-To'] = msg_references[-1]
            msg['References'] = ', '.join(msg_references)

        if msg_text:
            try:
                msg_text.encode('us-ascii')
                charset = 'us-ascii'
            except UnicodeEncodeError:
                charset = 'utf-8'
            textpart = MIMEText(msg_text, _subtype='plain', _charset=charset)
            textpart.signature_info = SignatureInfo()
            textpart.encryption_info = EncryptionInfo()
            msg.attach(textpart)
            del textpart['MIME-Version']

        if save:
            msg_key = mbx.add(msg)
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
                       msg_parsed=msg, msg_parsed_pgpmime=msg,
                       ephemeral_mid=ephemeral_mid)

    def is_editable(self):
        return (self.ephemeral_mid or
                self.config.is_editable_message(self.get_msg_info()))

    MIME_HEADERS = ('mime-version', 'content-type', 'content-disposition',
                    'content-transfer-encoding')
    UNEDITABLE_HEADERS = ('message-id', ) + MIME_HEADERS
    MANDATORY_HEADERS = ('From', 'To', 'Cc', 'Bcc', 'Subject', 'Encryption')
    HEADER_ORDER = {
        'in-reply-to': -2,
        'references': -1,
        'date': 1,
        'from': 2,
        'subject': 3,
        'to': 4,
        'cc': 5,
        'bcc': 6,
        'encryption': 99,
    }

    def get_editing_strings(self, tree=None):
        tree = tree or self.get_message_tree()
        strings = {
            'from': '', 'to': '', 'cc': '', 'bcc': '', 'subject': '',
            'encryption': '', 'attachments': {}
        }
        header_lines = []
        body_lines = []

        # We care about header order and such things...
        hdrs = dict([(h.lower(), h) for h in tree['headers'].keys()
                     if h.lower() not in self.UNEDITABLE_HEADERS])
        for mandate in self.MANDATORY_HEADERS:
            hdrs[mandate.lower()] = hdrs.get(mandate.lower(), mandate)
        keys = hdrs.keys()
        keys.sort(key=lambda k: (self.HEADER_ORDER.get(k, 99), k))
        lowman = [m.lower() for m in self.MANDATORY_HEADERS]
        for hdr in [hdrs[k] for k in keys]:
            data = tree['headers'].get(hdr, '')
            if hdr.lower() in lowman:
                strings[hdr.lower()] = unicode(data)
            else:
                header_lines.append(unicode('%s: %s' % (hdr, data)))

        for att in tree['attachments']:
            strings['attachments'][att['count']] = (att['filename']
                                                    or '(unnamed)')

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

    def get_editing_string(self, tree=None):
        tree = tree or self.get_message_tree()
        estrings = self.get_editing_strings(tree)
        bits = [estrings['headers']]
        for mh in self.MANDATORY_HEADERS:
            bits.append('%s: %s' % (mh, estrings[mh.lower()]))
        bits.append('')
        bits.append(estrings['body'])
        return '\n'.join(bits)

    def make_attachment(self, fn, filedata=None):
        if filedata and fn in filedata:
            data = filedata[fn]
        else:
            data = open(fn, 'rb').read()
        ctype, encoding = mimetypes.guess_type(fn)
        maintype, subtype = (ctype or 'application/octet-stream').split('/', 1)
        if maintype == 'image':
            att = MIMEImage(data, _subtype=subtype)
        else:
            att = MIMEBase(maintype, subtype)
            att.set_payload(data)
            encoders.encode_base64(att)
        att.add_header('Content-Disposition', 'attachment',
                       filename=os.path.basename(fn))
        return att

    def add_attachments(self, session, filenames, filedata=None):
        if not self.is_editable():
            raise NotEditableError(_('Mailbox is read-only.'))
        msg = self.get_msg()
        if 'x-mp-internal-readonly' in msg:
            raise NotEditableError(_('Message is read-only.'))
        for fn in filenames:
            msg.attach(self.make_attachment(fn, filedata=filedata))
        return self.update_from_msg(session, msg)

    def update_from_string(self, session, data, final=False):
        if not self.is_editable():
            raise NotEditableError(_('Mailbox is read-only.'))

        oldmsg = self.get_msg()
        if 'x-mp-internal-readonly' in oldmsg:
            raise NotEditableError(_('Message is read-only.'))

        if not data:
            outmsg = oldmsg

        else:
            newmsg = email.parser.Parser().parsestr(data.encode('utf-8'))
            outmsg = MIMEMultipart()

            # Copy over editable headers from the input string, skipping blanks
            for hdr in newmsg.keys():
                if hdr.startswith('Attachment-'):
                    pass
                else:
                    encoded_hdr = self.encoded_hdr(newmsg, hdr)
                    if len(encoded_hdr.strip()) > 0:
                        outmsg[hdr] = encoded_hdr

            # Copy over the uneditable headers from the old message
            for hdr in oldmsg.keys():
                if ((hdr.lower() not in self.MIME_HEADERS)
                        and (hdr.lower() in self.UNEDITABLE_HEADERS)):
                    outmsg[hdr] = oldmsg[hdr]

            # Copy the message text
            new_body = newmsg.get_payload().decode('utf-8')
            try:
                new_body.encode('us-ascii')
                charset = 'us-ascii'
            except:
                charset = 'utf-8'
            textbody = MIMEText(new_body, _subtype='plain', _charset=charset)
            outmsg.attach(textbody)
            del textbody['MIME-Version']

            # FIXME: Use markdown and template to generate fancy HTML part

            # Copy the attachments we are keeping
            attachments = [h for h in newmsg.keys()
                           if h.startswith('Attachment-')]
            if attachments:
                oldtree = self.get_message_tree()
                for att in oldtree['attachments']:
                    hdr = 'Attachment-%s' % att['count']
                    if hdr in attachments:
                        # FIXME: Update the filename to match whatever
                        #        the user typed
                        outmsg.attach(att['part'])
                        attachments.remove(hdr)

            # Attach some new files?
            for hdr in attachments:
                try:
                    outmsg.attach(self.make_attachment(newmsg[hdr]))
                except:
                    pass  # FIXME: Warn user that failed...

        # Save result back to mailbox
        if final:
            sender, rcpts, outmsg, ev = PrepareMessage(self.config, outmsg)
        return self.update_from_msg(session, outmsg)

    def update_from_msg(self, session, newmsg):
        if not self.is_editable():
            raise NotEditableError(_('Mailbox is read-only.'))

        mbx, ptr, fd = self.get_mbox_ptr_and_fd()

        # OK, adding to the mailbox worked
        newptr = ptr[:MBX_ID_LEN] + mbx.add(newmsg)

        # Remove the old message...
        mbx.remove(ptr[MBX_ID_LEN:])

        # FIXME: We should DELETE the old version from the index first.

        # Update the in-memory-index
        mi = self.get_msg_info()
        mi[self.index.MSG_PTRS] = newptr
        self.index.set_msg_at_idx_pos(self.msg_idx_pos, mi)
        self.index.index_email(session, Email(self.index, self.msg_idx_pos))

        self.reset_caches()
        return self

    def reset_caches(self,
                     msg_info=None, msg_parsed=None, msg_parsed_pgpmime=None):
        self.msg_info = msg_info
        self.msg_parsed = msg_parsed
        self.msg_parsed_pgpmime = msg_parsed_pgpmime

    def get_msg_info(self, field=None):
        if not self.msg_info:
            self.msg_info = self.index.get_msg_at_idx_pos(self.msg_idx_pos)
        if field is None:
            return self.msg_info
        else:
            return self.msg_info[field]

    def get_mbox_ptr_and_fd(self):
        for msg_ptr in self.get_msg_info(self.index.MSG_PTRS).split(','):
            try:
                mbox = self.config.open_mailbox(None, msg_ptr[:MBX_ID_LEN])
                fd = mbox.get_file_by_ptr(msg_ptr)
                # FIXME: How do we know we have the right message?
                return mbox, msg_ptr, fd
            except (IOError, OSError, KeyError, ValueError, IndexError):
                # FIXME: If this pointer is wrong, should we fix the index?
                print 'WARNING: %s not found' % msg_ptr
        return None, None, None

    def get_file(self):
        return self.get_mbox_ptr_and_fd()[2]

    def get_msg_size(self):
        mbox, ptr, fd = self.get_mbox_ptr_and_fd()
        fd.seek(0, 2)
        return fd.tell()

    def _get_parsed_msg(self, pgpmime):
        fd = self.get_file()
        if fd:
            return ParseMessage(fd, pgpmime=pgpmime)

    def get_msg(self, pgpmime=True):
        if pgpmime:
            if not self.msg_parsed_pgpmime:
                self.msg_parsed_pgpmime = self._get_parsed_msg(pgpmime)
            result = self.msg_parsed_pgpmime
        else:
            if not self.msg_parsed:
                self.msg_parsed = self._get_parsed_msg(pgpmime)
            result = self.msg_parsed
        if not result:
            raise IndexError(_('Message not found?'))
        return result

    def get_headerprint(self):
        return HeaderPrint(self.get_msg())

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
            raw = ' '.join(self.get_msg().get_all(field, default))
            return self.index.hdr(0, 0, value=raw) or raw

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
            self.is_editable()
        ]

    def extract_attachment(self, session, att_id,
                           name_fmt=None, mode='download'):
        msg = self.get_msg()
        count = 0
        extracted = 0
        filename, attributes = '', {}
        for part in (msg.walk() if msg else []):
            mimetype = part.get_content_type()
            if mimetype.startswith('multipart/'):
                continue

            content_id = part.get('content-id', '')
            pfn = part.get_filename() or ''
            count += 1

            if (('*' == att_id)
                    or ('#%s' % count == att_id)
                    or ('part:%s' % count == att_id)
                    or (content_id == att_id)
                    or (mimetype == att_id)
                    or (pfn.lower().endswith('.%s' % att_id))
                    or (pfn == att_id)):

                payload = part.get_payload(None, True) or ''
                attributes = {
                    'msg_mid': self.msg_mid(),
                    'count': count,
                    'length': len(payload),
                    'content-id': content_id,
                    'filename': pfn,
                }
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
                        session.ui.notify(_('Wrote preview to: %s') % filename)
                        attributes['length'] = thumb.tell()
                        filename, fd = session.ui.open_for_data(
                            name_fmt=name_fmt, attributes=attributes)
                        thumb.seek(0)
                        fd.write(thumb.read())
                        fd.close()
                    else:
                        session.ui.notify(_('Failed to generate thumbnail'))
                        raise UrlRedirectException('/static/img/image-default.png')
                else:
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

    RE_HTML_BORING = re.compile('(\s+|<style[^>]*>[^<>]*</style>)')
    RE_EXCESS_WHITESPACE = re.compile('\n\s*\n\s*')
    RE_HTML_NEWLINES = re.compile('(<br|</(tr|table))')
    RE_HTML_PARAGRAPHS = re.compile('(</?p|</?(title|div|html|body))')
    RE_HTML_LINKS = re.compile('<a\s+[^>]*href=[\'"]?([^\'">]+)[^>]*>'
                               '([^<]*)</a>')
    RE_HTML_IMGS = re.compile('<img\s+[^>]*src=[\'"]?([^\'">]+)[^>]*>')
    RE_HTML_IMG_ALT = re.compile('<img\s+[^>]*alt=[\'"]?([^\'">]+)[^>]*>')

    def _extract_text_from_html(self, html):
        try:
            # We compensate for some of the limitations of lxml...
            links, imgs = [], []
            def delink(m):
                url, txt = m.group(1), m.group(2).strip()
                if txt[:4] in ('http', 'www.'):
                    return txt
                elif url.startswith('mailto:'):
                    if '@' in txt:
                        return txt
                    else:
                        return '%s (%s)' % (txt, url.split(':', 1)[1])
                else:
                    links.append(' [%d] %s%s' % (len(links) + 1,
                                                 txt and (txt + ': ') or '',
                                                 url))
                    return '%s[%d]' % (txt, len(links))
            def deimg(m):
                tag, url = m.group(0), m.group(1)
                if ' alt=' in tag:
                    return re.sub(self.RE_HTML_IMG_ALT, '\1', tag).strip()
                else:
                    imgs.append(' [%d] %s' % (len(imgs)+1, url))
                    return '[Image %d]' % len(imgs)
            html = re.sub(self.RE_HTML_PARAGRAPHS, '\n\n\\1',
                       re.sub(self.RE_HTML_NEWLINES, '\n\\1',
                           re.sub(self.RE_HTML_BORING, ' ',
                               re.sub(self.RE_HTML_LINKS, delink,
                                   re.sub(self.RE_HTML_IMGS, deimg, html)))))
            text = (lxml.html.fromstring(html).text_content() +
                    (links and '\n\nLinks:\n' or '') + '\n'.join(links) +
                    (imgs and '\n\nImages:\n' or '') + '\n'.join(imgs))
            return re.sub(self.RE_EXCESS_WHITESPACE, '\n\n', text).strip()
        except:
            import traceback
            traceback.print_exc()
            return html

    def get_message_tree(self, want=None):
        msg = self.get_msg()
        tree = {
            'id': self.get_msg_info(self.index.MSG_ID)
        }

        for p in 'text_parts', 'html_parts', 'attachments':
            if want is None or p in want:
                tree[p] = []

        if want is None or 'summary' in want:
            tree['summary'] = self.get_msg_summary()

        if want is None or 'tags' in want:
            tree['tags'] = self.get_msg_info(self.index.MSG_TAGS).split(',')

        if want is None or 'conversation' in want:
            tree['conversation'] = {}
            conv_id = self.get_msg_info(self.index.MSG_THREAD_MID)
            if conv_id:
                conv = Email(self.index, int(conv_id, 36))
                tree['conversation'] = convs = [conv.get_msg_summary()]
                for rid in conv.get_msg_info(self.index.MSG_REPLIES
                                             ).split(','):
                    if rid:
                        convs.append(Email(self.index, int(rid, 36)
                                           ).get_msg_summary())

        if (want is None
                or 'headers' in want
                or 'editing_string' in want
                or 'editing_strings' in want):
            tree['headers'] = {}
            for hdr in msg.keys():
                tree['headers'][hdr] = self.index.hdr(msg, hdr)

        if want is None or 'headers_lc' in want:
            tree['headers_lc'] = {}
            for hdr in msg.keys():
                tree['headers_lc'][hdr.lower()] = self.index.hdr(msg, hdr)

        if want is None or 'header_list' in want:
            tree['header_list'] = [(k, self.index.hdr(msg, k, value=v))
                                   for k, v in msg.items()]

        if want is None or 'addresses' in want:
            tree['addresses'] = {}
            for hdr in msg.keys():
                hdrl = hdr.lower()
                if hdrl in ('reply-to', 'from', 'to', 'cc', 'bcc'):
                    tree['addresses'][hdrl] = AddressHeaderParser(msg[hdr])

        # FIXME: Decide if this is strict enough or too strict...?
        html_cleaner = Cleaner(page_structure=True, meta=True, links=True,
                               javascript=True, scripts=True, frames=True,
                               embedded=True, safe_attrs_only=True)

        # Note: count algorithm must match that used in extract_attachment
        #       above
        count = 0
        for part in msg.walk():
            mimetype = part.get_content_type()
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
            if (part.get('content-disposition', 'inline') == 'inline'
                    and mimetype in ('text/plain', 'text/html')):
                payload, charset = self.decode_payload(part)
                start = payload[:100].strip()

                if mimetype == 'text/html':
                    if want is None or 'html_parts' in want:
                        tree['html_parts'].append({
                            'charset': charset,
                            'type': 'html',
                            'data': ((payload.strip()
                                      and html_cleaner.clean_html(payload))
                                     or '')
                        })

                elif want is None or 'text_parts' in want:
                    if start[:3] in ('<di', '<ht', '<p>', '<p ', '<ta', '<bo'):
                        payload = self._extract_text_from_html(payload)
                    # Ignore white-space only text parts, they usually mean
                    # the message is HTML only and we want the code below
                    # to try and extract meaning from it.
                    if (start or payload.strip()) != '':
                        text_parts = self.parse_text_part(payload, charset)
                        tree['text_parts'].extend(text_parts)

            elif want is None or 'attachments' in want:
                tree['attachments'].append({
                    'mimetype': mimetype,
                    'count': count,
                    'part': part,
                    'length': len(part.get_payload(None, True) or ''),
                    'content-id': part.get('content-id', ''),
                    'filename': part.get_filename() or ''
                })

        if want is None or 'text_parts' in want:
            if tree.get('html_parts') and not tree.get('text_parts'):
                html_part = tree['html_parts'][0]
                payload = self._extract_text_from_html(html_part['data'])
                text_parts = self.parse_text_part(payload,
                                                  html_part['charset'])
                tree['text_parts'].extend(text_parts)

        if self.is_editable():
            if not want or 'editing_strings' in want:
                tree['editing_strings'] = self.get_editing_strings(tree)
            if not want or 'editing_string' in want:
                tree['editing_string'] = self.get_editing_string(tree)

        if want is None or 'crypto' in want:
            if 'crypto' not in tree:
                tree['crypto'] = {'encryption': msg.encryption_info,
                                  'signature': msg.signature_info}
            else:
                tree['crypto']['encryption'] = msg.encryption_info
                tree['crypto']['signature'] = msg.signature_info

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
        payload = part.get_payload(None, True) or ''
        return self.decode_text(payload, charset=charset)

    def parse_text_part(self, data, charset):
        current = {
            'type': 'bogus',
            'charset': charset,
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
                }
                parse.append(current)
            current['data'] += line
            clines.append(line)
        return parse

    def parse_line_type(self, line, block):
        # FIXME: Detect forwarded messages, ...

        if block in ('body', 'quote') and line in ('-- \n', '-- \r\n'):
            return 'signature', 'signature'

        if block == 'signature':
            return 'signature', 'signature'

        stripped = line.rstrip()

        if stripped == '-----BEGIN PGP SIGNED MESSAGE-----':
            return 'pgpbeginsigned', 'pgpbeginsigned'
        if block == 'pgpbeginsigned':
            if line.startswith('Hash: ') or stripped == '':
                return 'pgpbeginsigned', 'pgpbeginsigned'
            else:
                return 'pgpsignedtext', 'pgpsignedtext'
        if block == 'pgpsignedtext':
            if (stripped == '-----BEGIN PGP SIGNATURE-----'):
                return 'pgpsignature', 'pgpsignature'
            else:
                return 'pgpsignedtext', 'pgpsignedtext'
        if block == 'pgpsignature':
            if stripped == '-----END PGP SIGNATURE-----':
                return 'pgpend', 'pgpsignature'
            else:
                return 'pgpsignature', 'pgpsignature'

        if stripped == '-----BEGIN PGP MESSAGE-----':
            return 'pgpbegin', 'pgpbegin'
        if block == 'pgpbegin':
            if ':' in line or stripped == '':
                return 'pgpbegin', 'pgpbegin'
            else:
                return 'pgptext', 'pgptext'
        if block == 'pgptext':
            if stripped == '-----END PGP MESSAGE-----':
                return 'pgpend', 'pgpend'
            else:
                return 'pgptext', 'pgptext'

        if block == 'quote':
            if stripped == '':
                return 'quote', 'quote'
        if line.startswith('>'):
            return 'quote', 'quote'

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

    def evaluate_pgp(self, tree, check_sigs=True, decrypt=False):
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
                        gpg = GnuPG()
                        message = ''.join([p['data'].encode(p['charset'])
                                           for p in pgpdata])
                        si = pgpdata[1]['crypto']['signature'
                                                  ] = gpg.verify(message)
                        pgpdata[0]['data'] = ''
                        pgpdata[2]['data'] = ''

                    except Exception, e:
                        print e

            if decrypt:
                if part['type'] in ('pgpbegin', 'pgptext'):
                    pgpdata.append(part)
                elif part['type'] == 'pgpend':
                    pgpdata.append(part)

                    gpg = GnuPG()
                    (signature_info, encryption_info, text
                     ) = gpg.decrypt(''.join([p['data'] for p in pgpdata]))

                    # FIXME: If the data is binary, we should provide some
                    #        sort of download link or maybe leave the PGP
                    #        blob entirely intact, undecoded.
                    text, charset = self.decode_text(text, binary=False)

                    ei = pgpdata[1]['crypto']['encryption'] = encryption_info
                    si = pgpdata[1]['crypto']['signature'] = signature_info
                    if encryption_info["status"] == "decrypted":
                        pgpdata[1]['data'] = text
                        pgpdata[0]['data'] = ""
                        pgpdata[2]['data'] = ""

            # Bubbling up!
            if (si or ei) and 'crypto' not in tree:
                tree['crypto'] = {'signature': SignatureInfo(),
                                  'encryption': EncryptionInfo()}
            if si:
                tree['crypto']['signature'].mix(si)
            if ei:
                tree['crypto']['encryption'].mix(ei)

        # Cleanup, remove empty 'crypto': {} blocks.
        for part in tree['text_parts']:
            if not part['crypto']:
                del part['crypto']

        return tree

    def _decode_gpg(self, message, decrypted):
        header, body = message.replace('\r\n', '\n').split('\n\n', 1)
        for line in header.lower().split('\n'):
            if line.startswith('charset:'):
                return decrypted.decode(line.split()[1])
        return decrypted.decode('utf-8')


class AddressHeaderParser(list):
    """
    This is a class which tries very hard to interpret the From:, To:
    and Cc: lines found in real-world e-mail and make sense of them.

    The general strategy of this parser is to:
       1. parse header data into tokens
       2. group tokens together into address + name constructs.

    And optionaly,
       3. normalize each group to a standard format

    In practice, we do this in multiple passes: first a strict pass where
    we try to parse things semi-sensibly, followed by fuzzier heuristics.

    Ideally, if folks format things correctly we should parse correctly.
    But if that fails, there are are other passes where we try to cope
    with various types of weirdness we've seen in the wild. The wild can
    be pretty wild.

    This parser is NOT (yet) fully RFC2822 compliant - in particular it
    will get confused by nested comments (see FIXME in tests below).

    Examples:

    >>> ahp = AddressHeaderParser(AddressHeaderParser.TEST_HEADER_DATA)
    >>> ai = ahp[1]
    >>> ai.fn
    'Bjarni'
    >>> ai.address
    'bre@klaki.net'
    >>> ahp.normalized_addresses() == ahp.TEST_EXPECT_NORMALIZED_ADDRESSES
    True

    >>> AddressHeaderParser('Weird email@somewhere.com Header').normalized()
    '"Weird Header" <email@somewhere.com>'
    """

    TEST_HEADER_DATA = """
        bre@klaki.net  ,
        bre@klaki.net Bjarni ,
        bre@klaki.net bre@klaki.net,
        bre@klaki.net (bre@notmail.com),
        bre@klaki.net ((nested) bre@notmail.com comment),
        (FIXME: (nested) bre@wrongmail.com parser breaker) bre@klaki.net,
        undisclosed-recipients-gets-ignored:,
        Bjarni [mailto:bre@klaki.net],
        "This is a key test" <bre@klaki.net#123456789>,
        bre@klaki.net (Bjarni Runar Einar's son);
        Bjarni is bre @klaki.net,
        Bjarni =?iso-8859-1?Q?Runar?=Einarsson<' bre'@ klaki.net>,
    """
    TEST_EXPECT_NORMALIZED_ADDRESSES = [
        '<bre@klaki.net>',
        '"Bjarni" <bre@klaki.net>',
        '"bre@klaki.net" <bre@klaki.net>',
        '"bre@notmail.com" <bre@klaki.net>',
        '"(nested bre@notmail.com comment)" <bre@klaki.net>',
        '"(FIXME: nested parser breaker) bre@klaki.net" <bre@wrongmail.com>',
        '"Bjarni" <bre@klaki.net>',
        '"This is a key test" <bre@klaki.net>',
        '"Bjarni Runar Einar\\\'s son" <bre@klaki.net>',
        '"Bjarni is" <bre@klaki.net>',
        '"Bjarni Runar Einarsson" <bre@klaki.net>']

    # Escaping and quoting
    TXT_RE_QUOTE = '=\\?([^\\?\\s]+)\\?([QqBb])\\?([^\\?\\s]+)\\?='
    TXT_RE_QUOTE_NG = TXT_RE_QUOTE.replace('(', '(?:')
    RE_ESCAPES = re.compile('\\\\([\\\\"\'])')
    RE_QUOTED = re.compile(TXT_RE_QUOTE)
    RE_SHOULD_ESCAPE = re.compile('([\\\\"\'])')

    # This is how we normally break a header line into tokens
    RE_TOKENIZER = re.compile('(<[^<>]*>'                    # <stuff>
                              '|\\([^\\(\\)]*\\)'            # (stuff)
                              '|\\[[^\\[\\]]*\\]'            # [stuff]
                              '|"(?:\\\\\\\\|\\\\"|[^"])*"'  # "stuff"
                              "|'(?:\\\\\\\\|\\\\'|[^'])*'"  # 'stuff'
                              '|' + TXT_RE_QUOTE_NG +        # =?stuff?=
                              '|,'                           # ,
                              '|;'                           # ;
                              '|\\s+'                        # white space
                              '|[^\\s;,]+'                   # non-white space
                              ')')

    # Where to insert spaces to help the tokenizer parse bad data
    RE_MUNGE_TOKENSPACERS = (re.compile('(\S)(<)'), re.compile('(\S)(=\\?)'))

    # Characters to strip aware entirely when tokenizing munged data
    RE_MUNGE_TOKENSTRIPPERS = (re.compile('[<>"]'),)

    # This is stuff we ignore (undisclosed-recipients, etc)
    RE_IGNORED_GROUP_TOKENS = re.compile('(?i)undisclosed')

    # Things we strip out to try and un-mangle e-mail addresses when
    # working with bad data.
    RE_MUNGE_STRIP = re.compile('(?i)(?:\\bmailto:|[\\s"\']|\?$)')

    # This a simple regular expression for detecting e-mail addresses.
    RE_MAYBE_EMAIL = re.compile('^[^()<>@,;:\\\\"\\[\\]\\s\000-\031]+'
                                '@[a-zA-Z0-9_\\.-]+(?:#[A-Za-z0-9]+)?$')

    # We try and interpret non-ascii data as a particular charset, in
    # this order by default. Should be overridden whenever we have more
    # useful info from the message itself.
    DEFAULT_CHARSET_ORDER = ('iso-8859-1', 'utf-8')

    def __init__(self, data=None, charset_order=None, **kwargs):
        self.charset_order = charset_order or self.DEFAULT_CHARSET_ORDER
        self._parse_args = kwargs
        if data is None:
            self._reset(**kwargs)
        else:
            self.parse(data)

    def _reset(self, _raw_data=None, strict=False, _raise=False):
        self._raw_data = _raw_data
        self._tokens = []
        self._groups = []
        self[:] = []

    def parse(self, data):
        return self._parse(data, **self._parse_args)

    def _parse(self, data, strict=False, _raise=False):
        self._reset(_raw_data=data)

        # 1st pass, strict
        try:
            self._tokens = self._tokenize(self._raw_data)
            self._groups = self._group(self._tokens)
            self[:] = self._find_addresses(self._groups,
                                           _raise=(not strict))
            return self
        except ValueError:
            if strict and _raise:
                raise
        if strict:
            return self

        # 2nd & 3rd passes; various types of sloppy
        for _pass in ('2', '3'):
            try:
                self._tokens = self._tokenize(self._raw_data, munge=_pass)
                self._groups = self._group(self._tokens, munge=_pass)
                self[:] = self._find_addresses(self._groups,
                                               munge=_pass,
                                               _raise=_raise)
                return self
            except ValueError:
                if _pass == 3 and _raise:
                    raise
        return self

    def unquote(self, string, charset_order=None):
        def uq(m):
            cs, how, data = m.group(1), m.group(2), m.group(3)
            if how in ('b', 'B'):
                return base64.b64decode(data).decode(cs).encode('utf-8')
            else:
                return quopri.decodestring(data, header=True
                                           ).decode(cs).encode('utf-8')

        for cs in charset_order or self.charset_order:
             try:
                 string = string.decode(cs).encode('utf-8')
                 break
             except UnicodeDecodeError:
                 pass

        return re.sub(self.RE_QUOTED, uq, string)

    @classmethod
    def unescape(self, string):
        return re.sub(self.RE_ESCAPES, lambda m: m.group(1), string)

    @classmethod
    def escape(self, strng):
        return re.sub(self.RE_SHOULD_ESCAPE, lambda m: '\\'+m.group(0), strng)

    def _tokenize(self, string, munge=False):
        if munge:
            for ts in self.RE_MUNGE_TOKENSPACERS:
                string = re.sub(ts, '\\1 \\2', string)
            if munge == 3:
                for ts in self.RE_MUNGE_TOKENSTRIPPERS:
                    string = re.sub(ts, '', string)
        return re.findall(self.RE_TOKENIZER, string)

    def _clean(self, token):
        if token[:1] in ('"', "'"):
            if token[:1] == token[-1:]:
                return self.unescape(token[1:-1])
        elif token.startswith('[mailto:') and token[-1:] == ']':
            # Just convert [mailto:...] crap into a <address>
            return '<%s>' % token[8:-1]
        elif (token[:1] == '[' and token[-1:] == ']'):
            return token[1:-1]
        return token

    def _group(self, tokens, munge=False):
        groups = [[]]
        for token in tokens:
            token = token.strip()
            if token in (',', ';'):
                # Those tokens SHOULD separate groups, but we don't like to
                # create groups that have no e-mail addresses at all.
                if groups[-1]:
                    if [g for g in groups[-1] if '@' in g]:
                        groups.append([])
                        continue
                    # However, this stuff is just begging to be ignored.
                    elif [g for g in groups[-1]
                          if re.match(self.RE_IGNORED_GROUP_TOKENS, g)]:
                        groups[-1] = []
                        continue
            if token:
                groups[-1].append(self.unquote(self._clean(token)))
        if not groups[-1]:
            groups.pop(-1)
        return groups

    def _find_addresses(self, groups, **fa_kwargs):
        alist = [self._find_address(g, **fa_kwargs) for g in groups]
        return [a for a in alist if a]

    def _find_address(self, g, _raise=False, munge=False):
        if g:
            g = g[:]
        else:
            return []

        def email_at(i):
            for j in range(0, len(g)):
                if g[j][:1] == '(' and g[j][-1:] == ')':
                    g[j] = g[j][1:-1]
            rest = ' '.join([g[j] for j in range(0, len(g)) if j != i
                             ]).replace(' ,', ',').replace(' ;', ';')
            email, keys = g[i], None
            if '#' in email[email.index('@'):]:
                email, key = email.rsplit('#', 1)
                keys = [{'fingerprint': key}]
            return AddressInfo(email, rest.strip(), keys=keys)

        def munger(string):
            if munge:
                return re.sub(self.RE_MUNGE_STRIP, '', string)
            else:
                return string

        # If munging, look for email @domain.com in two parts, rejoin
        if munge:
            for i in range(0, len(g)):
                if i > 0 and i < len(g) and g[i][:1] == '@':
                    g[i-1:i+1] = [g[i-1]+g[i]]
                elif i < len(g)-1 and g[i][-1:] == '@':
                    g[i:i+2] = [g[i]+g[i+1]]

        # 1st, look for <email@domain.com>
        for i in range(0, len(g)):
            if g[i][:1] == '<' and g[i][-1:] == '>':
                maybemail = munger(g[i][1:-1])
                if re.match(self.RE_MAYBE_EMAIL, maybemail):
                    g[i] = maybemail
                    return email_at(i)

        # 2nd, look for bare email@domain.com
        for i in range(0, len(g)):
            maybemail = munger(g[i])
            if re.match(self.RE_MAYBE_EMAIL, maybemail):
                g[i] = maybemail
                return email_at(i)

        if _raise:
            raise ValueError('No email found in %s' % (g,))
        else:
            return None

    def normalized_addresses(self, addresses=None, with_keys=False):
        if addresses is None:
            addresses = self
        def fmt(ai):
            if with_keys and ai.keys:
                fp = ai.keys[0].get('fingerprint')
                epart = '<%s%s>' % (ai.address, fp and ('#%s' % fp) or '')
            else:
                epart = '<%s>' % ai.address
            if ai.fn:
                 return '"%s" %s' % (self.escape(ai.fn), epart)
            else:
                 return epart
        return [fmt(ai) for ai in (addresses or [])]

    def normalized(self, **kwargs):
        return ', '.join(self.normalized_addresses(**kwargs))


if __name__ == "__main__":
    import doctest
    import sys

    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
