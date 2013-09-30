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
# For details on type 20 compromisation, see http://lists.gnupg.org/pipermail/gnupg-announce/2003q4/000160.html


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
        self.needed_fds = ["stdin", "stdout", "stderr"] # , "logger", "status"]
        self.callbacks = dict([[x, []] for x in self.needed_fds])
        self.reg_callback("stderr", self.default_errorhandler)
        self.errors = []

    def default_errorhandler(self, *error):
        if error != "":
            self.errors.append(error)
        return True

    def reg_callback(self, cbtype, cb):
        assert(hasattr(cb, "__call__"))
        self.callbacks[cbtype].append(cb)

    def clear_callbacks(self, cbtype="all"):
        if cbtype == "all":
            for cb in self.callbacks.keys():
                self.callbacks[cb] = []
        else:
            self.callbacks[cb] = []

    def remove_callback(self, cbtype, cb):
        if cb in self.callbacks[cbtype]:
            self.callbacks[cbtype].remove(cb)
            return True
        else:
            return False

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

    def run(self, args=[]):
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
            args.append("--%s-fd=%d" % (fd, self.pipes[fd][not self.fds[fd]]))
            self.handles[fd] = os.fdopen(self.pipes[fd][self.fds[fd]], self.rw[self.fds[fd]])
            fcntl.fcntl( self.handles[fd], fcntl.F_SETFD, 0 )   # Stay open after execing

        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        self.handles["stdout"] = proc.stdout
        self.handles["stderr"] = proc.stderr
        self.handles["stdin"] = proc.stdin
        if self.passphrase:
            self.handles["passphrase"].write(self.passphrase)
            self.handles["passphrase"].close()

        retvals = {}
        while True:
            proc.poll()
            for fd in self.needed_fds:
                if fd in ("stdin", "passphrase"):
                    continue
                if not retvals.has_key(fd):
                    retvals[fd] = []
                buf = self.handles[fd].read()
                if buf != "":
                    for cb in self.callbacks[fd]:
                        retvals[fd].append(cb(buf))

            if proc.returncode is not None:
                break

        return proc.returncode, retvals

    def list_keys(self):
        """
        >>> g = GnuPG()
        >>> g.list_keys()[0]
        0
        """
        self.reg_callback("stdout", self.parse_keylist)
        retvals = self.run(["--list-keys", "--fingerprint"])
        self.remove_callback("stdout", self.parse_keylist)
        return retvals

    def list_sigs(self):
        self.reg_callback("stdout", self.parse_keylist)
        self.run(["--list-sigs", "--fingerprint"])
        self.remove_callback("stdout", self.parse_keylist)        
        return retvals

    def list_secret_keys(self):
        """
        >>> g = GnuPG()
        >>> g.list_secret_keys()[0]
        0
        """
        self.reg_callback("stdout", self.parse_keylist)
        retvals = self.run(["--list-secret-keys", "--fingerprint"])
        self.remove_callback("stdout", self.parse_keylist)
        return retvals

    def encrypt(self, data):
        pass

    def decrypt(self, data):
        pass

    def sign(self, data):
        pass

    def verify(self, data):
        pass


if __name__ == "__main__":
    import doctest
    t = doctest.testmod()
    if t.failed == 0:
        print "GPG Interface: All %d tests successful" % (t.attempted)
    else:
        print "GPG Interface: %d out of %d tests failed" % (t.failed, t.attempted)
