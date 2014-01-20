# Common crypto state and structure


STATE_CONTEXT_ID = 0


class KeyLookupError(ValueError):
    def __init__(self, message, missing):
        ValueError.__init__(self, message)
        self.missing = missing


class CryptoInfo(dict):
    """Base class for crypto-info classes"""
    KEYS = ["protocol", "context", "status", "description"]
    STATUSES = ["none", "mixed-error", "error"]
    DEFAULTS = {"status": "none"}

    def __init__(self, copy=None):
        self.update(copy or self.DEFAULTS)
        global STATE_CONTEXT_ID
        self["context"] = STATE_CONTEXT_ID
        STATE_CONTEXT_ID += 1
        STATE_CONTEXT_ID %= 1000

    def __setitem__(self, item, value):
        assert(item in self.KEYS)
        if item == "status":
            assert(value in self.STATUSES)
        dict.__setitem__(self, item, value)

    def mix(self, ci):
        """
        This generates a mixed state for the message. The most exciting state
        is returned/explained, the status prfixed with "mixed-". How exciting
        states are, is determined by the order of the STATUSES attribute.

        Yes, this is a bit dumb.
        """
        if ci["status"] == "none":
            return
        elif (self.STATUSES.index(self["status"])
                < self.STATUSES.index(ci["status"])):
            for k in self.keys():
                del self[k]
            self.update(ci)
            if not ci["status"].startswith('mixed-'):
                self["status"] = "mixed-%s" % ci["status"]
        elif self["status"] != "none":
            self["status"] = 'mixed-%s' % self["status"]


class EncryptionInfo(CryptoInfo):
    """Contains information about the encryption status of a MIME part"""
    KEYS = (CryptoInfo.KEYS + ["have_keys", "missing_keys"])
    STATUSES = (CryptoInfo.STATUSES +
                ["mixed-decrypted", "decrypted",
                 "mixed-missingkey", "missingkey"])


class SignatureInfo(CryptoInfo):
    """Contains information about the signature status of a MIME part"""
    KEYS = (CryptoInfo.KEYS + ["name", "email", "keyinfo", "timestamp"])
    STATUSES = (CryptoInfo.STATUSES +
                ["mixed-error", "error",
                 "mixed-unknown", "unknown",
                 "mixed-expired", "expired",
                 "mixed-revoked", "revoked",
                 "mixed-unverified", "unverified",
                 "mixed-verified", "verified",
                 "mixed-invalid", "invalid"])
