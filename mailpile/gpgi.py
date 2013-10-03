#coding:utf-8
import os
import sys
import fcntl
import time
import re
from subprocess import Popen, PIPE

openpgp_trust = {"-": "Trust not calculated", 
                 "o": "Unknown trust",
                 "q": "Undefined trust",
                 "n": "Never trust",
                 "m": "Marginally trust",
                 "f": "Full trust",
                 "u": "Ultimate trust",
                 "e": "Expired key, not trusted",
                 "r": "Revoked key, not trusted",
                 "d": "Disabled key, not trusted",  # Deprecated flag.
                }

openpgp_algorithms = {1: "RSA",
                      2: "RSA (encrypt only)",
                      3: "RSA (sign only)",
                      16: "Elgamal (encrypt only)",
                      17: "DSA",
                      20: "Elgamal (encrypt/sign) [COMPROMISED]",
                     }
# For details on type 20 compromisation, see 
# http://lists.gnupg.org/pipermail/gnupg-announce/2003q4/000160.html

# These are detailed in the GnuPG source under doc/DETAILS.
status_messages = {
    "ENTER": [],
    "LEAVE": [],
    "ABORT": [],
    "NEWSIG": [],
    "GOODSIG": ["long_keyid_or_fpr", "username"],
    "KEYEXPIRED": ["expire_timestamp"],
    "KEYREVOKED": [],
    "BADSIG": ["long_keyid_or_fpr", "username"],
    "ERRSIG": ["long_keyid_or_fpr", "pubkey_algo", "hash_algo", "sig_class", 
               "timestamp", "rc"],
    "BADARMOR": [],
    "TRUST_UNDEFINED": ["error_token"],
    "TRUST_NEVER": ["error_token"],
    "TRUST_MARGINAL": ["zero", "validation_model"],
    "TRUST_FULLY": ["zero", "validation_model"],
    "TRUST_ULTIMATE": ["zero", "validation_model"],
    "GET_BOOL": [],
    "GET_LINE": [],
    "GET_HIDDEN": [],
    "GOT_IT": [],
    "SHM_INFO": [],
    "SHM_GET": [],
    "SHM_GET_BOOL": [],
    "SHM_GET_HIDDEN": [],
    "NEED_PASSPHRASE": ["long_main_keyid", "long_keyid", 
                        "keytype", "keylength"],
    "VALIDSIG": ["fingerprint", "sig_creation_date", "sig_timestamp", 
                 "expire_timestamp","sig_version", "reserved", "pubkey_algo", 
                 "hash_algo", "sig_class", "primary_key_fpr"],
    "SIG_ID": ["radix64_string", "sig_creation_date", "sig_timestamp"],
    "ENC_TO": ["long_keyid", "keytype", "keylength"],
    "NODATA": ["what"],
    "BAD_PASSPHRASE": ["long_keyid"],
    "NO_PUBKEY": ["long_keyid"],
    "NO_SECKEY": ["long_keyid"],
    "NEED_PASSPHRASE_SYM": ["cipher_algo", "s2k_mode", "s2k_hash"],
    "NEED_PASSPHRASE_PIN": ["card_type", "chvno", "serialno"],
    "DECRYPTION_FAILED": [],
    "DECRYPTION_OKAY": [],
    "MISSING_PASSPHRASE": [],
    "GOOD_PASSPHRASE": [],
    "GOODMDC": [],
    "BADMDC": [],
    "ERRMDC": [],
    "IMPORTED": ["long keyid", "username"],
    "IMPORT_OK": ["reason", "fingerprint"],
    "IMPORT_PROBLEM": ["reason", "fingerprint"],
    "IMPORT_CHECK": [],
    "IMPORT_RES": ["count", "no_user_id", "imported", "imported_rsa", 
                   "unchanged", "n_uids", "n_subk", "n_sigs", "n_revoc", 
                   "sec_read", "sec_imported", "sec_dups", "skipped_new_keys",
                   "not_imported"],
    "FILE_START": ["what", "filename"],
    "FILE_DONE": [],
    "FILE_ERROR": [],
    "BEGIN_DECRYPTION": ["mdc_method", "sym_algo"],
    "END_DECRYPTION": [],
    "BEGIN_ENCRYPTION": [],
    "END_ENCRYPTION": [],
    "DELETE_PROBLEM": ["reason_code"],
    "PROGRESS": ["what", "char", "cur", "total"],
    "SIG_CREATED": ["type" "pubkey algo", "hash algo", "class", 
                    "timestamp", "key fpr"],
    "SESSION_KEY": ["algo:hexdigits"],
    "NOTATION_NAME" : ["name"],
    "NOTATION_DATA" : ["string"],
    "POLICY_URL" : ["string"],
    "BEGIN_STREAM": [],
    "END_STREAM": [],
    "KEY_CREATED": ["type", "fingerprint", "handle"],
    "KEY_NOT_CREATED": ["handle"],
    "USERID_HINT": ["long main keyid", "string"],
    "UNEXPECTED": ["what"],
    "INV_RECP": ["reason", "requested_recipient"],
    "INV_SGNR": ["reason", "requested_sender"],
    "NO_RECP": ["reserved"],
    "NO_SGNR": ["reserved"],
    "ALREADY_SIGNED": ["long-keyid"], # Experimental, may disappear
    "SIGEXPIRED": [], # Deprecated but may crop up; keyexpired overrides
    "TRUNCATED": ["maxno"],
    "EXPSIG": ["long_keyid_or_fpr", "username"],
    "EXPKEYSIG": ["long_keyid_or_fpr", "username"],
    "REVKEYSIG": ["long_keyid_or_fpr", "username"],
    "ATTRIBUTE": ["fpr", "octets", "type", "index", 
                  "count", "timestamp", "expiredate", "flags"],
    "CARDCTRL": ["what", "serialno"],
    "PLAINTEXT": ["format", "timestamp", "filename"],
    "PLAINTEXT_LENGTH": ["length"],
    "SIG_SUBPACKET": ["type", "flags", "len", "data"],
    "SC_OP_SUCCESS": ["code"],
    "SC_OP_FAILURE": ["code"],
    "BACKUP_KEY_CREATED": ["fingerprint", "fname"],
    "PKA_TRUST_BAD": ["unknown"],
    "PKA_TRUST_GOOD": ["unknown"],
    "BEGIN_SIGNING": [],
    "ERROR": ["error location", "error code", "more"],
    "MOUNTPOINT": ["mdc_method", "sym_algo"],
    "SUCCESS": ["location"],
    "DECRYPTION_INFO": [],
}

class GnuPG:
    """
    Wrap GnuPG and make all functionality feel Pythonic.
    """

    def __init__(self):
        self.gpgbinary = 'gpg'
        self.passphrase = None
        self.rw = ["r", "w"]
        self.fds = {"passphrase": True, "command": True, "logger": False, "status": False}
        self.handles = {}
        self.pipes = {}
        self.needed_fds = ["stdin", "stdout", "stderr"]
        self.errors = []

    def default_errorhandler(self, *error):
        if error != "":
            self.errors.append(error)
        return True

    def default_output(self, output):
        return output

    def parse_status(self, output, *args):
        status = []
        lines = output.split("\n")
        for line in lines:
            line = line.replace("[GNUPG:] ", "")
            if line == "":
                continue
            elems = line.split(" ")
            callback_kwargs = dict(zip(status_messages, elems[1:]))
            if self.statuscallbacks.has_key(elems[0]):
                for callback in self.statuscallbacks[elems[0]]:
                    callback(*kwargs)
            status.append(elems)

        return status

    def parse_verify(self, output, *args):
        lines = output.split("\n")
        sig = {"datetime": "",
               "status": "",
               "keyid": "",
               "signer": "",
               "ok": None,
               "version": "",
               "hash": ""
              }

        if "no valid OpenPGP data found" in lines[0]:
            sig["ok"] = False
            sig["status"] = lines[1][4:]
        elif False:
            pass

        return sig

    def parse_keylist(self, keylist, *args):
        """
        >>> g = GnuPG()
        >>> v = g.parse_keylist("pub:u:4096:1:D5DC2A79C2E4AE92:2010-12-30:::u:Smari McCarthy <smari@immi.is>::scESC:\\nsub:u:4096:1:13E0BB42176BA0AC:2010-12-30::::::e:")
        >>> v.has_key("D5DC2A79C2E4AE92")
        True
        >>> v["D5DC2A79C2E4AE92"]["size"]
        4096
        >>> v["D5DC2A79C2E4AE92"]["creation-date"]
        '2010-12-30'
        >>> v["D5DC2A79C2E4AE92"]["algorithm"]
        1
        >>> v["D5DC2A79C2E4AE92"]["subkeys"][0]["algorithm"]
        1
        """
        keys = {}
        curkey = None

        def parse_pubkey(line, curkey, keys):
            keys[line[4]] = {
                "size": int(line[2]),
                "creation-date": line[5],
                "uids": [],
                "subkeys": [],
                "signatures": [],
                "trust": line[1],
                "algorithm": int(line[3])
            }
            if line[6] != "":
                keys[line[4]]["revocation-date"] = line[5]
            curkey = line[4]
            curkey, keys = parse_uid(line, curkey, keys)
            return (curkey, keys)

        def parse_subkey(line, curkey, keys):
            subkey = {"id": line[4], "size": int(line[2]), "creation-date": line[5], "algorithm": int(line[3])}
            if line[0] == "ssb":
                subkey["secret"] = True
            keys[curkey]["subkeys"].append(subkey)            
            return (curkey, keys)

        def parse_fingerprint(line, curkey, keys):
            keys[curkey]["fingerprint"] = line[9]
            return (curkey, keys)

        def parse_userattribute(line, curkey, keys):
            # TODO: We are currently ignoring user attributes as not useful.
            #       We may at some point want to use --attribute-fd and read
            #       in user photos and such?
            return (curkey, keys)

        def parse_privkey(line, curkey, keys):
            curkey, keys = parse_pubkey(line, curkey, keys)
            return (curkey, keys)

        def parse_uid(line, curkey, keys):
            matches = re.match("([^\(\)]*)( \((.*)\)){0,1} \<(.*)\>", line[9])
            if matches:
                email = matches.groups(0)[3]
                comment = matches.groups(0)[2] or ""
                name = matches.groups(0)[0]
            else:
                email = line[9]
                name = ""
                comment = ""
            keys[curkey]["uids"].append({"email": email, "name": name, "comment": comment, "creation-date": line[5] })
            return (curkey, keys)

        def parse_trust(line, curkey, keys):
            # TODO: We are currently ignoring commentary from the Trust DB.
            return (curkey, keys)

        def parse_signature(line, curkey, keys):
            sig = {"signer": line[9], "signature-date": line[5], "keyid": line[4], "trust": line[10], "algorithm": line[4]}

            keys[curkey]["signatures"].append(sig)
            return (curkey, keys)

        def parse_unknown(line, curkey, keys):
            print "Unknown line with code '%s'" % line[0]
            return (curkey, keys)

        def parse_none(line, curkey, keys):
            return (curkey, keys)

        disp = {"pub": parse_pubkey,
                "sub": parse_subkey,
                "ssb": parse_subkey,
                "fpr": parse_fingerprint,
                "uat": parse_userattribute,
                "sec": parse_privkey,
                "tru": parse_trust,
                "sig": parse_signature,
                "uid": parse_uid,
                "gpg": parse_none,
               }

        lines = keylist.split("\n")
        for line in lines:
            if line == "":
                continue
            parms = line.split(":")
            r = disp.get(parms[0], parse_unknown)
            curkey, keys = r(parms, curkey, keys)

        return keys

    def emptycallbackmap():
        """Utility function for people who are confused about what callbacks exist."""
        return dict([[x, []] for x in self.needed_fds])

    def run(self, args=[], callbacks={}, output=None, debug=False):
        """
        >>> g = GnuPG()
        >>> g.run(["--list-keys"])[0]
        0
        """
        self.pipes = {}
        args.insert(0, self.gpgbinary)
        args.append("--with-colons")
        args.append("--verbose")
        args.append("--enable-progress-filter")

        for fd in self.fds.keys():
            if fd not in self.needed_fds:
                continue
            self.pipes[fd] = os.pipe()
            if debug: 
                print "Opening fd %s, fh %d, mode %s" % (fd, 
                    self.pipes[fd][self.fds[fd]], ["r", "w"][self.fds[fd]])
            args.append("--%s-fd" % fd)
            # The remote end of the pipe:
            args.append("%d" % self.pipes[fd][not self.fds[fd]])
            fdno = self.pipes[fd][self.fds[fd]]
            self.handles[fd] = os.fdopen(fdno, ["r", "w"][self.fds[fd]])
            # Cause file handles to stay open after execing
            fcntl.fcntl(self.handles[fd], fcntl.F_SETFD, 0)
            fl = fcntl.fcntl(self.handles[fd], fcntl.F_GETFL)
            fcntl.fcntl(self.handles[fd], fcntl.F_SETFL, fl | os.O_NONBLOCK)

        if debug: print "Running gpg with %s" % args

        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        self.handles["stdout"] = proc.stdout
        self.handles["stderr"] = proc.stderr
        self.handles["stdin"] = proc.stdin

        if output:
            self.handles["stdin"].write(output)
            self.handles["stdin"].close()

        if self.passphrase:
            self.handles["passphrase"].write(self.passphrase)
            self.handles["passphrase"].close()

        retvals = {}
        for fd in self.needed_fds:
            if fd in ("stdin", "passphrase"):
                continue
            if not callbacks.has_key(fd):
                continue
            while True:
                if debug: print "Reading %s" % fd

                try:
                    buf = self.handles[fd].read()
                except IOError:
                    break

                if not retvals.has_key(fd):
                    retvals[fd] = []
                if buf == "":
                    break

                if type(callbacks[fd]) == list:
                    for cb in callbacks[fd]:
                        retvals[fd].append(cb(buf))
                else:
                    retvals[fd].append(callbacks[fd](buf))

        return proc.returncode, retvals

    def list_keys(self):
        """
        >>> g = GnuPG()
        >>> g.list_keys()[0]
        0
        """
        retvals = self.run(["--list-keys", "--fingerprint"], callbacks={"stdout": self.parse_keylist})
        return retvals

    def list_sigs(self):
        self.run(["--list-sigs", "--fingerprint"], callbacks={"stdout": self.parse_keylist})
        return retvals

    def list_secret_keys(self):
        """
        >>> g = GnuPG()
        >>> g.list_secret_keys()[0]
        0
        """
        retvals = self.run(["--list-secret-keys", "--fingerprint"], callbacks={"stdout": self.parse_keylist})
        return retvals

    def encrypt(self, data, to=[], armor=True):
        """
        >>> g = GnuPG()
        >>> g.encrypt("Hello, World", to=["smari@mailpile.is"])[0]
        0
        """
        action = ["--encrypt"]
        if armor:
            action.append("--armor")
        for r in to:
            action.append("--recipient")
            action.append(r)
        retvals = self.run(action, callbacks={"stdout": self.default_output}, output=data)
        return retvals[0], retvals[1]["stdout"][0]

    def decrypt(self, data, passphrase=None):
        """
        Note that this test will fail if you don't replace the recipient with one whose key you control.
        >>> g = GnuPG()
        >>> ct = g.encrypt("Hello, World", to=["smari@mailpile.is"])[1]
        >>> g.decrypt(ct)[1]
        'Hello, World'
        """
        if passphrase:
            self.passphrase = passphrase
        action = ["--decrypt"]
        retvals = self.run(action, callbacks={"stdout": self.default_output}, output=data)
        return retvals[0], retvals[1]["stdout"][0]

    def sign(self, data, _from=None, armor=True, detatch=True, clearsign=False, passphrase=None):
        """
        >>> g = GnuPG()
        >>> g.sign("Hello, World", _from="smari@mailpile.is")[0]
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
        if _from:
            action.append("--local-user")
            action.append(_from)

        retvals = self.run(action, callbacks={"stdout": self.default_output}, output=data)
        return retvals[0], retvals[1]["stdout"][0]

    def verify(self, data, signature=None):
        """
        >>> g = GnuPG()
        >>> s = g.sign("Hello, World", _from="smari@mailpile.is", clearsign=True)[1]
        >>> g.verify(s)
        """
        print "BEFORE: %s" % self.needed_fds
        self.needed_fds.append("status")
        print "AFTER: %s" % self.needed_fds
        retvals = self.run(["--verify"], callbacks={"stderr": self.parse_verify, "status": self.default_output}, output=data, debug=True)
        self.needed_fds.remove("status")

        return retvals[0], retvals[1]["stderr"]

    def sign_encrypt(self, data, _from=None, to=[], armor=True, detatch=True, clearsign=False):
        retval, signblock = self.sign(data, _from=_from, armor=armor, detatch=detatch, clearsign=clearsign)
        if detatch:
            # TODO: Deal with detached signature.
            retval, cryptblock = self.encrypt(data, to=to, armor=armor)
        else:
            retval, cryptblock = self.encrypt(signblock, to=to, armor=armor)

        return cryptblock



if __name__ == "__main__":
    g = GnuPG()
    g.verify("Foo")
#    import doctest
#    t = doctest.testmod()
#    if t.failed == 0:
#        print "GPG Interface: All %d tests successful" % (t.attempted)
#    else:
#        print "GPG Interface: %d out of %d tests failed" % (t.failed, t.attempted)
