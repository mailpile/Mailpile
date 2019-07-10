from __future__ import print_function
import copy
import json
import random
import rfc822
import time
import traceback

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.index.msginfo import MessageInfoConstants
from mailpile.index.search import SearchResultSet
from mailpile.mailutils import MBX_ID_LEN
from mailpile.mailutils.addresses import AddressHeaderParser
from mailpile.mailutils.safe import *
from mailpile.util import *


class BaseIndex(MessageInfoConstants):

    MAX_CACHE_ENTRIES = 250

    CAN_SEARCH = 'can_search'  # Can search message contents
    CAN_SORT = 'can_sort'      # Can sort search results
    HAS_UNREAD = 'has_unread'  # Can filter messages by read/unread
    HAS_ATTS = 'has_atts'      # Can filter messages by attachments or no
    HAS_TAGS = 'has_tags'      # Can filter messages by tags and/or apply tags

    # What is this Index capable of?  A list or set of the above.
    CAPABILITIES = []

    def __init__(self, config):
        self.config = config
        self.CACHE = {}
        self.EMAILS = []
        self.EMAIL_IDS = {}

    ### Known e-mail addresses #############################################

    # NOTE: This is all probably a misfeature and should probably go away.

    def add_email(self, email, name=None, eid=None):
        if eid is None:
            eid = len(self.EMAILS)
            self.EMAILS.append('')
        self.EMAILS[eid] = '%s (%s)' % (email, name or email)
        self.EMAIL_IDS[email.lower()] = eid
        # FIXME: This needs to get written out...
        return eid

    def update_email(self, email, name=None, change_name=True):
        eid = self.EMAIL_IDS.get(email.lower())
        if (eid is not None) and not change_name:
            el = self.EMAILS[eid].split(' ')
            if len(el) == 2:
                en = el[1][1:-1]
                if '@' not in en:
                    name = en
        return self.add_email(email, name=name, eid=eid)

    def compact_to_list(self, msg_to):
        eids = []
        for ai in msg_to:
            email = ai.address
            eid = self.EMAIL_IDS.get(email.lower())
            if eid is None:
                eid = self.add_email(email, name=ai.fn)
            elif ai.fn and ai.fn != email:
                self.update_email(email, name=ai.fn, change_name=False)
            eids.append(eid)
        return ','.join([b36(e) for e in set(eids)])

    def expand_to_list(self, msg_info, field=None):
        eids = msg_info[field if (field is not None) else self.MSG_TO]
        eids = [e for e in eids.strip().split(',') if e]
        return [self.EMAILS[int(e, 36)] for e in eids]


    ### Tags & filters #####################################################

    def remove_tag(self, session, tid, msg_idxs=None):
        pass

    def add_tag(self, session, tid, msg_idxs=None):
        pass

    def apply_filters(self, session, fid, msg_idxs=None):
        pass


    ### Searching & sorting ################################################

    def search(self, session, terms, context=None):
        return SearchResultSet(self, terms, [], [])

    def sort_results(self, session, results, sort_order):
        pass

    def get_conversation(self, msg_idx=None):
        return []


    ### Loading data: subclasses override these ############################

    def get_msg_at_idx_pos_uncached(self, msg_idx):
        raise IndexError('Unimplemented')

    def open_mailbox_by_ptr(self, msg_ptr):
        return self.config.open_mailbox(None, msg_ptr[:MBX_ID_LEN])


    ### Loading data: higher level methods #################################

    def unique_mbox_ids(self, msg_info):
        return set([
            p[:MBX_ID_LEN] for p in msg_info[self.MSG_PTRS].split(',') if p])

    def enumerate_ptrs_mboxes_fds(self, msg_info):
        for msg_ptr in self._sorted_msg_ptrs(msg_info):
            mbox = fd = None
            try:
                mbox = self.open_mailbox_by_ptr(msg_ptr)
                fd = mbox.get_file_by_ptr(msg_ptr)
            except (IOError, OSError, KeyError, ValueError, IndexError):
                if 'sources' in self.config.sys.debug:
                    traceback.print_exc()
                    print('WARNING: %s not found' % msg_ptr)
            yield (msg_ptr, mbox, fd)

    ### ... ################################################################

    def _sorted_msg_ptrs(self, msg_info):
        ptrs = (p.strip() for p in msg_info[self.MSG_PTRS].split(','))
        # FIXME: Prefer local data? Prefer some mailbox types? Hmm.
        #        Doing this well would speed things up and ensure the
        #        `message/delete --keep` deduplication works nicely.
        return sorted([p for p in ptrs if p])

    def _encode_msg_id(self, msg_id):
        """Normalize and hash a message ID for the metadata index"""
        if '<' in msg_id:
            new_msg_id = '<%s>' % msg_id.split('<')[1].split('>')[0]
            if len(new_msg_id) > 2:
                msg_id = new_msg_id
        return b64c(sha1b64(msg_id.strip()))

    def get_msg_id(self, msg, msg_ptr):
        return self._encode_msg_id(safe_get_msg_id(msg) or msg_ptr)

    def _message_to_msg_info(self, msg_idx_pos, msg_ptr, msg):
        msg_mid = b36(msg_idx_pos)
        msg_to = AddressHeaderParser(msg.get('to'))
        msg_cc = AddressHeaderParser(msg.get('cc'))
        msg_cc += AddressHeaderParser(msg.get('bcc'))
        return [
            msg_mid,
            msg_ptr,                          # Message PTR
            self.get_msg_id(msg, msg_ptr),    # Message ID
            b36(safe_message_ts(msg)),        # Message timestamp
            safe_decode_hdr(msg, 'from'),     # Message from
            self.compact_to_list(msg_to),     # Compacted to-list
            self.compact_to_list(msg_cc),     # Compacted cc/bcc-list
            b36(len(msg) // 1024),            # Message size
            safe_decode_hdr(msg, 'subject'),  # Subject
            self.MSG_BODY_LAZY,               # Body snippets come later
            '',                               # Tags
            '',                               # Replies
            msg_mid]                          # Thread

    def get_msg_at_idx_pos(self, msg_idx):
        try:
            crv = self.CACHE.get(msg_idx, {})
            if 'msg_info' in crv:
                return crv['msg_info']

            if len(self.CACHE) > self.MAX_CACHE_ENTRIES:
                try:
                    for k in random.sample(
                            self.CACHE.keys(), self.MAX_CACHE_ENTRIES/20):
                        del self.CACHE[k]
                except KeyError:
                    pass
            rv = self.get_msg_at_idx_pos_uncached(msg_idx)
            crv['msg_info'] = rv
            self.CACHE[msg_idx] = crv
            return rv

        except (IndexError, ValueError):
            return copy.copy(self.BOGUS_METADATA)

    def set_msg_at_idx_pos(self, msg_idx, msg_info):
        pass

        return []  # FIXME

    @classmethod
    def get_body(self, msg_info):
        msg_body = msg_info[self.MSG_BODY]
        if msg_body.startswith('{'):
            if msg_body == self.MSG_BODY_LAZY:
                return {'snippet': _('(unprocessed)'), 'lazy': True}
            elif msg_body == self.MSG_BODY_GHOST:
                return {'snippet': _('(ghost)'), 'ghost': True}
            elif msg_body == self.MSG_BODY_DELETED:
                return {'snippet': _('(deleted)'), 'deleted': True}
            try:
                return json.loads(msg_body)
            except ValueError:
                pass
        return {
            'snippet': msg_body
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
            snippet = d['snippet']
            if snippet[:3] in self.MSG_BODY_MAGIC or snippet[:1] != '{':
                return d['snippet']
        return json.dumps(d, indent=None, separators=(',', ':'))

    @classmethod
    def set_body(self, msg_info, **kwargs):
        d = self.get_body(msg_info)
        msg_info[self.MSG_BODY] = self.encode_body(d, **kwargs)


if __name__ == '__main__':
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print('%s' % (results, ))
    if results.failed:
        sys.exit(1)
