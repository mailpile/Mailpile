# Plugins!

import mailpile.commands
import mailpile.defaults
import mailpile.vcard

# These are the plugins we import by default
__all__ = ['search', 'tags', 'contacts', 'compose', 'groups', 'dates',
           'setup_magic', 'networkgraph', 'exporters',
           'vcard_carddav', 'vcard_gnupg', 'vcard_gravatar', 'vcard_mork',
           'hacks']


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


##[ Pluggable vcard functions ]###############################################

VCARD_IMPORTERS = {}
VCARD_EXPORTERS = {}
VCARD_CONTEXT_PROVIDERS = {}


def _reg_vcard_plugin(what, cfg_sect, plugin_classes, cls, dct):
    for plugin_class in plugin_classes:
        if not plugin_class.SHORT_NAME or not plugin_class.FORMAT_NAME:
            raise PluginError("Please set SHORT_NAME and FORMAT_* attributes!")
        if not issubclass(plugin_class, cls):
            raise PluginError("%s must be a %s" % (what, cls))
        if plugin_class.SHORT_NAME in dct:
            raise PluginError("%s for %s already registered"
                              % (what, importer.FORMAT_NAME))

        if plugin_class.CONFIG_RULES:
            rules = {
                'guid': ['VCard source UID', str, ''],
                'description': ['VCard source description', str, '']
            }
            rules.update(plugin_class.CONFIG_RULES)
            register_config_section('prefs', 'vcard', cfg_sect,
                                    plugin_class.SHORT_NAME,
            [
                plugin_class.FORMAT_DESCRIPTION, rules, []
            ])

        dct[plugin_class.SHORT_NAME] = plugin_class


def register_vcard_importers(*importers):
    _reg_vcard_plugin('Importer', 'importers', importers,
                      mailpile.vcard.VCardImporter, VCARD_IMPORTERS)


def register_contact_exporters(*exporters):
    _reg_vcard_plugin('Exporter', 'exporters', exporters,
                      mailpile.vcard.VCardExporter, VCARD_EXPORTERS)


def register_contact_context_providers(*providers):
    _reg_vcard_plugin('Context provider', 'context', providers,
                      mailpile.vcard.VCardContextProvider,
                      VCARD_CONTEXT_PROVIDERS)


##[ Pluggable commands ]######################################################

def register_commands(*args):
    COMMANDS = mailpile.commands.COMMANDS
    for cls in args:
        if cls not in COMMANDS:
            COMMANDS.append(cls)
