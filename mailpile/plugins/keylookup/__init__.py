from mailpile.crypto.gpgi import GnuPG
# from mailpile.crypto.dnspka import DNSPKALookupHandler

__all__ = ['email_keylookup', 'nicknym', 'dnspka']

KEY_LOOKUP_SCORERS = []
KEY_LOOKUP_HANDLERS = []


def register_crypto_key_lookup_handler(handler):
    if handler not in KEY_LOOKUP_HANDLERS:
        KEY_LOOKUP_HANDLERS.append(handler)

def register_crypto_key_scorer(scorer):
    if scorer not in KEY_LOOKUP_SCORERS:
        KEY_LOOKUP_SCORERS.append(scorer)

def lookup_crypto_keys(session, address):
    x = {}
    scores = []
    for handler in KEY_LOOKUP_HANDLERS:
        h = handler(session)
        print "Trying %s" % h.NAME
        r, s = h.lookup(address)
        for key, value in r.iteritems():
            if key in x:
                x[key].update(value)
            else:
                x[key] = value
        scores.append(s)

    for scoreset in scores:
        for key, value in scoreset.iteritems():
            if key not in x:
                continue
            if "score" not in x[key]:
                x[key]["score"] = 0
            x[key]["score"] += value

    for key in x.keys():
        x[key]["fingerprint"] = key
        for scorer in KEY_LOOKUP_SCORERS:
            x[key]["score"] += scorer(key)

    x = [i for i in x.values()]
    x.sort(key=lambda k: k["score"])
    return x


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
        return g.search_key(address) or {}

    def _getkey(self, key):
        pass

register_crypto_key_lookup_handler(KeyserverLookupHandler)




#########################################

known_keys_list = None

def scorer_trust(key):
    global known_keys_list
    score = 0
    if known_keys_list == None:
        g = GnuPG()
        known_keys_list = g.list_keys()

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

register_crypto_key_scorer(scorer_trust)


# Being explicitly trusted by user     | 50                   | X
# Being implicitly trusted by user     | 10                   | X
# Each explicitly trusted signature    | 1                    |
# Contradicting key found in E-mail    | -5                   |
# Being explicitly distrusted by user  | -10000               | X
# Being revoked                        | -10000               | X
# Being expired                        | -100                 | X
# Being superceded by new key          | -50                  |
