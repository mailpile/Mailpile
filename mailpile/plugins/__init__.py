# Plugins!

import mailpile.commands

# These are the plugins we import by default
__all__ = ['search', 'compose', 'groups', 'dates']

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

def get_data_kw_extractors(): return DATA_KW_EXTRACTORS.values()
def get_text_kw_extractors(): return TEXT_KW_EXTRACTORS.values()
def get_meta_kw_extractors(): return META_KW_EXTRACTORS.values()


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

def register_command(shortname, longname, cls):
  COMMANDS = mailpile.commands.COMMANDS
  if shortname in COMMANDS or shortname.replace(':', '') in COMMANDS:
    raise PluginError('Already registered: %s' % shortname)
  COMMANDS[shortname] = (longname, cls)

