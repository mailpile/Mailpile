# Plugins!

import mailpile.commands
import mailpile.defaults

# These are the plugins we import by default
__all__ = ['search', 'tags', 'contacts', 'compose', 'groups', 'dates',
           'setup', 'networkgraph', 'exporters']


class PluginError(Exception):
    pass


##[ Pluggable configuration ]#################################################

def register_config_variables(*args):
    args = list(args)
    rules = args.pop(-1)
    dest = mailpile.defaults.CONFIG_RULES
    path = '/'.join(args)
    for arg in args:
        dest = dest[arg][-1]
    for rname, rule in rules.iteritems():
        if rname in dest:
            raise PluginError('Variable already exist: %s/%s' % (path, rname))
        else:
            dest[rname] = rule


def register_config_section(*args):
    args = list(args)
    rules = args.pop(-1)
    rname = args.pop(-1)
    dest = mailpile.defaults.CONFIG_RULES
    path = '/'.join(args)
    for arg in args:
        dest = dest[arg][-1]
    if rname in dest:
        raise PluginError('Section already exist: %s/%s' % (path, rname))
    else:
        dest[rname] = rules


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
    import sys
    sys.stderr.write("WARNING: Patching %s into COMMANDS\n" % cls)
    if shortcode.startswith('_'):
      shortcode = ''
    cls.SYNOPSIS = [shortcode.replace(':', ''),
                    name.replace('=', ''),
                    None,
                    cls.SYNOPSIS]
    register_commands(cls)

##[ Pluggable contact management ]########################################

from mailpile.plugins.contacts import ContactImporter, ContactExporter, ContactFieldValidator, ContactContextProvider

CONTACT_IMPORTERS = {}
CONTACT_EXPORTERS = {}
CONTACT_FIELD_VALIDATORS = {}
CONTACT_CONTEXT_PROVIDERS = {}

def register_contact_importer(importer):
    if not issubclass(importer, ContactImporter):
        raise PluginError("Plugin must be a ContactImporter")
    if importer.format_name in CONTACT_IMPORTERS.keys():
        raise PluginError("Importer for %s already registered" % importer.format_name)
    CONTACT_IMPORTERS[importer.format_name] = importer

def register_contact_exporter(exporter):
    if not issubclass(importer, ContactExporter):
        raise PluginError("Plugin must be a ContactExporter")
    if exporter.format_name in CONTACT_EXPORTERS.keys():
        raise PluginError("Exporter for %s already registered" % exporter.format_name)
    CONTACT_EXPORTERS[exporter.format_name] = exporter

def register_contact_field_validator(field, validator):
    if not issubclass(importer, ContactFieldValidator):
        raise PluginError("Plugin must be a ContactFieldValidator")
    if field in CONTACT_FIELD_VALIDATORS.keys():
        raise PluginError("Field validator for field %s already registered" % field)
    CONTACT_FIELD_VALIDATORS[field] = validator

def register_contact_context_provider(provider):
    if not issubclass(importer, ContactContextProvider):
        raise PluginError("Plugin must be a ContactContextProvider")
    if importer.provider_name in CONTACT_CONTEXT_PROVIDERS.keys():
        raise PluginError("Context provider for %s already registered" % provider.provider_name)
    CONTACT_CONTEXT_PROVIDERS[provider.provider_name] = provider

