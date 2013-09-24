# Plugins!

import mailpile.commands

# These are the plugins we import by default
__all__ = ['search', 'tags', 'contacts', 'compose', 'groups', 'dates',
           'gpg', 'setup', 'networkgraph']


class PluginError(Exception):
    pass


##[ Pluggable keyword extractors ]############################################

DATA_KW_EXTRACTORS = {}
TEXT_KW_EXTRACTORS = {}
META_KW_EXTRACTORS = {}


def _rkwe(kw_hash, term, function):
    if term in kw_hash:
        raise PluginError('Already registered: %s' % term)
    kw_hash[term] = function


def register_data_kw_extractor(term, function):
    return _rkwe(DATA_KW_EXTRACTORS, term, function)


def register_text_kw_extractor(term, function):
    return _rkwe(TEXT_KW_EXTRACTORS, term, function)


def register_meta_kw_extractor(term, function):
    return _rkwe(META_KW_EXTRACTORS, term, function)


def get_data_kw_extractors():
    return DATA_KW_EXTRACTORS.values()


def get_text_kw_extractors():
    return TEXT_KW_EXTRACTORS.values()


def get_meta_kw_extractors():
    return META_KW_EXTRACTORS.values()


##[ Pluggable search terms ]##################################################

SEARCH_TERMS = {}


def get_search_term(term, default=None):
    return SEARCH_TERMS.get(term, default)


def register_search_term(term, function):
    global SEARCH_TERMS
    if term in SEARCH_TERMS:
        raise PluginError('Already registered: %s' % term)
    SEARCH_TERMS[term] = function


##[ Pluggable commands ]##################################################


def register_commands(*args):
    COMMANDS = mailpile.commands.COMMANDS
    for cls in args:
        if cls not in COMMANDS:
            COMMANDS.append(cls)


def register_command(shortcode, name, cls):
    """Backwards compatibility hack."""
    print "WARNING: Patching %s into COMMANDS" % cls
    if shortcode.startswith('_'):
      shortcode = ''
    cls.SYNOPSIS = [shortcode.replace(':', ''),
                    name.replace('=', '').replace('/', ' '),
                    name.replace('=', ''),
                    cls.SYNOPSIS]
    register_commands(cls)
