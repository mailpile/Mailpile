import os
import fcntl
import hashlib
import random
import sys
import threading
from datetime import datetime
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile

from mailpile.util import sha512b64 as genkey


class IOFilter(threading.Thread):
    """
    This class will wrap a filehandle and spawn a background thread to
    filter either the input or output.
    """
    def __init__(self, fd, callback):
        threading.Thread.__init__(self)
        self.fd = fd
        self.callback = callback
        self.writing = None
        self.pipe = os.pipe()

    def writer(self):
        if self.writing is None:
            self.writing = True
            self.start()
        return os.fdopen(self.pipe[1], 'w')

    def reader(self):
        if self.writing is None:
            self.writing = False
            self.start()
        return os.fdopen(self.pipe[0], 'r')

    def _do_write(self):
        while True:
            data = os.read(self.pipe[0], 4096)
            if len(data) == 0:
                self.fd.flush()
                return
            else:
                self.fd.write(self.callback(data))

    def _do_read(self):
        while True:
            data = self.fd.read(4096)
            if len(data) == 0:
                os.close(self.pipe[1])
                return
            else:
                os.write(self.pipe[1], self.callback(data))

    def run(self):
        if self.writing is True:
            self._do_write()
        elif self.writing is False:
            self._do_read()


class OutputCoprocess:
    """
    This class will stream data to an external coprocess.
    """
    def __init__(self, command, dest_fd):
        self.proc = Popen(command,
                          bufsize=0, stdin=PIPE, stdout=dest_fd,
                          close_fds=True)

    def write(self, data):
        return self.proc.stdin.write(data)

    def close(self):
        self.proc.stdin.close()
        return self.proc.wait()


class InputCoprocess:
    """
    This class will stream data from an external coprocess.
    """
    def __init__(self, command, input_fd):
        self.proc = Popen(command,
                          bufsize=0, stdin=input_fd, stdout=PIPE,
                          close_fds=True)

    def read(self, *args):
        return self.proc.stdout.read(*args)

    def close(self):
        self.proc.stdout.close()
        return self.proc.wait()


class EncryptingStreamer(OutputCoprocess):
    """
    This class creates a coprocess for encrypting data. The data will
    be streamed to a named temporary file on disk, which can then be
    read back or linked to a final location.
    """
    BEGIN_DATA = "-----BEGIN MAILPILE ENCRYPTED DATA-----\n"
    END_DATA = "-----END MAILPILE ENCRYPTED DATA-----\n"
    DEFAULT_CIPHER = "aes-256-gcm"

    def __init__(self, key, dir=None, cipher=None):
        self.tempfile = NamedTemporaryFile(dir=dir, delete=False)
        self.cipher = cipher or self.DEFAULT_CIPHER
        self.nonce, self.key = self._mutate_key(key)

        self.inner_md5 = hashlib.md5()
        self.outer_md5 = hashlib.md5()
        self.md5filter = IOFilter(self.tempfile, self._outer_md5_callback)
        self.fd = self.md5filter.writer()

        self.outer_md5sum = None
        self.inner_md5sum = None

        self.finished = False
        self._write_preamble()
        OutputCoprocess.__init__(self, self._mk_command(), self.fd)
        self._send_key()

    def finish(self):
        if not self.finished:
            self.finished = True
            OutputCoprocess.close(self)
            self._write_postamble()
            self.fd.close()
            self.md5filter.join()
            self.outer_md5sum = self.outer_md5.hexdigest()
            self.tempfile.seek(0, 0)

    def close(self):
        self.finish()
        self.tempfile.close()

    def save(self, filename):
        self.close()
        os.rename(self.tempfile.name, filename)

    def _outer_md5_callback(self, data):
        # We calculate the MD5 sum as if the data used the CRLF linefeed
        # convention, whether it's actually using that or not.
        self.outer_md5.update(data.replace('\r', '').replace('\n', '\r\n'))
        return data

    def _mutate_key(self, key):
        nonce = genkey(str(random.getrandbits(512)))[:32].strip()
        return nonce, genkey(key, nonce)[:32].strip()

    def _send_key(self):
        self.write('%s\n' % self.key)

    def _mk_command(self):
        return ["openssl", "enc", "-e", "-a", "-%s" % self.cipher,
                "-pass", "stdin"]

    def _write_preamble(self):
        self.fd.write(self.BEGIN_DATA)
        self.fd.write('cipher: %s\n' % self.cipher)
        self.fd.write('nonce: %s\n' % self.nonce)
        self.fd.write('\n')
        self.fd.flush()

    def _write_postamble(self):
        self.fd.write('\n')
        self.fd.write(self.END_DATA)
        self.fd.flush()


class DecryptingStreamer(InputCoprocess):
    """
    This class creates a coprocess for decrypting data. The data will
    be streamed to a named temporary file on disk, which can then be
    read back or linked to a final location.
    """
    BEGIN_DATA = "-----BEGIN MAILPILE ENCRYPTED DATA-----\n"
    END_DATA = "-----END MAILPILE ENCRYPTED DATA-----\n"
    DEFAULT_CIPHER = "aes-256-gcm"

    STATE_BEGIN = 0
    STATE_HEADER = 1
    STATE_DATA = 2
    STATE_END = 3
    STATE_ERROR = -1

    def __init__(self, key, fd, md5sum=None, cipher=None):
                
        self.expected_outer_md5sum = md5sum
        self.outer_md5 = hashlib.md5()
        self.data_filter = IOFilter(fd, self._read_data)
        self.cipher = self.DEFAULT_CIPHER
        self.state = self.STATE_BEGIN
        self.buffered = ''
        self.key = key

        InputCoprocess.__init__(self, self._mk_command(),
                                self.data_filter.reader())

    def verify(self):
        if not self.expected_outer_md5sum:
            return False
        return (self.expected_outer_md5sum == self.outer_md5.hexdigest())

    def _read_data(self, data):
        self.outer_md5.update(data.replace('\r', '').replace('\n', '\r\n'))

        if self.state == self.STATE_BEGIN:
            self.buffered += data
            if '\r\n\r\n' in self.buffered:
                header, data = self.buffered.split('\r\n\r\n', 1)
                headlines = header.strip().split('\r\n')
                self.state = self.STATE_HEADER
            elif '\n\n' in self.buffered:
                header, data = self.buffered.split('\n\n', 1)
                headlines = header.strip().split('\n')
                self.state = self.STATE_HEADER
            else:
                return ''

        if self.state == self.STATE_HEADER:
            if header.startswith(self.BEGIN_DATA):
                headers = dict([l.split(': ', 1) for l in headlines[1:]])
                self.cipher = headers.get('cipher', self.cipher)
                nonce = headers.get('nonce')
                mutated = self._mutate_key(self.key, nonce)
                data = '\n'.join((mutated, data))
                self.state = self.STATE_DATA
            else:
                self.state = self.STATE_ERROR 

        if self.state == self.STATE_DATA:
            if '\n\n-' in data:
                data = data.split('\n\n-', 1)[0]
                self.state = self.STATE_END
            elif '\r\n\r\n-' in data:
                data = data.split('\r\n\r\n-', 1)[0]
                self.state = self.STATE_END
            return data

        # Error, end and unknown states...
        return ''

    def _mutate_key(self, key, nonce):
        return genkey(key, nonce)[:32].strip()

    def _mk_command(self):
        return ["openssl", "enc", "-d", "-a", "-%s" % self.cipher,
                "-pass", "stdin"]


if __name__ == "__main__":
    
     bc = [0]
     def counter(data):
         bc[0] += len(data)
         return data

     # Test the IOFilter in write mode
     iof = IOFilter(open('/tmp/iofilter.tmp', 'w'), counter)
     fd = iof.writer()
     fd.write('Hello world!')
     fd.close()
     iof.join()
     assert(open('/tmp/iofilter.out', 'r').read() == 'Hello world!')
     assert(bc[0] == 12)

     # Test the IOFilter in read mode
     bc[0] = 0
     iof = IOFilter(open('/tmp/iofilter.tmp', 'r'), counter)
     data = iof.reader().read()
     assert(data == 'Hello world!')
     assert(bc[0] == 12)

     # Cleanup
     os.unlink('/tmp/iofilter.tmp')

     # Encryption test
     data = 'Hello world! This is great!\nHooray, lalalalla!\n'
     es = EncryptingStreamer('test key', dir='/tmp')
     es.write(data)
     es.finish()
     fn = '/tmp/%s.aes' % es.outer_md5sum
     es.save(fn)

     # Decryption test!
     ds = DecryptingStreamer('test key', open(fn, 'rb'),
                             md5sum=es.outer_md5sum)
     new_data = ds.read()
     assert(ds.verify())
     assert(data == new_data)
 
     os.unlink(fn)
