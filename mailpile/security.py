"""
Global Mailpile crypto/privacy/security policy

This module attempts to collect in one place all of the different
security related decisions made by the app, in order to facilitate
review and testing.

"""
import copy
import hashlib
import json
import ssl
import time

# Note: Do NOT import mailpile.conn_broker, as our monkey patching
#       of ssl depends on things happening in the right order. :-/
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *
import mailpile.platforms

DISABLE_LOCKDOWN = False


##[ This is a secret only user owning Mailpile could know ]###################

def GetUserSecret(workdir):
    """Return a secret that only this Unix user could know."""
    secret_file = os.path.join(workdir, 'mailpile.sec')
    try:
        return open(secret_file).read().strip()
    except (OSError, IOError):
        pass

    # FIXME: Does this work reasonably on Windows? Does chmod do anything?
    random_secret = okay_random(64, __file__)
    with open(secret_file, 'w') as fd:
        fd.write(random_secret)
    mailpile.platforms.RestrictReadAccess(secret_file)
    return random_secret


##[ These are the sys.lockdown restrictions ]#################################

def _lockdown(config):
    if DISABLE_LOCKDOWN: return False
    if config.detected_memory_corruption: return 99  # FIXME: Breaks demos?
    lockdown = config.sys.lockdown or 0
    try:
        return int(lockdown)
    except ValueError:
        pass
    lockdown = lockdown.lower()
    if lockdown == 'false': return 0
    if lockdown == 'true': return 1
    if lockdown == 'demo': return -1
    if lockdown == 'strict': return 2
    return 1


def in_disk_lockdown(config):
    if DISABLE_LOCKDOWN: return False
    # If we've dropped below 50% of our target free space, we stop
    # almost all operations and go into lockdown. This makes the
    # Mailpile effectively read-only, which should be safe without
    # being totally useless.
    if config.need_more_disk_space(ratio=0.5):
        return _('Insufficient free disk space')
    return False


def _lockdown_minimal(config):
    if DISABLE_LOCKDOWN: return False
    if _lockdown(config) != 0:
        return _('In lockdown, doing nothing.')
    return False


def _lockdown_config(config):
    if DISABLE_LOCKDOWN: return False
    # This is just like lockdown_basic, except we allow the user to
    # change the config so they can adjust the minimum free disk space
    # requirement if it was accidentally made too strict.
    if _lockdown(config) > 0:
        return _('In lockdown, doing nothing.')
    return False


def _lockdown_quit(config):
    if DISABLE_LOCKDOWN: return False
    # The user is always allowed to quit, except in demo mode.
    if _lockdown(config) < 0:
        return _('In lockdown, doing nothing.')
    return False


def _lockdown_basic(config):
    if DISABLE_LOCKDOWN: return False
    return _lockdown_config(config) or in_disk_lockdown(config)


def _lockdown_strict(config):
    if DISABLE_LOCKDOWN: return False
    if _lockdown(config) > 1:
        return _('In lockdown, doing nothing.')
    return in_disk_lockdown(config)


CC_ACCESS_FILESYSTEM  = [_lockdown_minimal]
CC_BROWSE_FILESYSTEM  = [_lockdown_basic]
CC_CHANGE_CONFIG      = [_lockdown_config]
CC_CHANGE_CONTACTS    = [_lockdown_basic]
CC_CHANGE_GNUPG       = [_lockdown_basic]
CC_CHANGE_FILTERS     = [_lockdown_strict]
CC_CHANGE_SECURITY    = [_lockdown_minimal]
CC_CHANGE_TAGS        = [_lockdown_strict]
CC_COMPOSE_EMAIL      = [_lockdown_strict]
CC_CPU_INTENSIVE      = [_lockdown_basic]
CC_LIST_PRIVATE_DATA  = [_lockdown_minimal]
CC_TAG_EMAIL          = [_lockdown_strict]
CC_QUIT               = [_lockdown_quit]
CC_WEB_TERMINAL       = [_lockdown_config]

CC_CONFIG_MAP = {
    # These are security critical
    'homedir': CC_CHANGE_SECURITY,
    'master_key': CC_CHANGE_SECURITY,
    'sys': CC_CHANGE_SECURITY,
    'prefs.gpg_use_agent': CC_CHANGE_SECURITY,
    'prefs.gpg_recipient': CC_CHANGE_SECURITY,
    'prefs.encrypt_mail': CC_CHANGE_SECURITY,
    'prefs.encrypt_index': CC_CHANGE_SECURITY,
    'prefs.encrypt_vcards': CC_CHANGE_SECURITY,
    'prefs.encrypt_events': CC_CHANGE_SECURITY,
    'prefs.encrypt_misc': CC_CHANGE_SECURITY,

    # These access the filesystem and local OS
    'prefs.open_in_browser': CC_ACCESS_FILESYSTEM,
    'prefs.rescan_command': CC_ACCESS_FILESYSTEM,
    '*.command': CC_ACCESS_FILESYSTEM,

    # These have their own CC
    'tags': CC_CHANGE_TAGS,
    'filters': CC_CHANGE_FILTERS,
}


def forbid_command(command_obj, cc_list=None, config=None):
    """
    Determine whether to block a command or not.
    """
    if cc_list is None:
        cc_list = command_obj.COMMAND_SECURITY
    if cc_list:
        for cc in cc_list:
            forbid = cc(config or command_obj.session.config)
            if forbid:
                return forbid
    return False


def forbid_config_change(config, config_key):
    parts = config_key.split('.')
    cc_list = []
    while parts:
        cc_list += CC_CONFIG_MAP.get('.'.join(parts), [])
        cc_list += CC_CONFIG_MAP.get('*.' + parts.pop(-1), [])
    if not cc_list:
        cc_list = CC_CHANGE_CONFIG
    return forbid_command(None, cc_list=cc_list, config=config)


##[ Securely download content from the web ]#################################

def secure_urlget(session, url, data=None, timeout=30, anonymous=False):
    from mailpile.conn_brokers import Master as ConnBroker
    from urllib2 import urlopen

    if session.config.prefs.web_content not in ("on", "anon"):
        raise IOError("Web content is disabled by policy")

    if url[:5].lower() not in ('http:', 'https'):
        raise IOError('Non-HTTP URLs are forbidden: %s' % url)

    if url.startswith('https:'):
        conn_need, conn_reject = [ConnBroker.OUTGOING_HTTPS], []
    else:
        conn_need, conn_reject = [ConnBroker.OUTGOING_HTTP], []

    if session.config.prefs.web_content == "anon" or anonymous:
        conn_reject += [ConnBroker.OUTGOING_TRACKABLE]

    with ConnBroker.context(need=conn_need, reject=conn_reject) as ctx:
        # Flagged #nosec, because the URL scheme is constrained above
        return urlopen(url, data=None, timeout=timeout).read()  # nosec


##[ Common web-server security code ]########################################

CSRF_VALIDITY = 48 * 3600  # How long a CSRF token remains valid

def http_content_security_policy(http_server):
    """
    Calculate the default Content Security Policy string.

    This provides an important line of defense against malicious
    Javascript being injected into our web user-interface.
    """
    # FIXME: Allow deviations in config, for integration purposes
    # FIXME: Clean up Javascript and then make this more strict
    return ("default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "img-src 'self' data:")


def make_csrf_token(secret, session_id, ts=None):
    """
    Generate a hashed token from the current timestamp, session ID and
    the server secret, to avoid CSRF attacks.
    """
    ts = '%x' % (ts if (ts is not None) else time.time())
    payload = [secret, session_id, ts]
    return '%s-%s' % (ts, b64w(sha512b64('-'.join(payload))))


def valid_csrf_token(secret, session_id, csrf_token):
    """
    Check the validity of a CSRF token.
    """
    try:
        when = int(csrf_token.split('-')[0], 16)
        return ((when > time.time() - CSRF_VALIDITY) and
                (csrf_token == make_csrf_token(secret, session_id, ts=when)))
    except (ValueError, IndexError):
        return False


##[ Secure-ish handling of passphrases ]#####################################

Scrypt = PBKDF2HMAC = None
try:
    # Depending on whether Cryptography is installed (and which version),
    # this may all fail, all succeed or succeed in part.
    import cryptography.hazmat.backends
    import cryptography.hazmat.primitives.hashes
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
except ImportError:
    pass


def stretch_with_pbkdf2(password, salt, params):
    return b64w(PBKDF2HMAC(
        backend=cryptography.hazmat.backends.default_backend(),
        algorithm=cryptography.hazmat.primitives.hashes.SHA256(),
        salt=salt,
        iterations=int(params['iterations']),
        length=32).derive(password).encode('base64'))


def stretch_with_scrypt(password, salt, params):
    return b64w(Scrypt(
        backend=cryptography.hazmat.backends.default_backend(),
        salt=salt,
        n=int(params['n']),
        r=int(params['r']),
        p=int(params['p']),
        length=32).derive(password).encode('base64'))


# These are our defaults, based on recommendations found on The Internet.
# The parameters actually used should be stored along with the output so
# we can change them later if they're found to be too weak or flawed in
# some other way.
KDF_PARAMS = {
    'pbkdf2': {
        'iterations': 400000
    },
    'scrypt': {
        'n': 2**17,
        'r': 8,
        'p': 1
    }
}


class SecurePassphraseStorage(object):
    """
    This is slightly obfuscated in-memory storage of passphrases.

    The data is currently stored as an array of integers, which takes
    advantage of Python's internal shared storage for small numbers.
    This is not secure against a determined adversary, but at least the
    passphrase won't be written in the clear to core dumps or swap.

    >>> sps = SecurePassphraseStorage(passphrase='ABC')
    >>> sps.data
    [65, 66, 67]

    To copy a passphrase:

    >>> sps2 = SecurePassphraseStorage().copy(sps)
    >>> sps2.data
    [65, 66, 67]

    To check passphrases for validity, use compare():

    >>> sps.compare('CBA')
    False
    >>> sps.compare('ABC')
    True

    To extract the passphrase, use the get_reader() method to get a
    file-like object that will return the characters of the passphrase
    one byte at a time.

    >>> rdr = sps.get_reader()
    >>> rdr.seek(1)
    >>> [rdr.read(5), rdr.read(), rdr.read(), rdr.read()]
    ['B', 'C', '', '']

    If an expiration time is set, trying to access the passphrase will
    make it evaporate.

    >>> sps.expiration = time.time() - 5
    >>> sps.get_reader() is None
    True
    >>> sps.data is None
    True
    """
    # FIXME: Replace this with a memlocked ctype buffer, whenever possible

    def __init__(self, passphrase=None, stretched=False):
        self.generation = 0
        self.expiration = -1
        self.is_stretched = stretched
        self.stretch_cache = {}
        if passphrase is not None:
            self.set_passphrase(passphrase)
        else:
            self.data = None

    def copy(self, src):
        self.data = src.data
        self.expiration = src.expiration
        self.generation += 1
        return self

    def is_set(self):
        return (self.data is not None)

    def stretches(self, salt, params=None):
        if self.is_stretched:
            yield (self.is_stretched, self)
            return

        if params is None:
            params = KDF_PARAMS

        for which, name, stretch in (
                (Scrypt, 'scrypt', stretch_with_scrypt),
                (PBKDF2HMAC, 'pbkdf2', stretch_with_pbkdf2), ):
            if which:
                try:
                    how = params[name]
                    name += ' ' + json.dumps(how, sort_keys=True)
                    sc_key = '%s/%s' % (name, salt)
                    if sc_key not in self.stretch_cache:
                        pf = intlist_to_string(self.data).encode('utf-8')
                        self.stretch_cache[sc_key] = SecurePassphraseStorage(
                            stretch(pf, salt, how), stretched=name)
                    yield (name, self.stretch_cache[sc_key])
                except (KeyError, AttributeError, UnsupportedAlgorithm):
                    pass

        yield ('clear', self)

    def stretched(self, salt, params=None):
        for name, stretch in self.stretches(salt, params=params):
            return stretch

    def set_passphrase(self, passphrase):
        # This stores the passphrase as a list of integers, which is a
        # primitive in-memory obfuscation relying on how Python represents
        # small integers as globally shared objects. Better Than Nothing!
        self.data = string_to_intlist(passphrase)
        self.stretch_cache = {}
        self.generation += 1

    def compare(self, passphrase):
        if (self.expiration > 0) and (time.time() > self.expiration):
            self.data = None
            return False
        return (self.data is not None and
                self.data == string_to_intlist(passphrase))

    def read_byte_at(self, offset):
        if self.data is None or offset >= len(self.data):
            return ''
        return chr(self.data[offset])

    def get_passphrase(self):
        if self.data is None:
            return ''
        return intlist_to_string(self.data)

    def get_reader(self):
        class SecurePassphraseReader(object):
            def __init__(self, sps):
                self.storage = sps
                self.offset = 0

            def seek(self, offset, whence=0):
                safe_assert(whence == 0)
                self.offset = offset

            def read(self, ignored_bytecount=None):
                one_byte = self.storage.read_byte_at(self.offset)
                self.offset += 1

                return one_byte

            def close(self):
                pass

        if (self.expiration > 0) and (time.time() > self.expiration):
            self.data = None
            return None
        elif self.data is not None:
            return SecurePassphraseReader(self)
        else:
            return None


##[ TLS/SSL security code ]##################################################
#
# We monkey-patch ssl.wrap_socket and ssl.SSLContext.wrap_socket so we can
# implement and enforce our own policies here.
#
KNOWN_TLS_HOSTS = {}
MAX_TLS_CERTS = 5


def tls_sock_cert_sha256(sock=None, cert=None):
    if cert is None:
        try:
            peer_cert = sock.getpeercert(binary_form=True)
        except ValueError:
            return None
    else:
        peer_cert = cert

    if peer_cert:
        return unicode(
            hashlib.sha256(peer_cert).digest().encode('base64').strip())
    else:
        return None


def tls_configure(sock, context, args, kwargs):
    # FIXME: We should convert positional arguments to named ones, to
    #        make sure everything Just Works.
    #
    # Pop off any positional arguments that just want defaults
    args = list(args)
    while args and args[-1] is None:
        args.pop(-1)

    kwargs = copy.copy(kwargs)
    if (not hasattr(ssl, 'OP_NO_SSLv3')) and not context:
        # This build/version of Python is insecure!
        # Force the protocol version to TLSv1.
        kwargs['ssl_version'] = kwargs.get('ssl_version', ssl.PROTOCOL_TLSv1)

    # Per-site configuration, SNI and TOFU!
    hostname = None
    accept_certs = []
    if 'server_hostname' in kwargs:
        try:
            hostname = '%s:%s' % (kwargs['server_hostname'], sock.getpeername()[1])
        except TypeError:
            # sock.getpeername() may fail
            hostname = '%s' % (kwargs.get('server_hostname'),)

        if hostname:
            tls_settings = KNOWN_TLS_HOSTS.get(md5_hex(hostname))
        else:
            tls_settings = None

        # These defaults allow us to do certificate TOFU
        if tls_settings is not None:
            accept_certs = [c for c in tls_settings.accept_certs]
        kwargs['cert_reqs'] = ssl.CERT_NONE
        if context:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        # Attempt to configure for Certificate Authorities
        use_web_ca = kwargs.get('use_web_ca',
            tls_settings is None or tls_settings.use_web_ca)
        if use_web_ca:
            try:
                if context:
                    context.load_default_certs()
                    context.verify_mode = ssl.CERT_REQUIRED
                    context.check_hostname = True
                    accept_certs = None
                elif 'ca_certs' in kwargs:
                    kwargs['cert_reqs'] = ssl.CERT_REQUIRED
                    accept_certs = None
                elif hasattr(ssl, 'get_default_verify_paths'):
                    kwargs['cert_reqs'] = ssl.CERT_REQUIRED
                    kwargs['ca_certs'] = ssl.get_default_verify_paths().cafile
                    accept_certs = None
                else:
                    # Fall back to TOFU.
                    pass
            except (NameError, AttributeError):
                # Old Python: Fall back to TOFU
                pass

        if context:
            del kwargs['cert_reqs']
        else:
            # The context-less ssl.wrap_socket() doesn't understand this
            # argument, so get rid of it.
            del kwargs['server_hostname']

    if 'use_web_ca' in kwargs:
        del kwargs['use_web_ca']

    return tuple(args), kwargs, hostname, accept_certs


def tls_new_context():
    if hasattr(ssl, 'OP_NO_SSLv3'):
        return ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    else:
        return ssl.SSLContext(ssl.PROTOCOL_TLSv1)


def tls_cert_tofu(wrapped, accept_certs, sname):
    global KNOWN_TLS_HOSTS
    cert = tls_sock_cert_sha256(wrapped)
    if accept_certs and cert not in accept_certs:
        raise ssl.CertificateError('Unrecognized certificate: %s' % cert)

    skey = md5_hex(sname)
    if skey not in KNOWN_TLS_HOSTS:
        KNOWN_TLS_HOSTS[skey] = {'server': sname}
        KNOWN_TLS_HOSTS[skey].use_web_ca = (accept_certs is None)
    if cert not in KNOWN_TLS_HOSTS[skey].accept_certs:
        KNOWN_TLS_HOSTS[skey].accept_certs.append(cert)
        while len(KNOWN_TLS_HOSTS[skey].accept_certs) > MAX_TLS_CERTS:
            del KNOWN_TLS_HOSTS[skey].accept_certs[0]

def tls_context_wrap_socket(org_wrap, context, sock, *args, **kwargs):
    args, kwargs, sname, accept_certs = tls_configure(sock, context, args, kwargs)
    tofu = kwargs.get('tofu', True)
    if 'tofu' in kwargs: del kwargs['tofu']
    wrapped = org_wrap(context, sock, *args, **kwargs)
    if tofu:
        tls_cert_tofu(wrapped, accept_certs, sname)
    return wrapped


def tls_wrap_socket(org_wrap, sock, *args, **kwargs):
    args, kwargs, sname, accept_certs = tls_configure(sock, None, args, kwargs)
    tofu = kwargs.get('tofu', True)
    if 'tofu' in kwargs: del kwargs['tofu']
    wrapped = org_wrap(sock, *args, **kwargs)
    if tofu:
        tls_cert_tofu(wrapped, accept_certs, sname)
    return wrapped


##[ Key Trust ]#############################################################

def evaluate_sender_trust(config, email, tree):
    """
    This uses historic data from the search engine to refine and expand
    upon the states we get back from GnuPG and attempt to detect forgeries.

    The new potential signature states are:

      unsigned  We expected a signature from this sender but found none
      changed   The signature was made with a key we've rarely seen before
      signed    The signature was made with a key we've often seen before

    The first state depends on the user's ratio of signed to unsigned
    messages, the second two depend on how frequently we've seen a given
    key used for signatures vs. the total number of signatures.

    These states will supercede the states we get from GnuPG like so:

      * `none` becomes `unsigned`
      * `unknown` or `unverified` may become `changed`
      * `unverified` may become `signed`

    The constants used in this algorithm can be found and tweaked in the
    `prefs.key_trust` section of the configuration file.
    """
    sender = email.get_sender()
    if not sender:
        return

    tree['trust'] = {}
    trust = tree["trust"]

    # If this mail didn't come from outside, skip all this.
    # We don't vet ourselves for forgeries.
    # FIXME: THIS IS INSECURE. We need to fix this mechanism globally.
    message = email.get_msg()
    if 'x-mp-internal-sender' in message:
        trust["status"] = _("We trust ourselves")
        return tree

    # Calculate the default window we search for information. Don't include
    # the same day as the message was received, to not be fooled by other
    # junk that arrived the same day.
    days = config.prefs.key_trust.window_days
    msgts = long(email.get_msg_info(config.index.MSG_DATE), 36)
    end = msgts - (24 * 3600)
    begin = end - (days * 24 * 3600)
    scope = ['dates:%d..%d' % (begin, end), 'from:%s' % sender]

    messages_per_key = {}
    trust['counts'] = messages_per_key
    def count(name, terms):
        if name not in messages_per_key:
            # Note: using .as_set() will exclude spam and trash, which
            #       is almsot certainly a good thing.
            msgs = config.index.search(config.background, scope + terms)
            messages_per_key[name] = len(msgs.as_set())
        return messages_per_key[name]

    total = lambda: count('total', [])
    if total() < min(5, config.prefs.key_trust.threshold):
        # If we have too few messages within our desired window, try
        # expanding the window...
        scope[1] = 'dates:1970..%d' % end
        del messages_per_key['total']

        # Still too few? Abort.
        if total() < min(5, config.prefs.key_trust.threshold):
            trust["trust_unknown"] = True
            trust["warning"] = _("This sender's reputation is unknown")
            return tree

    signed = lambda: count('signed', ['has:signature'])
    swr = config.prefs.key_trust.sig_warn_pct / 100.0
    ktr = config.prefs.key_trust.key_trust_pct / 100.0
    knr = config.prefs.key_trust.key_new_pct / 100.0

    def update_siginfo(si, trust):
        stat = si["status"]
        keyid = si.get('keyinfo', '')[-16:].lower()

        # Unsigned message: if the ratio of total signed messages is
        # above config.prefs.sig_warn_pct percent, we EXPECT signatures
        # and warn the user if they're not present.
        if (stat == 'none') and (signed() > swr * total()):
            si["status"] = 'unsigned'
            trust["missing_signature"] = True

        # Compare email timestamp with the signature timestamp.
        # If they differ by a great deal, treat the signature as
        # invalid. This makes it much harder to copy old signed
        # content (undetected) into new messages.
        elif abs(msgts - si.get("timestamp", msgts)) > 7 * 24 * 3600:
            si["status"] = 'invalid'
            trust["invalid_signature"] = True

        # Signed by unverified key: Signal that we trust this key if
        # this is the key we've seen most of the time for this user.
        # This is TOFU-ish.
        elif (keyid and
                ('unverified' in stat) and
                (count(keyid, ['sig:%s' % keyid]) > ktr * signed())):
            si["status"] = stat.replace('unverified', 'signed')
            trust["signed"] = True

        # Signed by a key we have seen very rarely for this user. Gently
        # warn the user that something unsual is going on.
        elif (keyid and
                ('unverified' in stat or 'unknown' in stat) and
                (count(keyid, ['sig:%s' % keyid]) < knr * signed())):
            changed = "mixed-changed" if ("mixed" in stat) else "changed"
            si["status"] = changed
            trust["key_changed"] = True

        else:
            trust["%s_signature" % si["status"].replace("mixed-", "")] = True

    if signed() >= config.prefs.key_trust.threshold:
        if 'crypto' in tree:
            update_siginfo(tree['crypto']['signature'], tree["trust"])

        for skey in ('text_parts', 'html_parts', 'attachments'):
            for i, part in enumerate(tree[skey]):
                if 'crypto' in part:
                    update_siginfo(part['crypto']['signature'], {})

    if 'received' in message:
        headerprints = email.get_headerprints()
        term = 'hps:%s' % headerprints['sender']
        hps = count(term, [term])
        if hps < 2:
            trust["mua_or_mta_changed"] = True

    # Translate accumulated state into a "problem" if applicable
    problem = "problem" if (total() > 20) else "warning"
    if trust.get("invalid_signature") or trust.get("revoked_signature"):
        trust[problem] = _("The digital signature is invalid")
    elif trust.get("missing_signature"):
        trust[problem] = _("This person usually signs their mail")
    elif trust.get("key_changed"):
        trust[problem] = _("This was signed by an unexpected key")
    elif trust.get("expired_signature"):
        trust[problem] = _("This was signed by an expired key")
    elif trust.get("verified_signature") or trust.get("signed"):
        trust["status"] = _("Good signature, we are happy")
    elif trust.get("mua_or_mta_changed"):
        trust["warning"] = _("This came from an unexpected source")
    else:
        trust["status"] = _("No problems detected.")

    return tree


##[ Setup ]#################################################################

if __name__ != "__main__":
    if hasattr(ssl, 'SSLContext'):
        ssl.SSLContext.wrap_socket = monkey_patch(
            ssl.SSLContext.wrap_socket, tls_context_wrap_socket)
        def add_tls_context(unused_org_wrap, sock, *args, **kwargs):
            try:
                return tls_new_context().wrap_socket(sock, *args, **kwargs)
            except:
                raise
        ssl.wrap_socket = monkey_patch(ssl.wrap_socket, add_tls_context)
    else:
        ssl.wrap_socket = monkey_patch(ssl.wrap_socket, tls_wrap_socket)


##[ Tests ]##################################################################

if __name__ == "__main__":
    import doctest
    import sys
    result = doctest.testmod(optionflags=doctest.ELLIPSIS)
    print '%s' % (result, )
    if result.failed:
        sys.exit(1)
