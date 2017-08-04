#coding:utf-8
import os
import string
import sys
import time
import re
import StringIO
import tempfile
import threading
import traceback
import select
import pgpdump
import base64
import quopri
from datetime import datetime
from email.parser import Parser
from email.message import Message
from threading import Thread

from mailpile.i18n import gettext
from mailpile.i18n import ngettext as _n
from mailpile.crypto.state import *
from mailpile.crypto.mime import MimeSigningWrapper, MimeEncryptingWrapper
from mailpile.safe_popen import Popen, PIPE, Safe_Pipe


_ = lambda s: s

DEFAULT_KEYSERVERS = ["hkps://hkps.pool.sks-keyservers.net",
                      "hkp://subset.pool.sks-keyservers.net"]
DEFAULT_KEYSERVER_OPTIONS = [
  'ca-cert-file=%s' % __file__.replace('.pyc', '.py')]

GPG_KEYID_LENGTH = 8
GNUPG_HOMEDIR = None  # None=use what gpg uses
GPG_BINARY = 'gpg'
GPG_VERSIONS = {}
if sys.platform.startswith('win'):
    GPG_BINARY = 'GnuPG\\gpg.exe'
BLOCKSIZE = 65536

openpgp_algorithms = {1: _("RSA"),
                      2: _("RSA (encrypt only)"),
                      3: _("RSA (sign only)"),
                      16: _("ElGamal (encrypt only)"),
                      17: _("DSA"),
                      20: _("ElGamal (encrypt/sign) [COMPROMISED]"),
                      22: _("EdDSA"),
                      999: _("Unknown")}
# For details on type 20 compromisation, see
# http://lists.gnupg.org/pipermail/gnupg-announce/2003q4/000160.html

ENTROPY_LOCK = threading.Lock()

class GnuPGEventUpdater:
    """
    Parse the GPG response into something useful for the Event Log.
    """
    def __init__(self, event):
        from mailpile.eventlog import Event
        self.event = event or Event()

    def _log(self, section, message):
        data = section.get('gnupg', [])
        if data:
            data[-1].append(message)

    def _log_private(self, message):
        self._log(self.event.private_data, message)

    def _log_public(self, message):
        self._log(self.event.private_data, message)
        self._log(self.event.data, message)

    def running_gpg(self, why):
        for section in (self.event.data, self.event.private_data):
            data = section.get('gnupg', [])
            data.append([why, int(time.time())])
            section['gnupg'] = data

    def update_args(self, args):
        self._log_public(' '.join(args))

    def update_sent_passphrase(self):
        self._log_public(_('Sent passphrase'))

    def _parse_gpg_line(self, line):
        if line.startswith('[GNUPG:] '):
            pass  # FIXME: Parse for machine-readable data
        elif line.startswith('gpg: '):
            self._log_private(line[5:].strip())

    def update_stdout(self, line):
        self._parse_gpg_line(line)

    def update_stderr(self, line):
        self._parse_gpg_line(line)

    def update_return_code(self, code):
        self._log_public(_('GnuPG returned %s') % code)


class GnuPGResultParser:
    """
    Parse the GPG response into EncryptionInfo and SignatureInfo.
    """
    def __init__(rp):
        rp.signature_info = SignatureInfo()
        rp.signature_info["protocol"] = "openpgp"

        rp.encryption_info = EncryptionInfo()
        rp.encryption_info["protocol"] = "openpgp"

        rp.plaintext = ""

    def parse(rp, retvals):
        signature_info = rp.signature_info
        encryption_info = rp.encryption_info
        from mailpile.mailutils import ExtractEmailAndName

        # First pass, set some initial state.
        locked, missing = [], []
        for data in retvals[1]["status"]:
            keyword = data[0].strip()  # The last keyword often ends in \n

            if keyword == 'NEED_PASSPHRASE':
                locked += [data[2]]
                encryption_info.part_status = "lockedkey"
                encryption_info["locked_keys"] = list(set(locked))

            elif keyword == 'GOOD_PASSPHRASE':
                encryption_info["locked_keys"] = []

            elif keyword == "DECRYPTION_FAILED":
                missing += [x[1].strip() for x in retvals[1]["status"]
                            if x[0] == "NO_SECKEY"]
                if missing:
                    encryption_info["missing_keys"] = list(set(missing))
                if encryption_info.part_status != "lockedkey":
                    if missing:
                        encryption_info.part_status = "missingkey"
                    else:
                        encryption_info.part_status = "error"

            elif keyword == "DECRYPTION_OKAY":
                encryption_info.part_status = "decrypted"
                rp.plaintext = "".join(retvals[1]["stdout"])

            elif keyword == "ENC_TO":
                keylist = encryption_info.get("have_keys", [])
                if data[0] not in keylist:
                    keylist.append(data[1].strip())
                encryption_info["have_keys"] = list(set(keylist))
                
            elif keyword == "PLAINTEXT":
                encryption_info.filename = data[3].strip()

            elif signature_info.part_status == "none":
                # Only one of these will ever be emitted per key, use
                # this to set initial state. We may end up revising
                # the status depending on more info later.
                if keyword in ("GOODSIG", "BADSIG"):
                    email, fn = ExtractEmailAndName(
                        " ".join(data[2:]).decode('utf-8'))
                    signature_info["name"] = fn
                    signature_info["email"] = email
                    signature_info.part_status = ((keyword == "GOODSIG")
                                                  and "unverified"
                                                  or "invalid")
                    rp.plaintext = "".join(retvals[1]["stdout"])
                                                  
                elif keyword == "ERRSIG":
                    signature_info.part_status = "error"
                    signature_info["keyinfo"] = data[1]
                    signature_info["timestamp"] = int(data[5])

        # Second pass, this may update/mutate the state set above
        for data in retvals[1]["status"]:
            keyword = data[0].strip()  # The last keyword often ends in \n

            if keyword == "NO_SECKEY":
                keyid = data[1].strip()
                if "missing_keys" not in encryption_info:
                    encryption_info["missing_keys"] = [keyid]
                elif keyid not in encryption_info["missing_keys"]:
                    encryption_info["missing_keys"].append(keyid)
                while keyid in encryption_info["have_keys"]:
                    encryption_info["have_keys"].remove(keyid)

            elif keyword == "VALIDSIG":
                # FIXME: Determine trust level, between new, unverified,
                #        verified, untrusted.
                signature_info["keyinfo"] = data[1]
                signature_info["timestamp"] = int(data[3])

            elif keyword in ("EXPKEYSIG", "REVKEYSIG"):
                email, fn = ExtractEmailAndName(
                    " ".join(data[2:]).decode('utf-8'))
                signature_info["name"] = fn
                signature_info["email"] = email
                signature_info.part_status = ((keyword == "EXPKEYSIG")
                                              and "expired"
                                              or "revoked")

          # FIXME: This appears to be spammy. Is my key borked, or
          #        is GnuPG being stupid?
          #
          # elif keyword == "KEYEXPIRED":  # Ignoring: SIGEXPIRED
          #     signature_info.part_status = "expired"
            elif keyword == "KEYREVOKED":
                signature_info.part_status = "revoked"
            elif keyword == "NO_PUBKEY":
                signature_info.part_status = "unknown"

            elif keyword in ("TRUST_ULTIMATE", "TRUST_FULLY"):
                if signature_info.part_status == "unverified":
                    signature_info.part_status = "verified"

        return rp


class GnuPGRecordParser:
    def __init__(self):
        self.keys = {}
        self.curkeyid = None
        self.curdata = None

        self.record_fields = ["record", "validity", "keysize", "keytype",
                              "keyid", "creation_date", "expiration_date",
                              "uidhash", "ownertrust", "uid", "sigclass",
                              "capabilities", "flag", "sn", "hashtype",
                              "curve"]
        self.record_types = ["pub", "sub", "ssb", "fpr", "uat", "sec", "tru",
                             "sig", "rev", "uid", "gpg", "rvk", "grp"]
        self.record_parsers = [self.parse_pubkey, self.parse_subkey,
                               self.parse_subkey, self.parse_fingerprint,
                               self.parse_userattribute, self.parse_privkey,
                               self.parse_trust, self.parse_signature,
                               self.parse_revoke, self.parse_uidline,
                               self.parse_none, self.parse_revocation_key,
                               self.parse_keygrip]

        self.dispatch = dict(zip(self.record_types, self.record_parsers))

    def parse(self, lines):
        for line in lines:
            self.parse_line(line)
        return self.keys

    def parse_line(self, line):
        line = dict(zip(self.record_fields,
                        map(lambda s: s.replace("\\x3a", ":"),
                        stubborn_decode(line).strip().split(":"))))
        r = self.dispatch.get(line["record"], self.parse_unknown)
        r(line)

    def _parse_dates(self, line):
        for ts in ('expiration_date', 'creation_date'):
            if line.get(ts) and '-' not in line[ts]:
                try:
                    unixtime = int(line[ts])
                    if unixtime > 946684800:  # 2000-01-01
                        dt = datetime.fromtimestamp(unixtime)
                        line[ts] = dt.strftime('%Y-%m-%d')
                except ValueError:
                    line[ts+'_unparsed'] = line[ts]
                    line[ts] = '1970-01-01'

    def _parse_keydata(self, line):
        line["keytype_name"] = _(openpgp_algorithms.get(int(line["keytype"]),
                                                        'Unknown'))
        line["capabilities_map"] = {
            "encrypt": "E" in line["capabilities"],
            "sign": "S" in line["capabilities"],
            "certify": "C" in line["capabilities"],
            "authenticate": "A" in line["capabilities"],
        }
        line["disabled"] = "D" in line["capabilities"]
	line["revoked"] = "r" in line["validity"]

        self._parse_dates(line)

        return line

    def _clean_curdata(self):
        for v in self.curdata.keys():
            if self.curdata[v] == "":
                del self.curdata[v]
        del self.curdata["record"]

    def parse_pubkey(self, line):
        self.curkeyid = line["keyid"]
        self.curdata = self.keys[self.curkeyid] = self._parse_keydata(line)
        self.curdata["subkeys"] = []
        self.curdata["uids"] = []
        self.curdata["secret"] = (self.curdata["record"] == "sec")
        self.parse_uidline(self.curdata)
        self._clean_curdata()

    def parse_subkey(self, line):
        self.curdata = self._parse_keydata(line)
        self.keys[self.curkeyid]["subkeys"].append(self.curdata)
        self._clean_curdata()

    def parse_fingerprint(self, line):
        fpr = line["uid"]
        self.curdata["fingerprint"] = fpr
        if len(self.curkeyid) < len(fpr):
            self.keys[fpr] = self.keys[self.curkeyid]
            del(self.keys[self.curkeyid])
            self.curkeyid = fpr

    def parse_userattribute(self, line):
        # TODO: We are currently ignoring user attributes as not useful.
        #       We may at some point want to use --attribute-fd and read
        #       in user photos and such?
        pass

    def parse_privkey(self, line):
        self.parse_pubkey(line)

    def parse_uidline(self, line):
        email, name, comment = parse_uid(line["uid"])
        self._parse_dates(line)
        if email or name or comment:
            self.keys[self.curkeyid]["uids"].append({
                "email": email,
                "name": name,
                "comment": comment,
                "creation_date": line["creation_date"]
            })
        else:
            pass  # This is the case where a uid or sec line have no
                  # information aside from the creation date, which we
                  # parse elsewhere. As these lines are effectively blank,
                  # we omit them to simplify presentation to the user.

    def parse_trust(self, line):
        # FIXME: We are currently ignoring commentary from the Trust DB.
        pass

    def parse_signature(self, line):
        # FIXME: This is probably wrong; signatures are on UIDs and not
        #        the key itself. No? Yes? Figure this out.
        if "signatures" not in self.keys[self.curkeyid]:
            self.keys[self.curkeyid]["signatures"] = []
        sig = {
            "signer": line[9],
            "signature_date": line[5],
            "keyid": line[4],
            "trust": line[10],
            "keytype": line[4]
        }
        self.keys[self.curkeyid]["signatures"].append(sig)

    def parse_keygrip(self, line):
        self.curdata["keygrip"] = line["uid"]

    def parse_revoke(self, line):
        pass  # FIXME

    def parse_revocation_key(self, line):
        pass  # FIXME

    def parse_unknown(self, line):
        print "Unknown line with code '%s'" % (line,)

    def parse_none(line):
        pass


UID_PARSE_RE = "^([^\(\<]+?){0,1}( \((.+?)\)){0,1}( \<(.+?)\>){0,1}\s*$"


def stubborn_decode(text):
    if isinstance(text, unicode):
        return text
    try:
        return text.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return text.decode("iso-8859-1")
        except UnicodeDecodeError:
            return uidstr.decode("utf-8", "replace")


def parse_uid(uidstr):
    matches = re.match(UID_PARSE_RE, uidstr)
    if matches:
        email = matches.groups(0)[4] or ""
        comment = matches.groups(0)[2] or ""
        name = matches.groups(0)[0] or ""
    else:
        if '@' in uidstr and ' ' not in uidstr:
            email, name = uidstr, ""
        else:
            email, name = "", uidstr
        comment = ""

    return email, name, comment


class StreamReader(Thread):
    def __init__(self, name, fd, callback, lines=True):
        Thread.__init__(self, target=self.readin, args=(fd, callback))
        self.name = name
        self.state = 'startup'
        self.lines = lines
        self.start()

    def __str__(self):
        return '%s(%s/%s, lines=%s)' % (Thread.__str__(self),
                                        self.name, self.state, self.lines)

    def readin(self, fd, callback):
        try:
            if self.lines:
                self.state = 'read'
                for line in iter(fd.readline, b''):
                    self.state = 'callback'
                    callback(line)
                    self.state = 'read'
            else:
                while True:
                    self.state = 'read'
                    buf = fd.read(BLOCKSIZE)
                    self.state = 'callback'
                    callback(buf)
                    if buf == "":
                        break
        except:
            traceback.print_exc()
        finally:
            self.state = 'done'
            fd.close()


class StreamWriter(Thread):
    def __init__(self, name, fd, output, partial_write_ok=False):
        Thread.__init__(self, target=self.writeout, args=(fd, output))
        self.name = name
        self.state = 'startup'
        self.partial_write_ok = partial_write_ok
        self.start()

    def __str__(self):
        return '%s(%s/%s)' % (Thread.__str__(self), self.name, self.state)

    def writeout(self, fd, output):
        if isinstance(output, (str, unicode)):
            total = len(output)
            output = StringIO.StringIO(output)
        else:
            total = 0
        try:
            while True:
                self.state = 'read'
                line = output.read(BLOCKSIZE)
                if line == "":
                    break
                self.state = 'write'
                fd.write(line)
                total -= len(line)
            output.close()
        except:
            if not self.partial_write_ok:
                print '%s: %s bytes left' % (self, total)
                traceback.print_exc()
        finally:
            self.state = 'done'
            fd.close()


DEBUG_GNUPG = False

class GnuPG:
    """
    Wrap GnuPG and make all functionality feel Pythonic.
    """
    ARMOR_BEGIN_SIGNED    = '-----BEGIN PGP SIGNED MESSAGE-----'
    ARMOR_BEGIN_SIGNATURE = '-----BEGIN PGP SIGNATURE-----'
    ARMOR_END_SIGNED      = '-----END PGP SIGNATURE-----'
    ARMOR_END_SIGNATURE   = '-----END PGP SIGNATURE-----'

    ARMOR_BEGIN_ENCRYPTED = '-----BEGIN PGP MESSAGE-----'
    ARMOR_END_ENCRYPTED   = '-----END PGP MESSAGE-----'

    ARMOR_BEGIN_PUB_KEY   = '-----BEGIN PGP PUBLIC KEY BLOCK-----'
    ARMOR_END_PUB_KEY     = '-----END PGP PUBLIC KEY BLOCK-----'

    LAST_KEY_USED = 'DEFAULT'  # This is a 1-value global cache

    def __init__(self, config,
                 session=None, use_agent=None, debug=False, dry_run=False,
                 event=None, passphrase=None):
        global DEBUG_GNUPG
        self.available = None
        self.outputfds = ["stdout", "stderr", "status"]
        self.errors = []
        self.event = GnuPGEventUpdater(event)
        self.session = session
        self.config = config or (session and session.config) or None
        if self.config:
            DEBUG_GNUPG = ('gnupg' in self.config.sys.debug)
            self.homedir = self.config.sys.gpg_home or GNUPG_HOMEDIR
            self.gpgbinary = self.config.sys.gpg_binary or GPG_BINARY
            self.passphrases = self.config.passphrases
            self.passphrase = (passphrase if (passphrase is not None) else
                               self.passphrases['DEFAULT']).get_reader()
            self.use_agent = (use_agent if (use_agent is not None)
                              else self.config.prefs.gpg_use_agent)
        else:
            self.homedir = GNUPG_HOMEDIR
            self.gpgbinary = GPG_BINARY
            self.passphrases = None
            self.passphrase = passphrase.get_reader()
            self.use_agent = use_agent
        self.dry_run = dry_run
        self.debug = (self._debug_all if (debug or DEBUG_GNUPG)
                      else self._debug_none)

    def prepare_passphrase(self, keyid, signing=False, decrypting=False):
        """Query the Mailpile secrets for a usable passphrase."""
        def _use(kid, sps_reader):
            self.passphrase = sps_reader
            GnuPG.LAST_KEY_USED = kid
            return True

        if self.config:
            message = []
            if decrypting:
                message.append(_("Your PGP key is needed for decrypting."))
            if signing:
                message.append(_("Your PGP key is needed for signing."))
            match, sps = self.config.get_passphrase(keyid,
                prompt=_('Unlock your encryption key'),
                description=' '.join(message))
            if match:
                return _use(match, sps.get_reader())

        self.passphrase = None  # This *may* allow use of the GnuPG agent
        return False

    def _debug_all(self, msg):
        if self.session:
            self.session.debug(msg.rstrip())
        else:
            print '%s' % str(msg).rstrip()

    def _debug_none(self, msg):
        pass

    def set_home(self, path):
        self.homedir = path

    def version(self):
        """Returns a string representing the GnuPG version number."""
        self.event.running_gpg(_('Checking GnuPG version'))
        retvals = self.run(["--version"], novercheck=True)
        return retvals[1]["stdout"][0].split('\n')[0]

    def version_tuple(self, update=False):
        """Returns a tuple representing the GnuPG version number."""
        global GPG_VERSIONS
        if update or not GPG_VERSIONS.get(self.gpgbinary):
            vertext = self.version().strip().split()[-1]
            version = tuple(int(v) for v in vertext.split('.'))
            GPG_VERSIONS[self.gpgbinary] = version
        return GPG_VERSIONS[self.gpgbinary]

    def gnupghome(self):
        """Returns the location of the GnuPG keyring"""
        self.event.running_gpg(_('Checking GnuPG home directory'))
        rv = self.run(["--version"], novercheck=True)[1]["stdout"][0]
        for l in rv.splitlines():
            if l.startswith('Home: '):
                return os.path.expanduser(l[6:].strip())
        return os.path.expanduser(os.getenv('GNUPGHOME', '~/.gnupg'))

    def is_available(self):
        try:
            self.event.running_gpg(_('Checking GnuPG availability'))
            self.version_tuple(update=True)
            self.available = True
        except OSError:
            self.available = False

        return self.available

    def common_args(self, args=None, version=None, will_send_passphrase=False):
        if args is None:
            args = []
        if version is None:
            version = self.version_tuple()

        args.insert(0, self.gpgbinary)
        args.insert(1, "--utf8-strings")
        args.insert(1, "--with-colons")
        args.insert(1, "--verbose")
        args.insert(1, "--batch")
        args.insert(1, "--enable-progress-filter")

        # Disable SHA1 in all things GnuPG
        args[1:1] = ["--personal-digest-preferences=SHA512",
                     "--digest-algo=SHA512",
                     "--cert-digest-algo=SHA512"]

        if (not self.use_agent) or will_send_passphrase:
            if version < (1, 5):
                args.insert(1, "--no-use-agent")
            elif version > (2, 1, 11):
                args.insert(1, "--pinentry-mode=loopback")
            else:
                raise ImportError('Mailpile requires GnuPG 1.4.x or 2.1.12+ !')

        if self.homedir:
            args.insert(1, "--homedir=%s" % self.homedir)

        args.insert(1, "--status-fd=2")
        if will_send_passphrase:
            args.insert(2, "--passphrase-fd=0")

        if self.dry_run:
            args.insert(1, "--dry-run")

        return args

    def run(self,
            args=None, gpg_input=None, outputfd=None, partial_read_ok=False,
            send_passphrase=False, _raise=None, novercheck=False):
        if novercheck:
            version = (1, 4)
        else:
            version = self.version_tuple()

        args = self.common_args(
            args=list(args if args else []),
            version=version,
            will_send_passphrase=(self.passphrase and send_passphrase))

        self.outputbuffers = dict([(x, []) for x in self.outputfds])
        self.threads = {}
        gpg_retcode = -1
        proc = None
        try:
            if send_passphrase and (self.passphrase is None):
                self.debug('Running WITHOUT PASSPHRASE %s' % ' '.join(args))
                self.debug(''.join(traceback.format_stack()))
            else:
                self.debug('Running %s' % ' '.join(args))

            # Here we go!
            self.event.update_args(args)
            proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=0)

            # GnuPG is a bit crazy, and requires that the passphrase
            # be sent and the filehandle closed before anything else
            # interesting happens.
            if send_passphrase and self.passphrase is not None:
                self.passphrase.seek(0, 0)
                c = self.passphrase.read(BLOCKSIZE)
                while c != '':
                    proc.stdin.write(c)
                    c = self.passphrase.read(BLOCKSIZE)
                proc.stdin.write('\n')
                self.event.update_sent_passphrase()

            wtf = ' '.join(args)
            self.threads = {
                "stderr": StreamReader('gpgi-stderr(%s)' % wtf,
                                       proc.stderr, self.parse_stderr)
            }

            if outputfd:
                self.threads["stdout"] = StreamReader(
                    'gpgi-stdout-to-fd(%s)' % wtf,
                    proc.stdout, outputfd.write, lines=False)
            else:
                self.threads["stdout"] = StreamReader(
                    'gpgi-stdout-parsed(%s)' % wtf,
                    proc.stdout, self.parse_stdout)

            if gpg_input:
                # If we have output, we just stream it. Technically, this
                # doesn't really need to be a thread at the moment.
                self.debug('<<STDOUT<< %s' % gpg_input)
                StreamWriter('gpgi-output(%s)' % wtf,
                             proc.stdin, gpg_input,
                             partial_write_ok=partial_read_ok).join()
            else:
                proc.stdin.close()

            # Reap GnuPG
            gpg_retcode = proc.wait()

        finally:
            # Close this so GPG will terminate. This should already have
            # been done, but we're handling errors here...
            if proc and proc.stdin:
                proc.stdin.close()

        # Update event with return code
        self.event.update_return_code(gpg_retcode)

        # Reap the threads
        self._reap_threads()

        if outputfd:
            outputfd.close()

        if gpg_retcode != 0 and _raise:
            raise _raise('GnuPG failed, exit code: %s' % gpg_retcode)

        return gpg_retcode, self.outputbuffers

    def _reap_threads(self):
        for tries in (1, 2, 3):
            for name, thr in self.threads.iteritems():
                if thr.isAlive():
                    thr.join(timeout=15)
                    if thr.isAlive() and tries > 1:
                        print 'WARNING: Failed to reap thread %s' % thr

    def parse_status(self, line, *args):
        self.debug('<<STATUS<< %s' % line)
        line = line.replace("[GNUPG:] ", "")
        if line == "":
            return
        elems = line.split(" ")
        self.outputbuffers["status"].append(elems)

    def parse_stdout(self, line):
        self.event.update_stdout(line)
        self.debug('<<STDOUT<< %s' % line)
        self.outputbuffers["stdout"].append(line)

    def parse_stderr(self, line):
        self.event.update_stderr(line)
        if line.startswith("[GNUPG:] "):
            return self.parse_status(line)
        self.debug('<<STDERR<< %s' % line)
        self.outputbuffers["stderr"].append(line)

    def parse_keylist(self, keylist):
        rlp = GnuPGRecordParser()
        return rlp.parse(keylist)

    def list_keys(self, selectors=None):
        """
        >>> g = GnuPG(None)
        >>> g.list_keys()[0]
        0
        """
        list_keys = ["--fingerprint"]
        for sel in set(selectors or []):
            list_keys += ["--list-keys", sel]
        if not selectors:
            list_keys += ["--list-keys"]
        self.event.running_gpg(_('Fetching GnuPG public key list (selectors=%s)'
                                 ) % ', '.join(selectors or []))
        retvals = self.run(list_keys)
        return self.parse_keylist(retvals[1]["stdout"])

    def list_secret_keys(self, selectors=None):
        #
        # Note: The selectors that are passed by default work around a bug
        #       in GnuPG < 2.1, where --list-secret-keys does not list
        #       details about key capabilities or expiry for
        #       --list-secret-keys unless a selector is provided. A dot
        #       is reasonably likely to appear in all PGP keys, as it is
        #       a common component of e-mail addresses (and @ does not
        #       work as a selector for some reason...)
        #
        #       The downside of this workaround is that keys with no e-mail
        #       address or an address like alice@localhost won't be found.
        #       So we disable this hack on GnuPG >= 2.1.
        #
        if not selectors and self.version_tuple() < (2, 1):
            selectors = [".", "a", "e", "i", "p", "t", "k"]

        list_keys = ["--fingerprint"]
        if selectors:
            for sel in selectors:
                list_keys += ["--list-secret-keys", sel]
        else:
            list_keys += ["--list-secret-keys"]

        self.event.running_gpg(_('Fetching GnuPG secret key list (selectors=%s)'
                                 ) % ', '.join(selectors or ['None']))
        retvals = self.run(list_keys)
        secret_keys = self.parse_keylist(retvals[1]["stdout"])

        # Another unfortunate thing GPG does, is it hides the disabled
        # state when listing secret keys; it seems internally only the
        # public key is disabled. This makes it hard for us to reason about
        # which keys can actually be used, so we compensate...
        list_keys = ["--fingerprint"]
        for fprint in set(secret_keys):
            list_keys += ["--list-keys", fprint]
        retvals = self.run(list_keys)
        public_keys = self.parse_keylist(retvals[1]["stdout"])
        for fprint, info in public_keys.iteritems():
            if fprint in set(secret_keys):
                for k in ("disabled", "revoked"):  # FIXME: Copy more?
                    secret_keys[fprint][k] = info[k]

        return secret_keys

    def import_keys(self, key_data=None):
        """
        Imports gpg keys from a file object or string.
        >>> key_data = open("testing/pub.key").read()
        >>> g = GnuPG(None)
        >>> g.import_keys(key_data)
        {'failed': [], 'updated': [{'details_text': 'unchanged', 'details': 0, 'fingerprint': '08A650B8E2CBC1B02297915DC65626EED13C70DA'}], 'imported': [], 'results': {'sec_dups': 0, 'unchanged': 1, 'num_uids': 0, 'skipped_new_keys': 0, 'no_userids': 0, 'num_signatures': 0, 'num_revoked': 0, 'sec_imported': 0, 'sec_read': 0, 'not_imported': 0, 'count': 1, 'imported_rsa': 0, 'imported': 0, 'num_subkeys': 0}}
        """
        self.event.running_gpg(_('Importing key to GnuPG key chain'))
        retvals = self.run(["--import"], gpg_input=key_data)
        return self._parse_import(retvals[1]["status"])

    def _parse_import(self, output):
        res = {"imported": [], "updated": [], "failed": []}
        for x in output:
            if x[0] == "IMPORTED":
                res["imported"].append({
                    "fingerprint": x[1],
                    "username": x[2].rstrip()
                })
            elif x[0] == "IMPORT_OK":
                reasons = {
                    "0": "unchanged",
                    "1": "new key",
                    "2": "new user IDs",
                    "4": "new signatures",
                    "8": "new subkeys",
                    "16": "contains private key",
                }
                res["updated"].append({
                    "details": int(x[1]),
                    "details_text": reasons[x[1]],
                    "fingerprint": x[2].rstrip(),
                })
            elif x[0] == "IMPORT_PROBLEM":
                reasons = {
                    "0": "no reason given",
                    "1": "invalid certificate",
                    "2": "issuer certificate missing",
                    "3": "certificate chain too long",
                    "4": "error storing certificate",
                }
                res["failed"].append({
                    "details": int(x[1]),
                    "details_text": reasons[x[1]],
                    "fingerprint": x[2].rstrip()
                })
            elif x[0] == "IMPORT_RES":
                res["results"] = {
                    "count": int(x[1]),
                    "no_userids": int(x[2]),
                    "imported": int(x[3]),
                    "imported_rsa": int(x[4]),
                    "unchanged": int(x[5]),
                    "num_uids": int(x[6]),
                    "num_subkeys": int(x[7]),
                    "num_signatures": int(x[8]),
                    "num_revoked": int(x[9]),
                    "sec_read": int(x[10]),
                    "sec_imported": int(x[11]),
                    "sec_dups": int(x[12]),
                    "skipped_new_keys": int(x[13]),
                    "not_imported": int(x[14].rstrip()),
                }
        return res

    def decrypt(self, data, outputfd=None, passphrase=None, as_lines=False):
        """
        Note that this test will fail if you don't replace the recipient with
        one whose key you control.
        >>> g = GnuPG(None)
        >>> ct = g.encrypt("Hello, World", to=["smari@mailpile.is"])[1]
        >>> g.decrypt(ct)["text"]
        'Hello, World'
        """
        if passphrase is not None:
            self.passphrase = passphrase.get_reader()
        elif GnuPG.LAST_KEY_USED:
            # This is an opportunistic approach to passphrase usage... we
            # just hope the passphrase we used last time will work again.
            # If we are right, we are done. If we are wrong, the output
            # will tell us which key IDs to look for in our secret stash.
            self.prepare_passphrase(GnuPG.LAST_KEY_USED, decrypting=True)

        self.event.running_gpg(_('Decrypting %d bytes of data') % len(data))
        for tries in (1, 2):
            retvals = self.run(["--decrypt"], gpg_input=data,
                                              outputfd=outputfd,
                                              send_passphrase=True)
            if retvals[0] == 0:
                break
            elif tries == 1:
                # Uh, oh, failed! Probably the wrong passphrase. Parse the
                # gpg output for the keyid and try again if we have it.
                keyid = None
                for msg in retvals[1]['status']:
                    if (msg[0] == 'NEED_PASSPHRASE') and (passphrase is None):
                        if self.prepare_passphrase(msg[2], decrypting=True):
                            keyid = msg[2]
                            break
                if not keyid:
                    break

        if as_lines:
            as_lines = retvals[1]["stdout"]
            retvals[1]["stdout"] = []

        rp = GnuPGResultParser().parse(retvals)
        return (rp.signature_info, rp.encryption_info,
                as_lines or rp.plaintext)
                
    def base64_segment(self, dec_start, dec_end, skip, line_len, line_end = 2):
        """
        Given the start and end index of a desired segment of decoded data,
        this function finds smallest segment of an encoded base64 array that
        when decoded will include the desired decoded segment.
        It's assumed that the base64 data has a uniform line structure of
        line_len encoded characters including line_end eol characters,
        and that there are skip header characters preceding the base64 data.
        """
        enc_start =  4*(dec_start/3)
        dec_skip  =  dec_start - 3*enc_start/4
        enc_start += line_end*(enc_start/(line_len-line_end))
        enc_end =    4*(dec_end/3)
        enc_end +=   line_end*(enc_end/(line_len-line_end))

        return enc_start, enc_end, dec_skip
        
    def pgp_packet_hdr_parse(self, header, prev_partial = False):
        """
        Parse the header of a PGP packet to get the packet type, header length,
        and data length.  Extra trailing characters in header are ignored.
        prev_partial indicates that the previous packet was a partial packet.
        An illegal header returns type -1, lengths 0.
        Header format is defined in RFC4880 section 4.
        """
        hdr = bytearray(header.ljust( 6, chr(0)))
        if not prev_partial:
            hdr_len = 1
        else:
            hdr[1:] = hdr           # Partial block headers don't have a tag
            hdr[0] = 0              # Insert a dummy tag.
            hdr_len = 0
        is_partial = False
        
        if prev_partial or (hdr[0] & 0xC0) == 0xC0:
            # New format packet
            ptag = hdr[0] & 0x3F
            body_len = hdr[1]
            lengthtype = 0
            hdr_len += 1
            if body_len < 192:
                pass
            elif body_len <= 223:
                hdr_len += 1
                body_len = ((body_len - 192) << 8) + hdr[2] + 192
            elif body_len == 255:
                hdr_len += 4
                body_len =  ( (hdr[2] << 24) + (hdr[3] << 16) +
                                (hdr[4] << 8)  + hdr[5] )
            else:
                # Partial packet headers are only legal for data packets.
                if not prev_partial and not ptag in {8,9,11,18}:
                    return (-1, 0, 0, False)
                # Could do extra testing here.
                is_partial = True
                body_len = 1 << (hdr[1] & 0x1F)
                
        elif (hdr[0] & 0xC0) == 0x80:
            # Old format packet
            ptag = (hdr[0] & 0x3C) >> 2
            lengthtype = hdr[0] & 0x03
            if lengthtype < 3:
                hdr_len = 2
                body_len = hdr[1]
                if lengthtype > 0:
                    hdr_len = 3
                    body_len = (body_len << 8) + hdr[2]
                if lengthtype > 1:
                    hdr_len = 5
                    body_len = ( 
                        (body_len << 16) + (hdr[3] << 8) + hdr[4] )
            else:
                # Kludgy extra test for compressed packets w/ "unknown" length
                # gpg generates these in signed-only files. Check for valid
                # compression algorithm id to minimize false positives.
                if ptag != 8 or (hdr[1] < 1 or hdr[1] > 3):
                    return (-1, 0, 0, False)
                hdr_len = 1
                body_len = -1               
        else:
            return (-1, 0, 0, False)
        
        if hdr_len > len(header):
            return (-1, 0, 0, False)    
    
        return ptag, hdr_len, body_len, is_partial


    def sniff(self, data, encoding = None):
        """
        Checks arbitrary data to see if it is a PGP object and returns a set
        that indicates the kind(s) of object found. The names of the set
        elements are based on RFC3156 content types with 'pgp-' stripped so
        they can be used in sniffers for other protocols, e.g. S/MIME.
        There are additional set elements 'armored' and 'unencrypted'.
        
        This code should give no false negatives, but may give false positives.
        For efficient handling of encoded data, only small segments are decoded.
        Armored files are detected by their armor header alone.
        Non-armored data is detected by looking for a sequence of valid PGP
        packet headers.
        """
     
        found = set()
        is_base64 = False
        is_quopri = False
        line_len = 0
        line_end = 1
        enc_start = 0
        enc_end = 0
        dec_start = 0
        skip = 0
        ptag = 0
        hdr_len = 0
        body_len = 0
        partial = False
        offset_enc = 0
        offset_dec = 0
        offset_packet = 0
        
        # Identify encoding and base64 line length.                                      
        if encoding and encoding.lower() == 'base64':
            line_len = data.find('\n') + 1          # Assume uniform length           
            if line_len < 0:
                line_len = len(data)
            elif line_len > 1 and data[line_len-2] == '\r':
                line_end = 2
            if line_len - line_end > 76:            # Maximum per RFC2045 6.8
                return found 
            enc_end = line_len
            try:
                segment = base64.b64decode(data[enc_start:enc_end])
            except TypeError:
                return found
            is_base64 = True
                            
        elif encoding and encoding.lower() == 'quoted-printable':
            # Can't selectively decode quopri because encoded length is data
            # dependent due to escapes!  Just decode one medium length segment.
            # This is enough to contain the first few packets of a long file.
            try:
                segment = quopri.decodestring(data[0:1500])
            except TypeError:                         
                return found                # *** ? Docs don't list exceptions
            is_quopri = True
        else:
            line_len = len(data)
            segment = data                          # *** Shallow copy?
                  
        if not segment:
            found = set()
        elif not (ord(segment[0]) & 0x80):
            # Not a PGP packet header if MSbit is 0.  Check for armoured data.
            found.add('armored')
            if segment.startswith(self.ARMOR_BEGIN_SIGNED):
                # Clearsigned
                found.add('unencrypted')                           
                found.add('signature')                
            elif segment.startswith(self.ARMOR_BEGIN_SIGNATURE):
                # Detached signature
                found.add('signature')                               
            elif segment.startswith(self.ARMOR_BEGIN_ENCRYPTED):
                # PGP uses the same armor header for encrypted and signed only
                # Fortunately gpg --decrypt handles both!
                found.add('encrypted')           
            elif segment.startswith(self.ARMOR_BEGIN_PUB_KEY):
                found.add('key')              
            else:
                found = set()
        else:
            # Could be PGP packet header. Check for sequence of legal headers.
            while skip < len(segment) and body_len <> -1:
                # Check this packet header.
                prev_partial = partial
                ptag, hdr_len, body_len, partial = ( 
                    self.pgp_packet_hdr_parse(segment[skip:], prev_partial) )
                    
                if prev_partial or partial:
                    pass
                elif ptag == 11:               
                    found.add('unencrypted')    # Literal Data
                elif ptag ==  1:
                    found.add('encrypted')      # Encrypted Session Key
                elif ptag ==  9:
                    found.add('encrypted')      # Symmetrically Encrypted Data
                elif ptag ==  18:
                    found.add('encrypted')      # Symmetrically Encrypted & MDC
                elif ptag ==  2:
                    found.add('signature')      # Signature
                elif ptag ==  4:
                    found.add('signature')      # One-Pass Signature
                elif ptag ==  6:
                    found.add('key')            # Public Key
                elif ptag ==  14:
                    found.add('key')            # Public Subkey
                elif ptag == 8:                 # Compressed Data Packet
                    # This is a kludge.  Signed, non-encrypted files made by gpg
                    # (but no other gpg files) consist of one compressed data
                    # packet of unknown length which contains the signature
                    # and data packets.
                    # This appears to be an interpretation of RFC4880 2.3.
                    # The compression prevents selective parsing of headers.
                    # So such packets are assumed to be signed messages.
                    if dec_start == 0 and body_len == -1: 
                        found.add('signature')
                        found.add('unencrypted')                   
                elif ptag < 0  or ptag > 19:
                    found = set()
                    return found
                    
                dec_start += hdr_len + body_len
                skip = dec_start    
                if is_base64 and body_len <> -1:    
                    enc_start, enc_end, skip = self.base64_segment( dec_start, 
                                        dec_start + 6, 0, line_len, line_end )
                    segment = base64.b64decode(data[enc_start:enc_end])
 
            if is_base64 and body_len <> -1 and skip <> len(segment):
                # End of last packet does not match end of data.
                found = set()
        return found
    
    
    def remove_armor(self, text):
        lines = text.strip().splitlines(True)
        if lines[0].startswith(self.ARMOR_BEGIN_SIGNED):
            for idx in reversed(range(0, len(lines))):
                if lines[idx].startswith(self.ARMOR_BEGIN_SIGNATURE):
                    lines = lines[:idx]
                    while lines and lines[0].strip():
                        lines.pop(0)
                    break
        return ''.join(lines).strip()

    def verify(self, data, signature=None):
        """
        >>> g = GnuPG(None)
        >>> s = g.sign("Hello, World", _from="smari@mailpile.is",
            clearsign=True)[1]
        >>> g.verify(s)
        """
        params = ["--verify"]
        if signature:
            sig = tempfile.NamedTemporaryFile()
            sig.write(signature)
            sig.flush()
            params.append(sig.name)
            params.append("-")

        self.event.running_gpg(_('Checking signature in %d bytes of data'
                                 ) % len(data))
        ret, retvals = self.run(params, gpg_input=data, partial_read_ok=True)

        return GnuPGResultParser().parse([None, retvals]).signature_info

    def encrypt(self, data, tokeys=[], armor=True,
                            sign=False, fromkey=None, throw_keyids=False):
        """
        >>> g = GnuPG(None)
        >>> g.encrypt("Hello, World", to=["smari@mailpile.is"])[0]
        0
        """
        if tokeys:
            action = ["--encrypt", "--yes", "--expert",
                      "--trust-model", "always"]
            for r in tokeys:
                action.append("--recipient")
                action.append(r)
            action.extend([])
            self.event.running_gpg(_('Encrypting %d bytes of data to %s'
                                     ) % (len(data), ', '.join(tokeys)))
        else:
            action = ["--symmetric", "--yes", "--expert"]
            self.event.running_gpg(_('Encrypting %d bytes of data with password'
                                     ) % len(data))

        if armor:
            action.append("--armor")
        if sign:
            action.append("--sign")
        if sign and fromkey:
            action.append("--local-user")
            action.append(fromkey)
        if throw_keyids:
            action.append("--throw-keyids")
        if fromkey:
            self.prepare_passphrase(fromkey, signing=True)

        retvals = self.run(action, gpg_input=data,
                           send_passphrase=(sign or not tokeys))

        return retvals[0], "".join(retvals[1]["stdout"])

    def sign(self, data,
             fromkey=None, armor=True, detatch=True, clearsign=False,
             passphrase=None):
        """
        >>> g = GnuPG(None)
        >>> g.sign("Hello, World", fromkey="smari@mailpile.is")[0]
        0
        """
        if passphrase is not None:
            self.passphrase = passphrase.get_reader()
        if fromkey and passphrase is None:
            self.prepare_passphrase(fromkey, signing=True)

        if detatch and not clearsign:
            action = ["--detach-sign"]
        elif clearsign:
            action = ["--clearsign"]
        else:
            action = ["--sign"]
        if armor:
            action.append("--armor")
        if fromkey:
            action.append("--local-user")
            action.append(fromkey)

        self.event.running_gpg(_('Signing %d bytes of data with %s'
                                 ) % (len(data), fromkey or _('default')))
        retvals = self.run(action, gpg_input=data, send_passphrase=True)

        self.passphrase = None
        return retvals[0], "".join(retvals[1]["stdout"])

    def sign_key(self, keyid, signingkey=None):
        action = ["--yes", "--sign-key", keyid]
        if signingkey:
            action.insert(1, "-u")
            action.insert(2, signingkey)

        self.event.running_gpg(_('Signing key %s with %s'
                                 ) % (keyid, signingkey or _('default')))
        retvals = self.run(action, send_passphrase=True)

        return retvals

    def delete_key(self, key_fingerprint):
        cmd = ['--yes', '--delete-secret-and-public-key', key_fingerprint]
        return self.run(cmd)

    def recv_key(self, keyid,
                 keyservers=DEFAULT_KEYSERVERS,
                 keyserver_options=DEFAULT_KEYSERVER_OPTIONS):
        self.event.running_gpg(_('Downloading key %s from key servers'
                                 ) % (keyid))
        for keyserver in keyservers:
            cmd = ['--keyserver', keyserver,
                   '--recv-key', self._escape_hex_keyid_term(keyid)]
            for opt in keyserver_options:
                cmd[2:2] = ['--keyserver-options', opt]
            retvals = self.run(cmd)
            if 'unsupported' not in ''.join(retvals[1]["stdout"]):
                break
        return self._parse_import(retvals[1]["status"])

    def search_key(self, term,
                   keyservers=DEFAULT_KEYSERVERS,
                   keyserver_options=DEFAULT_KEYSERVER_OPTIONS):
        self.event.running_gpg(_('Searching for key for %s in key servers'
                                 ) % (term))
        for keyserver in keyservers:
            cmd = ['--keyserver', keyserver,
                   '--fingerprint',
                   '--search-key', self._escape_hex_keyid_term(term)]
            for opt in keyserver_options:
                cmd[2:2] = ['--keyserver-options', opt]
            retvals = self.run(cmd)
            if 'unsupported' not in ''.join(retvals[1]["stdout"]):
                break
        results = {}
        lines = [x.strip().split(":") for x in retvals[1]["stdout"]]
        curpub = None
        for line in lines:
            if line[0] == "info":
                pass
            elif line[0] == "pub":
                curpub = line[1]
                validity = line[6]
                if line[5]:
                    if int(line[5]) < time.time():
                        validity += 'e'
                results[curpub] = {
                    "created": datetime.fromtimestamp(int(line[4])),
                    "keytype_name": _(openpgp_algorithms.get(int(line[2]),
                                                             'Unknown')),
                    "keysize": line[3],
                    "validity": validity,
                    "uids": [],
                    "fingerprint": curpub
                }
            elif line[0] == "uid":
                email, name, comment = parse_uid(line[1])
                results[curpub]["uids"].append({"name": name,
                                                "email": email,
                                                "comment": comment})
        return results

    def get_pubkey(self, keyid):
        self.event.running_gpg(_('Searching for key for %s in key servers'
                                 ) % (keyid))
        retvals = self.run(['--armor',
                            '--export', keyid]
                            )[1]["stdout"]
        return "".join(retvals)

    def address_to_keys(self, address):
        res = {}
        keys = self.list_keys(selectors=[address])
        for key, props in keys.iteritems():
            if any([x["email"] == address for x in props["uids"]]):
                res[key] = props

        return res

    def _escape_hex_keyid_term(self, term):
        """Prepends a 0x to hexadecimal key ids.

        For example, D13C70DA is converted to 0xD13C70DA. This is required
        by version 2.x of GnuPG (and is accepted by 1.x).
        """
        is_hex_keyid = False
        if len(term) == GPG_KEYID_LENGTH or len(term) == 2*GPG_KEYID_LENGTH:
            hex_digits = set(string.hexdigits)
            is_hex_keyid = all(c in hex_digits for c in term)

        if is_hex_keyid:
            return '0x%s' % term
        else:
            return term

    def chat(self, gpg_args, callback, *args, **kwargs):
        """This lets a callback have a chat with the GPG process..."""
        gpg_args = [self.gpgbinary,
                    "--utf8-strings",
                    # Disable SHA1 in all things GnuPG
                    "--personal-digest-preferences=SHA512",
                    "--digest-algo=SHA512",
                    "--cert-digest-algo=SHA512",
                    # We're not a human!
                    "--no-tty",
                    "--command-fd=0",
                    "--status-fd=1"] + (gpg_args or [])
        if self.homedir:
            gpg_args.insert(1, "--homedir=%s" % self.homedir)

        if self.version_tuple() > (2, 1):
            gpg_args.insert(2, "--pinentry-mode=loopback")
        else:
            gpg_args.insert(2, "--no-use-agent")

        proc = None
        try:
            # Here we go!
            self.debug('Running %s' % ' '.join(gpg_args))
            self.event.update_args(gpg_args)
            proc = Popen(gpg_args, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                         bufsize=0, long_running=True)

            return callback(proc, *args, **kwargs)
        finally:
            # Close this so GPG will terminate. This should already have
            # been done, but we're handling errors here...
            if proc and proc.stdin:
                proc.stdin.close()
            if proc:
                self.event.update_return_code(proc.wait())
            else:
                self.event.update_return_code(-1)


def GetKeys(gnupg, config, people):
    keys = []
    missing = []
    ambig = []

    # First, we go to the contact database and get a list of keys.
    for person in set(people):
        if '#' in person:
            keys.append(person.rsplit('#', 1)[1])
        else:
            vcard = config.vcards.get_vcard(person)
            if vcard:
                # It is the VCard's job to give us the best key first.
                lines = [vcl for vcl in vcard.get_all('KEY')
                         if vcl.value.startswith('data:application'
                                                 '/x-pgp-fingerprint,')]
                if len(lines) > 0:
                    keys.append(lines[0].value.split(',', 1)[1])
                else:
                    missing.append(person)
            else:
                missing.append(person)

    # Load key data from gnupg for use below
    if keys:
        all_keys = gnupg.list_keys(selectors=keys)
    else:
        all_keys = {}

    if missing:
        # Keys are missing, so we try to just search the keychain
        all_keys.update(gnupg.list_keys(selectors=missing))
        found = []
        for key_id, key in all_keys.iteritems():
            for uid in key.get("uids", []):
                if uid.get("email", None) in missing:
                    missing.remove(uid["email"])
                    found.append(uid["email"])
                    keys.append(key_id)
                elif uid.get("email", None) in found:
                    ambig.append(uid["email"])

    # Next, we go make sure all those keys are really in our keychain.
    fprints = all_keys.keys()
    for key in keys:
        key = key.upper()
        if key.startswith('0x'):
            key = key[2:]
        if key not in fprints:
            match = [k for k in fprints if k.endswith(key)]
            if len(match) == 0:
                missing.append(key)
            elif len(match) > 1:
                ambig.append(key)

    if missing:
        raise KeyLookupError(_('Keys missing for %s'
                               ) % ', '.join(missing), missing)
    elif ambig:
        ambig = list(set(ambig))
        raise KeyLookupError(_('Keys ambiguous for %s'
                               ) % ', '.join(ambig), ambig)
    return keys


class OpenPGPMimeSigningWrapper(MimeSigningWrapper):
    CONTAINER_PARAMS = (('micalg', 'pgp-sha512'),
                        ('protocol', 'application/pgp-signature'))
    SIGNATURE_TYPE = 'application/pgp-signature'
    SIGNATURE_DESC = 'OpenPGP Digital Signature'

    def crypto(self):
        return GnuPG(self.config, event=self.event)

    def get_keys(self, who):
        return GetKeys(self.crypto(), self.config, who)


class OpenPGPMimeEncryptingWrapper(MimeEncryptingWrapper):
    CONTAINER_PARAMS = (('protocol', 'application/pgp-encrypted'), )
    ENCRYPTION_TYPE = 'application/pgp-encrypted'
    ENCRYPTION_VERSION = 1

    # FIXME: Define _encrypt, allow throw_keyids

    def crypto(self):
        return GnuPG(self.config, event=self.event)

    def get_keys(self, who):
        return GetKeys(self.crypto(), self.config, who)


class OpenPGPMimeSignEncryptWrapper(OpenPGPMimeEncryptingWrapper):
    CONTAINER_PARAMS = (('protocol', 'application/pgp-encrypted'), )
    ENCRYPTION_TYPE = 'application/pgp-encrypted'
    ENCRYPTION_VERSION = 1

    def crypto(self):
        return GnuPG(self.config)

    def _encrypt(self, message_text, tokeys=None, armor=False):
        from_key = self.get_keys([self.sender])[0]
        # FIXME: Allow throw_keyids here.
        return self.crypto().encrypt(message_text,
                                     tokeys=tokeys, armor=True,
                                     sign=True, fromkey=from_key)

    def _update_crypto_status(self, part):
        part.signature_info.part_status = 'verified'
        part.encryption_info.part_status = 'decrypted'


class GnuPGExpectScript(threading.Thread):
    STARTUP = 'Startup'
    START_GPG = 'Start GPG'
    FINISHED = 'Finished'
    SCRIPT = []
    VARIABLES = {}
    DESCRIPTION = 'GnuPG Expect Script'
    RUNNING_STATES = [STARTUP, START_GPG]

    def __init__(self, gnupg,
                 sps=None, event=None, variables={}, on_complete=None):
        threading.Thread.__init__(self)
        self.daemon = True
        self._lock = threading.RLock()
        self.before = ''
        with self._lock:
            self.state = self.STARTUP
            self.gnupg = gnupg
            self.event = event
            self.variables = variables or self.VARIABLES
            self._on_complete = [on_complete] if on_complete else []
            self.main_script = self.SCRIPT[:]
            self.sps = sps
            if sps:
                self.variables['passphrase'] = '!!<SPS'

    def __str__(self):
        return '%s: %s' % (threading.Thread.__str__(self), self.state)

    running = property(lambda self: (self.state in self.RUNNING_STATES))
    failed = property(lambda self: False)

    def in_state(self, state):
        pass

    def set_state(self, state):
        self.state = state
        self.in_state(state)

    def sendline(self, proc, line):
        if line == '!!<SPS':
            reader = self.sps.get_reader()
            while True:
                c = reader.read()
                if c != '':
                    proc.stdin.write(c)
                else:
                    proc.stdin.write('\n')
                    break
        else:
            proc.stdin.write(line.encode('utf-8'))
            proc.stdin.write('\n')

    def _expecter(self, proc, exp, timebox):
        while timebox[0] > 0:
            self.before += proc.stdout.read(1)
            if exp in self.before:
                self.before = self.before.split(exp)[0]
                return True
        return False

    def expect_exact(self, proc, exp, timeout=None):
        from mailpile.util import RunTimed, TimedOut
        timeout = timeout if (timeout and timeout > 0) else 5
        timebox = [timeout]
        self.before = ''
        try:
            self.gnupg.debug('Expect: %s' % exp)
            if RunTimed(timeout, self._expecter, proc, exp, timebox):
                return True
            else:
                raise TimedOut()
        except TimedOut:
            timebox[0] = 0
            self.gnupg.debug('Timed out')
            print 'Boo! %s not found in %s' % (exp, self.before)
            raise

    def run_script(self, proc, script):
        for exp, rpl, tmo, state in script:
            self.expect_exact(proc, exp, timeout=tmo)
            if rpl:
                self.sendline(proc, (rpl % self.variables).strip())
            if state:
                self.set_state(state)

    def gpg_args(self):
        return ['--no-use-agent', '--list-keys']

    def run(self):
        try:
            self.set_state(self.START_GPG)
            gpg = self.gnupg
            gpg.event.running_gpg(_(self.DESCRIPTION) % self.variables)
            gpg.chat(self.gpg_args(), self.run_script, self.main_script)
            self.set_state(self.FINISHED)
        except:
            import traceback
            traceback.print_exc()
        finally:
            with self._lock:
                if self.state != self.FINISHED:
                    self.state = 'Failed: ' + self.state
                for name, callback in self._on_complete:
                    callback()
                self._on_complete = None

    def on_complete(self, name, callback):
        with self._lock:
            if self._on_complete is not None:
                if name not in [o[0] for o in self._on_complete]:
                    self._on_complete.append((name, callback))
            else:
                callback()


class GnuPGBaseKeyGenerator(GnuPGExpectScript):
    """This is a background thread which generates a new PGP key."""
    AWAITING_LOCK = 'Pending keygen'
    KEY_SETUP = 'Key Setup'
    GATHER_ENTROPY = 'Creating key'
    CREATED_KEY = 'Created key'
    HAVE_KEY = 'Have Key'
    VARIABLES = {
        'keytype': '1',
        'bits': '2048',
        'name': 'Mailpile Generated Key',
        'email': '',
        'comment': 'www.mailpile.is',
        'passphrase': 'mailpile'}
    DESCRIPTION = _('Creating a %(bits)s bit GnuPG key')
    RUNNING_STATES = (GnuPGExpectScript.RUNNING_STATES +
                      [AWAITING_LOCK, KEY_SETUP, GATHER_ENTROPY, HAVE_KEY])

    failed = property(lambda self: (not self.running and
                                    not self.generated_key))

    def __init__(self, *args, **kwargs):
        super(GnuPGBaseKeyGenerator, self).__init__(*args, **kwargs)
        self.generated_key = None

    def in_state(self, state):
        if state == self.HAVE_KEY:
             self.generated_key = self.before.strip().split()[-1]

    def run(self):
        # In order to minimize risk of timeout during key generation (due to
        # lack of entropy), we serialize them here using a global lock
        self.set_state(self.AWAITING_LOCK)
        self.event.message = _('Waiting to generate a %d bit GnuPG key.'
                               % self.variables['bits'])
        with ENTROPY_LOCK:
            self.event.data['keygen_gotlock'] = 1
            self.event.message = _('Generating new %d bit PGP key.'
                                   % self.variables['bits'])
            super(GnuPGBaseKeyGenerator, self).run()


class GnuPG14KeyGenerator(GnuPGBaseKeyGenerator):
    """This is the GnuPG 1.4x specific PGP key generation script."""
    B = GnuPGBaseKeyGenerator

    # FIXME: If GnuPG starts asking for things in a different order,
    #        we'll needlessly fail. To address this, we need to make
    #        the expect logic smarter. For now, we just assume the GnuPG
    #        team  will be hesitant to change things.

    SCRIPT = [
        ('GET_LINE keygen.algo',        '%(keytype)s',   -1, B.KEY_SETUP),
        ('GET_LINE keygen.size',           '%(bits)s',   -1, None),
        ('GET_LINE keygen.valid',                 '0',   -1, None),
        ('GET_LINE keygen.name',           '%(name)s',   -1, None),
        ('GET_LINE keygen.email',         '%(email)s',   -1, None),
        ('GET_LINE keygen.comment',     '%(comment)s',   -1, None),
        ('GET_HIDDEN passphrase',    '%(passphrase)s',   -1, None),
        ('GOT_IT',                               None,   -1, B.GATHER_ENTROPY),
        ('KEY_CREATED',                          None, 7200, B.CREATED_KEY),
        ('\n',                                   None,   -1, B.HAVE_KEY)]

    def gpg_args(self):
        return ['--no-use-agent', '--allow-freeform-uid', '--gen-key']


class GnuPG21KeyGenerator(GnuPG14KeyGenerator):
    """This is the GnuPG 2.1.x specific PGP key generation script."""

    # Note: We don't use the nice --quick-generate-key function, because
    #       it won't let us generate a usable key with custom parameters in
    #       a single pass. So using the existing expect logic turns out to
    #       be less work in practice. Oh well.

    def gpg_args(self):
        # --yes should keep GnuPG from complaining if there already exists
        #       a key with this UID.
        return ['--yes', '--allow-freeform-uid', '--full-gen-key']


class GnuPGDummyKeyGenerator(GnuPGBaseKeyGenerator):
    """A dummy key generator class, for incompatible versions of GnuPG."""

    DESCRIPTION = _('Unable to create a %(bits)s bit key, wrong GnuPG version')

    def __init__(self, *args, **kwargs):
        GnuPGBaseKeyGenerator.__init__(self, *args, **kwargs)
        self.generated_key = False

    def run(self):
        with self._lock:
            self.gnupg.event.running_gpg(_(self.DESCRIPTION) % self.variables)
            self.set_state(self.FINISHED)
            for name, callback in self._on_complete:
                callback()
            self._on_complete = None


def GnuPGKeyGenerator(gnupg, **kwargs):
    """Return an instanciated generator, depending on GnuPG version."""
    version = gnupg.version_tuple()
    if version < (1, 5):
        return GnuPG14KeyGenerator(gnupg, **kwargs)
    elif version >= (2, 1):
        return GnuPG21KeyGenerator(gnupg, **kwargs)
    else:
        return GnuPGDummyKeyGenerator(gnupg, **kwargs)


# Reset our translation variable
_ = gettext

## Include the SKS keyserver certificate here ##
KEYSERVER_CERTIFICATE="""
-----BEGIN CERTIFICATE-----
MIIFizCCA3OgAwIBAgIJAK9zyLTPn4CPMA0GCSqGSIb3DQEBBQUAMFwxCzAJBgNV
BAYTAk5PMQ0wCwYDVQQIDARPc2xvMR4wHAYDVQQKDBVza3Mta2V5c2VydmVycy5u
ZXQgQ0ExHjAcBgNVBAMMFXNrcy1rZXlzZXJ2ZXJzLm5ldCBDQTAeFw0xMjEwMDkw
MDMzMzdaFw0yMjEwMDcwMDMzMzdaMFwxCzAJBgNVBAYTAk5PMQ0wCwYDVQQIDARP
c2xvMR4wHAYDVQQKDBVza3Mta2V5c2VydmVycy5uZXQgQ0ExHjAcBgNVBAMMFXNr
cy1rZXlzZXJ2ZXJzLm5ldCBDQTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoC
ggIBANdsWy4PXWNUCkS3L//nrd0GqN3dVwoBGZ6w94Tw2jPDPifegwxQozFXkG6I
6A4TK1CJLXPvfz0UP0aBYyPmTNadDinaB9T4jIwd4rnxl+59GiEmqkN3IfPsv5Jj
MkKUmJnvOT0DEVlEaO1UZIwx5WpfprB3mR81/qm4XkAgmYrmgnLXd/pJDAMk7y1F
45b5zWofiD5l677lplcIPRbFhpJ6kDTODXh/XEdtF71EAeaOdEGOvyGDmCO0GWqS
FDkMMPTlieLA/0rgFTcz4xwUYj/cD5e0ZBuSkYsYFAU3hd1cGfBue0cPZaQH2HYx
Qk4zXD8S3F4690fRhr+tki5gyG6JDR67aKp3BIGLqm7f45WkX1hYp+YXywmEziM4
aSbGYhx8hoFGfq9UcfPEvp2aoc8u5sdqjDslhyUzM1v3m3ZGbhwEOnVjljY6JJLx
MxagxnZZSAY424ZZ3t71E/Mn27dm2w+xFRuoy8JEjv1d+BT3eChM5KaNwrj0IO/y
u8kFIgWYA1vZ/15qMT+tyJTfyrNVV/7Df7TNeWyNqjJ5rBmt0M6NpHG7CrUSkBy9
p8JhimgjP5r0FlEkgg+lyD+V79H98gQfVgP3pbJICz0SpBQf2F/2tyS4rLm+49rP
fcOajiXEuyhpcmzgusAj/1FjrtlynH1r9mnNaX4e+rLWzvU5AgMBAAGjUDBOMB0G
A1UdDgQWBBTkwyoJFGfYTVISTpM8E+igjdq28zAfBgNVHSMEGDAWgBTkwyoJFGfY
TVISTpM8E+igjdq28zAMBgNVHRMEBTADAQH/MA0GCSqGSIb3DQEBBQUAA4ICAQAR
OXnYwu3g1ZjHyley3fZI5aLPsaE17cOImVTehC8DcIphm2HOMR/hYTTL+V0G4P+u
gH+6xeRLKSHMHZTtSBIa6GDL03434y9CBuwGvAFCMU2GV8w92/Z7apkAhdLToZA/
X/iWP2jeaVJhxgEcH8uPrnSlqoPBcKC9PrgUzQYfSZJkLmB+3jEa3HKruy1abJP5
gAdQvwvcPpvYRnIzUc9fZODsVmlHVFBCl2dlu/iHh2h4GmL4Da2rRkUMlbVTdioB
UYIvMycdOkpH5wJftzw7cpjsudGas0PARDXCFfGyKhwBRFY7Xp7lbjtU5Rz0Gc04
lPrhDf0pFE98Aw4jJRpFeWMjpXUEaG1cq7D641RpgcMfPFvOHY47rvDTS7XJOaUT
BwRjmDt896s6vMDcaG/uXJbQjuzmmx3W2Idyh3s5SI0GTHb0IwMKYb4eBUIpQOnB
cE77VnCYqKvN1NVYAqhWjXbY7XasZvszCRcOG+W3FqNaHOK/n/0ueb0uijdLan+U
f4p1bjbAox8eAOQS/8a3bzkJzdyBNUKGx1BIK2IBL9bn/HravSDOiNRSnZ/R3l9G
ZauX0tu7IIDlRCILXSyeazu0aj/vdT3YFQXPcvt5Fkf5wiNTo53f72/jYEJd6qph
WrpoKqrwGwTpRUCMhYIUt65hsTxCiJJ5nKe39h46sg==
-----END CERTIFICATE-----
"""
