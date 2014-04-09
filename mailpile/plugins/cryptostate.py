from gettext import gettext as _

from mailpile.plugins import PluginManager


_plugins = PluginManager(builtin=__file__)


##[ Keywords ]################################################################

def text_kw_extractor(index, msg, ctype, text):
    kw = set()
    if ('-----BEGIN PGP' in text and '\n-----END PGP' in text):
        kw.add('pgp:has')
        kw.add('crypto:has')
    return kw


def meta_kw_extractor(index, msg_mid, msg, msg_size, msg_ts):
    kw, enc, sig = set(), set(), set()
    for part in msg.walk():
        enc.add('mp_%s-%s' % ('enc', part.encryption_info['status']))
        sig.add('mp_%s-%s' % ('sig', part.signature_info['status']))

        # This is generic
        if (part.encryption_info.get('status') != 'none'
                or part.signature_info.get('status') != 'none'):
            kw.add('crypto:has')

        # This is OpenPGP-specific
        if (part.encryption_info.get('protocol') == 'openpgp'
                or part.signature_info.get('protocol') == 'openpgp'):
            kw.add('pgp:has')

        # FIXME: Other encryption protocols?

    for tname in (enc | sig):
        tag = index.config.get_tags(slug=tname)
        if tag:
            kw.add('%s:in' % tag[0]._key)

    return list(kw)

_plugins.register_text_kw_extractor('crypto_tkwe', text_kw_extractor)
_plugins.register_meta_kw_extractor('crypto_mkwe', meta_kw_extractor)


##[ Search helpers ]##########################################################

def search(config, idx, term, hits):
    #
    # FIXME: Translate things like pgp:signed into a search for all the
    #        tags that have signatures (good or bad).
    #
    return []

_plugins.register_search_term('crypto', search)
_plugins.register_search_term('pgp', search)
