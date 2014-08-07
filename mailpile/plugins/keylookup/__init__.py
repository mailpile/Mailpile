import math
from mailpile.crypto.gpgi import GnuPG
from mailpile.plugins import PluginManager
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n


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


def score_and_check_known_keys(key_id, key_info, known_keys_list):
    key_info["score"] = sum([score for score, reason in
                             key_info.get('scores', {}).values()])
    if key_id in known_keys_list:
        score = 0
        known_info = known_keys_list[key_id]
        if "e" in known_info["validity"]:
            score += -100
            reason = _('Key has expired')
        elif "r" in known_info["validity"]:
            score += -1000
            reason = _('Key is revoked')
        elif "d" in known_info["validity"]:
            score += -1000
            reason = _('Key is disabled')
        elif "f" in known_info["validity"]:
            score += 50
            reason = _('Key is trusted')
        elif "u" in known_info["validity"]:
            score += 50
            reason = _('Key is trusted')
        else:
            score += 10
            reason = _('Key is on keychain')

        key_info["on_keychain"] = True
        key_info['score'] += score
        key_info['scores']['Keychain'] = [score, reason]
    else:
        key_info["on_keychain"] = False

    sc, reason = max([(abs(score), reason)
                     for score, reason in key_info['scores'].values()])
    key_info['score_reason'] = '%s' % reason

    log_score = math.log(3 * abs(key_info['score']), 3)
    key_info['score_stars'] = (max(1, min(int(round(log_score)), 5))
                               * (-1 if (key_info['score'] < 0) else 1))


def lookup_crypto_keys(session, address, event=None, allowremote=True):
    known_keys_list = _GnuPG(session).list_keys()
    found_keys = {}
    ordered_keys = []
    for handler in KEY_LOOKUP_HANDLERS:
        h = handler(session)
        if not allowremote and not h.LOCAL:
            continue

        if event:
            ordered_keys.sort(key=lambda k: -k["score"])
            event.message = _('Searching for keys in: %s') % _(h.NAME)
            event.private_data = {"result": ordered_keys,
                                  "runningsearch": h.NAME}
            session.config.event_log.log_event(event)

        results = h.lookup(address)
        for key_id, key_info in results.iteritems():
            if key_id in found_keys:
                old_scores = found_keys[key_id].get('scores', {})
                found_keys[key_id].update(key_info)
                if 'scores' in found_keys[key_id]:
                    found_keys[key_id]['scores'].update(old_scores)
                    # No need for an else, as old_scores will be empty
            else:
                found_keys[key_id] = key_info
                found_keys[key_id]["origin"] = []
            found_keys[key_id]["origin"].append(h.NAME)
            score_and_check_known_keys(key_id, found_keys[key_id],
                                       known_keys_list)

        # This updates and sorts ordered_keys in place. This will magically
        # also update the data on the viewable event, because Python.
        ordered_keys[:] = found_keys.values()
        ordered_keys.sort(key=lambda k: -k["score"])

    if event:
        event.private_data = {"result": ordered_keys, "runningsearch": False}
        session.config.event_log.log_event(event)
    return ordered_keys


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
        return self._success(_n('Found %d key', 'Found %d keys', len(result)
                                ) % len(result),
                             result=result)


class KeyImport(Command):
    """Import keys"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'crypto/keyimport', 'crypto/keyimport',
                '<address>')
    HTTP_CALLABLE = ('POST',)
    HTTP_QUERY_VARS = {
        'address': 'The nick/address to find a key for',
        'fingerprints': 'List of fingerprints we want',
        'origins': 'List of origins to search'
    }

    def command(self):
        if len(self.args) > 1:
            allowremote = self.args.pop()
        else:
            allowremote = self.data.get('allowremote', True)

        address = " ".join(self.data.get('address', self.args))
        result = lookup_crypto_keys(self.session, address, event=self.event,
                                    allowremote=allowremote)
        return self._success(_n('Found %d key', 'Found %d keys', len(result)
                                ) % len(result),
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
        for key_id, key_info in keys.iteritems():
            score, reason = self._score(key_info)
            key_info["score"] = score
            key_info['scores'] = {
                self.NAME: [score, reason]
            }

        return keys

    def key_import(self, address):
        return True

#########################################

from mailpile.plugins.keylookup.email_keylookup import EmailKeyLookupHandler
from mailpile.plugins.keylookup.dnspka import DNSPKALookupHandler

class KeyserverLookupHandler(LookupHandler):
    NAME = "PGP Keyservers"

    def _score(self, key):
        return (1, _('Found key in keyserver'))

    def _lookup(self, address):
        return self._gnupg().search_key(address)

    def _getkey(self, key):
        pass


register_crypto_key_lookup_handler(KeyserverLookupHandler)
