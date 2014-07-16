import os
import hashlib
import random
import sys
import re
import threading
import traceback
from datetime import datetime
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile

from mailpile.util import md5_hex, CryptoLock
from mailpile.util import sha512b64 as genkey


LEN_MD5 = len(md5_hex('testing'))
MD5_SUM_FORMAT = 'md5sum: %s'
MD5_SUM_PLACEHOLDER = MD5_SUM_FORMAT % ('0' * LEN_MD5)
MD5_SUM_RE = re.compile('(?m)^' + MD5_SUM_FORMAT % (r'[^\n]+',))


class IOFilter(threading.Thread):
    """
    This class will wrap a filehandle and spawn a background thread to
    filter either the input or output.
    """
    BLOCKSIZE = 8192

    def __init__(self, fd, callback, error_callback=None):
        threading.Thread.__init__(self)
        self.fd = fd
        self.callback = callback
        self.error_callback = error_callback
        self.writing = None
        self.info = 'Starting'
        self.pipe = list(os.pipe())

    def __str__(self):
        return '%s: %s' % (threading.Thread.__str__(self), self.info)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def writer(self):
        try:
            if self.writing is None:
                self.writing = True
                self.start()
            return os.fdopen(self.pipe[1], 'w')
        finally:
            self.pipe[1] = None

    def reader(self):
        try:
            if self.writing is None:
                self.writing = False
                self.daemon = True
                self.start()
            return os.fdopen(self.pipe[0], 'r')
        finally:
            self.pipe[0] = None

    def _do_write(self):
        while True:
            self.info = 'Writer, reading'
            data = os.read(self.pipe[0], self.BLOCKSIZE)
            self.info = 'Writer, writing'
            if len(data) == 0:
                self.fd.write(self.callback(None))
                self.fd.flush()
                self.info = 'Writer, done'
                return
            else:
                self.fd.write(self.callback(data))

    def _do_read(self):
        while True:
            self.info = 'Reader, reading'
            data = self.fd.read(self.BLOCKSIZE)
            self.info = 'Reader, writing'
            if len(data) == 0:
                os.write(self.pipe[1], self.callback(None))
                os.close(self.pipe[1])
                self.info = 'Reader, done'
                return
            else:
                os.write(self.pipe[1], self.callback(data))

    def close(self):
        self._close_pipe_fd(self.pipe[0])
        self._close_pipe_fd(self.pipe[1])
        self.info = 'Closed'

    def _close_pipe_fd(self, pipe_fd):
        try:
            if pipe_fd is not None:
                os.close(pipe_fd)
        except OSError:
            pass

    def run(self):
        try:
            self.info = 'Starting: %s' % self.writing
            if self.writing is True:
                self._do_write()
            elif self.writing is False:
                self._do_read()
        except:
            traceback.print_exc()
            if self.error_callback:
                try:
                    self.error_callback()
                except:
                    pass
        finally:
            self.info = 'Dead'


class IOCoprocess(object):
    def __init__(self, command, fd):
        self.stderr = ''
        self._retval = None
        if command:
            self._proc, self._fd = self._popen(command, fd)
        else:
            self._proc, self._fd = None, fd

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

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

    def _write_filter(self, data):
        return data

    def write(self, data, *args, **kwargs):
        return self._fd.write(self._write_filter(data), *args, **kwargs)


class InputCoprocess(IOCoprocess):
    """
    This class will stream data from an external coprocess.
    """
    def _popen(self, command, fd):
        proc = Popen(command, stdin=fd, stderr=PIPE, stdout=PIPE,
                     bufsize=0, close_fds=True)
        return proc, proc.stdout

    def _read_filter(self, data):
        return data

    def __iter__(self, *args):
        return (self._read_filter(d) for d in self._fd.__iter__(*args))

    def readline(self, *args):
        return self._read_filter(self._fd.readline(*args))

    def readlines(self, *args):
        return [self._read_filter(line) for line in self.readlines(*args)]

    def read(self, *args):
        return self._read_filter(self._fd.read(*args))


class ChecksummingStreamer(OutputCoprocess):
    """
    This checksums and streams data a named temporary file on disk, which
    can then be read back or linked to a final location.
    """
    def __init__(self, dir=None):
        self.tempfile, self.temppath = self._mk_tempfile_and_path(dir)

        self.outer_md5sum = None
        self.outer_md5 = hashlib.md5()
        self.md5filter = IOFilter(self.tempfile, self._md5_callback)
        self.fd = self.md5filter.writer()

        self.saved = False
        self.finished = False
        try:
            self._write_preamble()
            OutputCoprocess.__init__(self, self._mk_command(), self.fd)
        except:
            try:
                self.tempfile.close()
                os.remove(self.temppath)
                self.fd.close()
            except (IOError, OSError):
                pass
            raise

    def _mk_tempfile_and_path(self, _dir):
        ntf = NamedTemporaryFile(dir=_dir, delete=False)
        return ntf, ntf.name

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
        self.md5filter.close()
        self.tempfile.seek(0, 0)

    def close(self):
        self.finish()
        self.tempfile.close()

    def save(self, filename, finish=True):
        if finish:
            self.finish()
        if not self.saved:
            # 1st save just renames the tempfile
            os.rename(self.temppath, filename)
            self.saved = True
        else:
            # 2nd save creates a copy
            with open(filename, 'wb') as out:
                self.save_copy(out)

    def save_copy(self, ofd):
        self.tempfile.seek(0, 0)
        data = self.tempfile.read(4096)
        while data != '':
            ofd.write(data)
            data = self.tempfile.read(4096)

    def _md5_callback(self, data):
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


class EncryptingDelimitedStreamer(ChecksummingStreamer):
    """
    This class creates a coprocess for encrypting data. The data will
    be streamed to a named temporary file on disk, which can then be
    read back or linked to a final location.
    """
    BEGIN_DATA = "-----BEGIN MAILPILE ENCRYPTED DATA-----\n"
    EXTRA_HEADERS = ""
    END_DATA = "-----END MAILPILE ENCRYPTED DATA-----\n"

    # We would prefer AES-256-GCM, but unfortunately openssl does not
    # (yet) behave well with it.
    DEFAULT_CIPHER = "aes-256-cbc"

    def __init__(self, key, dir=None, cipher=None):
        self.cipher = cipher or self.DEFAULT_CIPHER
        self.nonce, self.key = self._nonce_and_mutated_key(key)

        ChecksummingStreamer.__init__(self, dir=dir)

        self.inner_md5sum = None
        self.inner_md5 = hashlib.md5()
        self.inner_md5.update(self.key)
        self.inner_md5.update(self.nonce or '')

        self._send_key()

    def _write_filter(self, data):
        if data:
            self.inner_md5.update(data)
        return data

    def finish(self, *args, **kwargs):
        if not self.finished:
            rv = ChecksummingStreamer.finish(self, *args, **kwargs)
            self._write_inner_md5sum()
            return rv
        else:
            return ChecksummingStreamer.finish(self, *args, **kwargs)

    def _write_inner_md5sum(self):
        if not self.inner_md5sum:
            self.inner_md5sum = self.inner_md5.hexdigest()
            pos = self.tempfile.tell()
            self.tempfile.seek(0, 0)
            old_data = self.tempfile.read(4096)

            md5_sum_header = MD5_SUM_FORMAT % (self.inner_md5sum, )
            new_data = re.sub(MD5_SUM_RE, md5_sum_header, old_data)
            if old_data != new_data:
                self.tempfile.seek(0, 0)
                self.tempfile.write(new_data)

            self.tempfile.seek(pos, 0)

    def _nonce_and_mutated_key(self, key):
        #
        # Note: This nonce is NOT generated using strong randomness.
        #       That is not the point and should not matter.
        #
        nonce = genkey(str(random.getrandbits(512)))[:32].strip()
        return nonce, genkey(key, nonce)[:32].strip()

    def _send_key(self):
        # We talk directly to the underlying FD, to avoid corrupting the
        # inner MD5 sum (calculated using the _write_filter() above).
        self._fd.write('%s\n' % self.key)

    def _mk_command(self):
        return ["openssl", "enc", "-e", "-a", "-%s" % self.cipher,
                "-pass", "stdin"]

    def _write_preamble(self):
        self.fd.write(self.BEGIN_DATA)
        self.fd.write('cipher: %s\n' % self.cipher)
        if self.nonce:
            self.fd.write('nonce: %s\n' % self.nonce)
        self.fd.write(MD5_SUM_PLACEHOLDER + '\n')
        if self.EXTRA_HEADERS:
            self.fd.write(self.EXTRA_HEADERS)
        self.fd.write('\n')
        self.fd.flush()

    def _write_postamble(self):
        if self.END_DATA:
            self.fd.write('\n')
            self.fd.write(self.END_DATA)
        self.fd.flush()


class EncryptingUndelimitedStreamer(EncryptingDelimitedStreamer):
    """
    This class creates a coprocess for encrypting data. The data will
    be streamed to a named temporary file on disk, which can then be
    read back or linked to a final location.
    """
    BEGIN_DATA = "X-Mailpile-Encrypted-Data: v1\n"
    EXTRA_HEADERS = ("From: Mailpile <encrypted@mailpile.is>\n"
                     "Subject: Mailpile encrypted data\n")
    END_DATA = ""


def EncryptingStreamer(*args, **kwargs):
    delimited = kwargs.get('delimited', False)
    if 'delimited' in kwargs:
        del kwargs['delimited']
    if delimited:
        return EncryptingDelimitedStreamer(*args, **kwargs)
    else:
        return EncryptingUndelimitedStreamer(*args, **kwargs)


class DecryptingStreamer(InputCoprocess):
    """
    This class creates a coprocess for decrypting data.
    """
    BEGIN_PGP = "-----BEGIN PGP MESSAGE-----"
    END_PGP = "-----END PGP MESSAGE-----"
    BEGIN_MED = "-----BEGIN MAILPILE ENCRYPTED DATA-----\n"
    BEGIN_MED2 = "X-Mailpile-Encrypted-Data: "
    END_MED = "-----END MAILPILE ENCRYPTED DATA-----\n"
    DEFAULT_CIPHER = "aes-256-cbc"

    STATE_BEGIN = 0
    STATE_HEADER = 1
    STATE_DATA = 2
    STATE_ONLY_DATA = 3
    STATE_END = 4
    STATE_RAW_DATA = 5
    STATE_PGP_DATA = 6
    STATE_ERROR = -1

    @classmethod
    def StartEncrypted(cls, line):
        return (line.startswith(cls.BEGIN_MED[:-1]) or
                line.startswith(cls.BEGIN_MED2) or
                line.startswith(cls.BEGIN_PGP[:-1]))

    @classmethod
    def EndEncrypted(cls, line):
        return (line.startswith(cls.END_MED[:-1]) or
                line.startswith(cls.END_PGP[:-1]))

    def __init__(self, fd,
                 mep_key=None, gpg_pass=None, md5sum=None, cipher=None):
        self.expected_outer_md5sum = md5sum
        self.expected_inner_md5sum = None
        self.outer_md5 = hashlib.md5()
        self.inner_md5 = hashlib.md5()
        self.cipher = self.DEFAULT_CIPHER
        self.state = self.STATE_BEGIN
        self.buffered = ''
        self.mep_key = mep_key
        self.gpg_pass = gpg_pass

        # Start reading our data...
        self.startup_lock = CryptoLock()
        self.startup_lock.acquire()
        self.data_filter = self._mk_data_filter(fd, self._read_data,
                                                self.startup_lock.release)
        self.read_fd = self.data_filter.reader()
        try:
            # Once the header has been processed (_read_data() will release
            # the lock), fork out our coprocess.
            self.startup_lock.acquire()
            InputCoprocess.__init__(self, self._mk_command(), self.read_fd)
            self.startup_lock = None
        except:
            try:
                fd.close()
                self.read_fd.close()
            except (IOError, OSError):
                pass
            raise

    def _read_filter(self, data):
        if data:
            self.inner_md5.update(data)
        return data

    def close(self):
        return InputCoprocess.close(self)

    def verify(self, testing=False, _raise=None):
        if self.close() != 0:
            if testing:
                print 'Close returned nonzero'
            if _raise:
                raise _raise('Non-zero exit code from coprocess')
            return False
        if (self.expected_inner_md5sum and
                self.expected_inner_md5sum != self.inner_md5.hexdigest()):
            if testing:
                print 'Inner %s != %s' % (self.expected_inner_md5sum,
                                          self.inner_md5.hexdigest())
            if _raise:
                raise _raise('Invalid inner MD5 sum')
            return False
        if (self.expected_outer_md5sum and
                self.expected_outer_md5sum != self.outer_md5.hexdigest()):
            if testing:
                print 'Outer %s != %s' % (self.expected_outer_md5sum,
                                          self.outer_md5.hexdigest())
            if _raise:
                raise _raise('Invalid outer MD5 sum')
            return False
        return True

    def _mk_data_filter(self, fd, cb, ecb):
        return IOFilter(fd, cb, error_callback=ecb)

    def _read_data(self, data):
        if data is None:
            if self.state in (self.STATE_BEGIN, self.STATE_HEADER):
                self.state = self.STATE_RAW_DATA
                self.startup_lock.release()
                data, self.buffered = self.buffered, ''
                return data
            return ''

        if self.expected_outer_md5sum:
            if self.state in (self.STATE_BEGIN, self.STATE_HEADER):
                sum_data = re.sub(MD5_SUM_RE, MD5_SUM_PLACEHOLDER, data)
            else:
                sum_data = data
            sum_data = sum_data.replace('\r', '').replace('\n', '\r\n')
            self.outer_md5.update(sum_data)

        if self.state in (self.STATE_RAW_DATA, self.STATE_PGP_DATA):
            return data

        if self.state == self.STATE_BEGIN:
            self.buffered += data
            if (len(self.buffered) >= len(self.BEGIN_PGP)
                    and self.buffered.startswith(self.BEGIN_PGP)):
                self.state = self.STATE_PGP_DATA
                if self.gpg_pass:
                    passphrase, c = [], self.gpg_pass.read(1)
                    while c != '':
                        passphrase.append(c)
                        c = self.gpg_pass.read(1)
                    self.startup_lock.release()
                    return ''.join(passphrase + ['\n', self.buffered])
                else:
                    self.startup_lock.release()
                    return self.buffered

            # Note: The max() check is OK, because both formats add more
            #       data which covers the difference.
            if len(self.buffered) >= max(len(self.BEGIN_MED),
                                         len(self.BEGIN_MED2)):
                if not (self.buffered.startswith(self.BEGIN_MED) or
                        self.buffered.startswith(self.BEGIN_MED2)):
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
            nonce = headers.get('nonce', '')
            mutated = self._mutate_key(self.mep_key, nonce)

            self.cipher = headers.get('cipher', self.cipher)
            self.expected_inner_md5sum = headers.get('md5sum')
            self.inner_md5.update(mutated)
            self.inner_md5.update(nonce)

            data = '\n'.join((mutated, data))
            if self.buffered.startswith(self.BEGIN_MED2):
                self.state = self.STATE_ONLY_DATA
            else:
                self.state = self.STATE_DATA
            self.startup_lock.release()

        if self.state == self.STATE_ONLY_DATA:
            return data

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
            gpg = ["gpg", "--batch"]
            if self.gpg_pass:
                gpg.extend(["--no-use-agent", "--passphrase-fd=0"])
            return gpg
        return ["openssl", "enc", "-d", "-a", "-%s" % self.cipher,
                "-pass", "stdin"]


class ReadLineIOFilter(IOFilter):
    """
    This is a line-based IOFilter, which can stop when it sees a
    particular marker to hand off processing to others.
    """
    def __init__(self, fd, callback,
                 start_data=None, stop_check=None, error_callback=None):
        self.stop_check = stop_check
        self.start_data = start_data
        IOFilter.__init__(self, fd, callback, error_callback=error_callback)

    def _do_read(self):
        if self.start_data:
            os.write(self.pipe[1], self.callback(''.join(self.start_data)))

        for data in self.fd:
            os.write(self.pipe[1], self.callback(data))
            if self.stop_check and self.stop_check(data):
                break

        os.write(self.pipe[1], self.callback(None))
        os.close(self.pipe[1])


class PartialDecryptingStreamer(DecryptingStreamer):
    def __init__(self, start_data, *args, **kwargs):
        self.start_data = start_data
        DecryptingStreamer.__init__(self, *args, **kwargs)

    def _mk_data_filter(self, fd, cb, ecb):
        return ReadLineIOFilter(fd, cb,
                                start_data=self.start_data,
                                stop_check=self.EndEncrypted,
                                error_callback=ecb)


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


     # Null decryption test, md5 verification only
     ds = DecryptingStreamer(open('/tmp/iofilter.tmp', 'rb'),
                             mep_key='test key',
                             md5sum='86fb269d190d2c85f6e0468ceca42a20')
     assert('Hello world!' == ds.read())
     assert(ds.verify(testing=True))

     # Encryption test
     for delim in (True, False):
         data = 'Hello world! This is great!\nHooray, lalalalla!\n'
         es = EncryptingStreamer('test key', dir='/tmp', delimited=delim)
         es.write(data)
         es.finish()
         fn = '/tmp/%s.aes' % es.outer_md5sum
         open(fn, 'wb').write('junk')  # Make sure overwriting works
         es.save(fn)

         # Decryption test!
         ds = DecryptingStreamer(open(fn, 'rb'),
                                 mep_key='test key',
                                 md5sum=es.outer_md5sum)
         new_data = ds.read()
         assert(ds.close() == 0)
         assert(data == new_data)
         assert(ds.verify(testing=True))


         # Cleanup
         os.unlink(fn)
     os.unlink('/tmp/iofilter.tmp')
