from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.crypto.state import EncryptionInfo, SignatureInfo


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
    def crypto_eval(part):
        # This is generic
        if part.encryption_info.get('status') != 'none':
            enc.add('mp_%s-%s' % ('enc', part.encryption_info['status']))
            kw.add('crypto:has')
        if part.signature_info.get('status') != 'none':
            sig.add('mp_%s-%s' % ('sig', part.signature_info['status']))
            kw.add('crypto:has')
        if 'cryptostate' in index.config.sys.debug:
            print 'part status(=%s): enc=%s sig=%s' % (msg_mid,
                part.encryption_info.get('status'),
                part.signature_info.get('status')
            )

        # This is OpenPGP-specific
        if (part.encryption_info.get('protocol') == 'openpgp'
                or part.signature_info.get('protocol') == 'openpgp'):
            kw.add('pgp:has')

        # FIXME: Other encryption protocols?

    def choose_one(fmt, statuses, ordering):
        for o in ordering:
            for mix in ('', 'mixed-'):
                status = (fmt % (mix+o))
                if status in statuses:
                    return set([status])
        return set(list(statuses)[:1])

    # Evaluate all the message parts
    crypto_eval(msg)
    for p in msg.walk():
        crypto_eval(p)

    # OK, we should have exactly encryption state...
    if len(enc) < 1:
        enc.add('mp_enc-none')
    elif len(enc) > 1:
        enc = choose_one('mp_enc-%s', enc, EncryptionInfo.STATUSES)

    # ... and exactly one signature state.
    if len(sig) < 1:
        sig.add('mp_sig-none')
    elif len(sig) > 1:
        sig = choose_one('mp_sig-%s', sig, SignatureInfo.STATUSES)

    # Emit tags for our states
    for tname in (enc | sig):
        tag = index.config.get_tags(slug=tname)
        if tag:
            kw.add('%s:in' % tag[0]._key)

    if 'cryptostate' in index.config.sys.debug:
        print 'part crypto state(=%s): %s' % (msg_mid, ','.join(list(kw)))

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
