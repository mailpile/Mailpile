from mailpile.crypto.gpgi import GnuPG
from mailpile.plugins import PluginManager
from mailpile.commands import Command

__all__ = ['email_keylookup', 'nicknym', 'dnspka']

KEY_LOOKUP_HANDLERS = []

def register_crypto_key_lookup_handler(handler):
    if handler not in KEY_LOOKUP_HANDLERS:
        KEY_LOOKUP_HANDLERS.append(handler)


def crypto_keys_scorer(known_keys_list, key):
    score = 0
    if key in known_keys_list:
        if "e" in known_keys_list[key]["validity"]:
            score += -100
        elif "r" in known_keys_list[key]["validity"]:
            score += -10000
        elif "d" in known_keys_list[key]["validity"]:
            score += -10000
        elif ("f" in known_keys_list[key]["validity"] 
           or "u" in known_keys_list[key]["validity"]):
            score += 50
        else:
            score += 10

    return score


def lookup_crypto_keys(session, address):
    x = {}
    scores = []
    for handler in KEY_LOOKUP_HANDLERS:
        h = handler(session)
        r, s = h.lookup(address)
        for key, value in r.iteritems():
            if key in x:
                x[key].update(value)
            else:
                x[key] = value
                x[key]["origin"] = []
            x[key]["origin"].append(h.NAME)
        scores.append(s)

    for scoreset in scores:
        for key, value in scoreset.iteritems():
            if key not in x:
                continue
            if "score" not in x[key]:
                x[key]["score"] = 0
            x[key]["score"] += value

    g = GnuPG()
    known_keys_list = g.list_keys()
    for key in x.keys():
        x[key]["fingerprint"] = key
        x[key]["score"] += crypto_keys_scorer(known_keys_list, key)

    x = [i for i in x.values()]
    x.sort(key=lambda k: -k["score"])
    return x


class KeyLookup(Command):
    """Perform a key lookup"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/keylookup', 'crypto/keylookup', '<address>')
    HTTP_CALLABLE = ('GET',)
    HTTP_QUERY_VARS = {'address': 'The nick/address to find a key for'}

    def command(self):
        address = " ".join(self.data.get('address', self.args))
        return lookup_crypto_keys(self.session, address)

_plugins = PluginManager(builtin=__file__)
_plugins.register_commands(KeyLookup)


class LookupHandler:
    NAME = "NONE"

    def __init__(self, session):
        self.session = session

    def _score(self, key):
        raise NotImplemented("Subclass and override _score")

    def _lookup(self, address):
        raise NotImplemented("Subclass and override _lookup")

    def lookup(self, address):
        keys = self._lookup(address)
        scores = {}
        for key, value in keys.iteritems():
            scores[key] = self._score(value)

        return keys, scores

    def key_import(self, address):
        return True

#########################################


class KeyserverLookupHandler(LookupHandler):
    NAME = "PGP Keyservers"

    def _score(self, key):
        return 1

    def _lookup(self, address):
        g = GnuPG()
        return g.search_key(address)

    def _getkey(self, key):
        pass

register_crypto_key_lookup_handler(KeyserverLookupHandler)


from mailpile.plugins.keylookup.dnspka import DNSPKALookupHandler
from mailpile.plugins.keylookup.email_keylookup import EmailKeyLookupHandler
