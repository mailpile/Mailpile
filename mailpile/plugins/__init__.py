# Plugins!

class PluginError(Exception):
  pass


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

COMMANDS = {}

def register_command(shortname, longname, cls):
  global COMMANDS
  if shortname in COMMANDS or shortname.replace(':', '') in COMMANDS:
    raise PluginError('Already registered: %s' % shortname)
  COMMANDS[shortname] = (longname, cls)

