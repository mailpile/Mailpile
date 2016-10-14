from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n


class MessageInfoConstants(object):
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

    MSG_BODY_LAZY = '{L}'
    MSG_BODY_GHOST = '{G}'
    MSG_BODY_DELETED = '{D}'
    MSG_BODY_UNSCANNED = (MSG_BODY_LAZY, MSG_BODY_GHOST)
    MSG_BODY_MAGIC = (MSG_BODY_LAZY, MSG_BODY_GHOST, MSG_BODY_DELETED)

    BOGUS_METADATA = [None, '', None, '0', '(no sender)', '', '', '0',
                      '(not in index)', '', '', '', '-1']


if __name__ == '__main__':
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
