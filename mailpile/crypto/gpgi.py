#coding:utf-8
import os
import string
import sys
import time
import re
import StringIO
import tempfile
import traceback
import select
from datetime import datetime
from email.parser import Parser
from email.message import Message
from gettext import gettext as _
from subprocess import Popen, PIPE
from threading import Thread

from mailpile.crypto.state import *
from mailpile.crypto.mime import MimeSigningWrapper, MimeEncryptingWrapper

DEFAULT_SERVER = "pool.sks-keyservers.net"
GPG_KEYID_LENGTH = 8
GNUPG_HOMEDIR = None  # None=use what gpg uses
BLOCKSIZE = 65536

openpgp_trust = {"-": _("Trust not calculated"),
                 "o": _("Unknown trust"),
                 "q": _("Undefined trust"),
                 "n": _("Never trust"),
                 "m": _("Marginally trust"),
                 "f": _("Full trust"),
                 "u": _("Ultimate trust"),
                 "e": _("Expired key, not trusted"),
                 "d": _("Disabled key, not trusted"),  # Deprecated flag.
                 "r": _("Revoked key, not trusted")}

openpgp_algorithms = {1: _("RSA"),
                      2: _("RSA (encrypt only)"),
                      3: _("RSA (sign only)"),
                      16: _("Elgamal (encrypt only)"),
                      17: _("DSA"),
                      20: _("Elgamal (encrypt/sign) [COMPROMISED]")}
# For details on type 20 compromisation, see
# http://lists.gnupg.org/pipermail/gnupg-announce/2003q4/000160.html

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
        for data in retvals[1]["status"]:
            keyword = data[0].strip()
            if keyword == "DECRYPTION_FAILED":
                missing = [x[1] for x in retvals[1]["status"]
                           if x[0] == "NO_SECKEY"]
                if missing:
                    encryption_info["status"] = "missingkey"
                    encryption_info["missing_keys"] = missing
                else:
                    encryption_info["status"] = "error"

            elif keyword == "DECRYPTION_OKAY":
                encryption_info["status"] = "decrypted"
                rp.plaintext = "".join(retvals[1]["stdout"])

            elif keyword == "ENC_TO":
                keylist = encryption_info.get("have_keys", [])
                if data[0] not in keylist:
                    keylist.append(data[1])
                encryption_info["have_keys"] = keylist

            elif signature_info["status"] == "none":
                # Only one of these will ever be emitted per key, use
                # this to set initial state. We may end up revising
                # the status depending on more info later.
                if keyword in ("GOODSIG", "BADSIG"):
                    email, fn = ExtractEmailAndName(
                        " ".join(data[2:]).decode('utf-8'))
                    signature_info["name"] = fn
                    signature_info["email"] = email
                    signature_info["status"] = ((keyword == "GOODSIG")
                                                and "unverified"
                                                or "invalid")
                elif keyword == "ERRSIG":
                    signature_info["status"] = "error"
                    signature_info["keyinfo"] = data[1]
                    signature_info["timestamp"] = int(data[5])

        # Second pass, this may update/mutate the state set above
        for data in retvals[1]["status"]:
            keyword = data[0]

            if keyword == "NO_SECKEY":
                if "missing_keys" not in encryption_info:
                    encryption_info["missing_keys"] = [data[1]]
                else:
                    encryption_info["missing_keys"].append(data[1])
                try:
                    encryption_info["have_keys"].remove(data[1])
                except (KeyError, ValueError):
                    pass

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
                signature_info["status"] = ((keyword == "EXPKEYSIG")
                                            and "expired"
                                            or "revoked")

          # FIXME: This appears to be spammy. Is my key borked, or
          #        is GnuPG being stupid?
          #
          # elif keyword == "KEYEXPIRED":  # Ignoring: SIGEXPIRED
          #     signature_info["status"] = "expired"
            elif keyword == "KEYREVOKED":
                signature_info["status"] = "revoked"
            elif keyword == "NO_PUBKEY":
                signature_info["status"] = "unknown"

            elif keyword in ["TRUST_ULTIMATE", "TRUST_FULLY"]:
                if signature_info["status"] == "unverified":
                    signature_info["status"] = "verified"

        return rp

class GnuPGRecordParser:
    def __init__(self):
        self.keys = {}
        self.curkey = None

        self.record_fields = ["record", "validity", "keysize", "keytype", 
                              "keyid", "creation_date", "expiration_date", 
                              "uidhash", "ownertrust", "uid", "sigclass", 
                              "capabilities", "flag", "sn", "hashtype", "curve"]
        self.record_types = ["pub", "sub", "ssb", "fpr", "uat", "sec", "tru", 
                             "sig", "rev", "uid", "gpg"]
        self.record_parsers = [self.parse_pubkey, self.parse_subkey, 
                          self.parse_subkey, self.parse_fingerprint,
                          self.parse_userattribute, self.parse_privkey, 
                          self.parse_trust, self.parse_signature, 
                          self.parse_revoke, self.parse_uidline, self.parse_none]

        self.dispatch = dict(zip(self.record_types, self.record_parsers))

    def parse(self, lines):
        for line in lines:
            self.parse_line(line)
        return self.keys

    def parse_line(self, line):
        line = dict(zip(self.record_fields, line.strip().split(":")))
        r = self.dispatch.get(line["record"], self.parse_unknown)
        r(line)

    def parse_pubkey(self, line):
        self.curkey = line["keyid"]
        line["keytype_name"] = openpgp_algorithms[int(line["keytype"])]
        line["capabilities_map"] = {
            "encrypt": "E" in line["capabilities"],
            "sign": "S" in line["capabilities"],
            "certify": "C" in line["capabilities"],
            "authenticate": "A" in line["capabilities"],
        },
        line["disabled"] = "D" in line["capabilities"]
        line["private_key"] = False
        line["subkeys"] = []
        line["uids"] = []

        if line["record"] == "sec":
            line["secret"] = True

        self.keys[self.curkey] = line
        self.parse_uidline(line)

    def parse_subkey(self, line):
        subkey = {"id": line["keyid"], "keysize": line["keysize"],
                  "creation_date": line["creation_date"],
                  "keytype_name": openpgp_algorithms[int(line["keytype"])]}
        self.keys[self.curkey]["subkeys"].append(subkey)

    def parse_fingerprint(self, line):
        self.keys[self.curkey]["fingerprint"] = line["keyid"]

    def parse_userattribute(self, line):
        # TODO: We are currently ignoring user attributes as not useful.
        #       We may at some point want to use --attribute-fd and read
        #       in user photos and such?
        pass

    def parse_privkey(self, line):
        self.parse_pubkey(line)

    def parse_uidline(self, line):
        email, name, comment = parse_uid(line["uid"])
        self.keys[self.curkey]["uids"].append({"email": email,
                                     "name": name,
                                     "comment": comment,
                                     "creation_date": line["creation_date"]})

    def parse_trust(self, line):
        # TODO: We are currently ignoring commentary from the Trust DB.
        pass

    def parse_signature(self, line):
        if "signatures" not in self.keys[self.curkey]:
            self.keys[self.curkey]["signatures"] = []
        sig = {"signer": line[9], "signature_date": line[5],
               "keyid": line[4], "trust": line[10], "keytype": line[4]}

        self.keys[self.curkey]["signatures"].append(sig)

    def parse_revoke(self, line):
        # FIXME: Do something more to this
        print line

    def parse_unknown(self, line):
        print "Unknown line with code '%s'" % line[0]

    def parse_none(line):
        pass

UID_PARSE_RE = "([^\(\<]+){0,1}( \((.+)\)){0,1} (\<(.+)\>){0,1}"
def parse_uid(uidstr):
    matches = re.match(UID_PARSE_RE, uidstr)
    if matches:
        email = matches.groups(0)[4] or ""
        comment = matches.groups(0)[2] or ""
        name = matches.groups(0)[0] or ""
    else:
        email = uidstr
        name = ""
        comment = ""

    try:
        name = name.decode("utf-8")
    except UnicodeDecodeError:
        try:
            name = name.decode("iso-8859-1")
        except UnicodeDecodeError:
            name = name.decode("utf-8", "replace")

    try:
        comment = comment.decode("utf-8")
    except UnicodeDecodeError:
        try:
            comment = comment.decode("iso-8859-1")
        except UnicodeDecodeError:
            comment = comment.decode("utf-8", "replace")

    return email, name, comment

class StreamReader(Thread):
    def __init__(self, fd, callback, lines=True):
        Thread.__init__(self, target=self.readin, args=(fd, callback))
        self.lines = lines
        self.start()

    def readin(self, fd, callback):
        try:
            if self.lines:
                for line in iter(fd.readline, b''):
                    callback(line)
            else:
                while True:
                    buf = fd.read(BLOCKSIZE)
                    callback(buf)
                    if buf == "":
                        break
        except:
            traceback.print_exc()
        finally:
            fd.close()

class StreamWriter(Thread):
    def __init__(self, fd, output):
        Thread.__init__(self, target=self.writeout, args=(fd, output))
        self.start()

    def writeout(self, fd, output):
        if isinstance(output, (str, unicode)):
            output = StringIO.StringIO(output)
        try:
            while True:
                line = output.read(BLOCKSIZE)
                if line == "":
                    break
                fd.write(line)
            output.close()
        except:
            traceback.print_exc()
        finally:
            fd.close()

class GnuPG:
    """
    Wrap GnuPG and make all functionality feel Pythonic.
    """
    def __init__(self):
        self.available = None
        self.gpgbinary = 'gpg'
        self.passphrase = None
        self.outputfds = ["stdout", "stderr", "status"]
        self.errors = []
        self.homedir = GNUPG_HOMEDIR

    def set_home(self, path):
        self.homedir = path

    def version(self):
        retvals = self.run(["--version"])
        return retvals[1]["stdout"][0].split('\n')[0]

    def is_available(self):
        try:
            retvals = self.run(["--version"])
            self.available = True
        except OSError:
            self.available = False

        return self.available

    def run(self, args=[], output=None, outputfd=None):
        self.outputbuffers = dict([(x, []) for x in self.outputfds])
        self.pipes = {}
        args.insert(0, self.gpgbinary)
        args.insert(1, "--utf8-strings")
        args.insert(1, "--with-colons")
        args.insert(1, "--verbose")
        args.insert(1, "--batch")
        args.insert(1, "--enable-progress-filter")

        if self.homedir:
            args.insert(1, "--homedir=%s" % self.homedir)

        self.statuspipe = os.pipe()
        self.status = os.fdopen(self.statuspipe[0], "r")
        args.insert(1, "--status-fd")
        args.insert(2, "%d" % self.statuspipe[1])
        if self.passphrase:
            self.passphrase_pipe = os.pipe()
            self.passphrase_handle = os.fdopen(self.passphrase_pipe[1], "w")
            args.insert(1, "--passphrase-fd")
            args.insert(2, "%d" % self.statuspipe[0])

        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE,
            bufsize=1, close_fds=False)

        self.threads = {
            "stderr": StreamReader(proc.stderr, self.parse_stderr),
            "status": StreamReader(self.status, self.parse_status),
        }
        if self.passphrase:
            self.threads["passphrase"] = StreamWriter(self.passphrase_handle, 
                                                      self.passphrase)

        if outputfd:
            self.threads["stdout"] = StreamReader(proc.stdout, outputfd.write,
                                                  lines=False)
        else:
            self.threads["stdout"] = StreamReader(proc.stdout,
                                                  self.parse_stdout)

        if output:
            # If we have output, we just stream it. Technically, this
            # doesn't really need to be a thread at the moment.
            StreamWriter(proc.stdin, output).join()
        else:
            proc.stdin.close()

        # Reap GnuPG
        proc.wait()

        # Close our pipes so the threads finish
        os.close(self.statuspipe[1])
        if self.passphrase:
            os.close(self.passphrase_pipe[1])

        # Reap the threads
        for name, thr in self.threads.iteritems():
            thr.join()

        if outputfd:
            outputfd.close()

        return proc.returncode, self.outputbuffers

    def parse_status(self, line, *args):
        line = line.replace("[GNUPG:] ", "")
        if line == "":
            return
        elems = line.split(" ")
        self.outputbuffers["status"].append(elems)

    def parse_stdout(self, line):
        self.outputbuffers["stdout"].append(line)

    def parse_stderr(self, line):
        self.outputbuffers["stderr"].append(line)

    def parse_keylist(self, keylist):
        rlp = GnuPGRecordParser()
        return rlp.parse(keylist)

    def list_keys(self):
        """
        >>> g = GnuPG()
        >>> g.list_keys()[0]
        0
        """
        retvals = self.run(["--list-keys", "--fingerprint"])
        return self.parse_keylist(retvals[1]["stdout"])

    def list_secret_keys(self):
        #
        # Note: The "." parameter that is passed is to work around a bug
        #       in GnuPG < 2.1, where --list-secret-keys does not list
        #       details about key capabilities or expiry for 
        #       --list-secret-keys unless a selector is provided. A dot
        #       is reasonably likely to appear in all PGP keys, as it is
        #       a common component of e-mail addresses (and @ does not
        #       work as a selector for some reason...)
        #
        #       The downside of this workaround is that keys with no e-mail
        #       address or an address like alice@localhost won't be found.
        #       Therefore, this paramter should be removed when GnuPG >= 2.1
        #       becomes commonplace.
        #
        #       (This is a better workaround than doing an additional 
        #       --list-keys and trying to aggregate it though...)
        #
        retvals = self.run(["--list-secret-keys", ".", "--fingerprint"])
        return self.parse_keylist(retvals[1]["stdout"])

    def import_keys(self, key_data=None):
        """
        Imports gpg keys from a file object or string.
        >>> key_data = open("testing/pub.key").read()
        >>> g = GnuPG()
        >>> g.import_keys(key_data)
        {'failed': [], 'updated': [{'details_text': 'unchanged', 'details': 0, 'fingerprint': '08A650B8E2CBC1B02297915DC65626EED13C70DA'}], 'imported': [], 'results': {'sec_dups': 0, 'unchanged': 1, 'num_uids': 0, 'skipped_new_keys': 0, 'no_userids': 0, 'num_signatures': 0, 'num_revoked': 0, 'sec_imported': 0, 'sec_read': 0, 'not_imported': 0, 'count': 1, 'imported_rsa': 0, 'imported': 0, 'num_subkeys': 0}}
        """
        retvals = self.run(["--import"], output=key_data)
        return self._parse_import(retvals[1]["status"])

    def _parse_import(self, output):
        res = {"imported": [], "updated": [], "failed": []}
        for x in output:
            if x[0] == "IMPORTED":
                res["imported"].append({
                    "fingerprint": x[1],
                    "username": x[2]
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
                    "fingerprint": x[2],
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
                    "fingerprint": x[2]
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
                    "not_imported": int(x[14]),
                }
        return res

    def decrypt(self, data, outputfd=None, passphrase=None, as_lines=False):
        """
        Note that this test will fail if you don't replace the recipient with
        one whose key you control.
        >>> g = GnuPG()
        >>> ct = g.encrypt("Hello, World", to=["smari@mailpile.is"])[1]
        >>> g.decrypt(ct)["text"]
        'Hello, World'
        """
        if passphrase:
            self.passphrase = passphrase
        action = ["--decrypt"]
        retvals = self.run(action, output=data, outputfd=outputfd)
        self.passphrase = None

        if as_lines:
            as_lines = retvals[1]["stdout"]
            retvals[1]["stdout"] = []

        rp = GnuPGResultParser().parse(retvals)

        return (rp.signature_info, rp.encryption_info,
                as_lines or rp.plaintext)

    def verify(self, data, signature=None):
        """
        >>> g = GnuPG()
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

        ret, retvals = self.run(params, output=data)

        return GnuPGResultParser().parse([None, retvals]).signature_info

    def encrypt(self, data, tokeys=[], armor=True):
        """
        >>> g = GnuPG()
        >>> g.encrypt("Hello, World", to=["smari@mailpile.is"])[0]
        0
        """
        action = ["--encrypt", "--yes", "--expert", "--trust-model", "always"]
        if armor:
            action.append("--armor")
        for r in tokeys:
            action.append("--recipient")
            action.append(r)
        retvals = self.run(action, output=data)
        return retvals[0], "".join(retvals[1]["stdout"])

    def sign(self, data,
             fromkey=None, armor=True, detatch=True, clearsign=False,
             passphrase=None):
        """
        >>> g = GnuPG()
        >>> g.sign("Hello, World", fromkey="smari@mailpile.is")[0]
        0
        """
        if passphrase:
            self.passphrase = passphrase
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

        retvals = self.run(action, output=data)
        self.passphrase = None
        return retvals[0], retvals[1]["stdout"][0]

    def sign_encrypt(self, data, fromkey=None, tokeys=[], armor=True,
                     detatch=False, clearsign=True):
        retval, signblock = self.sign(data, fromkey=fromkey, armor=armor,
                                      detatch=detatch, clearsign=clearsign)
        if detatch:
            # TODO: Deal with detached signature.
            retval, cryptblock = self.encrypt(data, tokeys=tokeys,
                                              armor=armor)
        else:
            retval, cryptblock = self.encrypt(signblock, tokeys=tokeys,
                                              armor=armor)

        return cryptblock

    def sign_key(self, keyid, signingkey=None):
        action = ["--yes", "--sign-key", keyid]
        if signingkey:
            action.insert(1, "-u")
            action.insert(2, signingkey)
        retvals = self.run(action)
        return retvals

    def recv_key(self, keyid, keyserver=DEFAULT_SERVER):
        retvals = self.run(['--keyserver', keyserver, '--recv-key', keyid])
        return self._parse_import(retvals[1]["status"])

    def search_key(self, term, keyserver=DEFAULT_SERVER):
        retvals = self.run(['--keyserver', keyserver,
                            '--search-key', self._escape_hex_keyid_term(term)]
                            )[1]["stdout"]
        results = {}
        lines = [x.strip().split(":") for x in retvals]
        curpub = None
        for line in lines:
            if line[0] == "info":
                pass
            elif line[0] == "pub":
                curpub = line[1]
                results[curpub] = {"created": datetime.fromtimestamp(int(line[4])),
                                   "keytype_name": openpgp_algorithms[int(line[2])],
                                   "keysize": line[3],
                                   "uids": []}
            elif line[0] == "uid":
                email, name, comment = parse_uid(line[1])
                results[curpub]["uids"].append({"name": name,
                                                "email": email,
                                                "comment": comment})
        return results

    def address_to_keys(self, address):
        res = {}
        keys = self.list_keys()
        for key, props in keys.iteritems():
            if any([x["email"] == address for x in props["uids"]]):
                res[key] = props

        return res

    def _escape_hex_keyid_term(self, term):
        """Prepends a 0x to hexadecimal key ids, e.g. D13C70DA is converted to 0xD13C70DA.

            This is necessary because version 1 and 2 of GnuPG show a different behavior here,
            version 1 allows to search without 0x while version 2 requires 0x in front of the key id.
        """
        is_hex_keyid = False
        if len(term) == GPG_KEYID_LENGTH or len(term) == 2*GPG_KEYID_LENGTH:
            hex_digits = set(string.hexdigits)
            is_hex_keyid = all(c in hex_digits for c in term)

        if is_hex_keyid:
            return '0x%s' % term
        else:
            return term

def GetKeys(gnupg, config, people):
    keys = []
    missing = []

    # First, we go to the contact database and get a list of keys.
    for person in set(people):
        if '#' in person:
            keys.append(person.rsplit('#', 1)[1])
        else:
            vcard = config.vcards.get_vcard(person)
            if vcard:
                # FIXME: Rather than get_all, we should give the vcard the
                #        option of providing us with its favorite key.
                lines = [vcl for vcl in vcard.get_all('KEY')
                         if vcl.value.startswith('data:application'
                                                 '/x-pgp-fingerprint,')]
                if len(lines) == 1:
                    keys.append(lines[0].value.split(',', 1)[1])
                else:
                    missing.append(person)
            else:
                missing.append(person)

    # FIXME: This doesn't really feel scalable...
    all_keys = gnupg.list_keys()
    for key in all_keys.values():
        for uid in key["uids"]:
            if uid["email"] in missing:
                missing.remove(uid["email"])
                keys.append(key["fingerprint"])

    # Next, we go make sure all those keys are really in our keychain.
    fprints = [k["fingerprint"] for k in all_keys.values()]
    for key in keys:
        if key not in keys and key not in fprints:
            missing.append(key)

    if missing:
        raise KeyLookupError(_('Keys missing or ambiguous for %s'
                               ) % ', '.join(missing), missing)
    return keys

class OpenPGPMimeSigningWrapper(MimeSigningWrapper):
    CRYPTO_CLASS = GnuPG
    CONTAINER_PARAMS = (('micalg', 'pgp-sha1'),
                        ('protocol', 'application/pgp-signature'))
    SIGNATURE_TYPE = 'application/pgp-signature'
    SIGNATURE_DESC = 'OpenPGP Digital Signature'

    def get_keys(self, who):
        return GetKeys(self.crypto, self.config, who)

class OpenPGPMimeEncryptingWrapper(MimeEncryptingWrapper):
    CRYPTO_CLASS = GnuPG
    CONTAINER_PARAMS = (('protocol', 'application/pgp-encrypted'), )
    ENCRYPTION_TYPE = 'application/pgp-encrypted'
    ENCRYPTION_VERSION = 1

    def get_keys(self, who):
        return GetKeys(self.crypto, self.config, who)
