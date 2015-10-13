import math
import time
import datetime

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager


_plugins = PluginManager(builtin=__file__)


##[ Keywords ]################################################################

def meta_kw_extractor(index, msg_mid, msg, msg_size, msg_ts, **kwargs):
    """Create a search term with the floored log2 size of the message."""
    if msg_size <= 0:
        return []
    return ['%s:ln2sz' % int(math.log(msg_size, 2))]

_plugins.register_meta_kw_extractor('sizes', meta_kw_extractor)


##[ Search terms ]############################################################


_size_units = {
    't': 40,
    'g': 30,
    'm': 20,
    'k': 10,
    'b': 0
}
_range_keywords = [
    '..',
    '-'
]


def _mk_logsize(size, default_unit=0):
    if not size:
        return 0
    unit = 0
    size = size.lower()
    if size[-1].isdigit():  # ends with a number
        unit = default_unit
    elif len(size) >= 2 and size[-2] in _size_units and size[-1] == 'b':
        unit = _size_units[size[-2]]
        size = size[:-2]
    elif size[-1] in _size_units:
        unit = _size_units[size[-1]]
        size = size[:-1]
    try:
        return int(math.log(float(size), 2) + unit)
    except ValueError:
        return 1 + unit


def search(config, idx, term, hits):
    try:
        word = term.split(':', 1)[1].lower()

        for range_keyword in _range_keywords:
            if range_keyword in term:
                start, end = word.split(range_keyword)
                break
        else:
            start = end = word

        # if no unit is setup in the start term, use the unit from the end term
        end_unit_size = end.lower()[-1]
        end_unit = 0
        if end_unit_size in _size_units:
            end_unit = _size_units[end_unit_size]

        start = _mk_logsize(start, end_unit)
        end = _mk_logsize(end)
        terms = ['%s:ln2sz' % sz for sz in range(start, end+1)]

        rt = []
        for t in terms:
            rt.extend(hits(t))
        return rt
    except:
        raise ValueError('Invalid size: %s' % term)


_plugins.register_search_term('size', search)
