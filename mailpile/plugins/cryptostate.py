from gettext import gettext as _

import mailpile.plugins


##[ Keywords ]################################################################

def meta_kw_extractor(index, msg_mid, msg, msg_size, msg_ts):
    kw, enc, sig = set(), set(), set()

    # FIXME: Track which crypto protocol is being used?

    for part in msg.walk():
        enc.add('mp_%s-%s' % ('enc', part.encryption_info['status']))
        sig.add('mp_%s-%s' % ('sig', part.signature_info['status']))
    for tname in (enc|sig):
        tag = index.config.get_tags(slug=tname)
        if tag:
            kw.add('%s:tag' % tag[0]._key)
    return list(kw)

mailpile.plugins.register_meta_kw_extractor('crypto_kws', meta_kw_extractor)


##[ Search helpers ]##########################################################

def search(config, idx, term, hits):
    #
    # FIXME: Translate things like pgp:signed into a search for all the
    #        tags that have signatures (good or bad).
    #
    return []

mailpile.plugins.register_search_term('crypto', search)
mailpile.plugins.register_search_term('pgp', search)
