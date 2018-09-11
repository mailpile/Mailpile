#. Common crypto state and structure
import copy

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n


class KeyLookupError(ValueError):
    def __init__(self, message, missing):
        ValueError.__init__(self, message)
        self.missing = missing


# Crypto state is a strange beast, it needs to flow down and then
# back up again - parts need to inherit a crypto context from their
# container, but if something interesting is discovered that has to
# be overridden.
#
# The discoveries then usually have to bubble up to influence the
# overall state of that container and the message itself (mixed-*
# states, etc).
#
class CryptoInfo(dict):
    """Base class for crypto-info classes"""
    KEYS = ["protocol", "status", "description"]
    STATUSES = ["none", "mixed-error", "error"]
    DEFAULTS = {"status": "none"}

    def __init__(self, parent=None, copy=None, bubbly=True):
        self.parent = parent
        self.bubbly = bubbly
        self.filename = None
        self.bubbles = []
        self._status = None
        if copy:
            self.update(copy)
            self._status = self.get("status")
        elif parent:
            self.update(parent)
            self._status = self.get("status")
        else:
            self.update(self.DEFAULTS)

    part_status = property(lambda self: (self._status or
                                         self.DEFAULTS["status"]),
                           lambda self, v: self._set_status(v))

    def _set_status(self, value):
        if value not in self.STATUSES:
            print 'Bogus status for %s: %s' % (type(self), value)
            raise ValueError('Invalid status: %s' % value)
        self._status = value
        self.mix_bubbles()

    def __setitem__(self, item, value):
        if item not in self.KEYS:
            raise KeyError('Invalid key: %s' % item)
        if item == "status":
            if value not in self.STATUSES:
                print 'Bogus status for %s: %s' % (type(self), value)
                raise ValueError('Invalid value for %s: %s' % (key, value))
            if self._status is None:  # Capture initial value
                self._status = value
        dict.__setitem__(self, item, value)

    def _overwrite_with(self, ci):
        for k in self.keys():
            del self[k]
        self.update(ci)

    def bubble_up(self, parent=None):
        # Bubbling up adds this context to the list of contexts to be
        # evaluated for all parent states.
        if parent is not None and parent != self:
            self.parent = parent

        # Some contexts are neutral (pure MIME boilerplate) and do not
        # bubble up at all.
        if not self.bubbly:
            return

        parent = self.parent
        while parent is not None:
            parent.bubbles.append(self)
            parent = parent.parent

    def mix_bubbles(self):
        # Reset visible status to initial state
        self["status"] = self.part_status
        # Mix in all the bubbly bubbles
        for bubble in self.bubbles:
            if bubble.bubbly:
                self._mix_in(bubble)

    def _mix_in(self, ci):
        """
        This generates a mixed state for the message. The most exciting state
        is returned/explained, the status prefixed with "mixed-". How exciting
        states are, is determined by the order of the STATUSES attribute.

        This is lossy, but hopefully in a useful and non-harmful way.
        """
        status = self["status"]
        if self.STATUSES.index(status) <= self.STATUSES.index(ci.part_status):
            # ci is MORE or EQUALLY interesting
            mix = copy.copy(ci)
            if (self.bubbly and
                   status != mix.part_status and
                   not mix.part_status.startswith('mixed-')):
                mix["status"] = "mixed-%s" % mix.part_status
            else:
                mix["status"] = mix.part_status
            self._overwrite_with(mix)
        elif not status.startswith("mixed-"):
            # ci is LESS interesting
            self["status"] = 'mixed-%s' % status


class EncryptionInfo(CryptoInfo):
    """Contains information about the encryption status of a MIME part"""
    KEYS = (CryptoInfo.KEYS + ["have_keys", "missing_keys", "locked_keys"])
    STATUSES = (CryptoInfo.STATUSES +
                ["mixed-decrypted", "decrypted",
                 "mixed-missingkey", "missingkey",
                 "mixed-lockedkey", "lockedkey"])


class SignatureInfo(CryptoInfo):
    """Contains information about the signature status of a MIME part"""
    KEYS = (CryptoInfo.KEYS + ["name", "email", "keyinfo", "timestamp"])
    STATUSES = (CryptoInfo.STATUSES +
                ["mixed-unknown", "unknown",
                 "mixed-changed", "changed",  # TOFU; not the key we expected!
                 "mixed-unsigned", "unsigned",  # TOFU; should be signed!
                 "mixed-expired", "expired",
                 "mixed-revoked", "revoked",
                 "mixed-unverified", "unverified",
                 "mixed-signed", "signed",  # TOFU; signature matches history
                 "mixed-verified", "verified",
                 "mixed-invalid", "invalid"])
