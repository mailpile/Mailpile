import os
import sys
import tempfile
from hashlib import sha512
from subprocess import Popen, PIPE

def genkey(self, filename, magic):
    """
    Generate keys for files based on host key and filename. 
    Nice utility, Bob!
    """
    h = sha512()
    h.update(":%s:%s:" % (os.path.basename(filename), magic))
    return h.hexdigest()


class OpenSSL:
    """
    Wrap OpenSSL and make all functionality feel Pythonic.
    """

    def __init__(self):
        self.available = None
        self.binary = 'openssl'
        self.handles = {}
        self.pipes = {}
        self.fds = ["stdout", "stderr"]
        self.errors = []
        self.statuscallbacks = {}

    def run(self, args=[], output=None, debug=False):
        self.pipes = {}
        args.insert(0, self.binary)

        if debug: print "Running openssl as: %s" % " ".join(args)

        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        self.handles["stdout"] = proc.stdout
        self.handles["stderr"] = proc.stderr
        self.handles["stdin"] = proc.stdin

        if output:
            self.handles["stdin"].write(output)
            self.handles["stdin"].close()

        retvals = dict([(fd, "") for fd in self.fds])
        while True:
            proc.poll()

            for fd in self.fds:
                try:
                    buf = self.handles[fd].read()
                except IOError:
                    continue

                if buf == "":
                    continue

                retvals[fd] += buf

            if proc.returncode is not None:
                break

        return proc.returncode, retvals


    def encrypt(self, data, key):
        # TODO: Make keys get passed through files or environment
        inbuf = tempfile.NamedTemporaryFile()
        inbuf.write(data)
        inbuf.flush()
        outbuf = tempfile.NamedTemporaryFile()
        params = ["enc", "-e", "-a", "-aes-256-gcm", 
                  "-pass", "pass:%s" % key,
                  "-in", inbuf.name, 
                  "-out", outbuf.name, 
                 ]
        self.run(params)
        res = outbuf.read()
        inbuf.close()
        outbuf.close()
        return res


    def decrypt(self, data, key):
        # TODO: Make keys get passed through files or environment
        inbuf = tempfile.NamedTemporaryFile()
        inbuf.write(data)
        inbuf.flush()
        outbuf = tempfile.NamedTemporaryFile()
        params = ["enc", "-d", "-a", "-aes-256-gcm", 
                  "-pass", "pass:%s" % key,
                  "-in", inbuf.name, 
                  "-out", outbuf.name, 
                 ]
        self.run(params)
        res = outbuf.read()
        inbuf.close()
        outbuf.close()
        return res


if __name__ == "__main__":
    s = OpenSSL()
    teststr = "Hello! This is a longish thing."
    testpass = "kukalabbi"
    if teststr == s.decrypt(s.encrypt(teststr, testpass), testpass):
        print "Test passed"
    else:
        print "Test failed"
