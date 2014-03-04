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
    BLOCKSIZE = 8192

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
            data = os.read(self.pipe[0], self.BLOCKSIZE)
            if len(data) == 0:
                self.fd.write(self.callback(None))
                self.fd.flush()
                return
            else:
                self.fd.write(self.callback(data))

    def _do_read(self):
        while True:
            data = self.fd.read(self.BLOCKSIZE)
            if len(data) == 0:
                os.write(self.pipe[1], self.callback(None))
                os.close(self.pipe[1])
                return
            else:
                os.write(self.pipe[1], self.callback(data))

    def run(self):
        if self.writing is True:
            self._do_write()
        elif self.writing is False:
            self._do_read()


class IOCoprocess:
    def __init__(self, command, fd):
        self.stderr = ''
        self._retval = None
        if command:
            self._proc, self._fd = self._popen(command, fd)
        else:
            self._proc, self._fd = None, fd

    def close(self, *args):
        if self._retval is None:
            self._fd.close(*args)
            if self._proc:
                self.stderr = self._proc.stderr.read()
                self._retval = self._proc.wait()
                self._proc = None
            else:
                self._retval = 0
        return self._retval


class OutputCoprocess(IOCoprocess):
    """
    This class will stream data to an external coprocess.
    """
    def _popen(self, command, fd):
         proc = Popen(command, stdin=PIPE, stderr=PIPE, stdout=fd,
                      bufsize=0, close_fds=True)
         return proc, proc.stdin

    def write(self, *args):
        return self._fd.write(*args)


class InputCoprocess(IOCoprocess):
    """
    This class will stream data from an external coprocess.
    """
    def _popen(self, command, fd):
        proc = Popen(command, stdin=fd, stderr=PIPE, stdout=PIPE,
                     bufsize=0, close_fds=True)
        return proc, proc.stdout

    def read(self, *args):
        return self._fd.read(*args)


class ChecksummingStreamer(OutputCoprocess):
    """
    This checksums and streams data a named temporary file on disk, which
    can then be read back or linked to a final location.
    """
    def __init__(self, dir=None):
        self.tempfile = NamedTemporaryFile(dir=dir, delete=False)

        self.outer_md5sum = None
        self.outer_md5 = hashlib.md5()
        self.md5filter = IOFilter(self.tempfile, self._outer_md5_callback)
        self.fd = self.md5filter.writer()

        self.saved = False
        self.finished = False
        self._write_preamble()
        OutputCoprocess.__init__(self, self._mk_command(), self.fd)

    def _mk_command(self):
        return None

    def finish(self):
        if self.finished:
            return
        self.finished = True
        OutputCoprocess.close(self)
        self._write_postamble()
        self.fd.close()
        self.md5filter.join()
        self.tempfile.seek(0, 0)

    def close(self):
        self.finish()
        self.tempfile.close()

    def save(self, filename, finish=True):
        if finish:
            self.finish()
        if not self.saved:
            # 1st save just renames the tempfile
            os.rename(self.tempfile.name, filename)
            self.saved = True
        else:
            # 2nd save creates a copy
            self.save_copy(open(filename, 'wb'))

    def save_copy(self, ofd):
        self.tempfile.seek(0, 0)
        data = self.tempfile.read(4096)
        while data != '':
            ofd.write(data)
            data = self.tempfile.read(4096)
        ofd.close()

    def _outer_md5_callback(self, data):
        if data is None:
            # EOF...
            self.outer_md5sum = self.outer_md5.hexdigest()
            return ''
        else:
            # We calculate the MD5 sum as if the data used the CRLF linefeed
            # convention, whether it's actually using that or not.
            self.outer_md5.update(data.replace('\r', '').replace('\n', '\r\n'))
            return data

    def _write_preamble(self):
        pass

    def _write_postamble(self):
        pass


class EncryptingStreamer(ChecksummingStreamer):
    """
    This class creates a coprocess for encrypting data. The data will
    be streamed to a named temporary file on disk, which can then be
    read back or linked to a final location.
    """
    BEGIN_DATA = "-----BEGIN MAILPILE ENCRYPTED DATA-----\n"
    END_DATA = "-----END MAILPILE ENCRYPTED DATA-----\n"

    # We would prefer AES-256-GCM, but unfortunately openssl does not
    # (yet) behave well with it.
    DEFAULT_CIPHER = "aes-256-cbc"

    def __init__(self, key, dir=None, cipher=None):
        self.cipher = cipher or self.DEFAULT_CIPHER
        self.nonce, self.key = self._mutate_key(key)
        ChecksummingStreamer.__init__(self, dir=dir)
        self._send_key()

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
    This class creates a coprocess for decrypting data.
    """
    BEGIN_PGP = "-----BEGIN PGP MESSAGE-----"
    BEGIN_MED = "-----BEGIN MAILPILE ENCRYPTED DATA-----\n"
    END_MED = "-----END MAILPILE ENCRYPTED DATA-----\n"
    DEFAULT_CIPHER = "aes-256-cbc"

    STATE_BEGIN = 0
    STATE_HEADER = 1
    STATE_DATA = 2
    STATE_END = 3
    STATE_RAW_DATA = 4
    STATE_PGP_DATA = 5
    STATE_ERROR = -1

    def __init__(self, key, fd, md5sum=None, cipher=None):
        self.expected_outer_md5sum = md5sum
        self.outer_md5 = hashlib.md5()
        self.data_filter = IOFilter(fd, self._read_data)
        self.cipher = self.DEFAULT_CIPHER
        self.state = self.STATE_BEGIN
        self.buffered = ''
        self.key = key

        # Start reading our data...
        self.startup_lock = threading.Lock()
        self.startup_lock.acquire()
        self.read_fd = self.data_filter.reader()

        # Once the header has been processed (_read_data() will release the
        # lock), fork out our coprocess.
        self.startup_lock.acquire()
        InputCoprocess.__init__(self, self._mk_command(), self.read_fd)
        self.startup_lock = None

    def verify(self):
        if self.close() != 0:
            return False
        if not self.expected_outer_md5sum:
            return False
        return (self.expected_outer_md5sum == self.outer_md5.hexdigest())

    def _read_data(self, data):
        if data is None:
            if self.state in (self.STATE_BEGIN, self.STATE_HEADER):
                self.state = self.STATE_RAW_DATA
                self.startup_lock.release()
                data, self.buffered = self.buffered, ''
                return data
            return ''

        self.outer_md5.update(data.replace('\r', '').replace('\n', '\r\n'))

        if self.state == self.STATE_RAW_DATA:
            return data

        if self.state == self.STATE_BEGIN:
            self.buffered += data
            if (len(self.buffered) >= len(self.BEGIN_PGP)
                    and self.buffered.startswith(self.BEGIN_PGP)):
                self.state = self.STATE_PGP_DATA
                self.startup_lock.release()
                return self.buffered
            if len(self.buffered) >= len(self.BEGIN_MED):
                if not self.buffered.startswith(self.BEGIN_MED):
                    self.state = self.STATE_RAW_DATA
                    self.startup_lock.release()
                    return self.buffered
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
            else:
                return ''

        if self.state == self.STATE_HEADER:
            headers = dict([l.split(': ', 1) for l in headlines[1:]])
            self.cipher = headers.get('cipher', self.cipher)
            nonce = headers.get('nonce')
            mutated = self._mutate_key(self.key, nonce)
            data = '\n'.join((mutated, data))
            self.state = self.STATE_DATA
            self.startup_lock.release()

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
        if self.state == self.STATE_RAW_DATA:
            return None
        elif self.state == self.STATE_PGP_DATA:
            return ["gpg", "--batch"]
        return ["openssl", "enc", "-d", "-a", "-%s" % self.cipher,
                "-pass", "stdin"]


if __name__ == "__main__":

     bc = [0]
     def counter(data):
         bc[0] += len(data or '')
         return data or ''

     # Test the IOFilter in write mode
     iof = IOFilter(open('/tmp/iofilter.tmp', 'w'), counter)
     fd = iof.writer()
     fd.write('Hello world!')
     fd.close()
     iof.join()
     assert(open('/tmp/iofilter.tmp', 'r').read() == 'Hello world!')
     assert(bc[0] == 12)

     # Test the IOFilter in read mode
     bc[0] = 0
     iof = IOFilter(open('/tmp/iofilter.tmp', 'r'), counter)
     data = iof.reader().read()
     assert(data == 'Hello world!')
     assert(bc[0] == 12)

     # Encryption test
     data = 'Hello world! This is great!\nHooray, lalalalla!\n'
     es = EncryptingStreamer('test key', dir='/tmp')
     es.write(data)
     es.finish()
     fn = '/tmp/%s.aes' % es.outer_md5sum
     open(fn, 'wb').write('junk')  # Make sure overwriting works
     es.save(fn)

     # Decryption test!
     ds = DecryptingStreamer('test key', open(fn, 'rb'),
                             md5sum=es.outer_md5sum)
     new_data = ds.read()
     assert(ds.verify())
     assert(data == new_data)

     # Null decryption test, md5 verification only
     ds = DecryptingStreamer('test key', open('/tmp/iofilter.tmp', 'rb'),
                             md5sum='86fb269d190d2c85f6e0468ceca42a20')
     assert('Hello world!' == ds.read())
     assert(ds.verify())

     # Cleanup
     os.unlink('/tmp/iofilter.tmp')
     os.unlink(fn)
