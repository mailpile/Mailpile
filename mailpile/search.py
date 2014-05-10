import email
import lxml.html
import re
import rfc822
import time
import threading
import traceback
from gettext import gettext as _
from urllib import quote, unquote

import mailpile.util
from mailpile.util import *
from mailpile.plugins import PluginManager
from mailpile.mailutils import MBX_ID_LEN, NoSuchMailboxError
from mailpile.mailutils import ExtractEmails, ExtractEmailAndName
from mailpile.mailutils import Email, ParseMessage, HeaderPrint
from mailpile.postinglist import GlobalPostingList
from mailpile.ui import *


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


class MailIndex:
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
        self._saved_changes = 0
        self._lock = threading.Lock()

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
            return json.loads(msg_info[self.MSG_BODY])
        else:
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

        def process_line(line):
            try:
                line = line.strip()
                if line.startswith('#'):
                    pass
                elif line.startswith('@'):
                    pos, email = line[1:].split('\t', 1)
                    pos = int(pos, 36)
                    while len(self.EMAILS) < pos + 1:
                        self.EMAILS.append('')
                    unquoted_email = unquote(email).decode('utf-8')
                    self.EMAILS[pos] = unquoted_email
                    self.EMAIL_IDS[unquoted_email.split()[0].lower()] = pos
                elif line:
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
                            raise Exception(_('Your metadata index is either '
                                              'too old, too new or corrupt!'))

                    pos = int(words[self.MSG_MID], 36)
                    while len(self.INDEX) < pos + 1:
                        self.INDEX.append('')

                    self.INDEX[pos] = line
                    self.MSGIDS[words[self.MSG_ID]] = pos
                    self.update_msg_tags(pos, words)
                    for msg_ptr in words[self.MSG_PTRS].split(','):
                        self.PTRS[msg_ptr] = pos

            except ValueError:
                pass

        if session:
            session.ui.mark(_('Loading metadata index...'))
        try:
            self._lock.acquire()
            with open(self.config.mailindex_file(), 'r') as fd:
                for line in fd:
                    if line.startswith(GPG_BEGIN_MESSAGE):
                        for line in decrypt_gpg([line], fd):
                            process_line(line)
                    else:
                        process_line(line)
        except IOError:
            if session:
                session.ui.warning(_('Metadata index not found: %s'
                                     ) % self.config.mailindex_file())
        finally:
            self._lock.release()

        self.cache_sort_orders(session)
        if session:
            session.ui.mark(_('Loaded metadata, %d messages'
                              ) % len(self.INDEX))
        self.EMAILS_SAVED = len(self.EMAILS)

    def update_msg_tags(self, msg_idx_pos, msg_info):
        tags = set([t for t in msg_info[self.MSG_TAGS].split(',') if t])
        for tid in (set(self.TAGS.keys()) - tags):
            self.TAGS[tid] -= set([msg_idx_pos])
        for tid in tags:
            if tid not in self.TAGS:
                self.TAGS[tid] = set()
            self.TAGS[tid].add(msg_idx_pos)

    def save_changes(self, session=None):
        mods, self.MODIFIED = self.MODIFIED, set()
        if mods or len(self.EMAILS) > self.EMAILS_SAVED:
            if self._saved_changes >= self.MAX_INCREMENTAL_SAVES:
                return self.save(session=session)
            try:
                self._lock.acquire()
                if session:
                    session.ui.mark(_("Saving metadata index changes..."))
                with gpg_open(self.config.mailindex_file(),
                              self.config.prefs.gpg_recipient, 'a') as fd:
                    for eid in range(self.EMAILS_SAVED, len(self.EMAILS)):
                        quoted_email = quote(self.EMAILS[eid].encode('utf-8'))
                        fd.write('@%s\t%s\n' % (b36(eid), quoted_email))
                    for pos in mods:
                        fd.write(self.INDEX[pos] + '\n')
                if session:
                    session.ui.mark(_("Saved metadata index changes"))
                self.EMAILS_SAVED = len(self.EMAILS)
                self._saved_changes += 1
            finally:
                self._lock.release()

    def save(self, session=None):
        try:
            self._lock.acquire()
            self.MODIFIED = set()
            if session:
                session.ui.mark(_("Saving metadata index..."))

            idxfile = self.config.mailindex_file()
            newfile = '%s.new' % idxfile

            with gpg_open(newfile, self.config.prefs.gpg_recipient, 'w') as fd:
                fd.write('# This is the mailpile.py index file.\n')
                fd.write('# We have %d messages!\n' % len(self.INDEX))
                for eid in range(0, len(self.EMAILS)):
                    quoted_email = quote(self.EMAILS[eid].encode('utf-8'))
                    fd.write('@%s\t%s\n' % (b36(eid), quoted_email))
                for item in self.INDEX:
                    fd.write(item + '\n')

            # Keep the last 5 index files around... just in case.
            backup_file(idxfile, backups=5, min_age_delta=10)
            os.rename(newfile, idxfile)

            self._saved_changes = 0
            if session:
                session.ui.mark(_("Saved metadata index"))
        finally:
            self._lock.release()

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

    def try_decode(self, text, charset):
        for cs in (charset, 'iso-8859-1', 'utf-8'):
            if cs:
                try:
                    return text.decode(cs)
                except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
                    pass
        return "".join(i for i in text if ord(i) < 128)

    def hdr(self, msg, name, value=None):
        try:
            if value is None and msg:
                # Security: RFC822 headers are not allowed to have (unencoded)
                # non-ascii characters in them, so we just strip them all out
                # before parsing.
                # FIXME: This is "safe", but can we be smarter/gentler?
                value = CleanText(msg[name], replace='_').clean
            # Note: decode_header does the wrong thing with "quoted" data.
            decoded = email.header.decode_header((value or ''
                                                  ).replace('"', ''))
            return (' '.join([self.try_decode(t[0], t[1]) for t in decoded])
                    ).replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')
        except email.errors.HeaderParseError:
            return ''

    def update_location(self, session, msg_idx_pos, msg_ptr):
        if 'rescan' in session.config.sys.debug:
            session.ui.debug('Moved? %s -> %s' % (msg_idx_pos, msg_ptr))

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

    def _extract_date_ts(self, session, msg_mid, msg_id, msg, last_date):
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
            return last_date + 1

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

    def scan_mailbox(self, session, mailbox_idx, mailbox_fn, mailbox_opener):
        try:
            mbox = mailbox_opener(session, mailbox_idx)
            if mbox.editable:
                session.ui.mark(_('%s: Skipped: %s'
                                  ) % (mailbox_idx, mailbox_fn))
                return 0
            else:
                session.ui.mark(_('%s: Checking: %s'
                                  ) % (mailbox_idx, mailbox_fn))
        except (IOError, OSError, NoSuchMailboxError), e:
            session.ui.mark(_('%s: Error opening: %s (%s)'
                              ) % (mailbox_idx, mailbox_fn, e))
            return 0

        unparsed = mbox.unparsed()
        if not unparsed:
            return 0

        if len(self.PTRS.keys()) == 0:
            self.update_ptrs_and_msgids(session)

        snippet_max = session.config.sys.snippet_max
        added = 0
        msg_ts = int(time.time())
        for ui in range(0, len(unparsed)):
            if mailpile.util.QUITTING:
                break

            i = unparsed[ui]
            parse_status = _('%s: Reading your mail: %d%% (%d/%d messages)'
                             ) % (mailbox_idx,
                                  100 * ui / len(unparsed),
                                  ui, len(unparsed))

            msg_ptr = mbox.get_msg_ptr(mailbox_idx, i)
            if msg_ptr in self.PTRS:
                if (ui % 317) == 0:
                    session.ui.mark(parse_status)
                    play_nice_with_threads()
                continue
            else:
                session.ui.mark(parse_status)
                play_nice_with_threads()

            # Message new or modified, let's parse it.
            if 'rescan' in session.config.sys.debug:
                session.ui.debug('Reading message %s/%s' % (mailbox_idx, i))
            try:
                msg_fd = mbox.get_file(i)
                msg = ParseMessage(msg_fd,
                    pgpmime=session.config.prefs.index_encrypted)
            except (IOError, OSError, ValueError, IndexError, KeyError):
                if session.config.sys.debug:
                    traceback.print_exc()
                session.ui.warning(('Reading message %s/%s FAILED, skipping'
                                    ) % (mailbox_idx, i))
                continue

            msg_size = msg_fd.tell()
            msg_id = self.get_msg_id(msg, msg_ptr)
            if msg_id in self.MSGIDS:
                self.update_location(session, self.MSGIDS[msg_id], msg_ptr)
                added += 1
            else:
                # Add new message!
                msg_mid = b36(len(self.INDEX))

                msg_ts = self._extract_date_ts(session,
                                               msg_mid, msg_id, msg, msg_ts)

                play_nice_with_threads()
                keywords, body_info = self.index_message(
                    session,
                    msg_mid, msg_id, msg, msg_size, msg_ts,
                    mailbox=mailbox_idx,
                    compact=False,
                    filter_hooks=_plugins.get_filter_hooks([self.filter_keywords]),
                    is_new=True
                )

                msg_subject = self.hdr(msg, 'subject')
                self.truncate_body_snippet(
                    body_info, max(0, snippet_max - len(msg_subject)))
                msg_body = self.encode_body(body_info)

                tags = [k.split(':')[0] for k in keywords
                        if k.endswith(':in') or k.endswith(':tag')]

                msg_to = ExtractEmails(self.hdr(msg, 'to'))
                msg_cc = (ExtractEmails(self.hdr(msg, 'cc')) +
                          ExtractEmails(self.hdr(msg, 'bcc')))

                msg_idx_pos, msg_info = self.add_new_msg(
                    msg_ptr, msg_id, msg_ts, self.hdr(msg, 'from'),
                    msg_to, msg_cc, msg_size, msg_subject, msg_body,
                    tags
                )
                self.set_conversation_ids(msg_info[self.MSG_MID], msg)
                mbox.mark_parsed(i)

                added += 1
                GlobalPostingList.Optimize(session, self,
                                           lazy=True, quick=True)

        if added:
            mbox.save(session)
        session.ui.mark(_('%s: Indexed mailbox: %s'
                          ) % (mailbox_idx, mailbox_fn))
        return added

    def edit_msg_info(self, msg_info,
                      msg_mid=None, raw_msg_id=None, msg_id=None, msg_ts=None,
                      msg_from=None, msg_subject=None, msg_body=None,
                      msg_to=None, msg_cc=None, msg_tags=None):
        if msg_mid:
            msg_info[self.MSG_MID] = msg_mid
        if raw_msg_id:
            msg_info[self.MSG_ID] = self.encode_msg_id(raw_msg_id)
        if msg_id:
            msg_info[self.MSG_ID] = msg_id
        if msg_ts:
            msg_info[self.MSG_DATE] = b36(msg_ts)
        if msg_from:
            msg_info[self.MSG_FROM] = msg_from
        if msg_subject:
            msg_info[self.MSG_SUBJECT] = msg_subject
        if msg_body:
            msg_info[self.MSG_BODY] = msg_body
        if msg_to is not None:
            msg_info[self.MSG_TO] = self.compact_to_list(msg_to or [])
        if msg_cc is not None:
            msg_info[self.MSG_CC] = self.compact_to_list(msg_cc or [])
        if msg_tags is not None:
            msg_info[self.MSG_TAGS] = ','.join(msg_tags or [])
        return msg_info

    def index_email(self, session, email):
        msg = email.get_msg(pgpmime=session.config.prefs.index_encrypted)
        msg_info = email.get_msg_info()
        mbox_idx = msg_info[self.MSG_PTRS].split(',')[0][:MBX_ID_LEN]

        msg_subj = self.hdr(msg, 'subject')
        msg_to = ExtractEmails(self.hdr(msg, 'to'))
        msg_cc = (ExtractEmails(self.hdr(msg, 'cc')) +
                  ExtractEmails(self.hdr(msg, 'bcc')))

        filters = _plugins.get_filter_hooks([self.filter_keywords])
        kw, bi = self.index_message(session,
                                    email.msg_mid(),
                                    msg_info[self.MSG_ID],
                                    msg,
                                    email.get_msg_size(),
                                    long(msg_info[self.MSG_DATE], 36),
                                    mailbox=mbox_idx,
                                    compact=False,
                                    filter_hooks=filters,
                                    is_new=False)

        snippet_max = session.config.sys.snippet_max
        self.truncate_body_snippet(bi, max(0, snippet_max - len(msg_subj)))
        msg_body = self.encode_body(bi)

        tags = [k.split(':')[0] for k in kw
                if k.endswith(':in') or k.endswith(':tag')]

        self.edit_msg_info(msg_info,
                           msg_from=self.hdr(msg, 'from'),
                           msg_to=msg_to,
                           msg_cc=msg_cc,
                           msg_subject=msg_subj,
                           msg_body=msg_body)

        self.set_msg_at_idx_pos(email.msg_idx_pos, msg_info)

        # Reset the internal tags on this message
        for tag_id in [t for t in msg_info[self.MSG_TAGS].split(',') if t]:
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
        for email in msg_to:
            eid = self.EMAIL_IDS.get(email.lower())
            if eid is None:
                eid = self._add_email(email)
            eids.append(eid)
        return ','.join([b36(e) for e in set(eids)])

    def expand_to_list(self, msg_info):
        eids = msg_info[self.MSG_TO]
        return [self.EMAILS[int(e, 36)] for e in eids.split(',') if e]

    def add_new_msg(self, msg_ptr, msg_id, msg_ts, msg_from,
                    msg_to, msg_cc, msg_bytes, msg_subject, msg_body,
                    tags):
        msg_idx_pos = len(self.INDEX)
        msg_mid = b36(msg_idx_pos)
        # FIXME: Refactor this to use edit_msg_info.
        msg_info = [
            msg_mid,                                     # Index ID
            msg_ptr,                                     # Location on disk
            msg_id,                                      # Message ID
            b36(msg_ts),                                 # Date as UTC timstamp
            msg_from,                                    # From:
            self.compact_to_list(msg_to or []),          # To:
            self.compact_to_list(msg_cc or []),          # Cc:
            b36(msg_bytes // 1024),                      # KB
            msg_subject,                                 # Subject:
            msg_body,                                    # Snippet etc.
            ','.join(tags),                              # Initial tags
            '',                                          # No replies for now
            msg_mid                                      # Conversation ID
        ]
        email, fn = ExtractEmailAndName(msg_from)
        if email and fn:
            self.update_email(email, name=fn)
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)
        return msg_idx_pos, msg_info

    def filter_keywords(self, session, msg_mid, msg, keywords, is_new=True):
        keywordmap = {}
        msg_idx_list = [msg_mid]
        for kw in keywords:
            keywordmap[unicode(kw)] = msg_idx_list

        import mailpile.plugins.tags
        ftypes = set(mailpile.plugins.tags.FILTER_TYPES)
        if not is_new:
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

    def read_message(self, session, msg_mid, msg_id, msg, msg_size, msg_ts,
                     mailbox=None):
        keywords = []
        snippet_text = snippet_html = ''
        body_info = {}
        payload = [None]
        textparts = 0
        for part in msg.walk():
            textpart = payload[0] = None
            ctype = part.get_content_type()
            charset = part.get_content_charset() or 'iso-8859-1'

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
            e.evaluate_pgp(tree, decrypt=session.config.prefs.index_encrypted)
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
            keywords.append('%s:mailbox' % mailbox.lower())
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
                      mailbox=None, compact=True, filter_hooks=[],
                      is_new=True):
        keywords, snippet = self.read_message(session,
                                              msg_mid, msg_id, msg,
                                              msg_size, msg_ts,
                                              mailbox=mailbox)

        for hook in filter_hooks:
            keywords = hook(session, msg_mid, msg, keywords, is_new=is_new)

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

        return keywords, snippet

    def get_msg_at_idx_pos(self, msg_idx):
        try:
            rv = self.CACHE.get(msg_idx)
            if rv is None:
                if len(self.CACHE) > 20000:
                    self.CACHE = {}
                rv = self.CACHE[msg_idx] = self.l2m(self.INDEX[msg_idx])
            return rv
        except IndexError:
            return self.BOGUS_METADATA[:]

    def set_msg_at_idx_pos(self, msg_idx, msg_info):
        if msg_idx < len(self.INDEX):
            self.INDEX[msg_idx] = self.m2l(msg_info)
            self.INDEX_THR[msg_idx] = int(msg_info[self.MSG_THREAD_MID], 36)
        elif msg_idx == len(self.INDEX):
            self.INDEX.append(self.m2l(msg_info))
            self.INDEX_THR.append(int(msg_info[self.MSG_THREAD_MID], 36))
        else:
            raise IndexError(_('%s is outside the index') % msg_idx)

        CachedSearchResultSet.DropCaches(msg_idxs=[msg_idx])
        self.MODIFIED.add(msg_idx)
        if msg_idx in self.CACHE:
            del(self.CACHE[msg_idx])

        for order in self.INDEX_SORT:
            # FIXME: This is where we should insert, not append.
            while msg_idx >= len(self.INDEX_SORT[order]):
                self.INDEX_SORT[order].append(msg_idx)

        self.MSGIDS[msg_info[self.MSG_ID]] = msg_idx
        for msg_ptr in msg_info[self.MSG_PTRS].split(','):
            self.PTRS[msg_ptr] = msg_idx
        self.update_msg_tags(msg_idx, msg_info)

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
        return [r for r in msg_info[self.MSG_TAGS].split(',') if r]

    def add_tag(self, session, tag_id,
                msg_info=None, msg_idxs=None, conversation=False):
        if msg_info and msg_idxs is None:
            msg_idxs = set([int(msg_info[self.MSG_MID], 36)])
        else:
            msg_idxs = set(msg_idxs)
        if not msg_idxs:
            return
        CachedSearchResultSet.DropCaches()
        session.ui.mark(_('Tagging %d messages (%s)'
                          ) % (len(msg_idxs), tag_id))
        for msg_idx in list(msg_idxs):
            if conversation:
                for reply in self.get_conversation(msg_idx=msg_idx):
                    if reply[self.MSG_MID]:
                        msg_idxs.add(int(reply[self.MSG_MID], 36))
        eids = set()
        for msg_idx in msg_idxs:
            if msg_idx >= 0 and msg_idx < len(self.INDEX):
                msg_info = self.get_msg_at_idx_pos(msg_idx)
                tags = set([r for r in msg_info[self.MSG_TAGS].split(',')
                            if r])
                tags.add(tag_id)
                msg_info[self.MSG_TAGS] = ','.join(list(tags))
                self.INDEX[msg_idx] = self.m2l(msg_info)
                self.MODIFIED.add(msg_idx)
                eids.add(msg_idx)
        if tag_id in self.TAGS:
            self.TAGS[tag_id] |= eids
        elif eids:
            self.TAGS[tag_id] = eids

    def remove_tag(self, session, tag_id,
                   msg_info=None, msg_idxs=None, conversation=False):
        if msg_info and msg_idxs is None:
            msg_idxs = set([int(msg_info[self.MSG_MID], 36)])
        else:
            msg_idxs = set(msg_idxs)
        if not msg_idxs:
            return
        CachedSearchResultSet.DropCaches()
        session.ui.mark(_('Untagging conversations (%s)') % (tag_id, ))
        for msg_idx in list(msg_idxs):
            if conversation:
                for reply in self.get_conversation(msg_idx=msg_idx):
                    if reply[self.MSG_MID]:
                        msg_idxs.add(int(reply[self.MSG_MID], 36))
        session.ui.mark(_('Untagging %d messages (%s)') % (len(msg_idxs),
                                                           tag_id))
        eids = set()
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
                eids.add(msg_idx)
        if tag_id in self.TAGS:
            self.TAGS[tag_id] -= eids

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
               keywords=None, order=None, recursion=0):
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
            session.ui.mark(_('Found %d results (%d suppressed)'
                              ) % (len(results), len(srs.excluded())))
        return srs

    def _order_freshness(self, pos):
        msg_info = self.get_msg_at_idx_pos(pos)
        ts = long(msg_info[self.MSG_DATE], 36)
        if ts > self._fresh_cutoff:
            for tid in msg_info[self.MSG_TAGS].split(','):
                if tid in self._fresh_tags:
                    return ts + self.FRESHNESS_SORT_BOOST
        return ts

    FRESHNESS_SORT_BOOST = (5 * 24 * 3600)
    CACHED_SORT_ORDERS = [
        ('freshness', True, _order_freshness),
        ('date', True,
         lambda s, k: long(s.get_msg_at_idx_pos(k)[s.MSG_DATE], 36)),
        # FIXME: The following are effectively disabled for now
        ('from', False,
         lambda s, k: s.get_msg_at_idx_pos(k)[s.MSG_FROM]),
        ('subject', False,
         lambda s, k: s.get_msg_at_idx_pos(k)[s.MSG_SUBJECT]),
    ]

    def cache_sort_orders(self, session, wanted=None):
        self._fresh_cutoff = time.time() - self.FRESHNESS_SORT_BOOST
        self._fresh_tags = [tag._key for tag in
                            session.config.get_tags(type='unread')]
        try:
            self._lock.acquire()
            keys = range(0, len(self.INDEX))
            if session:
                session.ui.mark(_('Finding conversations (%d messages)...'
                                  ) % len(keys))
            self.INDEX_THR = [
                int(self.get_msg_at_idx_pos(r)[self.MSG_THREAD_MID], 36)
                for r in keys]
            for order, by_default, sorter in self.CACHED_SORT_ORDERS:
                if (not by_default) and not (wanted and order in wanted):
                    continue
                if session:
                    session.ui.mark(_('Sorting %d messages by %s...'
                                      ) % (len(keys), _(order)))

                play_nice_with_threads()
                o = keys[:]
                o.sort(key=lambda k: sorter(self, k))
                self.INDEX_SORT[order] = keys[:]
                self.INDEX_SORT[order+'_fwd'] = o

                play_nice_with_threads()
                for i in range(0, len(o)):
                    self.INDEX_SORT[order][o[i]] = i
        finally:
            self._lock.release()

    def sort_results(self, session, results, how):
        if not results:
            return

        count = len(results)
        session.ui.mark(_('Sorting %d messages by %s...') % (count, _(how)))
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
            session.ui.mark(_('Sorted %d messages by %s, %d conversations'
                              ) % (count, how, len(results)))
        else:
            session.ui.mark(_('Sorted %d messages by %s') % (count, _(how)))

        return True
