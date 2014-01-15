# Common crypto state and structure


STATE_CONTEXT_ID = 0


class CryptoInfo(dict):
    """Base class for crypto-info classes"""
    KEYS = ["protocol", "uid", "status", "description"]
    STATUSES = ["none", "partial-error", "error"]
    DEFAULTS = {"status": "none"}

    def __init__(self, copy=None, partial=False):
        self.update(copy or self.DEFAULTS)

        if partial and not self["status"].startswith("partial-"):
            self["status"] = "partial-%s" % self["status"]

        global STATE_CONTEXT_ID
        self["context"] = STATE_CONTEXT_ID
        STATE_CONTEXT_ID += 1
        STATE_CONTEXT_ID %= 1000

    def __setitem__(self, item, value):
        assert(item in self.KEYS)
        if item == "status":
            assert(value in self.STATUSES)
        dict.__setitem__(self, item, value)


class EncryptionInfo(CryptoInfo):
    """Contains information about the encryption status of a MIME part"""
    KEYS = (CryptoInfo.KEYS + ["have_keys", "missing_keys"])
    STATUSES = (CryptoInfo.STATUSES +
                ["partial-decrypted", "decrypted",
                 "partial-missingkey", "missingkey"])


class SignatureInfo(CryptoInfo):
    """Contains information about the signature status of a MIME part"""
    KEYS = (CryptoInfo.KEYS + ["name", "email", "keyinfo", "timestamp"])
    STATUSES = (CryptoInfo.STATUSES +
                ["partial-error", "error",
                 "partial-invalid", "invalid",
                 "partial-expired", "expired",
                 "partial-revoked", "revoked",
                 "partial-unknown", "unknown",
                 "partial-unverified", "unverified",
                 "partial-verified", "verified"])
