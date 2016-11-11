import email.parser
import json
import traceback

from mailpile.util import *
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.index.base import BaseIndex
from mailpile.index.msginfo import MessageInfoConstants
from mailpile.index.search import SearchResultSet
from mailpile.mailutils import MBX_ID_LEN


class MailboxIndex(BaseIndex):

    FAKE_MBX_ID = ('Z' * MBX_ID_LEN)

    def __init__(self, config, mailbox, mbx_mid=None):
        BaseIndex.__init__(self, config)
        self.mbx_mid = mbx_mid or self.FAKE_MBX_ID
        self.mailbox = mailbox
        self.ptrset = set([])
        self.idxmap = []

    def get_msg_at_idx_pos_uncached(self, msg_idx_pos):
        msg_ptr = self.idxmap[msg_idx_pos]
        msg_raw = self.mailbox.get_file_by_ptr(msg_ptr)
        message = email.parser.Parser().parse(msg_raw, True)
        return self._message_to_msg_info(msg_idx_pos, msg_ptr, message)

    def open_mailbox_by_ptr(self, msg_ptr):
        if msg_ptr[:MBX_ID_LEN] == self.mbx_mid:
            return self.mailbox
        else:
            return BaseIndex.open_mailbox_by_ptr(self, msg_ptr)

    def _update_keymap(self):
        try:
            mailbox_keys = self.mailbox.keys()
            mailbox_ptrs = [self.mailbox.get_msg_ptr(self.mbx_mid, i)
                            for i in mailbox_keys]
            for ptr in mailbox_ptrs:
                if ptr not in self.ptrset:
                    self.idxmap.append(ptr)
            self.ptrset = set(mailbox_ptrs)
        except:
            traceback.print_exc()

    def search(self, session, terms, context=None):
        if not terms or terms == ['all:mail']:
            self._update_keymap()
            result = [i for i, ptr in enumerate(self.idxmap)
                      if ptr in self.ptrset]
            result.reverse()
        else:
            print 'FIXME! %s: search %s' % (self, terms)
            result = []
        return SearchResultSet(self, terms, result, [])


if __name__ == '__main__':
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
