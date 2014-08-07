from mailpile.crypto.gpgi import GnuPG
from mailpile.plugins import PluginManager
from mailpile.commands import Command
from mailpile.i18n import gettext as _


__all__ = ['email_keylookup', 'nicknym', 'dnspka']

KEY_LOOKUP_HANDLERS = []


def register_crypto_key_lookup_handler(handler):
    if handler not in KEY_LOOKUP_HANDLERS:
        KEY_LOOKUP_HANDLERS.append(handler)


def _GnuPG(session):
    gpg = GnuPG()
    if session and session.config:
        gpg.passphrase = session.config.gnupg_passphrase.get_reader()
    return gpg


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


def lookup_crypto_keys(session, address, event=None, allowremote=True):
    def _calc_scores(x, scores):
        for key in x.keys():
            x[key]["score"] = 0

        for scoreset in scores:
            for key, value in scoreset.iteritems():
                if key not in x:
                    continue
                if "score" not in x[key]:
                    x[key]["score"] = 0
                x[key]["score"] += value
        return x

    x = {}
    scores = []
    lastresult = {}

    for handler in KEY_LOOKUP_HANDLERS:
        h = handler(session)
        if not allowremote and not h.LOCAL:
            continue

        if event:
            m = _calc_scores(x, scores)
            m = [i for i in m.values()]
            m.sort(key=lambda k: -k["score"])
            event.message = _('Searching for keys in: %s') % _(h.NAME)
            event.private_data = {"result": m,
                                  "runningsearch": h.NAME}
            session.config.event_log.log_event(event)

        r, s = h.lookup(address)
        for key, value in r.iteritems():
            if key in x:
                x[key].update(value)
            else:
                x[key] = value
                x[key]["origin"] = []
            x[key]["origin"].append(h.NAME)
        scores.append(s)

    x = _calc_scores(x, scores)

    known_keys_list = _GnuPG(session).list_keys()
    for key in x.keys():
        x[key]["fingerprint"] = key
        x[key]["score"] += crypto_keys_scorer(known_keys_list, key)

    x = [i for i in x.values()]
    x.sort(key=lambda k: -k["score"])
    if event:
        event.private_data = {"result": x, "runningsearch": False}
        session.config.event_log.log_event(event)
    return x


class KeyLookup(Command):
    """Perform a key lookup"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/keylookup', 'crypto/keylookup', 
        '<address> [<allowremote>]')
    HTTP_CALLABLE = ('GET',)
    HTTP_QUERY_VARS = {
        'address': 'The nick/address to find a key for',
        'allowremote': 'Whether to permit remote key lookups (defaults to true)'
    }

    def command(self):
        if len(self.args) > 1:
            allowremote = self.args.pop()
        else:
            allowremote = self.data.get('allowremote', True)
            
        address = " ".join(self.data.get('address', self.args))
        result = lookup_crypto_keys(self.session, address, event=self.event,
                                    allowremote=allowremote)
        return self._success(_('Found %d keys') % len(result),
                             result=result)

_plugins = PluginManager(builtin=__file__)
_plugins.register_commands(KeyLookup)


class LookupHandler:
    NAME = "NONE"
    LOCAL = False

    def __init__(self, session):
        self.session = session

    def _gnupg(self):
        return _GnuPG(self.session)

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

from mailpile.plugins.keylookup.email_keylookup import EmailKeyLookupHandler
from mailpile.plugins.keylookup.dnspka import DNSPKALookupHandler

class KeyserverLookupHandler(LookupHandler):
    NAME = "PGP Keyservers"

    def _score(self, key):
        return 1

    def _lookup(self, address):
        return self._gnupg().search_key(address)

    def _getkey(self, key):
        pass


register_crypto_key_lookup_handler(KeyserverLookupHandler)
