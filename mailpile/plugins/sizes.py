import math
import time
import datetime
from gettext import gettext as _

import mailpile.plugins


##[ Keywords ]################################################################

def meta_kw_extractor(index, msg_mid, msg, msg_size, msg_ts):
    """Create a search term with the floored log2 size of the message."""
    return ['%s:ln2sz' % int(math.log(msg_size, 2))]

mailpile.plugins.register_meta_kw_extractor('sizes', meta_kw_extractor)


##[ Search terms ]############################################################


_size_units = {
    't': 40,
    'g': 30,
    'm': 20,
    'k': 10
}


def _mk_logsize(size):
    unit = 0
    size = size.lower()
    if size.endswith('b'):
        size = size[:-1]
    if size[-1] in _size_units:
        unit = _size_units[size[-1]]
        size = size[:-1]
    try:
        return int(math.log(float(size), 2) + unit)
    except ValueError:
        return 1 + unit


def search(config, idx, term, hits):
    try:
        word = term.split(':', 1)[1].lower()
        if '..' in term:
            start, end = word.split('..')
        else:
            start = end = word

        start = _mk_logsize(start)
        end = _mk_logsize(end)
        terms = ['%s:ln2sz' % sz for sz in range(start, end+1)]

        rt = []
        for t in terms:
            rt.extend(hits(t))
        return rt
    except:
        raise ValueError('Invalid size: %s' % term)


mailpile.plugins.register_search_term('size', search)
