import cStringIO
import email
import lxml.html
import re
import rfc822
import time
import threading
import traceback
from urllib import quote, unquote

import mailpile.util
from mailpile.crypto.gpgi import GnuPG
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.mailutils import FormatMbxId, MBX_ID_LEN, NoSuchMailboxError
from mailpile.mailutils import AddressHeaderParser
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName
from mailpile.mailutils import Email, ParseMessage, HeaderPrint
from mailpile.postinglist import GlobalPostingList
from mailpile.ui import *
from mailpile.util import *


_plugins = PluginManager()


class SearchResultSet:
    """
    Search results!
    """
    def __init__(self, idx, terms, results, exclude):
        self.terms = set(terms)
        self._index = idx
        self.set_results(results, exclude)

    def set_results(self, results, exclude):
        self._results = {
            'raw': set(results),
            'excluded': set(exclude) & set(results)
        }
        return self

    def __len__(self):
        return len(self._results.get('raw', []))

    def as_set(self, order='raw'):
        return self._results[order] - self._results['excluded']

    def excluded(self):
        return self._results['excluded']


SEARCH_RESULT_CACHE = {}


class CachedSearchResultSet(SearchResultSet):
    """
    Cached search result.
    """
    def __init__(self, idx, terms):
        global SEARCH_RESULT_CACHE
        self.terms = set(terms)
        self._index = idx
        self._results = SEARCH_RESULT_CACHE.get(self._skey(), {})
        self._results['_last_used'] = time.time()

    def _skey(self):
        return ' '.join(self.terms)

    def set_results(self, *args):
        global SEARCH_RESULT_CACHE
        SearchResultSet.set_results(self, *args)
        SEARCH_RESULT_CACHE[self._skey()] = self._results
        self._results['_last_used'] = time.time()
        return self

    @classmethod
    def DropCaches(cls, msg_idxs=None, tags=None):
        # FIXME: Make this more granular
        global SEARCH_RESULT_CACHE
        SEARCH_RESULT_CACHE = {}


class MailIndex(object):
    """This is a lazily parsing object representing a mailpile index."""

    MSG_MID = 0
    MSG_PTRS = 1
    MSG_ID = 2
    MSG_DATE = 3
    MSG_FROM = 4
    MSG_TO = 5
    MSG_CC = 6
    MSG_KB = 7
    MSG_SUBJECT = 8
    MSG_BODY = 9
    MSG_TAGS = 10
    MSG_REPLIES = 11
    MSG_THREAD_MID = 12

    MSG_FIELDS_V1 = 11
    MSG_FIELDS_V2 = 13

    BOGUS_METADATA = [None, '', None, '0', '(no sender)', '', '', '0',
                      '(not in index)', '', '', '', '-1']

    MAX_INCREMENTAL_SAVES = 25

    def __init__(self, config):
        self.config = config
        self.interrupt = None
        self.INDEX = []
        self.INDEX_SORT = {}
        self.INDEX_THR = []
        self.PTRS = {}
        self.TAGS = {}
        self.MSGIDS = {}
        self.EMAILS = []
        self.EMAIL_IDS = {}
        self.CACHE = {}
        self.MODIFIED = set()
        self.EMAILS_SAVED = 0
        self._scanned = {}
        self._saved_changes = 0
        self._lock = SearchRLock()
        self._save_lock = SearchRLock()
        self._prepare_sorting()

    @classmethod
    def l2m(self, line):
        return line.decode('utf-8').split(u'\t')

    # A translation table for message parts stored in the index, consists of
    # a mapping from unicode ordinals to either another unicode ordinal or
    # None, to remove a character. By default it removes the ASCII control
    # characters and replaces tabs and newlines with spaces.
    NORM_TABLE = dict([(i, None) for i in range(0, 0x20)], **{
        ord(u'\t'): ord(u' '),
        ord(u'\r'): ord(u' '),
        ord(u'\n'): ord(u' '),
        0x7F: None
    })

    @classmethod
    def m2l(self, message):
        # Normalize the message before saving it so we can be sure that we will
        # be able to read it back later.
        parts = [unicode(p).translate(self.NORM_TABLE) for p in message]
        return (u'\t'.join(parts)).encode('utf-8')

    @classmethod
    def get_body(self, msg_info):
        if msg_info[self.MSG_BODY].startswith('{'):
            try:
                return json.loads(msg_info[self.MSG_BODY])
            except ValueError:
                pass
        return {
            'snippet': msg_info[self.MSG_BODY]
        }

    @classmethod
    def truncate_body_snippet(self, body, max_chars):
        if 'snippet' in body:
            delta = len(self.encode_body(body)) - max_chars
            if delta > 0:
                body['snippet'] = body['snippet'][:-delta].rsplit(' ', 1)[0]

    @classmethod
    def encode_body(self, d, **kwargs):
        for k, v in kwargs:
            if v is None:
                if k in d:
                    del d[k]
            else:
                d[k] = v
        if len(d) == 1 and 'snippet' in d:
            return d['snippet']
        else:
            return json.dumps(d)

    @classmethod
    def set_body(self, msg_info, **kwargs):
        d = self.get_body(msg_info)
        msg_info[self.MSG_BODY] = self.encode_body(d, **kwargs)

    def load(self, session=None):
        self.INDEX = []
        self.CACHE = {}
        self.PTRS = {}
        self.MSGIDS = {}
        self.EMAILS = []
        self.EMAIL_IDS = {}
        CachedSearchResultSet.DropCaches()
        bogus_lines = []

        def process_lines(lines):
            for line in lines:
                line = line.strip()
                if line[:1] in ('#', ''):
                    pass
                elif line[:1] == '@':
                    try:
                        pos, email = line[1:].split('\t', 1)
                        pos = int(pos, 36)
                        while len(self.EMAILS) < pos + 1:
                            self.EMAILS.append('')
                        unquoted_email = unquote(email).decode('utf-8')
                        self.EMAILS[pos] = unquoted_email
                        self.EMAIL_IDS[unquoted_email.split()[0].lower()] = pos
                    except (ValueError, IndexError, TypeError):
                        bogus_lines.append(line)
                else:
                    bogus = False
                    words = line.split('\t')

                    # Migration: converting old metadata into new!
                    if len(words) != self.MSG_FIELDS_V2:

                        # V1 -> V2 adds MSG_CC and MSG_KB
                        if len(words) == self.MSG_FIELDS_V1:
                            words[self.MSG_CC:self.MSG_CC] = ['']
                            words[self.MSG_KB:self.MSG_KB] = ['0']

                        # Add V2 -> V3 here, etc. etc.

                        if len(words) == self.MSG_FIELDS_V2:
                            line = '\t'.join(words)
                        else:
                            bogus = True

                    if not bogus:
                        try:
                            pos = int(words[self.MSG_MID], 36)
                            self.set_msg_at_idx_pos(pos, words,
                                                    original_line=line)
                        except ValueError:
                            bogus = True

                    if bogus:
                        bogus_lines.append(line)
                        if len(bogus_lines) > max(0.02 * len(self.INDEX), 50):
                            raise Exception(_('Your metadata index is '
                                              'either too old, too new '
                                              'or corrupt!'))
                        elif session and 1 == len(bogus_lines) % 100:
                            session.ui.error(_('Corrupt data in metadata '
                                               'index! Trying to cope...'))

        if session:
            session.ui.mark(_('Loading metadata index...'))
        try:
            import mailpile.mail_source
            with self._save_lock, self._lock:
                with open(self.config.mailindex_file(), 'r') as fd:
                    # We don't raise on errors, in case only some of the chunks
                    # are corrupt - we want to read the rest of them.
                    # FIXME: Differentiate between partial index and no index?
                    decrypt_and_parse_lines(fd, process_lines, self.config,
                                            newlines=True, decode=False,
                                            _raise=False)
        except IOError:
            if session:
                session.ui.warning(_('Metadata index not found: %s'
                                     ) % self.config.mailindex_file())

        session.ui.mark(_('Loading global posting list...'))
        GlobalPostingList(session, '')

        if bogus_lines:
            bogus_file = (self.config.mailindex_file() +
                          '.bogus.%x' % time.time())
            with open(bogus_file, 'w') as bl:
                bl.write('\n'.join(bogus_lines))
            if session:
                session.ui.warning(_('Recovered! Wrote bad metadata to: %s'
                                     ) % bogus_file)

        if session:
            session.ui.mark(_n('Loaded metadata, %d message',
                               'Loaded metadata, %d messages',
                               len(self.INDEX)
                               ) % len(self.INDEX))
        self.EMAILS_SAVED = len(self.EMAILS)

    def update_msg_tags(self, msg_idx_pos, msg_info):
        tags = set(self.get_tags(msg_info=msg_info))
        with self._lock:
            for tid in (set(self.TAGS.keys()) - tags):
                self.TAGS[tid] -= set([msg_idx_pos])
            for tid in tags:
                if tid not in self.TAGS:
                    self.TAGS[tid] = set()
                self.TAGS[tid].add(msg_idx_pos)

    def save_changes(self, session=None):
        self._save_lock.acquire()
        try:
            # In a locked section, check what needs to be done!
            with self._lock:
                mods, self.MODIFIED = self.MODIFIED, set()
                old_emails_saved, total = self.EMAILS_SAVED, len(self.EMAILS)

            if old_emails_saved == total and not mods:
                # Nothing to do...
                return

            if self._saved_changes >= self.MAX_INCREMENTAL_SAVES:
                # Too much to do!
                return self.save(session=session)

            if session:
                session.ui.mark(_("Saving metadata index changes..."))

            # In a locked section we just prepare our data
            with self._lock:
                emails = []
                for eid in range(old_emails_saved, total):
                    quoted_email = quote(self.EMAILS[eid].encode('utf-8'))
                    emails.append('@%s\t%s\n' % (b36(eid), quoted_email))
                self.EMAILS_SAVED = total

            # Unlocked, try to write this out
            gpgr = self.config.prefs.gpg_recipient
            gpgr = gpgr if gpgr not in (None, '', '!CREATE') else None
            data = ''.join(emails + [self.INDEX[pos] + '\n' for pos in mods])
            if gpgr:
                status, edata = GnuPG(self.config).encrypt(data, tokeys=[gpgr])
                if status == 0:
                    data = edata
            with open(self.config.mailindex_file(), 'a') as fd:
                fd.write(data)
                self._saved_changes += 1

            if session:
                session.ui.mark(_("Saved metadata index changes"))
        except:
            # Failed, roll back...
            self.MODIFIED |= mods
            self.EMAILS_SAVED = old_emails_saved
            raise
        finally:
            self._save_lock.release()

    def save(self, session=None):
        try:
            self._save_lock.acquire()
            with self._lock:
                old_mods, self.MODIFIED = self.MODIFIED, set()
                old_emails_saved = self.EMAILS_SAVED

            if session:
                session.ui.mark(_("Saving metadata index..."))

            idxfile = self.config.mailindex_file()
            newfile = '%s.new' % idxfile

            data = [
                '# This is the mailpile.py index file.\n',
                '# We have %d messages!\n' % len(self.INDEX)
            ]
            self.EMAILS_SAVED = email_counter = len(self.EMAILS)
            for eid in range(0, email_counter):
                quoted_email = quote(self.EMAILS[eid].encode('utf-8'))
                data.append('@%s\t%s\n' % (b36(eid), quoted_email))
            index_counter = len(self.INDEX)
            for i in range(0, index_counter):
                data.append(self.INDEX[i] + '\n')
            data = ''.join(data)

            gpgr = self.config.prefs.gpg_recipient
            gpgr = gpgr if gpgr not in (None, '', '!CREATE') else None
            if gpgr:
                status, edata = GnuPG(self.config).encrypt(data, tokeys=[gpgr])
                if status == 0:
                    data = edata

            with open(newfile, 'w') as fd:
                fd.write(data)

            # Keep the last 5 index files around... just in case.
            backup_file(idxfile, backups=5, min_age_delta=10)
            os.rename(newfile, idxfile)

            self._saved_changes = 0
            if session:
                session.ui.mark(_("Saved metadata index"))
        except:
            # Failed, roll back...
            with self._lock:
                self.MODIFIED |= old_mods
                self.EMAILS_SAVED = old_emails_saved
            raise
        finally:
            self._save_lock.release()

    def update_ptrs_and_msgids(self, session):
        session.ui.mark(_('Updating high level indexes'))
        for offset in range(0, len(self.INDEX)):
            message = self.l2m(self.INDEX[offset])
            if len(message) == self.MSG_FIELDS_V2:
                self.MSGIDS[message[self.MSG_ID]] = offset
                for msg_ptr in message[self.MSG_PTRS].split(','):
                    self.PTRS[msg_ptr] = offset
            else:
                session.ui.warning(_('Bogus line: %s') % line)

    @classmethod
    def try_decode(self, text, charset, replace=''):
        # FIXME: We need better heuristics for choosing charsets, as pretty
        #        much any 8-bit legacy charset will decode pretty much any
        #        blob of data. At least utf-8 will raise on some things
        #        (which is why we make it the 1st guess), but still not all.
        for cs in (charset, 'utf-8', 'iso-8859-1'):
            if cs:
                try:
                    return text.decode(cs)
                except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
                    pass
        return "".join((i if (ord(i) < 128) else replace) for i in text)

    @classmethod
    def hdr(self, msg, name, value=None, charset=None):
        """
        This method stubbornly tries to decode header data and convert
        to Pythonic unicode strings. The strings are guaranteed not to
        contain tab, newline or carriage return characters.

        If used with a message object, the header and the MIME charset
        will be inferred from the message headers.
        >>> hdr = MailIndex.hdr
        >>> msg = email.message.Message()
        >>> msg['content-type'] = 'text/plain; charset=utf-8'
        >>> msg['from'] = 'G\\xc3\\xadsli R \\xc3\\x93la <f@b.is>'
        >>> hdr(msg, 'from')
        u'G\\xedsli R \\xd3la <f@b.is>'

        The =?...?= MIME header encoding is also recognized and processed.

        >>> hdr(None, None, '=?iso-8859-1?Q?G=EDsli_R_=D3la?=\\r\\n<f@b.is>')
        u'G\\xedsli R \\xd3la <f@b.is>'

        >>> hdr(None, None, '"=?utf-8?Q?G=EDsli_R?= =?iso-8859-1?Q?=D3la?="')
        u'G\\xedsli R \\xd3la'

        And finally, guesses are made with raw binary data. This process
        could be improved, it currently only attempts utf-8 and iso-8859-1.

        >>> hdr(None, None, '"G\\xedsli R \\xd3la"\\r\\t<f@b.is>')
        u'"G\\xedsli R \\xd3la"  <f@b.is>'

        >>> hdr(None, None, '"G\\xc3\\xadsli R \\xc3\\x93la"\\n <f@b.is>')
        u'"G\\xedsli R \\xd3la"  <f@b.is>'
        """
        if value is None:
            value = msg and msg[name] or ''
            charset = charset or msg.get_content_charset() or 'utf-8'
        else:
            charset = charset or 'utf-8'

        if not isinstance(value, unicode):
            # Already a str! Oh shit, might be nasty binary data.
            value = self.try_decode(value, charset, replace='?')

        # At this point we know we have a unicode string. Next we try
        # to very stubbornly decode and discover character sets.
        if '=?' in value and '?=' in value:
            try:
                # decode_header wants an unquoted str (not unicode)
                value = value.encode('utf-8').replace('"', '')
                # decode_header gets confused by newlines
                value = value.replace('\r', ' ').replace('\n', ' ')
                # Decode!
                pairs = email.header.decode_header(value)
                value = ' '.join([self.try_decode(t, cs or charset)
                                  for t, cs in pairs])
            except email.errors.HeaderParseError:
                pass

        # Finally, return the unicode data, with white-space normalized
        return value.replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')

    def _remove_location(self, session, msg_ptr):
        msg_idx_pos = self.PTRS[msg_ptr]
        del self.PTRS[msg_ptr]

        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        msg_ptrs = [p for p in msg_info[self.MSG_PTRS].split(',')
                    if p != msg_ptr]

        msg_info[self.MSG_PTRS] = ','.join(msg_ptrs)
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def _update_location(self, session, msg_idx_pos, msg_ptr):
        if 'rescan' in session.config.sys.debug:
            session.ui.debug('Moved? %s -> %s' % (b36(msg_idx_pos), msg_ptr))

        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        msg_ptrs = msg_info[self.MSG_PTRS].split(',')
        self.PTRS[msg_ptr] = msg_idx_pos

        # If message was seen in this mailbox before, update the location
        for i in range(0, len(msg_ptrs)):
            if msg_ptrs[i][:MBX_ID_LEN] == msg_ptr[:MBX_ID_LEN]:
                msg_ptrs[i] = msg_ptr
                msg_ptr = None
                break
        # Otherwise, this is a new mailbox, record this sighting as well!
        if msg_ptr:
            msg_ptrs.append(msg_ptr)

        msg_info[self.MSG_PTRS] = ','.join(msg_ptrs)
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def _parse_date(self, date_hdr):
        """Parse a Date: or Received: header into a unix timestamp."""
        try:
            if ';' in date_hdr:
                date_hdr = date_hdr.split(';')[-1].strip()
            msg_ts = long(rfc822.mktime_tz(rfc822.parsedate_tz(date_hdr)))
            if (msg_ts > (time.time() + 24 * 3600)) or (msg_ts < 1):
                return None
            else:
                return msg_ts
        except (ValueError, TypeError, OverflowError):
            return None

    def _extract_date_ts(self, session, msg_mid, msg_id, msg, default):
        """Extract a date, sanity checking against the Received: headers."""
        hdrs = [self.hdr(msg, 'date')] + (msg.get_all('received') or [])
        dates = [self._parse_date(date_hdr) for date_hdr in hdrs]
        msg_ts = dates[0]
        nz_dates = sorted([d for d in dates if d])

        if nz_dates:
            a_week = 7 * 24 * 3600

            # Ideally, we compare with the date on the 2nd SMTP relay, as
            # the first will often be the same host as composed the mail
            # itself. If we don't have enough hops, just use the last one.
            #
            # We don't want to use a median or average, because if the
            # message bounces around lots of relays or gets resent, we
            # want to ignore the latter additions.
            #
            rcv_ts = nz_dates[min(len(nz_dates)-1, 2)]

            # Now, if everything is normal, the msg_ts will be at nz_dates[0]
            # and it won't be too far away from our reference date.
            if (msg_ts == nz_dates[0]) and (abs(msg_ts - rcv_ts) < a_week):
                # Note: Trivially true for len(nz_dates) in (1, 2)
                return msg_ts

            # Damn, dates are screwy!
            #
            # Maybe one of the SMTP servers has a wrong clock?  If the Date:
            # header falls within the range of all detected dates (plus a
            # week towards the past), still trust it.
            elif ((msg_ts >= (nz_dates[0]-a_week))
                    and (msg_ts <= nz_dates[-1])):
                return msg_ts

            # OK, Date: is insane, use one of the early Received: lines
            # instead.  We picked the 2nd one above, that should do.
            else:
                session.ui.warning(_('=%s/%s using Received: instead of Date:'
                                     ) % (msg_mid, msg_id))
                return rcv_ts
        else:
            # If the above fails, we assume the messages in the mailbox are in
            # chronological order and just add 1 second to the date of the last
            # message if date parsing fails for some reason.
            session.ui.warning(_('=%s/%s has a bogus date'
                                 ) % (msg_mid, msg_id))
            return (default or int(time.time()-1))

    def encode_msg_id(self, msg_id):
        return b64c(sha1b64(msg_id.strip()))

    def get_msg_id(self, msg, msg_ptr):
        raw_msg_id = self.hdr(msg, 'message-id')
        if not raw_msg_id:
            # Create a very long pseudo-msgid for messages without a
            # Message-ID. This was a very badly behaved mailer, so if
            # we create duplicates this way, we are probably only
            # losing spam. Even then the Received line should save us.
            raw_msg_id = ('\t'.join([self.hdr(msg, 'date'),
                                     self.hdr(msg, 'subject'),
                                     self.hdr(msg, 'received'),
                                     self.hdr(msg, 'from'),
                                     self.hdr(msg, 'to')])).strip()
        # Fall back to the msg_ptr if all else fails.
        if not raw_msg_id:
            print _('WARNING: No proper Message-ID for %s') % msg_ptr
        return self.encode_msg_id(raw_msg_id or msg_ptr)

    def _get_scan_progress(self, mailbox_idx, event=None, reset=False):
        if event and 'rescans' not in event.data:
            event.data['rescans'] = []
            if reset:
                event.data['rescan'] = {}
            progress = event.data['rescan']
        else:
            progress = {}
            reset = True
        if reset:
            progress.update({
                'running': True,
                'complete': False,
                'mailbox_id': mailbox_idx,
                'errors': [],
                'added': 0,
                'updated': 0,
                'total': 0,
                'batch_size': 0
            })
        return progress

    def scan_mailbox(self, session, mailbox_idx, mailbox_fn, mailbox_opener,
                     process_new=None, apply_tags=None, stop_after=None,
                     editable=False, event=None):
        mailbox_idx = FormatMbxId(mailbox_idx)
        progress = self._get_scan_progress(mailbox_idx,
                                           event=event, reset=True)

        def finito(code, message, **kwargs):
            if event:
                event.data['rescans'].append(
                    (mailbox_idx, code, message, kwargs))
                progress['running'] = False
                if 'complete' in kwargs:
                    progress['complete'] = kwargs['complete']
            session.ui.mark(message)
            return code

        try:
            mbox = mailbox_opener(session, mailbox_idx)
            if mbox.editable != editable:
                return finito(0, _('%s: Skipped: %s'
                                   ) % (mailbox_idx, mailbox_fn))
            else:
                session.ui.mark(_('%s: Checking: %s'
                                  ) % (mailbox_idx, mailbox_fn))
                mbox.update_toc()
        except (IOError, OSError, ValueError, NoSuchMailboxError), e:
            if 'rescan' in session.config.sys.debug:
                session.ui.debug(traceback.format_exc())
            return finito(-1, _('%s: Error opening: %s (%s)'
                                ) % (mailbox_idx, mailbox_fn, e),
                          error=True)

        if len(self.PTRS.keys()) == 0:
            self.update_ptrs_and_msgids(session)

        existing_ptrs = set()
        messages = sorted(mbox.keys())
        messages_md5 = md5_hex(str(messages))
        if messages_md5 == self._scanned.get(mailbox_idx, ''):
            return finito(0, _('%s: No new mail in: %s'
                               ) % (mailbox_idx, mailbox_fn),
                          complete=True)

        parse_fmt1 = _('%s: Reading your mail: %d%% (%d/%d message)')
        parse_fmtn = _('%s: Reading your mail: %d%% (%d/%d messages)')
        def parse_status(ui):
            n = len(messages)
            return ((n == 1) and parse_fmt1 or parse_fmtn
                    ) % (mailbox_idx, 100 * ui / n, ui, n)

        progress.update({
            'total': len(messages),
            'batch_size': stop_after or len(messages)
        })

        # Figure out which messages exist at all (so we can remove
        # stale pointers later on).
        for ui in range(0, len(messages)):
            msg_ptr = mbox.get_msg_ptr(mailbox_idx, messages[ui])
            existing_ptrs.add(msg_ptr)
            if (ui % 317) == 0:
                play_nice_with_threads()

        added = updated = 0
        last_date = long(time.time())
        not_done_yet = 'NOT DONE YET'
        for ui in range(0, len(messages)):
            if mailpile.util.QUITTING or self.interrupt:
                self.interrupt = None
                return finito(-1, _('Rescan interrupted: %s'
                                    ) % self.interrupt)
            if stop_after and added >= stop_after:
                messages_md5 = not_done_yet
                break

            i = messages[ui]
            msg_ptr = mbox.get_msg_ptr(mailbox_idx, i)
            if msg_ptr in self.PTRS:
                if (ui % 317) == 0:
                    session.ui.mark(parse_status(ui))
                elif (ui % 129) == 0:
                    play_nice_with_threads()
                continue
            else:
                session.ui.mark(parse_status(ui))

            # Message new or modified, let's parse it.
            try:
                last_date, a, u = self.scan_one_message(session,
                                                        mailbox_idx, mbox, i,
                                                        wait=True,
                                                        msg_ptr=msg_ptr,
                                                        last_date=last_date,
                                                        process_new=process_new,
                                                        apply_tags=apply_tags,
                                                        stop_after=stop_after,
                                                        editable=editable,
                                                        event=event,
                                                        progress=progress)
            except TypeError:
                a = u = 0

            added += a
            updated += u

        with self._lock:
            for msg_ptr in self.PTRS.keys():
                if (msg_ptr[:MBX_ID_LEN] == mailbox_idx and
                        msg_ptr not in existing_ptrs):
                    self._remove_location(session, msg_ptr)
                    updated += 1
        progress.update({
            'added': added,
            'updated': updated,
        })
        play_nice_with_threads()

        self._scanned[mailbox_idx] = messages_md5
        short_fn = '/'.join(mailbox_fn.split('/')[-2:])
        return finito(added,
                      _('%s: Indexed mailbox: ...%s (%d new, %d updated)'
                        ) % (mailbox_idx, short_fn, added, updated),
                      new=added,
                      updated=updated,
                      complete=(messages_md5 != not_done_yet))

    def scan_one_message(self, session, mailbox_idx, mbox, msg_mbox_key,
                         wait=False, **kwargs):
        args = [session, mailbox_idx, mbox, msg_mbox_key]
        task = 'scan:%s/%s' % (mailbox_idx, msg_mbox_key)
        if wait:
            return session.config.scan_worker.do(
                session, task, lambda: self._real_scan_one(*args, **kwargs))
        else:
            session.config.scan_worker.add_task(
                session, task, lambda: self._real_scan_one(*args, **kwargs))
            return 0, 0, 0

    def _real_scan_one(self, session,
                       mailbox_idx, mbox, msg_mbox_idx,
                       msg_ptr=None, msg_data=None, last_date=None,
                       process_new=None, apply_tags=None, stop_after=None,
                       editable=False, event=None, progress=None):
        added = updated = 0
        msg_ptr = msg_ptr or mbox.get_msg_ptr(mailbox_idx, msg_mbox_idx)
        last_date = last_date or long(time.time())
        progress = progress or self._get_scan_progress(mailbox_idx,
                                                       event=event)

        if 'rescan' in session.config.sys.debug:
            session.ui.debug('Reading message %s/%s'
                             % (mailbox_idx, msg_mbox_idx))
        try:
            if msg_data:
                msg_fd = cStringIO.StringIO(msg_data)
            else:
                msg_fd = mbox.get_file(msg_mbox_idx)
            msg = ParseMessage(msg_fd,
                               pgpmime=session.config.prefs.index_encrypted,
                               config=session.config)
        except (IOError, OSError, ValueError, IndexError, KeyError):
            if session.config.sys.debug:
                traceback.print_exc()
            progress['errors'].append(msg_mbox_idx)
            session.ui.warning(('Reading message %s/%s FAILED, skipping'
                                ) % (mailbox_idx, msg_mbox_idx))
            return last_date, added, updated

        msg_id = self.get_msg_id(msg, msg_ptr)
        if msg_id in self.MSGIDS:
            with self._lock:
                self._update_location(session, self.MSGIDS[msg_id], msg_ptr)
                updated += 1
        else:
            msg_info = self._index_incoming_message(
                session, msg_id, msg_ptr, msg_fd.tell(), msg,
                last_date + 1, mailbox_idx, process_new, apply_tags)
            last_date = long(msg_info[self.MSG_DATE], 36)
            added += 1

        play_nice_with_threads()
        progress['added'] += added
        progress['updated'] += updated
        return last_date, added, updated

    def edit_msg_info(self, msg_info,
                      msg_mid=None, raw_msg_id=None, msg_id=None, msg_ts=None,
                      msg_from=None, msg_subject=None, msg_body=None,
                      msg_to=None, msg_cc=None, msg_tags=None):
        if msg_mid is not None:
            msg_info[self.MSG_MID] = msg_mid
        if raw_msg_id is not None:
            msg_info[self.MSG_ID] = self.encode_msg_id(raw_msg_id)
        if msg_id is not None:
            msg_info[self.MSG_ID] = msg_id
        if msg_ts is not None:
            msg_info[self.MSG_DATE] = b36(msg_ts)
        if msg_from is not None:
            msg_info[self.MSG_FROM] = msg_from
        if msg_subject is not None:
            msg_info[self.MSG_SUBJECT] = msg_subject
        if msg_body is not None:
            msg_info[self.MSG_BODY] = msg_body
        if msg_to is not None:
            msg_info[self.MSG_TO] = self.compact_to_list(msg_to or [])
        if msg_cc is not None:
            msg_info[self.MSG_CC] = self.compact_to_list(msg_cc or [])
        if msg_tags is not None:
            msg_info[self.MSG_TAGS] = ','.join(msg_tags or [])
        return msg_info

    # FIXME: Finish merging this function with the one below it...
    def _extract_info_and_index(self, session, mailbox_idx,
                                msg_mid, msg_id,
                                msg_size, msg, default_date,
                                **index_kwargs):
        # Extract info from the message headers
        msg_ts = self._extract_date_ts(session, msg_mid, msg_id, msg,
                                       default_date)
        msg_to = AddressHeaderParser(msg.get('to', ''))
        msg_cc = (AddressHeaderParser(msg.get('cc', '')) +
                  AddressHeaderParser(msg.get('bcc', '')))
        msg_subj = self.hdr(msg, 'subject')

        filters = _plugins.get_filter_hooks([self.filter_keywords])
        kw, bi = self.index_message(session, msg_mid, msg_id,
                                    msg, msg_size, msg_ts,
                                    mailbox=mailbox_idx,
                                    compact=False,
                                    filter_hooks=filters,
                                    **index_kwargs)

        snippet_max = session.config.sys.snippet_max
        self.truncate_body_snippet(bi, max(0, snippet_max - len(msg_subj)))
        msg_body = self.encode_body(bi)

        tags = [k.split(':')[0] for k in kw
                if k.endswith(':in') or k.endswith(':tag')]

        return (msg_ts, msg_to, msg_cc, msg_subj, msg_body, tags)

    def _index_incoming_message(self, session,
                                msg_id, msg_ptr, msg_size, msg, default_date,
                                mailbox_idx, process_new, apply_tags):
        # First, add the message to the index so we can index terms to
        # the right MID.
        msg_idx_pos, msg_info = self.add_new_msg(
            msg_ptr, msg_id, default_date, self.hdr(msg, 'from'), [], [],
            msg_size, _('(processing message ...)'), '', [])
        msg_mid = b36(msg_idx_pos)

        # Now actually go parse it and update the search index
        (msg_ts, msg_to, msg_cc, msg_subj, msg_body, tags
         ) = self._extract_info_and_index(session, mailbox_idx,
                                          msg_mid, msg_id, msg_size, msg,
                                          default_date,
                                          process_new=process_new,
                                          apply_tags=apply_tags,
                                          incoming=True)

        # Finally, update the metadata index with whatever we learned
        self.edit_msg_info(msg_info,
                           msg_ts=msg_ts,
                           msg_to=msg_to,
                           msg_cc=msg_cc,
                           msg_subject=msg_subj,
                           msg_body=msg_body,
                           msg_tags=tags)

        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)
        self.set_conversation_ids(msg_info[self.MSG_MID], msg)
        return msg_info

    def index_email(self, session, email):
        # Extract info from the email object...
        msg = email.get_msg(pgpmime=session.config.prefs.index_encrypted,
                            crypto_state_feedback=False)
        msg_mid = email.msg_mid()
        msg_info = email.get_msg_info()
        msg_size = email.get_msg_size()
        msg_id = msg_info[self.MSG_ID]
        mailbox_idx = msg_info[self.MSG_PTRS].split(',')[0][:MBX_ID_LEN]
        default_date = long(msg_info[self.MSG_DATE], 36)

        (msg_ts, msg_to, msg_cc, msg_subj, msg_body, tags
         ) = self._extract_info_and_index(session, mailbox_idx,
                                          msg_mid, msg_id, msg_size, msg,
                                          default_date,
                                          incoming=False)
        self.edit_msg_info(msg_info,
                           msg_ts=msg_ts,
                           msg_from=self.hdr(msg, 'from'),
                           msg_to=msg_to,
                           msg_cc=msg_cc,
                           msg_subject=msg_subj,
                           msg_body=msg_body)

        self.set_msg_at_idx_pos(email.msg_idx_pos, msg_info)

        # Reset the internal tags on this message
        for tag_id in self.get_tags(msg_info=msg_info):
            tag = session.config.get_tag(tag_id)
            if tag and tag.slug.startswith('mp_'):
                self.remove_tag(session, tag_id, msg_idxs=[email.msg_idx_pos])

        # Add normal tags implied by a rescan
        for tag_id in tags:
            self.add_tag(session, tag_id, msg_idxs=[email.msg_idx_pos])

    def set_conversation_ids(self, msg_mid, msg, subject_threading=True):
        msg_thr_mid = None
        refs = set((self.hdr(msg, 'references') + ' ' +
                    self.hdr(msg, 'in-reply-to')
                    ).replace(',', ' ').strip().split())
        for ref_id in [self.encode_msg_id(r) for r in refs if r]:
            try:
                # Get conversation ID ...
                ref_idx_pos = self.MSGIDS[ref_id]
                msg_thr_mid = self.get_msg_at_idx_pos(ref_idx_pos
                                                      )[self.MSG_THREAD_MID]
                # Update root of conversation thread
                parent = self.get_msg_at_idx_pos(int(msg_thr_mid, 36))
                replies = parent[self.MSG_REPLIES][:-1].split(',')
                if msg_mid not in replies:
                    replies.append(msg_mid)
                parent[self.MSG_REPLIES] = ','.join(replies) + ','
                self.set_msg_at_idx_pos(int(msg_thr_mid, 36), parent)
                break
            except (KeyError, ValueError, IndexError):
                pass

        msg_idx_pos = int(msg_mid, 36)
        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)

        if subject_threading and not msg_thr_mid and not refs:
            # Can we do plain GMail style subject-based threading?
            # FIXME: Is this too aggressive? Make configurable?
            subj = msg_info[self.MSG_SUBJECT].lower()
            subj = subj.replace('re: ', '').replace('fwd: ', '')
            date = long(msg_info[self.MSG_DATE], 36)
            if subj.strip() != '':
                for midx in reversed(range(max(0, msg_idx_pos - 250),
                                           msg_idx_pos)):
                    try:
                        m_info = self.get_msg_at_idx_pos(midx)
                        if m_info[self.MSG_SUBJECT
                                  ].lower().replace('re: ', '') == subj:
                            msg_thr_mid = m_info[self.MSG_THREAD_MID]
                            parent = self.get_msg_at_idx_pos(int(msg_thr_mid,
                                                                 36))
                            replies = parent[self.MSG_REPLIES][:-1].split(',')
                            if len(replies) < 100:
                                if msg_mid not in replies:
                                    replies.append(msg_mid)
                                parent[self.MSG_REPLIES] = (','.join(replies)
                                                            + ',')
                                self.set_msg_at_idx_pos(int(msg_thr_mid, 36),
                                                        parent)
                                break
                        if date - long(m_info[self.MSG_DATE],
                                       36) > 5 * 24 * 3600:
                            break
                    except (KeyError, ValueError, IndexError):
                        pass

        if not msg_thr_mid:
            # OK, we are our own conversation root.
            msg_thr_mid = msg_mid

        msg_info[self.MSG_THREAD_MID] = msg_thr_mid
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def unthread_message(self, msg_mid):
        msg_idx_pos = int(msg_mid, 36)
        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        par_idx_pos = int(msg_info[self.MSG_THREAD_MID], 36)

        if par_idx_pos == msg_idx_pos:
            # Message is head of thread, chop head off!
            thread = msg_info[self.MSG_REPLIES][:-1].split(',')
            msg_info[self.MSG_REPLIES] = ''
            if msg_mid in thread:
                thread.remove(msg_mid)
            if thread and thread[0]:
                head_mid = thread[0]
                head_idx_pos = int(head_mid, 36)
                head_info = self.get_msg_at_idx_pos(head_idx_pos)
                head_info[self.MSG_REPLIES] = ','.join(thread) + ','
                self.set_msg_at_idx_pos(head_idx_pos, head_info)
                for msg_mid in thread:
                    kid_idx_pos = int(thread[0], 36)
                    kid_info = self.get_msg_at_idx_pos(head_idx_pos)
                    kid_info[self.MSG_THREAD_MID] = head_mid
                    kid.set_msg_at_idx_pos(head_idx_pos, head_info)
        else:
            # Message is a reply, remove it from thread
            par_info = self.get_msg_at_idx_pos(par_idx_pos)
            thread = par_info[self.MSG_REPLIES][:-1].split(',')
            if msg_mid in thread:
                thread.remove(msg_mid)
                par_info[self.MSG_REPLIES] = ','.join(thread) + ','
                self.set_msg_at_idx_pos(par_idx_pos, par_info)

        msg_info[self.MSG_THREAD_MID] = msg_mid
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def _add_email(self, email, name=None, eid=None):
        if eid is None:
            eid = len(self.EMAILS)
            self.EMAILS.append('')
        self.EMAILS[eid] = '%s (%s)' % (email, name or email)
        self.EMAIL_IDS[email.lower()] = eid
        # FIXME: This needs to get written out...
        return eid

    def update_email(self, email, name=None):
        eid = self.EMAIL_IDS.get(email.lower())
        return self._add_email(email, name=name, eid=eid)

    def compact_to_list(self, msg_to):
        eids = []
        for ai in msg_to:
            email = ai.address
            eid = self.EMAIL_IDS.get(email.lower())
            if eid is None:
                eid = self._add_email(email, name=ai.fn)
            elif ai.fn and ai.fn != email:
                self.update_email(email, name=ai.fn)
            eids.append(eid)
        return ','.join([b36(e) for e in set(eids)])

    def expand_to_list(self, msg_info, field=None):
        eids = msg_info[field if (field is not None) else self.MSG_TO]
        eids = [e for e in eids.strip().split(',') if e]
        return [self.EMAILS[int(e, 36)] for e in eids]

    def add_new_msg(self, msg_ptr, msg_id, msg_ts, msg_from,
                    msg_to, msg_cc, msg_bytes, msg_subject, msg_body,
                    tags):
        with self._lock:
            msg_idx_pos = len(self.INDEX)
            msg_mid = b36(msg_idx_pos)
            # FIXME: Refactor this to use edit_msg_info.
            msg_info = [
                msg_mid,                             # Index ID
                msg_ptr,                             # Location on disk
                msg_id,                              # Message ID
                b36(msg_ts),                         # Date as UTC timstamp
                msg_from,                            # From:
                self.compact_to_list(msg_to or []),  # To:
                self.compact_to_list(msg_cc or []),  # Cc:
                b36(msg_bytes // 1024),              # KB
                msg_subject,                         # Subject:
                msg_body,                            # Snippet etc.
                ','.join(tags),                      # Initial tags
                '',                                  # No replies for now
                msg_mid                              # Conversation ID
            ]
            email, fn = ExtractEmailAndName(msg_from)
            if email and fn:
                self.update_email(email, name=fn)
            self.set_msg_at_idx_pos(msg_idx_pos, msg_info)
            return msg_idx_pos, msg_info

    def filter_keywords(self, session, msg_mid, msg, keywords, incoming=True):
        keywordmap = {}
        msg_idx_list = [msg_mid]
        for kw in keywords:
            keywordmap[unicode(kw)] = msg_idx_list

        import mailpile.plugins.tags
        ftypes = set(mailpile.plugins.tags.FILTER_TYPES)
        if not incoming:
            ftypes -= set(['incoming'])

        for (fid, terms, tags, comment, ftype
             ) in session.config.get_filters(types=ftypes):
            if (terms == '*' or
                    len(self.search(None, terms.split(),
                                    keywords=keywordmap)) > 0):
                for t in tags.split():
                    for fmt in ('%s:in', '%s:tag'):
                        kw = unicode(fmt % t[1:])
                        if kw in keywordmap:
                            del keywordmap[kw]
                    if t[0] != '-':
                        keywordmap[unicode('%s:in' % t[1:])] = msg_idx_list

        return set(keywordmap.keys())

    def apply_filters(self, session, filter_on, msg_mids=None, msg_idxs=None):
        if msg_idxs is None:
            msg_idxs = [int(mid, 36) for mid in msg_mids]
        if not msg_idxs:
            return
        for fid, trms, tags, c, t in session.config.get_filters(
                filter_on=filter_on):
            for t in tags.split():
                tag_id = t[1:].split(':')[0]
                if t[0] == '-':
                    self.remove_tag(session, tag_id, msg_idxs=set(msg_idxs))
                else:
                    self.add_tag(session, tag_id, msg_idxs=set(msg_idxs))

    def read_message(self, session,
                     msg_mid, msg_id, msg, msg_size, msg_ts,
                     mailbox=None):
        keywords = []
        snippet_text = snippet_html = ''
        body_info = {}
        payload = [None]
        textparts = 0
        for part in msg.walk():
            textpart = payload[0] = None
            ctype = part.get_content_type()
            charset = part.get_content_charset() or 'utf-8'

            def _loader(p):
                if payload[0] is None:
                    payload[0] = self.try_decode(p.get_payload(None, True),
                                                 charset)
                return payload[0]

            if ctype == 'text/plain':
                textpart = _loader(part)
                if textpart[:3] in ('<di', '<ht', '<p>', '<p '):
                    ctype = 'text/html'
                else:
                    textparts += 1

            if ctype == 'text/html':
                _loader(part)
                if len(payload[0]) > 3:
                    try:
                        textpart = lxml.html.fromstring(payload[0]
                                                        ).text_content()
                    except:
                        session.ui.warning(_('=%s/%s has bogus HTML.'
                                             ) % (msg_mid, msg_id))
                        textpart = payload[0]
                else:
                    textpart = payload[0]

            if 'pgp' in part.get_content_type().lower():
                keywords.append('pgp:has')
                keywords.append('crypto:has')

            att = part.get_filename()
            if att:
                att = self.try_decode(att, charset)
                # FIXME: These should be tags!
                keywords.append('attachment:has')
                keywords.extend([t + ':att' for t
                                 in re.findall(WORD_REGEXP, att.lower())])
                textpart = (textpart or '') + ' ' + att

            if textpart:
                # FIXME: Does this lowercase non-ASCII characters correctly?
                keywords.extend(re.findall(WORD_REGEXP, textpart.lower()))

                # NOTE: As a side effect here, the cryptostate plugin will
                #       add a 'crypto:has' keyword which we check for below
                #       before performing further processing.
                for kwe in _plugins.get_text_kw_extractors():
                    keywords.extend(kwe(self, msg, ctype, textpart))

                if ctype == 'text/plain':
                    snippet_text += textpart.strip() + '\n'
                else:
                    snippet_html += textpart.strip() + '\n'

            for extract in _plugins.get_data_kw_extractors():
                keywords.extend(extract(self, msg, ctype, att, part,
                                        lambda: _loader(part)))

        if textparts == 0:
            keywords.append('text:missing')

        if 'crypto:has' in keywords:
            e = Email(self, -1,
                      msg_parsed=msg,
                      msg_parsed_pgpmime=msg,
                      msg_info=self.BOGUS_METADATA[:])
            tree = e.get_message_tree(want=(e.WANT_MSG_TREE_PGP +
                                            ('text_parts', )))

            # Look for inline PGP parts, update our status if found
            e.evaluate_pgp(tree, decrypt=session.config.prefs.index_encrypted,
                                 crypto_state_feedback=False)
            msg.signature_info = tree['crypto']['signature']
            msg.encryption_info = tree['crypto']['encryption']

            # Index the contents, if configured to do so
            if session.config.prefs.index_encrypted:
                for text in [t['data'] for t in tree['text_parts']]:
                    keywords.extend(re.findall(WORD_REGEXP, text.lower()))
                    for kwe in _plugins.get_text_kw_extractors():
                        keywords.extend(kwe(self, msg, 'text/plain', text))

        keywords.append('%s:id' % msg_id)
        keywords.extend(re.findall(WORD_REGEXP,
                                   self.hdr(msg, 'subject').lower()))
        keywords.extend(re.findall(WORD_REGEXP,
                                   self.hdr(msg, 'from').lower()))
        if mailbox:
            keywords.append('%s:mailbox' % FormatMbxId(mailbox).lower())
        keywords.append('%s:hp' % HeaderPrint(msg))

        for key in msg.keys():
            key_lower = key.lower()
            if key_lower not in BORING_HEADERS:
                emails = ExtractEmails(self.hdr(msg, key).lower())
                words = set(re.findall(WORD_REGEXP,
                                       self.hdr(msg, key).lower()))
                words -= STOPLIST
                keywords.extend(['%s:%s' % (t, key_lower) for t in words])
                keywords.extend(['%s:%s' % (e, key_lower) for e in emails])
                keywords.extend(['%s:email' % e for e in emails])
                if 'list' in key_lower:
                    keywords.extend(['%s:list' % t for t in words])
        for key in EXPECTED_HEADERS:
            if not msg[key]:
                keywords.append('%s:missing' % key)

        for extract in _plugins.get_meta_kw_extractors():
            keywords.extend(extract(self, msg_mid, msg, msg_size, msg_ts))

        # FIXME: Allow plugins to augment the body_info

        if snippet_text.strip() != '':
            body_info['snippet'] = self.clean_snippet(snippet_text[:1024])
        else:
            body_info['snippet'] = self.clean_snippet(snippet_html[:1024])

        return (set(keywords) - STOPLIST), body_info

    # FIXME: Here it would be nice to recognize more boilerplate junk in
    #        more languages!
    SNIPPET_JUNK_RE = re.compile(
        '(\n[^\s]+ [^\n]+(@[^\n]+|(wrote|crit|schreib)):\s+>[^\n]+'
                                                          # On .. X wrote:
        '|\n>[^\n]*'                                      # Quoted content
        '|\n--[^\n]+BEGIN PGP[^\n]+--\s+(\S+:[^\n]+\n)*'  # PGP header
        ')+')
    SNIPPET_SPACE_RE = re.compile('\s+')

    @classmethod
    def clean_snippet(self, snippet):
        # FIXME: Can we do better than this? Probably!
        return (re.sub(self.SNIPPET_SPACE_RE, ' ',
                       re.sub(self.SNIPPET_JUNK_RE, '',
                              '\n' + snippet.replace('\r', '')
                              ).split('\n--')[0])
                ).strip()

    def index_message(self, session, msg_mid, msg_id, msg, msg_size, msg_ts,
                      mailbox=None, compact=True, filter_hooks=None,
                      process_new=None, apply_tags=None, incoming=False):
        keywords, snippet = self.read_message(session,
                                              msg_mid, msg_id, msg,
                                              msg_size, msg_ts,
                                              mailbox=mailbox)

        # Apply the defaults for this mail source / mailbox.
        if apply_tags:
            keywords |= set(['%s:in' % tid for tid in apply_tags])
        if process_new:
            process_new(msg, msg_ts, keywords, snippet)
        elif incoming:
            # This is the default behavior if the above are undefined.
            if process_new is None:
                from mailpile.mail_source import ProcessNew
                ProcessNew(session, msg, msg_ts, keywords, snippet)
            if apply_tags is None:
                keywords |= set(['%s:in' % tag._key for tag in
                                 self.config.get_tags(type='inbox')])

        for hook in filter_hooks or []:
            keywords = hook(session, msg_mid, msg, keywords,
                            incoming=incoming)

        if 'keywords' in self.config.sys.debug:
            print 'KEYWORDS: %s' % keywords

        for word in keywords:
            if (word.startswith('__') or
                    # Tags are now handled outside the posting lists
                    word.endswith(':tag') or word.endswith(':in')):
                continue
            try:
                GlobalPostingList.Append(session, word, [msg_mid],
                                         compact=compact)
            except UnicodeDecodeError:
                # FIXME: we just ignore garbage
                pass

        self.config.command_cache.mark_dirty(set([u'mail:all']) | keywords)
        return keywords, snippet

    def get_msg_at_idx_pos(self, msg_idx):
        try:
            rv = self.CACHE.get(msg_idx)
            if rv is None:
                if len(self.CACHE) > 20000:
                    self.CACHE = {}
                rv = self.CACHE[msg_idx] = self.l2m(self.INDEX[msg_idx])
            if len(rv) != self.MSG_FIELDS_V2:
                raise ValueError()
            return rv
        except (IndexError, ValueError):
            return self.BOGUS_METADATA[:]

    def update_msg_sorting(self, msg_idx, msg_info):
        for order, sorter in self.SORT_ORDERS.iteritems():
            self.INDEX_SORT[order][msg_idx] = sorter(self, msg_info)

    def set_msg_at_idx_pos(self, msg_idx, msg_info, original_line=None):
        with self._lock:
            while len(self.INDEX) <= msg_idx:
                self.INDEX.append('')
                self.INDEX_THR.append(-1)
                for order in self.INDEX_SORT:
                    self.INDEX_SORT[order].append(0)

        msg_thr_mid = msg_info[self.MSG_THREAD_MID]
        self.INDEX[msg_idx] = original_line or self.m2l(msg_info)
        self.INDEX_THR[msg_idx] = int(msg_thr_mid, 36)
        self.MSGIDS[msg_info[self.MSG_ID]] = msg_idx
        for msg_ptr in msg_info[self.MSG_PTRS].split(','):
            self.PTRS[msg_ptr] = msg_idx
        self.update_msg_sorting(msg_idx, msg_info)
        self.update_msg_tags(msg_idx, msg_info)

        if not original_line:
            dirty_tags = [u'%s:in' % self.config.tags[t].slug for t in
                          self.get_tags(msg_info=msg_info)]
            self.config.command_cache.mark_dirty(
                [u'mail:all', u'%s:msg' % msg_idx,
                 u'%s:thread' % int(msg_thr_mid, 36)] + dirty_tags)
            CachedSearchResultSet.DropCaches(msg_idxs=[msg_idx])
            self.MODIFIED.add(msg_idx)
            try:
                del self.CACHE[msg_idx]
            except KeyError:
                pass

    def get_conversation(self, msg_info=None, msg_idx=None):
        if not msg_info:
            msg_info = self.get_msg_at_idx_pos(msg_idx)
        conv_mid = msg_info[self.MSG_THREAD_MID]
        if conv_mid:
            return ([self.get_msg_at_idx_pos(int(conv_mid, 36))] +
                    self.get_replies(msg_idx=int(conv_mid, 36)))
        else:
            return [msg_info]

    def get_replies(self, msg_info=None, msg_idx=None):
        if not msg_info:
            msg_info = self.get_msg_at_idx_pos(msg_idx)
        return [self.get_msg_at_idx_pos(int(r, 36)) for r
                in msg_info[self.MSG_REPLIES].split(',') if r]

    def get_tags(self, msg_info=None, msg_idx=None):
        if not msg_info:
            msg_info = self.get_msg_at_idx_pos(msg_idx)
        taglist = [r for r in msg_info[self.MSG_TAGS].split(',') if r]
        if not 'tags' in self.config:
            return taglist
        return [r for r in taglist if r in self.config.tags]

    def add_tag(self, session, tag_id,
                msg_info=None, msg_idxs=None, conversation=False):
        if msg_info and msg_idxs is None:
            msg_idxs = set([int(msg_info[self.MSG_MID], 36)])
        else:
            msg_idxs = set(msg_idxs)
        if not msg_idxs:
            return set()
        CachedSearchResultSet.DropCaches()
        session.ui.mark(_n('Tagging %d message (%s)',
                           'Tagging %d messages (%s)',
                           len(msg_idxs)
                           ) % (len(msg_idxs), tag_id))
        for msg_idx in list(msg_idxs):
            if conversation:
                for reply in self.get_conversation(msg_idx=msg_idx):
                    if reply[self.MSG_MID]:
                        msg_idxs.add(int(reply[self.MSG_MID], 36))
        eids = set()
        added = set()
        threads = set()
        for msg_idx in msg_idxs:
            if msg_idx >= 0 and msg_idx < len(self.INDEX):
                msg_info = self.get_msg_at_idx_pos(msg_idx)
                tags = set([r for r in msg_info[self.MSG_TAGS].split(',')
                            if r])
                if tag_id not in tags:
                    tags.add(tag_id)
                    msg_info[self.MSG_TAGS] = ','.join(list(tags))
                    self.INDEX[msg_idx] = self.m2l(msg_info)
                    self.MODIFIED.add(msg_idx)
                    self.update_msg_sorting(msg_idx, msg_info)
                    added.add(msg_idx)
                    threads.add(msg_info[self.MSG_THREAD_MID])
                eids.add(msg_idx)
        with self._lock:
            if tag_id in self.TAGS:
                self.TAGS[tag_id] |= eids
            elif eids:
                self.TAGS[tag_id] = eids
        try:
            self.config.command_cache.mark_dirty(
                [u'mail:all', u'%s:in' % self.config.tags[tag_id].slug] +
                [u'%s:msg' % e_idx for e_idx in added] +
                [u'%s:thread' % int(mid, 36) for mid in threads])
        except:
            pass
        return added

    def remove_tag(self, session, tag_id,
                   msg_info=None, msg_idxs=None, conversation=False):
        if msg_info and msg_idxs is None:
            msg_idxs = set([int(msg_info[self.MSG_MID], 36)])
        else:
            msg_idxs = set(msg_idxs)
        if not msg_idxs:
            return set()
        CachedSearchResultSet.DropCaches()
        session.ui.mark(_n('Untagging conversation (%s)',
                           'Untagging conversations (%s)',
                           len(msg_idxs)
                           ) % (tag_id, ))
        for msg_idx in list(msg_idxs):
            if conversation:
                for reply in self.get_conversation(msg_idx=msg_idx):
                    if reply[self.MSG_MID]:
                        msg_idxs.add(int(reply[self.MSG_MID], 36))
        session.ui.mark(_n('Untagging %d message (%s)',
                           'Untagging %d messages (%s)',
                           len(msg_idxs)
                           ) % (len(msg_idxs), tag_id))
        eids = set()
        removed = set()
        threads = set()
        for msg_idx in msg_idxs:
            if msg_idx >= 0 and msg_idx < len(self.INDEX):
                msg_info = self.get_msg_at_idx_pos(msg_idx)
                tags = set([r for r in msg_info[self.MSG_TAGS].split(',')
                            if r])
                if tag_id in tags:
                    tags.remove(tag_id)
                    msg_info[self.MSG_TAGS] = ','.join(list(tags))
                    self.INDEX[msg_idx] = self.m2l(msg_info)
                    self.MODIFIED.add(msg_idx)
                    self.update_msg_sorting(msg_idx, msg_info)
                    removed.add(msg_idx)
                    threads.add(msg_info[self.MSG_THREAD_MID])
                eids.add(msg_idx)
        with self._lock:
            if tag_id in self.TAGS:
                self.TAGS[tag_id] -= eids
        try:
            self.config.command_cache.mark_dirty(
                [u'%s:in' % self.config.tags[tag_id].slug] +
                [u'%s:msg' % e_idx for e_idx in removed] +
                [u'%s:thread' % int(mid, 36) for mid in threads])
        except:
            pass
        return removed

    def search_tag(self, session, term, hits, recursion=0):
        t = term.split(':', 1)
        tag_id, tag = t[1], self.config.get_tag(t[1])
        results = []
        if tag:
            tag_id = tag._key
            for subtag in self.config.get_tags(parent=tag_id):
                results.extend(hits('%s:in' % subtag._key))
            if tag.magic_terms and recursion < 5:
                results.extend(self.search(session, [tag.magic_terms],
                                           recursion=recursion+1).as_set())
        results.extend(hits('%s:in' % tag_id))
        return results

    def search(self, session, searchterms,
               keywords=None, order=None, recursion=0, context=None):
        # Stash the raw search terms, decide if this is cached or not
        raw_terms = searchterms[:]
        if keywords is None:
            srs = CachedSearchResultSet(self, raw_terms)
            if len(srs) > 0:
                return srs
        else:
            srs = SearchResultSet(self, raw_terms, [], [])

        # Choose how we are going to search
        if keywords is not None:
            def hits(term):
                return [int(h, 36) for h in keywords.get(term, [])]
        else:
            def hits(term):
                if term.endswith(':in'):
                    return self.TAGS.get(term.rsplit(':', 1)[0], [])
                else:
                    session.ui.mark(_('Searching for %s') % term)
                    return [int(h, 36) for h
                            in GlobalPostingList(session, term).hits()]

        # Replace some GMail-compatible terms with what we really use
        if 'tags' in self.config:
            for p in ('', '+', '-'):
                while p + 'is:unread' in searchterms:
                    where = searchterms.index(p + 'is:unread')
                    new = session.config.get_tags(type='unread')
                    if new:
                        searchterms[where] = p + 'in:%s' % new[0].slug
                for t in [term for term in searchterms
                          if term.startswith(p + 'tag:')]:
                    where = searchterms.index(t)
                    searchterms[where] = p + 'in:' + t.split(':', 1)[1]

        # If first term is a negative search, prepend an all:mail
        if searchterms and searchterms[0] and searchterms[0][0] == '-':
            searchterms[:0] = ['all:mail']

        if context:
            r = [(None, set(context))]
        else:
            r = []

        for term in searchterms:
            if term in STOPLIST:
                if session:
                    session.ui.warning(_('Ignoring common word: %s') % term)
                continue

            if term[0] in ('-', '+'):
                op = term[0]
                term = term[1:]
            else:
                op = None

            r.append((op, []))
            rt = r[-1][1]
            term = term.lower()

            if ':' in term:
                if term.startswith('body:'):
                    rt.extend(hits(term[5:]))
                elif term == 'all:mail':
                    rt.extend(range(0, len(self.INDEX)))
                elif term.startswith('in:'):
                    rt.extend(self.search_tag(session, term, hits,
                                              recursion=recursion))
                else:
                    t = term.split(':', 1)
                    fnc = _plugins.get_search_term(t[0])
                    if fnc:
                        rt.extend(fnc(self.config, self, term, hits))
                    else:
                        rt.extend(hits('%s:%s' % (t[1], t[0])))
            else:
                rt.extend(hits(term))

        if r:
            results = set(r[0][1])
            for (op, rt) in r[1:]:
                if op == '+':
                    results |= set(rt)
                elif op == '-':
                    results -= set(rt)
                else:
                    results &= set(rt)
            # Sometimes the scan gets aborted...
            if keywords is None:
                results -= set([len(self.INDEX)])
        else:
            results = set()

        # Unless we are searching for invisible things, remove them from
        # results by default.
        exclude = []
        order = order or (session and session.order) or 'flat-index'
        if (results and (keywords is None) and
                ('tags' in self.config) and
                (not session or 'all' not in order)):
            invisible = self.config.get_tags(flag_hides=True)
            exclude_terms = ['in:%s' % i._key for i in invisible]
            for tag in invisible:
                tid = tag._key
                for p in ('in:%s', '+in:%s', '-in:%s'):
                    if ((p % tid) in searchterms or
                            (p % tag.name) in searchterms or
                            (p % tag.slug) in searchterms):
                        exclude_terms = []
            if len(exclude_terms) > 1:
                exclude_terms = ([exclude_terms[0]] +
                                 ['+%s' % e for e in exclude_terms[1:]])
            # Recursing to pull the excluded terms from cache as well
            exclude = self.search(session, exclude_terms).as_set()

        srs.set_results(results, exclude)
        if session:
            session.ui.mark(_n('Found %d result ',
                               'Found %d results ',
                               len(results)) % (len(results), ) +
                            _n('%d suppressed',
                               '%d suppressed',
                               len(srs.excluded())
                               ) % (len(srs.excluded()), ))
        return srs

    def _freshness_sorter(self, msg_info):
        ts = long(msg_info[self.MSG_DATE], 36)
        for tid in self.get_tags(msg_info=msg_info):
            if tid in self._sort_freshness_tags:
                return ts + self.FRESHNESS_SORT_BOOST
        return ts

    FRESHNESS_SORT_BOOST = (5 * 24 * 3600)
    SORT_ORDERS = {
        'freshness': _freshness_sorter,
        'date': lambda s, mi: long(mi[s.MSG_DATE], 36),
# FIXME: The following are disabled for now for being memory hogs
#       'from': lambda s, mi: s.mi[s.MSG_FROM]),
#       'subject': lambda s, mi: s.mi[s.MSG_SUBJECT]),
    }

    def _prepare_sorting(self):
        self._sort_freshness_tags = [tag._key for tag in
                                     self.config.get_tags(type='unread')]
        self.INDEX_SORT = {}
        for order, sorter in self.SORT_ORDERS.iteritems():
            self.INDEX_SORT[order] = []

    def sort_results(self, session, results, how):
        if not results:
            return

        count = len(results)
        how = how or 'flat-unsorted'
        session.ui.mark(_n('Sorting %d message by %s...',
                           'Sorting %d messages by %s...',
                           count
                           ) % (count, _(how)))
        try:
            if how.endswith('unsorted'):
                pass
            elif how.endswith('index'):
                results.sort()
            elif how.endswith('random'):
                now = time.time()
                results.sort(key=lambda k: sha1b64('%s%s' % (now, k)))
            else:
                did_sort = False
                for order in self.INDEX_SORT:
                    if how.endswith(order):
                        try:
                            results.sort(
                                key=self.INDEX_SORT[order].__getitem__)
                        except IndexError:
                            say = session.ui.error
                            if session.config.sys.debug:
                                traceback.print_exc()
                            for result in results:
                                if result >= len(self.INDEX) or result < 0:
                                    say(('Bogus message index: %s'
                                         ) % result)
                            say(_('Recovering from bogus sort, '
                                  'corrupt index?'))
                            say(_('Please tell team@mailpile.is !'))
                            clean_results = [r for r in results
                                             if r >= 0 and r < len(self.INDEX)]
                            clean_results.sort(
                                key=self.INDEX_SORT[order].__getitem__)
                            results[:] = clean_results
                        did_sort = True
                        break
                if not did_sort:
                    session.ui.warning(_('Unknown sort order: %s') % how)
                    return False
        except:
            if session.config.sys.debug:
                traceback.print_exc()
            session.ui.warning(_('Sort failed, sorting badly. Partial index?'))
            results.sort()

        if how.startswith('rev'):
            results.reverse()

        if 'flat' not in how:
            # This filters away all but the first result in each conversation.
            session.ui.mark(_('Collapsing conversations...'))
            seen, r2 = {}, []
            for i in range(0, len(results)):
                if self.INDEX_THR[results[i]] not in seen:
                    r2.append(results[i])
                    seen[self.INDEX_THR[results[i]]] = True
            results[:] = r2
            session.ui.mark(_n('Sorted %d message by %s',
                               'Sorted %d messages by %s',
                               count
                               ) % (count, how) +
                            ', ' +
                            _n('%d conversation',
                               '%d conversations',
                               len(results)
                               ) % (len(results), ))
        else:
            session.ui.mark(_n('Sorted %d message by %s',
                               'Sorted %d messages by %s',
                               count
                               ) % (count, _(how)))

        return True


if __name__ == '__main__':
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
