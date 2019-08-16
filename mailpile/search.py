from __future__ import print_function
import cStringIO
import email
import random
import re
import rfc822
import time
import threading
import traceback
from urllib import quote, unquote

import mailpile.util
from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.state import CryptoInfo, SignatureInfo, EncryptionInfo
from mailpile.crypto.streamer import EncryptingStreamer
from mailpile.eventlog import GetThreadEvent
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.index.base import BaseIndex
from mailpile.index.search import SearchResultSet, CachedSearchResultSet
from mailpile.plugins import PluginManager
from mailpile.mailutils import FormatMbxId, MBX_ID_LEN, NoSuchMailboxError
from mailpile.mailutils.addresses import AddressHeaderParser
from mailpile.mailutils.emails import ExtractEmails, ExtractEmailAndName
from mailpile.mailutils.emails import Email, ParseMessage, GetTextPayload
from mailpile.mailutils.header import decode_header
from mailpile.mailutils.headerprint import HeaderPrints
from mailpile.mailutils.html import extract_text_from_html
from mailpile.mailutils.safe import *
from mailpile.postinglist import GlobalPostingList
from mailpile.ui import *
from mailpile.util import *
from mailpile.vfs import vfs, FilePath


_plugins = PluginManager()


class MailIndex(BaseIndex):
    """This is a lazily parsing object representing a mailpile index."""

    # Parameters that set threshold to rewrite complete metadata index file.
    MIN_ITEMS_PER_INCREMENT = 200   # Limits number of appends.
    MIN_ITEMS_PER_DUPLICATE = 10    # Limits number of duplicated MSG_MIDs.
    ITEM_COUNT_OFFSET = 5000        # Puts lower bound on limits.
    # Appends start with a comment including this so they can be counted.
    APPEND_MARK = '-----APPENDED SECTION-----'

    MAX_CACHE_ENTRIES = 2500
    CAPABILITIES = set([
        BaseIndex.CAN_SEARCH,
        BaseIndex.CAN_SORT,
        BaseIndex.HAS_UNREAD,
        BaseIndex.HAS_ATTS,
        BaseIndex.HAS_TAGS])

    def __init__(self, config):
        BaseIndex.__init__(self, config)
        self.interrupt = None
        self.loaded_index = False
        self.INDEX = []
        self.INDEX_SORT = {}
        self.INDEX_THR = []
        self.PTRS = {}
        self.TAGS = {}
        self.MSGIDS = {}
        self.MODIFIED = set()
        self.EMAILS_SAVED = 0
        self._scanned = {}
        self._saved_changes = 0
        self._saved_lines = 0
        self._lock = SearchRLock()
        self._save_lock = SearchRLock()
        self._prepare_sorting()
        self._url_re_cache = {}

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
                    if self.APPEND_MARK in line:
                        self._saved_changes += 1
                elif line[:1] == '@':
                    try:
                        pos, email = line[1:].split('\t', 1)
                        pos = int(pos, 36)
                        while len(self.EMAILS) < pos + 1:
                            self.EMAILS.append('')
                        unquoted_email = unquote(email).decode('utf-8')
                        self.EMAILS[pos] = unquoted_email
                        self.EMAIL_IDS[unquoted_email.split()[0].lower()] = pos
                        self._saved_lines += 1
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
                            if session and len(self.INDEX) % 107 == 100:
                                session.ui.mark(
                                    _('Loading metadata index...') +
                                    ' %s' % len(self.INDEX))
                            self._saved_lines += 1
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
                    errors = 0
                    def warn(offset):
                        if session:
                            session.ui.error('WARNING: Failed to decrypt '
                                             'block of index ending at %d'
                                             % offset)
                    # FIXME: Differentiate between partial index and no index?
                    gpgi = GnuPG(self.config, event=GetThreadEvent())
                    decrypt_and_parse_lines(fd, process_lines, self.config,
                        newlines=True, decode=False, gpgi=gpgi,
                        _raise=False, error_cb=warn)
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

        # Make sure metadata has entry for every msg_mid in keyword index.
        max_kw_msg_idx_pos = GlobalPostingList.GetMaxMsgIdxPos()
        if max_kw_msg_idx_pos and max_kw_msg_idx_pos >= len(self.INDEX):
            new_max_msg_idx_pos = max_kw_msg_idx_pos + 1
            if session:
                session.ui.warning(
                    _('Fixing %d messages in keyword index not in metadata.'
                      ) % (new_max_msg_idx_pos - len(self.INDEX)))

            for msg_idx_pos in range(len(self.INDEX), new_max_msg_idx_pos):
                self.add_new_ghost(b36(msg_idx_pos), trash=True)

        self.loaded_index = True

    def update_msg_tags(self, msg_idx_pos, msg_info):
        tags = set(self.get_tags(msg_info=msg_info))
        with self._lock:
            for tid in (set(self.TAGS.keys()) - tags):
                self.TAGS[tid] -= set([msg_idx_pos])
            for tid in tags:
                if tid not in self.TAGS:
                    self.TAGS[tid] = set()
                self.TAGS[tid].add(msg_idx_pos)

    def _maybe_encrypt(self, data):
        gpgr = self.config.prefs.gpg_recipient
        tokeys = ([gpgr]
                  if gpgr not in (None, '', '!CREATE', '!PASSWORD')
                  else None)

        if self.config.get_master_key():
            with EncryptingStreamer(self.config.get_master_key(),
                                    delimited=True) as es:
                es.write(data)
                es.finish()
                return es.save(None)

        elif tokeys:
            stat, edata = GnuPG(self.config, event=GetThreadEvent()
                                ).encrypt(data, tokeys=tokeys)
            if stat == 0:
                return edata

        return data

    def save_changes(self, session=None):
        self._save_lock.acquire()
        try:
            # In a locked section, check what needs to be done!
            with self._lock:
                mods, self.MODIFIED = self.MODIFIED, set()
                old_emails_saved, total = self.EMAILS_SAVED, len(self.EMAILS)
                index_items = total + len(self.INDEX)

            if old_emails_saved == total and not mods:
                # Nothing to do...
                return

            max_incremental_saves = (index_items + self.ITEM_COUNT_OFFSET
                                    ) / self.MIN_ITEMS_PER_INCREMENT
            max_saved_lines = index_items + (
                                      index_items + self.ITEM_COUNT_OFFSET
                                    ) / self.MIN_ITEMS_PER_DUPLICATE

            if (not os.path.isfile(self.config.mailindex_file())
                    or ((self._saved_changes > max_incremental_saves
                           or self._saved_lines > max_saved_lines)
                        and not mailpile.util.QUITTING)):
                # Write a new metadata index file.
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

            # Unlocked, try to write this out, prepending append mark comment.

            data = self._maybe_encrypt(''.join(
                ['#' + self.APPEND_MARK + '\n']
                + emails
                + [self.INDEX[pos] + '\n' for pos in mods]))
            with open(self.config.mailindex_file(), 'a') as fd:
                fd.write(data)
                self._saved_changes += 1
                self._saved_lines += total - old_emails_saved + len(mods)

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

            data = self._maybe_encrypt(''.join(data))
            with open(newfile, 'w') as fd:
                fd.write(data)

            # Keep the last 5 index files around... just in case.
            backup_file(idxfile, backups=5, min_age_delta=10)
            os.rename(newfile, idxfile)

            self._saved_changes = 0
            self._saved_lines = email_counter + index_counter
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
        with self._lock:
            self.PTRS = {}
            self.MSGIDS = {}
            for offset in range(0, len(self.INDEX)):
                message = self.l2m(self.INDEX[offset])
                if len(message) == self.MSG_FIELDS_V2:
                    self.MSGIDS[message[self.MSG_ID]] = offset
                    for msg_ptr in message[self.MSG_PTRS].split(','):
                        if msg_ptr:
                            self.PTRS[msg_ptr] = offset
                else:
                    session.ui.warning(_('Bogus line: %s') % line)

    def _remove_location(self, session, msg_ptr):
        msg_idx_pos = self.PTRS[msg_ptr]
        del self.PTRS[msg_ptr]

        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        msg_ptrs = [p for p in msg_info[self.MSG_PTRS].split(',')
                    if p and p != msg_ptr]

        msg_info[self.MSG_PTRS] = ','.join(msg_ptrs)
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def _update_location(self, session, msg_idx_pos, msg_ptr):
        if 'rescan' in session.config.sys.debug:
            session.ui.debug('Duplicate? %s -> %s' % (b36(msg_idx_pos), msg_ptr))

        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        msg_ptrs = msg_info[self.MSG_PTRS].split(',')

        # New location! Some other process will prune obsolete pointers.
        if msg_ptr:
            self.PTRS[msg_ptr] = msg_idx_pos
            msg_ptrs.append(msg_ptr)

        msg_info[self.MSG_PTRS] = ','.join(list(set(msg_ptrs)))
        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)
        return msg_info

    def _extract_date_ts(self, session, msg_mid, msg_id, msg, default):
        """Extract a date, sanity checking against the Received: headers."""
        return (safe_message_ts(
            msg,
            default=default,
            msg_mid=msg_mid,
            msg_id=msg_id,
            session=session) or int(time.time()-1))

    def _get_scan_progress(self, mailbox_idx, event=None, reset=False):
        if event:
            if 'rescans' not in event.data:
                event.data['rescans'] = []
            if reset:
                event.data['rescan'] = {}
            progress = event.data.get('rescan', {})
            if not progress.keys():
                reset = True
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
                     process_new=None, apply_tags=None, editable=False,
                     stop_after=None, deadline=None, reverse=False, lazy=False,
                     event=None, force=False):
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
            if 'rescan' in session.config.sys.debug:
                session.ui.debug(message)
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
        except (IOError, OSError, ValueError, NoSuchMailboxError) as e:
            if 'rescan' in session.config.sys.debug:
                session.ui.debug(traceback.format_exc())
            return finito(-1, _('%s: Error opening: %s (%s)'
                                ) % (mailbox_idx, mailbox_fn, e),
                          error=True)

        if len(self.PTRS.keys()) == 0:
            self.update_ptrs_and_msgids(session)

        messages = sorted(mbox.keys())
        messages_md5 = md5_hex(str(messages))
        mbox_version = mbox.last_updated()
        if (not force) and messages_md5 == self._scanned.get(mailbox_idx, ''):
            return finito(0, _('%s: No new mail in: %s'
                               ) % (mailbox_idx, mailbox_fn),
                          complete=True)

        parse_fmt1 = _('%s: Reading your mail: %d%% (%d/%d message)')
        parse_fmtn = _('%s: Reading your mail: %d%% (%d/%d messages)')
        def parse_status(ui):
            n = len(messages)
            return ((n == 1) and parse_fmt1 or parse_fmtn
                    ) % (mailbox_idx, 100 * ui / n, ui, n)

        start_time = time.time()
        progress.update({
            'total': len(messages),
            'batch_size': stop_after or len(messages)
        })

        added = updated = 0
        last_date = long(start_time)
        not_done_yet = 'NOT DONE YET'
        if reverse:
            messages.reverse()
        for ui in range(0, len(messages)):
            if not force:
                play_nice_with_threads(weak=True)
            if mailpile.util.QUITTING or self.interrupt:
                ir, self.interrupt = self.interrupt, None
                return finito(-1, _('Rescan interrupted: %s') % ir)
            if stop_after and added >= stop_after:
                messages_md5 = not_done_yet
                break
            elif deadline and time.time() > deadline:
                messages_md5 = not_done_yet
                break
            elif mbox_version != mbox.last_updated():
                messages_md5 = not_done_yet
                break

            i = messages[ui]
            msg_ptr = mbox.get_msg_ptr(mailbox_idx, i)
            if msg_ptr in self.PTRS:
                if (ui % 317) == 0:
                    session.ui.mark(parse_status(ui))
                elif (ui % 129) == 0 and not force:
                    play_nice_with_threads()
                if not lazy:
                    msg_info = self.get_msg_at_idx_pos(self.PTRS[msg_ptr])
                    msg_body = msg_info[self.MSG_BODY]
                if lazy or (msg_body not in self.MSG_BODY_UNSCANNED):
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
                                                        progress=progress,
                                                        lazy=lazy)
            except TypeError:
                a = u = 0

            added += a
            updated += u

        if not lazy:
            # Figure out which messages exist at all, and remove stale pointers.
            # This happens last and in a locked section, because other threads may
            # have added messages while we were busy with other things.
            with self._lock:
                existing_ptrs = set()
                for ui in range(0, len(messages)):
                    msg_ptr = mbox.get_msg_ptr(mailbox_idx, messages[ui])
                    existing_ptrs.add(msg_ptr)
                for msg_ptr in self.PTRS.keys():
                    if (msg_ptr[:MBX_ID_LEN] == mailbox_idx and
                            msg_ptr not in existing_ptrs):
                        self._remove_location(session, msg_ptr)
                        updated += 1
        if not force:
            play_nice_with_threads()

        progress.update({
            'added': added,
            'updated': updated})

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
                       msg_ptr=None, msg_data=None, msg_metadata_kws=None,
                       last_date=None,
                       process_new=None, apply_tags=None, stop_after=None,
                       editable=False, event=None, progress=None,
                       lazy=False):
        with self._lock:
            # This is not actually a critical section, this is more of a belt and
            # suspenders thing to encourage serialization of scanning processes.
            msg_ptr = msg_ptr or mbox.get_msg_ptr(mailbox_idx, msg_mbox_idx)

        added = updated = 0
        last_date = last_date or long(time.time())
        progress = progress or self._get_scan_progress(mailbox_idx,
                                                       event=event)

        if 'rescan' in session.config.sys.debug:
            session.ui.debug('Reading message %s/%s'
                             % (mailbox_idx, msg_mbox_idx))
        try:
            if msg_data:
                msg_fd = cStringIO.StringIO(msg_data)
                msg_metadata_kws = msg_metadata_kws or []
            elif lazy:
                msg_data = mbox.get_bytes(msg_mbox_idx, 10240)
                msg_data = msg_data.split('\r\n\r\n')[0].split('\n\n')[0]
                msg_fd = cStringIO.StringIO(msg_data)
                msg_bytes = mbox.get_msg_size(msg_mbox_idx)
                msg_metadata_kws = mbox.get_metadata_keywords(msg_mbox_idx)
            else:
                msg_fd = mbox.get_file(msg_mbox_idx)
                msg_metadata_kws = mbox.get_metadata_keywords(msg_mbox_idx)

            msg = ParseMessage(msg_fd,
                pgpmime=(session.config.prefs.index_encrypted and 'all'),
                config=session.config)
            if not lazy:
                msg_bytes = msg_fd.tell()

        except (IOError, OSError, ValueError, IndexError, KeyError):
            if session.config.sys.debug:
                traceback.print_exc()
            progress['errors'].append(msg_mbox_idx)
            session.ui.warning(('Reading message %s/%s FAILED, skipping'
                                ) % (mailbox_idx, msg_mbox_idx))
            return last_date, added, updated

        msg_snippet = msg_info = None
        msg_id = self.get_msg_id(msg, msg_ptr)
        if msg_id in self.MSGIDS:
            with self._lock:
                msg_info = self._update_location(session,
                                                 self.MSGIDS[msg_id],
                                                 msg_ptr)
                msg_snippet = msg_info[self.MSG_BODY]
                updated += 1

        rescan_body = (not lazy) and msg_snippet in self.MSG_BODY_UNSCANNED
        if rescan_body or msg_id not in self.MSGIDS:
            lazy_body = self.MSG_BODY_LAZY if lazy else None
            msg_info = self._index_incoming_message(
                session, msg_id, msg_ptr, msg_bytes,
                msg, msg_metadata_kws,
                last_date + 1, mailbox_idx, process_new, apply_tags,
                lazy_body, msg_info)
            last_date = long(msg_info[self.MSG_DATE], 36)
            added += 1

        progress['added'] = progress.get('added', 0) + added
        progress['updated'] = progress.get('updated', 0) + updated
        return last_date, added, updated

    def edit_msg_info(self, msg_info,
                      msg_mid=None, raw_msg_id=None, msg_id=None, msg_ts=None,
                      msg_from=None, msg_subject=None, msg_body=None,
                      msg_to=None, msg_cc=None, msg_size=None,
                      msg_tags=None, msg_replies=None,
                      msg_parent_mid=None, msg_thread_mid=None):
        if msg_mid is not None:
            msg_info[self.MSG_MID] = msg_mid
        if raw_msg_id is not None:
            msg_info[self.MSG_ID] = self._encode_msg_id(raw_msg_id)
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
        if msg_size is not None:
            msg_info[self.MSG_KB] = b36(int(msg_size) // 1024)
        if msg_to is not None:
            msg_info[self.MSG_TO] = self.compact_to_list(msg_to or [])
        if msg_cc is not None:
            msg_info[self.MSG_CC] = self.compact_to_list(msg_cc or [])
        if msg_tags is not None:
            msg_info[self.MSG_TAGS] = ','.join(msg_tags or [])
        if msg_replies is not None:
            if len(msg_replies) > 1:
                msg_info[self.MSG_REPLIES] = ','.join(msg_replies) + ','
            else:
                msg_info[self.MSG_REPLIES] = ''

        if msg_parent_mid is not None or msg_thread_mid is not None:
            if msg_thread_mid is None:
                msg_thread_mid = msg_info[self.MSG_THREAD_MID].split('/')[0]
            if msg_parent_mid is None:
                msg_parent_mid = msg_info[self.MSG_THREAD_MID].split('/')[-1]
            if msg_thread_mid != msg_parent_mid:
                msg_info[self.MSG_THREAD_MID] = (
                    '%s/%s' % (msg_thread_mid, msg_parent_mid))
            else:
                msg_info[self.MSG_THREAD_MID] = msg_thread_mid

        return msg_info

    def _extract_header_info(self, msg):
        # FIXME: this stuff is actually pretty weak!
        msg_to = AddressHeaderParser(msg.get('to', ''))
        msg_cc = AddressHeaderParser(msg.get('cc', ''))
        msg_cc += AddressHeaderParser(msg.get('bcc', ''))  # Usually a noop
        msg_subj = safe_decode_hdr(msg, 'subject')
        return msg_to, msg_cc, msg_subj

    # FIXME: Finish merging this function with the one below it...
    def _extract_info_and_index(self, session, mailbox_idx,
                                msg_mid, msg_id,
                                msg_size, msg, msg_metadata_kws,
                                default_date,
                                **index_kwargs):

        msg_ts = self._extract_date_ts(session, msg_mid, msg_id, msg,
                                       default_date)

        msg_to, msg_cc, msg_subj = self._extract_header_info(msg)

        filters = _plugins.get_filter_hooks([self.filter_keywords])
        kw, bi = self.index_message(session, msg_mid, msg_id,
                                    msg, msg_metadata_kws, msg_size, msg_ts,
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
                                msg_id, msg_ptr, msg_size,
                                msg, msg_metadata_kws, default_date,
                                mailbox_idx, process_new, apply_tags,
                                lazy_body, msg_info):
        if lazy_body:
            msg_ts = self._extract_date_ts(session, 'new', msg_id, msg,
                                           default_date)
            msg_to, msg_cc, msg_subj = self._extract_header_info(msg)
            msg_idx_pos, msg_info = self.add_new_msg(
                msg_ptr, msg_id, msg_ts,
                safe_decode_hdr(msg, 'from'), msg_to, msg_cc, msg_size,
                msg_subj, lazy_body, [])

        else:
            # If necessary, add the message to the index so we can index
            # terms to the right MID.
            if msg_info:
                msg_mid = msg_info[self.MSG_MID]
                msg_idx_pos = int(msg_mid, 36)
            else:
                msg_idx_pos, msg_info = self.add_new_msg(
                    msg_ptr, msg_id, default_date,
                    '', [], [], 0, _('(processing message ...)'),
                    self.MSG_BODY_GHOST, [])
                msg_mid = b36(msg_idx_pos)

            # Parse and index
            (msg_ts, msg_to, msg_cc, msg_subj, msg_body, tags
             ) = self._extract_info_and_index(session, mailbox_idx,
                                              msg_mid, msg_id, msg_size,
                                              msg, msg_metadata_kws,
                                              default_date,
                                              process_new=process_new,
                                              apply_tags=apply_tags,
                                              incoming=True)

            # Finally, update the metadata index with whatever we learned
            self.edit_msg_info(msg_info,
                               msg_from=safe_decode_hdr(msg, 'from'),
                               msg_ts=msg_ts,
                               msg_to=msg_to,
                               msg_cc=msg_cc,
                               msg_subject=msg_subj,
                               msg_body=msg_body,
                               msg_size=msg_size,
                               msg_tags=tags)
            self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

        self.set_conversation_ids(msg_info[self.MSG_MID], msg)
        return msg_info

    def index_email(self, session, email):
        # Extract info from the email object...
        msg = email.get_msg(
            pgpmime=(session.config.prefs.index_encrypted and 'all'),
            crypto_state_feedback=False)
        msg_mid = email.msg_mid()
        msg_info = email.get_msg_info()
        msg_size = email.get_msg_size()
        msg_metadata_kws = email.get_metadata_kws()
        msg_id = msg_info[self.MSG_ID]
        mailbox_idx = msg_info[self.MSG_PTRS].split(',')[0][:MBX_ID_LEN]
        default_date = long(msg_info[self.MSG_DATE], 36)

        (msg_ts, msg_to, msg_cc, msg_subj, msg_body, tags
         ) = self._extract_info_and_index(session, mailbox_idx,
                                          msg_mid, msg_id, msg_size,
                                          msg, msg_metadata_kws,
                                          default_date,
                                          incoming=False)
        self.edit_msg_info(msg_info,
                           msg_ts=msg_ts,
                           msg_from=safe_decode_hdr(msg, 'from'),
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

        # Update conversation threading
        self.set_conversation_ids(msg_info[self.MSG_MID], msg,
                                  subject_threading=False)

        # Add normal tags implied by a rescan
        for tag_id in tags:
            self.add_tag(session, tag_id, msg_idxs=[email.msg_idx_pos])

    def set_conversation_ids(self, msg_mid, msg, subject_threading=True):
        """
        This method will calculate/update the thread-ID and parent-ID of a
        given message. Mailpile will group all messages in a thread
        together as "replies" to the root message; but it will also keep track
        of what is the immediate parent of any given mail.

        Note that the "root" message may not be the actual root of the thread;
        it's just whatever message fit the bill at the time.

        See https://www.jwz.org/doc/threading.html for a very nice discussion
        and threading algorithm which we're not using, but wish we could.
        """
        # We are looking for two things: an immediate parent, and the
        # conversation we're linked to. Since messages may arrive out of
        # order, our strategy is as follows:
        #
        # 1. To determine immediate parent, look at in-reply-to or the
        #    last entry in references.
        #
        # 2. If any messages in References (or In-Reply-To) don't exist,
        #    create a ghost for the closest missing ancestor.
        #
        # 3. To determine converstation, look at In-Reply-To and References,
        #    merge all conversations we find into one, including us. Note
        #    that if a message in References has been "unthreaded", we should
        #    ignore all previous ones.
        #
        # Step two is a compromise; for the best possible threading we would
        # create a ghost for each missing reference; however that would leave
        # us vulnerable to a DOS where hostile messages contain hundreds of
        # bogus references. So we never add more than one...

        # Initial state of ignorance
        parent_mid = None
        parent_idx_pos = None
        msg_thr_mid = None

        # These are the headers we're examining
        in_reply_to = safe_decode_hdr(msg, 'in-reply-to')
        refs = safe_decode_hdr(msg, 'references'
                               ).replace(',', ' ').strip().split()

        # Part 1: Figure out parent stuff.
        if in_reply_to:
            if '<' in in_reply_to:
                irt_ref = '<%s>' % in_reply_to.split('<')[1].split('>')[0]
                while irt_ref in refs:
                    refs.remove(irt_ref)
                refs.append(irt_ref)
        # According to the RFCs, the last entry in the References header
        # should be our immediate parent. We have made sure In-Reply-To has
        # precedence if it exists...
        if refs:
            parent_idx_pos = self.MSGIDS.get(self._encode_msg_id(refs[-1]))
            if parent_idx_pos is not None:
                parent_mid = b36(parent_idx_pos)

        # Part 2: Add a ghost for at most 1 missing ancestor
        enc_refs = [self._encode_msg_id(r) for r in refs]
        ref_idxs = [self.MSGIDS.get(er) for er in enc_refs]
        last_missing = None
        for i, r in enumerate(ref_idxs):
            if r is None:
                last_missing = i
        if last_missing is not None:
            g_idx_pos, g_info = self.add_new_ghost(enc_refs[last_missing])
            ref_idxs[last_missing] = g_idx_pos

        # Part 3: Discover and merge conversations
        ref_idxs = [r for r in ref_idxs if r is not None]
        conversations = set([])
        for ref_idx_pos in (r for r in reversed(ref_idxs) if r is not None):
            try:
                ref_info = self.get_msg_at_idx_pos(ref_idx_pos)
                if ref_info[self.MSG_REPLIES]:
                    conversations.add(b36(ref_idx_pos))
                msg_thr_mid = ref_info[self.MSG_THREAD_MID].split('/')[0]
                conversations.add(msg_thr_mid)
                if ref_info[self.MSG_THREAD_MID].endswith('/-'):
                    break
            except (KeyError, ValueError, IndexError):
                pass

        root = None
        replies = []
        if msg_thr_mid:
            root = self.get_msg_at_idx_pos(int(msg_thr_mid, 36))
            replies = [r for r in root[self.MSG_REPLIES][:-1].split(',') if r]
            reparent = []
            conversations.add(msg_mid)
            for t_mid in (c for c in conversations if c != msg_thr_mid):
                t_msg_info = self.get_msg_at_idx_pos(int(t_mid, 36))
                reparent.extend(t_msg_info[self.MSG_REPLIES][:-1].split(','))
                reparent.append(t_mid)
            for m_mid in set([r for r in reparent if r]):
                m_msg_idx = int(m_mid, 36)
                m_msg_info = self.get_msg_at_idx_pos(m_msg_idx)
                otp = m_msg_info[self.MSG_THREAD_MID].split('/')
                otp[0] = msg_thr_mid
                m_msg_info[self.MSG_THREAD_MID] = '/'.join(otp)
                m_msg_info[self.MSG_REPLIES] = ''
                self.set_msg_at_idx_pos(m_msg_idx, m_msg_info)
                replies.append(m_mid)

        # FIXME: If nothing was found, do a subject-based search of recent
        #        messages, for subject-based grouping.

        # OK, finally we add ourselves and our references the conversation, yay!
        if msg_thr_mid and root:
            replies.append(msg_mid)
            for ref_idx_pos in (r for r in ref_idxs if r is not None):
                ref_mid = b36(ref_idx_pos)
                replies.append(ref_mid)
            root[self.MSG_REPLIES] = ','.join(sorted(list(set(replies)))) + ','
            self.set_msg_at_idx_pos(int(msg_thr_mid, 36), root)

        msg_idx_pos = int(msg_mid, 36)
        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
        msg_replies = msg_info[self.MSG_REPLIES][:-1].split(',')

        if subject_threading and not (msg_thr_mid or refs or msg_replies):
            # Can we do plain GMail style subject-based threading?
            subj = msg_info[self.MSG_SUBJECT].lower()
            subj = subj.replace('re: ', '')  # FIXME: i18n?
            date = long(msg_info[self.MSG_DATE], 36)
            if subj.strip() != '':
                # FIXME: Is this too aggressive? Make configurable?
                for midx in reversed(range(max(0, msg_idx_pos - 150),
                                           msg_idx_pos)):
                    try:
                        m_info = self.get_msg_at_idx_pos(midx)
                        m_date = long(m_info[self.MSG_DATE], 36)
                        m_subj = m_info[self.MSG_SUBJECT]
                        if ((m_date < date) and  # FIXME: i18n?
                                (m_subj.lower().replace('re: ', '') == subj)):
                            msg_thr_mid = m_info[self.MSG_THREAD_MID]
                            msg_thr_mid = msg_thr_mid.split('/')[0]
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
                            else:
                                msg_thr_mid = None
                        if date - m_date > 5 * 24 * 3600:
                            break
                    except (KeyError, ValueError, IndexError):
                        pass

        if not msg_thr_mid:
            # OK, we are our own conversation root.
            msg_thr_mid = msg_mid

        if parent_mid and parent_mid != msg_thr_mid:
            msg_info[self.MSG_THREAD_MID] = '/'.join([msg_thr_mid, parent_mid])
        else:
            msg_info[self.MSG_THREAD_MID] = msg_thr_mid

        self.set_msg_at_idx_pos(msg_idx_pos, msg_info)

    def unthread_message(self, msg_mid, new_subject=None):
        msg_idx_pos = int(msg_mid, 36)
        msg_info = self.get_msg_at_idx_pos(msg_idx_pos)

        par_mid = msg_info[self.MSG_THREAD_MID].split('/')[-1]
        thr_mid = msg_info[self.MSG_THREAD_MID].split('/')[0]
        thr_idx_pos = int(thr_mid, 36)
        thr_info = self.get_msg_at_idx_pos(thr_idx_pos)

        thread = [t for t in thr_info[self.MSG_REPLIES][:-1].split(',') if t]

        # Collect parent/children relationships
        has_kids = {}
        for t_mid in thread:
            t_info = self.get_msg_at_idx_pos(int(t_mid, 36))
            t_pmid = t_info[self.MSG_THREAD_MID].split('/')[-1]
            has_kids[t_pmid] = has_kids.get(t_pmid, []) + [t_mid]

        # Gather all descendants of a message
        def _family(p_mid, hk):
            family = [p_mid]
            if p_mid in hk:
                gather = copy.copy(hk[p_mid])
                while gather:
                    r_mid = gather.pop(0)
                    if r_mid not in family:
                        family.append(r_mid)
                    if r_mid in hk:
                        gather.extend([
                            m for m in hk[r_mid]
                            if m not in family and m not in gather])
            return family

        # Reparent all descendants of a message
        def _reparent(p_mid, hk, new_subj=None):
            new_thread = _family(p_mid, hk)
            old_tmids = set([])
            orphans = set([])

            # Set up the new thread structure
            for t_mid in new_thread:
                t_idx_pos = int(t_mid, 36)
                t_info = self.get_msg_at_idx_pos(t_idx_pos)

                old_tmids.add(t_info[self.MSG_THREAD_MID].split('/')[0])
                orphaning = [
                    o for o in t_info[self.MSG_REPLIES].split(',')
                    if o and o not in new_thread]
                if orphaning:
                    orphans |= set(orphaning)

                if t_mid == p_mid:
                    self.edit_msg_info(t_info,
                        msg_subject=new_subj,
                        msg_replies=new_thread,
                        msg_parent_mid=p_mid,
                        msg_thread_mid=p_mid)
                else:
                    self.edit_msg_info(t_info,
                        msg_subject=new_subj,
                        msg_replies=[],
                        msg_thread_mid=p_mid)
                self.set_msg_at_idx_pos(t_idx_pos, t_info)

            # If we've left any messages without a thread marker, choose
            # a new one and reparent.
            orphans = sorted(list(orphans))
            for o_mid in orphans:
                o_idx_pos = int(o_mid, 36)
                o_info = self.get_msg_at_idx_pos(o_idx_pos)
                if o_mid == orphans[0]:
                    self.edit_msg_info(o_info,
                        msg_replies=orphans,
                        msg_thread_mid=o_mid)
                else:
                    self.edit_msg_info(o_info, msg_thread_mid=orphans[0])
                self.set_msg_at_idx_pos(o_idx_pos, o_info)

            # If we've left an existing thread, clean its reply list.
            old_tmids -= set(new_thread)
            for ot_mid in old_tmids:
                ot_idx_pos = int(ot_mid, 36)
                ot_info = self.get_msg_at_idx_pos(ot_idx_pos)
                self.edit_msg_info(ot_info, msg_replies=[
                    rmid for rmid in ot_info[self.MSG_REPLIES].split(',')
                    if rmid and (rmid not in new_thread)])
                self.set_msg_at_idx_pos(ot_idx_pos, ot_info)

        if par_mid == msg_mid:
            # If we're reparenting the root of a thread, this actually means
            # cut all our kids loose to their own threads.
            for k_mid in has_kids.get(msg_mid, []):
                _reparent(k_mid, has_kids)
            msg_info = self.get_msg_at_idx_pos(msg_idx_pos)
            self.edit_msg_info(msg_info,
                msg_subject=new_subject,
                msg_thread_mid=msg_mid,
                msg_parent_mid=msg_mid)
            self.set_msg_at_idx_pos(msg_idx_pos, msg_info)
        else:
            # Otherwise, cut ourselves and our kids loose.
            _reparent(msg_mid, has_kids, new_subj=new_subject)

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
                msg_mid]                             # Conversation ID

            if msg_from:
                ahp = AddressHeaderParser(msg_from)
                if ahp:
                    fn = ahp[0].fn
                    email = ahp[0].address
                else:
                    email, fn = ExtractEmailAndName(msg_from)
            else:
                email = fn = None
            if email and fn:
                self.update_email(email, name=fn)
            self.set_msg_at_idx_pos(msg_idx_pos, msg_info)
            return msg_idx_pos, msg_info

    def add_new_ghost(self, msg_id, trash=False, subject=None):
        tags = []
        if trash:
            tags = [t._key for t in self.config.get_tags(type='trash')]
        return self.add_new_msg(
            '',  # msg_ptr
            msg_id,
            1,   # msg_ts
            '',  # from
            [],  # msg_to
            [],  # msg_cc
            0,
            subject or _('(missing message)'),
            self.MSG_BODY_GHOST,
            tags)

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

    def _list_header_keywords(self, hdr, val_lower, body_info):
        """Extracts IDs and such from <...> in list-headers."""
        words = []
        for word in val_lower.replace(',', ' ').split():
            if not word:
                continue
            elif word[:5] == '<http':
                continue  # We just ignore web URLs for now
            elif (len(word) > 65) and ('+' in word) and ('@' in word):
                continue  # Ignore very long plussed addresses
            elif word[-1:] == '>':
                if word[:8] == '<mailto:':
                    word = word[8:-1]
                    if '?' in word:
                        word = word.split('?')[0]
                elif word[:1] == '<':
                    word = word[1:-1]
                else:
                    continue
                if ((hdr == 'list-post') or
                        (hdr == 'list-id' and 'list' not in body_info)):
                    body_info['list'] = word
                words.append(word)
                words.extend(re.findall(WORD_REGEXP, word))
        return set(words)

    def read_message(self, session,
                     msg_mid, msg_id, msg, msg_size, msg_ts,
                     mailbox=None):
        keywords = []
        snippet_text = snippet_html = ''
        body_info = {}
        payload = [None]
        textparts = 0
        parts = []
        urls = []
        for part in msg.walk():
            textpart = payload[0] = None
            ctype = part.get_content_type()
            pinfo = ''
            charset = part.get_content_charset() or 'utf-8'

            def _loader(p):
                if payload[0] is None:
                    payload[0] = try_decode(GetTextPayload(p), charset)
                return payload[0]

            if ctype == 'text/plain':
                textpart = _loader(part)
                if textpart[:3] in ('<di', '<ht', '<p>', '<p '):
                    ctype = 'text/html'
                else:
                    # FIXME: Search for URLs in the text part, add to urls list.
                    textparts += 1
                    pinfo = '%x::T' % len(payload[0])

            if ctype == 'text/html':
                _loader(part)
                pinfo = '%x::H' % len(payload[0])
                if len(payload[0]) > 3:
                    try:
                        textpart = extract_text_from_html(
                            payload[0],
                            url_callback=lambda u, t: urls.append((u, t)))
                    except:
                        session.ui.warning(_('=%s/%s has bogus HTML.'
                                             ) % (msg_mid, msg_id))
                        textpart = payload[0]
                else:
                    textpart = payload[0]

            if ctype == 'message/delivery-status':
                keywords.append('dsn:has')
            elif ctype == 'message/disposition-notification':
                keywords.append('mdn:has')

            if 'pgp' in part.get_content_type().lower():
                keywords.append('pgp:has')
                keywords.append('crypto:has')

            att = part.get_filename()
            if att:
                att = try_decode(att, charset)
                keywords.append('attachment:has')
                keywords.extend([t + ':att' for t
                                 in re.findall(WORD_REGEXP, att.lower())])
                att_kws = []
                for kw, ext_list in ATT_EXTS.iteritems():
                    ext = att.lower().rsplit('.', 1)[-1]
                    if ext in ext_list:
                        keywords.append('%s:has' % kw)
                        att_kws.append(kw)

                pmore = squish_mimetype(ctype)
                pdata = part.get_payload(None, True) or ''
                if 'image' in att_kws:
                    try:
                        if pdata:
                            # We disallow use of C libraries here, because of
                            # the massive attack surface, it's just not safe
                            # to use on all incoming e-mail.
                            size = image_size(pdata, pure_python=True)
                            if size is not None:
                                pmore = '%dx%d' % size
                    except:
                        traceback.print_exc()
                        pass

                pinfo = '%x:%s:%s' % (len(pdata), pmore, att)
                textpart = (textpart or '') + ' ' + att

            if textpart:
                # FIXME: Does this lowercase non-ASCII characters correctly?
                lines = [l for l in textpart.splitlines(True)
                         if not l.startswith('>')
                         and l[:4] not in ('----', '====', '____')]
                keywords.extend(re.findall(WORD_REGEXP,
                                           ''.join(lines).lower()))

                # NOTE: As a side effect here, the cryptostate plugin will
                #       add a 'crypto:has' keyword which we check for below
                #       before performing further processing.
                for kwe in _plugins.get_text_kw_extractors():
                    try:
                        keywords.extend(kwe(self, msg, ctype, textpart,
                                            body_info=body_info))
                    except:
                        if session.config.sys.debug:
                            traceback.print_exc()

                if ctype == 'text/plain':
                    snippet_text += ''.join(lines).strip() + '\n'
                else:
                    snippet_html += textpart.strip() + '\n'

            for extract in _plugins.get_data_kw_extractors():
                try:
                    keywords.extend(extract(self, msg, ctype, att, part,
                                            lambda: _loader(part),
                                            body_info=body_info))
                except:
                    if session.config.sys.debug:
                        traceback.print_exc()

            if not ctype.startswith('multipart/'):
                parts.append(pinfo)

        if urls:
            att_urls = []
            for (full_url, txt) in set(urls):
                url = full_url.lower().split('/', 3)
                if len(url) == 4 and url[0] in ('http:', 'https:'):
                    keywords.append('%s:url' % url[2])
                    for raw_re in session.config.prefs.attachment_urls:
                        url_re = self._url_re_cache.get(raw_re)
                        if url_re is None:
                            url_re = re.compile(raw_re)
                            self._url_re_cache[raw_re] = url_re
                        if url_re.search(full_url):
                            att_urls.append((full_url, txt))
                            break
            if att_urls:
                body_info['att_urls'] = att_urls
                keywords.append('attachment_url:has')
                keywords.append('attachment:has')

        if len(parts) > 1:
            body_info['parts'] = parts

        if textparts == 0:
            keywords.append('text:missing')

        if 'crypto:has' in keywords:
            e = Email(self, -1,
                      msg_parsed=msg,
                      msg_parsed_pgpmime=('all', msg),
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
                        try:
                            keywords.extend(kwe(self, msg, 'text/plain', text,
                                                body_info=body_info))
                        except:
                            if session.config.sys.debug:
                                traceback.print_exc()

        keywords.append('%s:id' % msg_id)
        keywords.extend(re.findall(WORD_REGEXP,
                                   safe_decode_hdr(msg, 'subject').lower()))
        keywords.extend(re.findall(WORD_REGEXP,
                                   safe_decode_hdr(msg, 'from').lower()))
        if mailbox:
            keywords.append('%s:mailbox' % FormatMbxId(mailbox).lower())

        headerprints = HeaderPrints(msg)
        # This is a signal for the bayesian filters to discriminate by MUA.
        keywords.append('%s:hpt' % headerprints['tools'])
        # This is used to detect forgeries and phishing, it includes info
        # about how the message was delivered (DKIM, Received, ...)
        keywords.append('%s:hps' % headerprints['sender'])
        # If we think we know what MUA that was, make it searchable
        if headerprints.get('mua'):
            keywords.append('%s:mua' % headerprints['mua'].split()[0].lower())

        is_list = False
        for key in msg.keys():
            key_lower = key.lower()
            if key_lower.startswith('list-'):
                is_list = True
            if key_lower not in BORING_HEADERS and key_lower[:2] != 'x-':
                val_lower = safe_decode_hdr(msg, key).lower()
                if key_lower[:5] == 'list-':
                    words = self._list_header_keywords(key_lower, val_lower,
                                                       body_info)
                    emails = []
                    key_lower = 'list'
                else:
                    words = set(re.findall(WORD_REGEXP, val_lower))
                    emails = ExtractEmails(val_lower)

                # Strip some common crap off; stop-words and robotic emails.
                words -= STOPLIST
                emails = [e for e in emails if
                          (len(e) < 40) or ('+' not in e and '/' not in e)]

                domains = [e.split('@')[-1] for e in emails]

                keywords.extend(['%s:%s' % (t, key_lower) for t in words])
                keywords.extend(['%s:%s' % (e, key_lower) for e in emails])
                keywords.extend(['%s:%s' % (d, key_lower) for d in domains])
                keywords.extend(['%s:email' % e for e in emails])

        # Personal mail: not from lists or common robots?
        msg_from = msg.get('from', '').lower()
        reply_to = msg.get('reply-to', '').lower()
        if not (is_list
                or 'robot@' in msg_from or 'notifications@' in msg_from
                or 'noreply' in msg_from.replace('-', '')
                or 'noreply' in reply_to.replace('-', '')
                or 'billing@' in msg_from or 'itinerary@' in msg_from
                or 'root@' in msg_from or 'mailer-daemon@' in msg_from
                or 'cron@' in msg_from or 'postmaster@' in msg_from
                or 'logwatch@' in msg_from
                or 'feedback-id' in msg):
            keywords.extend(['personal:is'])

            # This generates a unique group:X keyword identifying the
            # participants in this conversation. This will facilitate
            # more people-focused UI work down the line.
            emails = []
            for hdr in ('from', 'to', 'cc'):
                hdr = msg.get(hdr)
                if hdr:
                    ahp = AddressHeaderParser(hdr)
                    emails.extend([a.address.lower() for a in ahp])
            emails = sorted(list(set(emails)))
            if len(emails) > 1:
                keywords.append('%s:group' % md5_hex(', '.join(emails)))

        for key in EXPECTED_HEADERS:
            # This is a useful signal for spam classification
            if not msg[key]:
                keywords.append('%s:missing' % key)

        for extract in _plugins.get_meta_kw_extractors():
            try:
                keywords.extend(extract(self, msg_mid, msg, msg_size, msg_ts,
                                        body_info=body_info))
            except:
                if session.config.sys.debug:
                    traceback.print_exc()

        # FIXME: If we have a good snippet from the HTML part, it is likely
        #        to be more relevant due to the unfortunate habit of some
        #        senders to put all content in HTML and useless crap in text.
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

    def index_message(self, session, msg_mid, msg_id,
                      msg, msg_metadata_kws, msg_size, msg_ts,
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
            process_new(msg, msg_metadata_kws, msg_ts, keywords, snippet)
        elif incoming:
            # This is the default behavior if the above are undefined.
            if process_new is None:
                from mailpile.mail_source import ProcessNew
                ProcessNew(session, msg, msg_metadata_kws, msg_ts,
                           keywords, snippet)
            if apply_tags is None:
                keywords |= set(['%s:in' % tag._key for tag in
                                 self.config.get_tags(type='inbox')])

        # Mark as updated (modified/touched) today and on msg_ts
        keywords.add('%x:u' % (time.time() / (24 * 3600)))
        if msg_ts:
            keywords.add('%x:u' % (msg_ts / (24 * 3600)))

        for hook in filter_hooks or []:
            keywords = hook(session, msg_mid, msg, keywords,
                            incoming=incoming)

        if 'keywords' in self.config.sys.debug:
            print('KEYWORDS: %s' % keywords)

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

    def get_msg_at_idx_pos_uncached(self, msg_idx):
        rv = self.l2m(self.INDEX[msg_idx])
        if len(rv) != self.MSG_FIELDS_V2:
            raise ValueError()
        return rv

    def delete_msg_at_idx_pos(self, session, msg_idx, keep_msgid=False):
        info = self.get_msg_at_idx_pos(msg_idx)

        # Remove from PTR index
        for ptr in (p for p in info[self.MSG_PTRS].split(',') if p):
            if ptr in self.PTRS:
                del self.PTRS[ptr]

        # Most of the information just gets nuked.
        info[self.MSG_PTRS] = ''
        info[self.MSG_FROM] = ''
        info[self.MSG_TO] = ''
        info[self.MSG_CC] = ''
        info[self.MSG_KB] = 0
        info[self.MSG_SUBJECT] = ''
        info[self.MSG_BODY] = self.MSG_BODY_DELETED

        # The timestamp we keep partially intact, to not completely break
        # ordering within theads. This may not really be necessary.
        ts = long(info[self.MSG_DATE], 36)
        info[self.MSG_DATE] = b36(ts - (ts % (3600 * 24)))

        # FIXME: Remove from threads? This may break threading. :(

        if not keep_msgid:
            # If we don't keep the msgid, the message may reappear later
            # if it wasn't deleted from all source mailboxes. The caller
            # may request this if deletion is known to be incomplete.
            if info[self.MSG_ID] in self.MSGIDS:
                del self.MSGIDS[info[self.MSG_ID]]
            info[self.MSG_ID] = self._encode_msg_id('%s' % msg_idx)

        # Save changes...
        self.set_msg_at_idx_pos(msg_idx, info)

        # Remove all tags
        for tag in self.get_tags(msg_info=info):
            self.remove_tag(session, tag, msg_idxs=[msg_idx])

        # Record that these messages were deleted
        GlobalPostingList.Append(session, 'deleted:is', [b36(msg_idx)])

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

        msg_thr_mid = msg_info[self.MSG_THREAD_MID].split('/')[0]
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

    def get_conversation(self, msg_info=None, msg_idx=None, ghosts=False):
        if not msg_info:
            msg_info = self.get_msg_at_idx_pos(msg_idx)
        conv_mid = msg_info[self.MSG_THREAD_MID].split('/')[0]
        if conv_mid:
            conv_mid_idx = int(conv_mid, 36)
            replies = self.get_replies(msg_idx=conv_mid_idx)

            # In case of buggy data, ensure both the conversation head and
            # the message itself are included in the results.
            reply_mids = [r[self.MSG_MID] for r in replies]
            if conv_mid not in reply_mids:
                replies = [self.get_msg_at_idx_pos(conv_mid_idx)] + replies
                reply_mids.append(conv_mid)
            if msg_info[self.MSG_MID] not in reply_mids:
                replies += [msg_info]

            if ghosts:
                return replies
            else:
                return [r for r in replies
                        if r[self.MSG_BODY] not in self.MSG_BODY_MAGIC]
        else:
            return [msg_info]

    def get_replies(self, msg_info=None, msg_idx=None):
        if not msg_info:
            msg_info = self.get_msg_at_idx_pos(msg_idx)
        return [self.get_msg_at_idx_pos(int(r, 36)) for r
                in set(msg_info[self.MSG_REPLIES].split(',')) if r]

    def get_tags(self, msg_info=None, msg_idx=None):
        if not msg_info:
            msg_info = self.get_msg_at_idx_pos(msg_idx)
        taglist = [r for r in msg_info[self.MSG_TAGS].split(',') if r]
        if not 'tags' in self.config:
            return taglist
        return [r for r in taglist if r in self.config.tags]

    def add_tag(self, session, tag_id,
                msg_info=None, msg_idxs=None,
                conversation=False, allow_message_id_clearing=False):
        if msg_info and msg_idxs is None:
            msg_idxs = set([int(msg_info[self.MSG_MID], 36)])
        else:
            msg_idxs = set(msg_idxs)
        if not msg_idxs:
            return set()

        CachedSearchResultSet.DropCaches()

        if conversation:
            session.ui.mark(_n('Tagging %d conversation (%s)',
                           'Tagging %d conversations (%s)',
                           len(msg_idxs)
                           ) % (len(msg_idxs), tag_id))
            for msg_idx in list(msg_idxs):
                for reply in self.get_conversation(msg_idx=msg_idx,
                                                   ghosts=True):
                    if reply[self.MSG_MID]:
                        msg_idxs.add(int(reply[self.MSG_MID], 36))
        else:
            session.ui.mark(_n('Tagging %d message (%s)',
                           'Tagging %d messages (%s)',
                           len(msg_idxs)
                           ) % (len(msg_idxs), tag_id))

        clear_message_id = False
        if allow_message_id_clearing:
            if session.config.tags[tag_id].type == 'trash':
                 clear_message_id = True

        eids = set()
        added = set()
        threads = set()
        for msg_idx in msg_idxs:
            if msg_idx >= 0 and msg_idx < len(self.INDEX):
                modified = False
                msg_info = self.get_msg_at_idx_pos(msg_idx)
                tags = set([r for r in msg_info[self.MSG_TAGS].split(',')
                            if r and r in session.config.tags])
                if tag_id not in tags:
                    tags.add(tag_id)
                    msg_info[self.MSG_TAGS] = ','.join(list(tags))
                    added.add(msg_idx)
                    threads.add(msg_info[self.MSG_THREAD_MID].split('/')[0])
                    modified = True
                if clear_message_id:
                    old_msgid = msg_info[self.MSG_ID]
                    if old_msgid in self.MSGIDS:
                        del self.MSGIDS[old_msgid]
                    msg_info[self.MSG_ID] = self._encode_msg_id('%s' % msg_idx)
                    self.MSGIDS[msg_info[self.MSG_ID]] = msg_idx
                    modified = True
                if modified:
                    self.INDEX[msg_idx] = self.m2l(msg_info)
                    self.MODIFIED.add(msg_idx)
                    self.update_msg_sorting(msg_idx, msg_info)
                    if msg_idx in self.CACHE:
                        del self.CACHE[msg_idx]
                eids.add(msg_idx)

        with self._lock:
            if tag_id in self.TAGS:
                self.TAGS[tag_id] |= eids
            elif eids:
                self.TAGS[tag_id] = eids

        # Record that these messages were touched in some way
        GlobalPostingList.Append(session,
                                 '%x:u' % (time.time() // (24 * 3600)),
                                 [b36(e) for e in eids])

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

        session.ui.mark(_n('Untagging conversation (%s)',
                           'Untagging conversations (%s)',
                           len(msg_idxs)
                           ) % (tag_id, ))
        CachedSearchResultSet.DropCaches()
        for msg_idx in list(msg_idxs):
            if conversation:
                for reply in self.get_conversation(msg_idx=msg_idx,
                                                   ghosts=True):
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
                            if r and r in session.config.tags])
                if tag_id in tags:
                    tags.remove(tag_id)
                    msg_info[self.MSG_TAGS] = ','.join(list(tags))
                    self.INDEX[msg_idx] = self.m2l(msg_info)
                    self.MODIFIED.add(msg_idx)
                    self.update_msg_sorting(msg_idx, msg_info)
                    if msg_idx in self.CACHE:
                        del self.CACHE[msg_idx]
                    removed.add(msg_idx)
                    threads.add(msg_info[self.MSG_THREAD_MID].split('/')[0])
                eids.add(msg_idx)
        with self._lock:
            if tag_id in self.TAGS:
                self.TAGS[tag_id] -= eids

        # Record that these messages were touched in some way
        GlobalPostingList.Append(session,
                                 '%x:u' % (time.time() // (24 * 3600)),
                                 [b36(e) for e in eids])

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
        return results, tag

    def search(self, session, searchterms,
               keywords=None, order=None, recursion=0, context=None):
        # Stash the raw search terms
        raw_terms = searchterms[:]

        # Choose how we are going to search
        if keywords is not None:
            # Searching within pre-defined keywords
            def hits(term):
                return [int(h, 36) for h in keywords.get(term, [])]
        else:
            # Normal search
            def hits(term):
                if term.endswith(':in'):
                    return self.TAGS.get(term.rsplit(':', 1)[0], [])
                else:
                    session.ui.mark(_('Searching for %s') % term)
                    gpl_hits = GlobalPostingList(session, term).hits()
                    try:
                        return [int(h, 36) for h in gpl_hits]
                    except ValueError:
                        b36re = re.compile('^[a-zA-Z0-9]{1,8}$')
                        print('FIXME! BAD HITS: %s => %s' % (term, [
                            h for h in gpl_hits if not b36re.match(h)]))
                        return [int(h, 36) for h in gpl_hits if b36re.match(h)]

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

        searched_invisible = False
        searched_mailbox = False
        searched_deleted = False

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
                if term.startswith('in:'):
                    results, tag = self.search_tag(session, term, hits,
                                                   recursion=recursion)
                    rt.extend(results)
                    if tag:
                        if tag.flag_hides:
                            searched_invisible = True
                        if tag.type == 'mailbox':
                            searched_mailbox = True

                elif term.startswith('mid:'):
                    rt.extend([int(t, 36) for t in
                               term[4:].replace('=', '').split(',')])
                elif term.startswith('body:'):
                    rt.extend(hits(term[5:]))
                elif term == 'all:mail':
                    rt.extend(range(0, len(self.INDEX)))
                elif term in ('to:me', 'cc:me', 'from:me'):
                    vcards = self.config.vcards
                    emails = []
                    for vc in vcards.find_vcards([], kinds=['profile']):
                        emails += [vcl.value for vcl in vc.get_all('email')]
                    for email in set(emails):
                        if email:
                            rt.extend(hits('%s:%s' % (email,
                                                      term.split(':')[0])))
                elif term == 'is:encrypted':
                    for status in EncryptionInfo.STATUSES:
                        if status in CryptoInfo.STATUSES:
                            continue
                        rt.extend(self.search_tag(
                            session, 'in:mp_enc-%s' % status, hits,
                            recursion=recursion)[0])
                elif term == 'is:signed':
                    for status in SignatureInfo.STATUSES:
                        if status in CryptoInfo.STATUSES:
                            continue
                        rt.extend(self.search_tag(
                            session, 'in:mp_sig-%s' % status, hits,
                            recursion=recursion)[0])
                else:
                    if term == 'is:deleted':
                        searched_deleted = True
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
                (not searched_invisible) and
                (not searched_mailbox) and
                (not searched_deleted) and
                ('tags' in self.config) and
                (not session or 'all' not in order)):
            invisible = self.config.get_tags(flag_hides=True)
            exclude_terms = (['is:deleted'] +
                             ['in:%s' % i._key for i in invisible])
            if len(exclude_terms) > 1:
                exclude_terms = ([exclude_terms[0]] +
                                 ['+%s' % e for e in exclude_terms[1:]])
            # Recursing to pull the excluded terms from cache as well
            exclude = self.search(session, exclude_terms).as_set()

        # Decide if this is cached or not
        if keywords is None:
            srs = CachedSearchResultSet(self, raw_terms)
            if len(srs) > 0:
                return srs
        else:
            srs = SearchResultSet(self, raw_terms, [], [])

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
            all_new = set()
            if 'freshness' in how:
                # FIXME: This calculation appears very cachable!
                new_tags = session.config.get_tags(type='unread')
                for tag in new_tags:
                    all_new |= self.TAGS.get(tag._key, set([]))

            # This filters away all but the first (or oldst unread) result in
            # each conversation.
            session.ui.mark(_('Collapsing conversations...'))
            seen, pi = {}, 0
            for ri in results:
                ti = self.INDEX_THR[ri]
                if ti in seen:
                    if ti in all_new:
                        results[seen[ti]] = ri
                else:
                    results[pi] = ri
                    seen[ti] = pi
                    pi += 1
            results[pi:] = []
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
    print('%s' % (results, ))
    if results.failed:
        sys.exit(1)
