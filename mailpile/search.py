import email
import re
import rfc822
import time
import traceback

from urllib import quote, unquote
import lxml.html

import mailpile.plugins as plugins
import mailpile.util
from mailpile.util import *
from mailpile.mailutils import MBX_ID_LEN, NoSuchMailboxError
from mailpile.mailutils import ExtractEmails, ParseMessage, HeaderPrint
from mailpile.postinglist import GlobalPostingList
from mailpile.ui import *


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
    MSG_SUBJECT = 6
    MSG_SNIPPET = 7
    MSG_TAGS = 8
    MSG_REPLIES = 9
    MSG_CONV_MID = 10

    def __init__(self, config):
        self.config = config
        self.STATS = {}
        self.INDEX = []
        self.INDEX_SORT = {}
        self.INDEX_CONV = []
        self.PTRS = {}
        self.MSGIDS = {}
        self.EMAILS = []
        self.EMAIL_IDS = {}
        self.CACHE = {}
        self.MODIFIED = set()
        self.EMAILS_SAVED = 0

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

    def m2l(self, message):
        # Normalize the message before saving it so we can be sure that we will
        # be able to read it back later.
        parts = [unicode(p).translate(self.NORM_TABLE) for p in message]
        return (u'\t'.join(parts)).encode('utf-8')

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
                    self.EMAILS[pos] = unquote(email)
                    self.EMAIL_IDS[unquote(email).lower()] = pos
                elif line:
                    words = line.split('\t')
                    # FIXME: Delete this old crap.
                    if len(words) == 10:
                        # This is an old index file, reorder it!
                        pos, p, unused, msgid, d, f, s, t, r, c = words
                        ptrs = ','.join(['0' + ptr for ptr in p.split(',')])
                        line = '\t'.join([pos, ptrs, msgid, d, f, '',
                                          s, '', t, r, c])
                    else:
                        pos, ptrs, msgid = words[:3]
                    pos = int(pos, 36)
                    while len(self.INDEX) < pos + 1:
                        self.INDEX.append('')
                    self.INDEX[pos] = line
                    self.MSGIDS[msgid] = pos
                    for msg_ptr in ptrs.split(','):
                        self.PTRS[msg_ptr] = pos
            except ValueError:
                pass

        if session:
            session.ui.mark('Loading metadata index...')
        try:
            fd = open(self.config.mailindex_file(), 'r')
            for line in fd:
                if line.startswith(GPG_BEGIN_MESSAGE):
                    for line in decrypt_gpg([line], fd):
                        process_line(line)
                else:
                    process_line(line)
            fd.close()
        except IOError:
            if session:
                session.ui.warning(('Metadata index not found: %s'
                                    ) % self.config.mailindex_file())
        self.cache_sort_orders(session)
        if session:
            session.ui.mark('Loaded metadata, %d messages' % len(self.INDEX))
        self.EMAILS_SAVED = len(self.EMAILS)

    def save_changes(self, session=None):
        mods, self.MODIFIED = self.MODIFIED, set()
        if mods or len(self.EMAILS) > self.EMAILS_SAVED:
            if session:
                session.ui.mark("Saving metadata index changes...")
            fd = gpg_open(self.config.mailindex_file(),
                          self.config.prefs.gpg_recipient, 'a')
            for eid in range(self.EMAILS_SAVED, len(self.EMAILS)):
                fd.write('@%s\t%s\n' % (b36(eid), quote(self.EMAILS[eid])))
            for pos in mods:
                fd.write(self.INDEX[pos] + '\n')
            fd.close()
            flush_append_cache()
            if session:
                session.ui.mark("Saved metadata index changes")
            self.EMAILS_SAVED = len(self.EMAILS)

    def save(self, session=None):
        self.MODIFIED = set()
        if session:
            session.ui.mark("Saving metadata index...")
        fd = gpg_open(self.config.mailindex_file(),
                                    self.config.prefs.gpg_recipient, 'w')
        fd.write('# This is the mailpile.py index file.\n')
        fd.write('# We have %d messages!\n' % len(self.INDEX))
        for eid in range(0, len(self.EMAILS)):
            fd.write('@%s\t%s\n' % (b36(eid), quote(self.EMAILS[eid])))
        for item in self.INDEX:
            fd.write(item + '\n')
        fd.close()
        flush_append_cache()
        if session:
            session.ui.mark("Saved metadata index")

    def update_ptrs_and_msgids(self, session):
        session.ui.mark('Updating high level indexes')
        for offset in range(0, len(self.INDEX)):
            message = self.l2m(self.INDEX[offset])
            if len(message) > self.MSG_CONV_MID:
                self.MSGIDS[message[self.MSG_ID]] = offset
                for msg_ptr in message[self.MSG_PTRS].split(','):
                    self.PTRS[msg_ptr] = offset
            else:
                session.ui.warning('Bogus line: %s' % line)

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
        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        msg_ptrs = msg_info[self.MSG_PTRS].split(',')
        self.PTRS[msg_ptr] = msg_idx_pos

        # If message was seen in this mailbox before, update the location
        for i in range(0, len(msg_ptrs)):
            if (msg_ptrs[i][:MBX_ID_LEN] == msg_ptr[:MBX_ID_LEN]):
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
            median = nz_dates[len(nz_dates) / 2]
            if msg_ts and abs(msg_ts - median) < 31 * 24 * 3600:
                return msg_ts
            else:
                session.ui.warning(('=%s/%s using Recieved: instead of Date:'
                                    ) % (msg_mid, msg_id))
                return median
        else:
            # If the above fails, we assume the messages in the mailbox are in
            # chronological order and just add 1 second to the date of the last
            # message if date parsing fails for some reason.
            session.ui.warning('=%s/%s has a bogus date' % (msg_mid, msg_id))
            return last_date + 1

    def scan_mailbox(self, session, mailbox_idx, mailbox_fn, mailbox_opener):
        try:
            mbox = mailbox_opener(session, mailbox_idx)
            if mbox.editable:
                session.ui.mark('%s: Skipped: %s' % (mailbox_idx, mailbox_fn))
                return 0
            else:
                session.ui.mark('%s: Checking: %s' % (mailbox_idx, mailbox_fn))
        except (IOError, OSError, NoSuchMailboxError), e:
            session.ui.mark(('%s: Error opening: %s (%s)'
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
            parse_status = ('%s: Reading your mail: %d%% (%d/%d messages)'
                            ) % (mailbox_idx,
                                 100 * ui / len(unparsed), ui, len(unparsed))

            msg_ptr = mbox.get_msg_ptr(mailbox_idx, i)
            if msg_ptr in self.PTRS:
                if (ui % 317) == 0:
                    session.ui.mark(parse_status)
                continue
            else:
                session.ui.mark(parse_status)

            # Message new or modified, let's parse it.
            msg = ParseMessage(mbox.get_file(i), pgpmime=False)
            msg_id = b64c(sha1b64((self.hdr(msg, 'message-id') or msg_ptr
                                   ).strip()))
            if msg_id in self.MSGIDS:
                self.update_location(session, self.MSGIDS[msg_id], msg_ptr)
                added += 1
            else:
                # Add new message!
                msg_mid = b36(len(self.INDEX))

                msg_ts = self._extract_date_ts(session, msg_mid, msg_id, msg,
                                                        msg_ts)

                keywords, snippet = self.index_message(session,
                                                       msg_mid, msg_id,
                                                       msg, msg_ts,
                                                       mailbox=mailbox_idx,
                                                       compact=False,
                                           filter_hooks=[self.filter_keywords])

                msg_subject = self.hdr(msg, 'subject')
                msg_snippet = snippet[:max(0, snippet_max - len(msg_subject))]

                tags = [k.split(':')[0] for k in keywords
                                              if k.endswith(':tag')]

                msg_to = (ExtractEmails(self.hdr(msg, 'to')) +
                          ExtractEmails(self.hdr(msg, 'cc')) +
                          ExtractEmails(self.hdr(msg, 'bcc')))

                msg_idx_pos, msg_info = self.add_new_msg(
                    msg_ptr, msg_id, msg_ts, self.hdr(msg, 'from'), msg_to,
                    msg_subject, msg_snippet, tags
                )
                self.set_conversation_ids(msg_info[self.MSG_MID], msg)
                mbox.mark_parsed(i)

                added += 1
                if (added % 1000) == 0:
                    GlobalPostingList.Optimize(session, self, quick=True)

        if added:
            mbox.save(session)
        session.ui.mark('%s: Indexed mailbox: %s' % (mailbox_idx, mailbox_fn))
        return added

    def index_email(self, session, email):
        mbox_idx = email.get_msg_info(self.MSG_PTRS).split(',')[0][:MBX_ID_LEN]
        kw, sn = self.index_message(session,
                                    email.msg_mid(),
                                    email.get_msg_info(self.MSG_ID),
                                    email.get_msg(),
                                   long(email.get_msg_info(self.MSG_DATE), 36),
                                    mailbox=mbox_idx,
                                    compact=False,
                                    filter_hooks=[self.filter_keywords])

    def set_conversation_ids(self, msg_mid, msg):
        msg_conv_mid = None
        refs = set((self.hdr(msg, 'references') + ' ' +
                    self.hdr(msg, 'in-reply-to')
                   ).replace(',', ' ').strip().split())
        for ref_id in [b64c(sha1b64(r)) for r in refs]:
            try:
                # Get conversation ID ...
                ref_idx_pos = self.MSGIDS[ref_id]
                msg_conv_mid = self.get_msg_at_idx_pos(ref_idx_pos
                                                       )[self.MSG_CONV_MID]
                # Update root of conversation thread
                parent = self.get_msg_at_idx_pos(int(msg_conv_mid, 36))
                replies = parent[self.MSG_REPLIES][:-1].split(',')
                if msg_mid not in replies:
                    replies.append(msg_mid)
                parent[self.MSG_REPLIES] = ','.join(replies) + ','
                self.set_msg_at_idx_pos(int(msg_conv_mid, 36), parent)
                break
            except (KeyError, ValueError, IndexError):
                pass

        msg_idx_pos = int(msg_mid, 36)
        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)

        if not msg_conv_mid:
            # Can we do plain GMail style subject-based threading?
            # FIXME: Is this too aggressive? Make configurable?
            subj = msg_info[self.MSG_SUBJECT].lower().replace('re: ', '')
            date = long(msg_info[self.MSG_DATE], 36)
            if subj.strip() != '':
                for midx in reversed(range(max(0, msg_idx_pos - 250),
                                           msg_idx_pos)):
                    try:
                        m_info = self.get_msg_at_idx_pos(midx)
                        if m_info[self.MSG_SUBJECT
                                  ].lower().replace('re: ', '') == subj:
                            msg_conv_mid = m_info[self.MSG_CONV_MID]
                            parent = self.get_msg_at_idx_pos(int(msg_conv_mid,
                                                                 36))
                            replies = parent[self.MSG_REPLIES][:-1].split(',')
                            if len(replies) < 100:
                                if msg_mid not in replies:
                                    replies.append(msg_mid)
                                parent[self.MSG_REPLIES] = (','.join(replies)
                                                            + ',')
                                self.set_msg_at_idx_pos(int(msg_conv_mid, 36),
                                                        parent)
                                break
                        if date - long(m_info[self.MSG_DATE],
                                       36) > 5 * 24 * 3600:
                            break
                    except (KeyError, ValueError, IndexError):
                        pass

        if not msg_conv_mid:
            # OK, we are our own conversation root.
            msg_conv_mid = msg_mid

        msg_info[self.MSG_CONV_MID] = msg_conv_mid
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def unthread_message(self, msg_mid):
        msg_idx_pos = int(msg_mid, 36)
        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        par_idx_pos = int(msg_info[self.MSG_CONV_MID], 36)

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
                    kid_info[self.MSG_CONV_MID] = head_mid
                    kid.set_msg_at_idx_pos(head_idx_pos, head_info)
        else:
            # Message is a reply, remove it from thread
            par_info = self.get_msg_at_idx_pos(par_idx_pos)
            thread = par_info[self.MSG_REPLIES][:-1].split(',')
            if msg_mid in thread:
                thread.remove(msg_mid)
                par_info[self.MSG_REPLIES] = ','.join(thread) + ','
                self.set_msg_at_idx_pos(par_idx_pos, par_info)

        msg_info[self.MSG_CONV_MID] = msg_mid
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def _add_email(self, email):
        eid = len(self.EMAILS)
        self.EMAILS.append(email)
        self.EMAIL_IDS[email.lower()] = eid
        # FIXME: This needs to get written out...
        return eid

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

    def add_new_msg(self, msg_ptr, msg_id, msg_ts, msg_from, msg_to,
                          msg_subject, msg_snippet, tags):
        msg_idx_pos = len(self.INDEX)
        msg_mid = b36(msg_idx_pos)
        msg_info = [
            msg_mid,                                     # Index ID
            msg_ptr,                                     # Location on disk
            b64c(sha1b64((msg_id or msg_ptr).strip())),  # Message ID
            b36(msg_ts),                                 # Date as UTC timstamp
            msg_from,                                    # From:
            self.compact_to_list(msg_to or []),          # To: / Cc: / Bcc:
            msg_subject,                                 # Subject
            msg_snippet,                                 # Snippet
            ','.join(tags),                              # Initial tags
            '',                                          # No replies for now
            msg_mid                                      # Conversation ID
        ]
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)
        return msg_idx_pos, msg_info

    def filter_keywords(self, session, msg_mid, msg, keywords):
        keywordmap = {}
        msg_idx_list = [msg_mid]
        for kw in keywords:
            keywordmap[kw] = msg_idx_list

        for fid, terms, tags, comment in session.config.get_filters():
            if (terms == '*' or
                    len(self.search(None, terms.split(),
                                    keywords=keywordmap)) > 0):
                for t in tags.split():
                    kw = '%s:tag' % t[1:]
                    if t[0] == '-':
                        if kw in keywordmap:
                            del keywordmap[kw]
                    else:
                        keywordmap[kw] = msg_idx_list

        return set(keywordmap.keys())

    def apply_filters(self, session, filter_on, msg_mids=None, msg_idxs=None):
        if msg_idxs is None:
            msg_idxs = [int(mid, 36) for mid in msg_mids]
        if not msg_idxs:
            return
        for fid, trms, tags, c in session.config.get_filters(
                                                     filter_on=filter_on):
            for t in tags.split():
                tag_id = t[1:].split(':')[0]
                if t[0] == '-':
                    self.remove_tag(session, tag_id, msg_idxs=set(msg_idxs))
                else:
                    self.add_tag(session, tag_id, msg_idxs=set(msg_idxs))

    def read_message(self, session, msg_mid, msg_id, msg, msg_ts,
                                    mailbox=None):
        keywords = []
        snippet = ''
        payload = [None]
        for part in msg.walk():
            textpart = payload[0] = None
            ctype = part.get_content_type()
            charset = part.get_charset() or 'iso-8859-1'

            def _loader(p):
                if payload[0] is None:
                    payload[0] = self.try_decode(p.get_payload(None, True),
                                                 charset)
                return payload[0]

            if ctype == 'text/plain':
                textpart = _loader(part)
            elif ctype == 'text/html':
                _loader(part)
                if len(payload[0]) > 3:
                    try:
                        textpart = lxml.html.fromstring(payload[0]
                                                        ).text_content()
                    except:
                        session.ui.warning(('=%s/%s has bogus HTML.'
                                            ) % (msg_mid, msg_id))
                        textpart = payload[0]
                else:
                    textpart = payload[0]
            elif 'pgp' in part.get_content_type():
                keywords.append('pgp:has')

            att = part.get_filename()
            if att:
                att = self.try_decode(att, charset)
                keywords.append('attachment:has')
                keywords.extend([t + ':att' for t
                                 in re.findall(WORD_REGEXP, att.lower())])
                textpart = (textpart or '') + ' ' + att

            if textpart:
                # FIXME: Does this lowercase non-ASCII characters correctly?
                # FIXME: What about encrypted content?
                keywords.extend(re.findall(WORD_REGEXP, textpart.lower()))
                # FIXME: Do this better.
                if ('-----BEGIN PGP' in textpart and
                        '-----END PGP' in textpart):
                    keywords.append('pgp:has')
                for extract in plugins.get_text_kw_extractors():
                    keywords.extend(extract(self, msg, ctype,
                                            lambda: textpart))

                if len(snippet) < 1024:
                    snippet += ' ' + textpart

            for extract in plugins.get_data_kw_extractors():
                keywords.extend(extract(self, msg, ctype, att, part,
                                        lambda: _loader(part)))

        keywords.append('%s:id' % msg_id)
        keywords.extend(re.findall(WORD_REGEXP,
                                   self.hdr(msg, 'subject').lower()))
        keywords.extend(re.findall(WORD_REGEXP,
                                   self.hdr(msg, 'from').lower()))
        if mailbox:
            keywords.append('%s:mailbox' % mailbox.lower())
        keywords.append('%s:hprint' % HeaderPrint(msg))

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

        for extract in plugins.get_meta_kw_extractors():
            keywords.extend(extract(self, msg_mid, msg, msg_ts))

        snippet = snippet.replace('\n', ' '
                                  ).replace('\t', ' ').replace('\r', '')
        return (set(keywords) - STOPLIST), snippet.strip()

    def index_message(self, session, msg_mid, msg_id, msg, msg_ts,
                            mailbox=None, compact=True, filter_hooks=[]):
        keywords, snippet = self.read_message(session,
                                              msg_mid, msg_id, msg, msg_ts,
                                              mailbox=mailbox)

        for hook in filter_hooks:
            keywords = hook(session, msg_mid, msg, keywords)

        for word in keywords:
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
            return [None, '', None, b36(0),
                            '(no sender)', '',
                            '(not in index: %s)' % msg_idx, '',
                            '', '', '-1']

    def set_msg_at_idx_pos(self, msg_idx, msg_info):
        if msg_idx < len(self.INDEX):
            self.INDEX[msg_idx] = self.m2l(msg_info)
            self.INDEX_CONV[msg_idx] = int(msg_info[self.MSG_CONV_MID], 36)
        elif msg_idx == len(self.INDEX):
            self.INDEX.append(self.m2l(msg_info))
            self.INDEX_CONV.append(int(msg_info[self.MSG_CONV_MID], 36))
        else:
            raise IndexError('%s is outside the index' % msg_idx)

        CachedSearchResultSet.DropCaches(msg_idxs=[msg_idx])
        self.MODIFIED.add(msg_idx)
        if msg_idx in self.CACHE:
            del(self.CACHE[msg_idx])

        for order in self.INDEX_SORT:
            while msg_idx >= len(self.INDEX_SORT[order]):
                self.INDEX_SORT[order].append(msg_idx)

        self.MSGIDS[msg_info[self.MSG_ID]] = msg_idx
        for msg_ptr in msg_info[self.MSG_PTRS].split(','):
            self.PTRS[msg_ptr] = msg_idx

    def get_conversation(self, msg_info=None, msg_idx=None):
        if not msg_info:
            msg_info = self.get_msg_at_idx_pos(msg_idx)
        conv_mid = msg_info[self.MSG_CONV_MID]
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
        pls = GlobalPostingList(session, '%s:tag' % tag_id)
        if msg_info and msg_idxs is None:
            msg_idxs = set([int(msg_info[self.MSG_MID], 36)])
        else:
            msg_idxs = set(msg_idxs)
        session.ui.mark('Tagging %d messages (%s)' % (len(msg_idxs), tag_id))
        for msg_idx in list(msg_idxs):
            if conversation:
                for reply in self.get_conversation(msg_idx=msg_idx):
                    if reply[self.MSG_MID]:
                        msg_idxs.add(int(reply[self.MSG_MID], 36))
        for msg_idx in msg_idxs:
            if msg_idx >= 0 and msg_idx < len(self.INDEX):
                msg_info = self.get_msg_at_idx_pos(msg_idx)
                tags = set([r for r in msg_info[self.MSG_TAGS].split(',')
                                    if r])
                tags.add(tag_id)
                msg_info[self.MSG_TAGS] = ','.join(list(tags))
                self.INDEX[msg_idx] = self.m2l(msg_info)
                self.MODIFIED.add(msg_idx)
                pls.append(msg_info[self.MSG_MID])
        pls.save()

    def remove_tag(self, session, tag_id,
                   msg_info=None, msg_idxs=None, conversation=False):
        pls = GlobalPostingList(session, '%s:tag' % tag_id)
        if msg_info and msg_idxs is None:
            msg_idxs = set([int(msg_info[self.MSG_MID], 36)])
        else:
            msg_idxs = set(msg_idxs)
        if not msg_idxs:
            return
        session.ui.mark('Untagging conversations (%s)' % (tag_id, ))
        for msg_idx in list(msg_idxs):
            if conversation:
                for reply in self.get_conversation(msg_idx=msg_idx):
                    if reply[self.MSG_MID]:
                        msg_idxs.add(int(reply[self.MSG_MID], 36))
        session.ui.mark('Untagging %d messages (%s)' % (len(msg_idxs),
                                                        tag_id))
        eids = []
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
                eids.append(msg_info[self.MSG_MID])
        pls.remove(eids)
        pls.save()

    def search_tag(self, term, hits):
        t = term.split(':', 1)
        t[1] = self.config.get_tag_id(t[1]) or t[1]
        return hits('%s:tag' % t[1])

    def search(self, session, searchterms, keywords=None):
        if keywords is not None:
            def hits(term):
                return [int(h, 36) for h in keywords.get(term, [])]
        else:
            def hits(term):
                session.ui.mark('Searching for %s' % term)
                return [int(h, 36) for h
                        in GlobalPostingList(session, term).hits()]

        # Stash the raw search terms
        raw_terms = searchterms[:]
        srs = CachedSearchResultSet(self, raw_terms)
        if len(srs) > 0:
            return srs

        # Replace some GMail-compatible terms with what we really use
        if 'tags' in self.config:
            for p in ('', '+', '-'):
                while p + 'is:unread' in searchterms:
                    where = searchterms.index(p + 'is:unread')
                    searchterms[where] = p + 'tag:New'
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
                    session.ui.warning('Ignoring common word: %s' % term)
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
                # FIXME: Make search words pluggable!
                if term.startswith('body:'):
                    rt.extend(hits(term[5:]))
                elif term == 'all:mail':
                    rt.extend(range(0, len(self.INDEX)))
                elif term.startswith('in:'):
                    rt.extend(self.search_tag(term, hits))
                else:
                    t = term.split(':', 1)
                    fnc = plugins.get_search_term(t[0])
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
        if (results and (keywords is None) and
                ('tags' in self.config) and
                (not session or 'all' not in session.order)):
            invisible = self.config.get_tags(hides_flag=True)
            exclude_terms = ['in:%s' % i._key for i in invisible]
            for tag in invisible:
                tid = tag._key
                for p in ('in:%s', '+in:%s', '-in:%s'):
                    if ((p % tid) in searchterms or
                            (p % tag.name) in searchterms or
                            (p % tag.slug) in searchterms):
                        exclude_terms = []
            for term in exclude_terms:
                exclude.extend(self.search_tag(term, hits))

        srs.set_results(results, exclude)
        if session:
            session.ui.mark(('Found %d results (%d suppressed)'
                             ) % (len(results), len(srs.excluded())))
        return srs

    def cache_sort_orders(self, session):
        keys = range(0, len(self.INDEX))
        if session:
            session.ui.mark(('Finding conversations (%d messages)...'
                             ) % len(keys))
        self.INDEX_CONV = [int(self.get_msg_at_idx_pos(r)[self.MSG_CONV_MID],
                               36) for r in keys]
        for order, sorter in [
            ('date',
             lambda k: long(self.get_msg_at_idx_pos(k)[self.MSG_DATE], 36)),
            ('from',
             lambda k: self.get_msg_at_idx_pos(k)[self.MSG_FROM]),
            ('subject',
             lambda k: self.get_msg_at_idx_pos(k)[self.MSG_SUBJECT]),
        ]:
            if session:
                session.ui.mark(('Sorting %d messages in %s order...'
                                 ) % (len(keys), order))
            o = keys[:]
            o.sort(key=sorter)
            self.INDEX_SORT[order] = keys[:]
            for i in range(0, len(o)):
                    self.INDEX_SORT[order][o[i]] = i

    def sort_results(self, session, results, how):
        if not results:
            return

        count = len(results)
        session.ui.mark('Sorting %d messages in %s order...' % (count, how))
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
                            say('Recovering from bogus sort, corrupt index?')
                            say('Please tell team@mailpile.is !')
                            clean_results = [r for r in results
                                             if r >= 0 and r < len(self.INDEX)]
                            clean_results.sort(
                                key=self.INDEX_SORT[order].__getitem__)
                            results[:] = clean_results
                        did_sort = True
                        break
                if not did_sort:
                    session.ui.warning('Unknown sort order: %s' % how)
                    return False
        except:
            if session.config.sys.debug:
                traceback.print_exc()
            session.ui.warning('Sort failed, sorting badly. Partial index?')
            results.sort()

        if how.startswith('rev'):
            results.reverse()

        if 'flat' not in how:
            # This filters away all but the first result in each conversation.
            results.reverse()
            cset = set(dict([(self.INDEX_CONV[r], r)
                             for r in results]).values())
            results.reverse()
            results[:] = filter(cset.__contains__, results)
            session.ui.mark(('Sorted %d messages by %s, %d conversations'
                             ) % (count, how, len(results)))
        else:
            session.ui.mark('Sorted %d messages in %s order' % (count, how))

        return True

    def update_tag_stats(self, session, config, update_tags=None):
        session = session or Session(config)
        new_tid = config.get_tag_id('new')
        new_msgs = (new_tid and GlobalPostingList(session,
                                                  '%s:tag' % new_tid).hits()
                             or set([]))
        self.STATS.update({
            'ALL': [len(self.INDEX), len(new_msgs)]
        })
        for tid in (update_tags or config.tags.keys()):
            if session:
                session.ui.mark('Counting messages in tag:%s' % tid)
            hits = GlobalPostingList(session, '%s:tag' % tid).hits()
            self.STATS[tid] = [len(hits), len(hits & new_msgs)]

        return self.STATS
