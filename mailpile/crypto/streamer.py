import os
import hashlib
import random
import sys
import re
import threading
import time
import traceback
from datetime import datetime
from tempfile import NamedTemporaryFile

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.crypto.gpgi import GPG_BINARY
from mailpile.safe_popen import Popen, PIPE
from mailpile.util import md5_hex, CryptoLock, safe_remove
from mailpile.util import sha512b64 as genkey


LEN_MD5 = len(md5_hex('testing'))
MD5_SUM_FORMAT = 'md5sum: %s'
MD5_SUM_PLACEHOLDER = MD5_SUM_FORMAT % ('0' * LEN_MD5)
MD5_SUM_RE = re.compile('(?m)^' + MD5_SUM_FORMAT % (r'[^\n]+',))

if sys.platform.startswith("win"):
    OPENSSL_COMMAND = 'OpenSSL\\bin\\openssl.exe'
    FILTER_MD5 = True
else:
    OPENSSL_COMMAND = "openssl"
    FILTER_MD5 = False


class IOFilter(threading.Thread):
    """
    This class will wrap a filehandle and spawn a background thread to
    filter either the input or output.
    """
    BLOCKSIZE = 8192

    def __init__(self, fd, callback, name=None, error_callback=None):
        threading.Thread.__init__(self)
        self.callback = callback
        self.error_callback = error_callback
        self.exc_info = None

        self.fd = fd
        self.writing = None
        self.reading_from = None
        self.writing_to = None

        self.exposed_fd = None
        self.my_pipe_fd = None

        pipe = os.pipe()
        self.pipe_reader = os.fdopen(pipe[0], 'rb', 0)
        self.pipe_writer = os.fdopen(pipe[1], 'wb', 0)

        self.info = 'Starting'
        self.aborting = False
        if name:
            self.name = name

    def __str__(self):
        return '%s: %s' % (threading.Thread.__str__(self), self.info)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        fd, self.exposed_fd = self.exposed_fd, None
        if fd is not None:
            try:
                fd.close()
            except OSError:  # May already have been closed, that's fine
                pass

        if self.writing is False:
            self.aborting = 'Closed reader'

        self.join()

    def join(self, aborting=None):
        if aborting is not None:
            self.aborting = aborting
        return threading.Thread.join(self)

    def writer(self):
        if self.writing is None:
            self.writing = True

            self.reading_from = self.pipe_reader
            self.writing_to = self.fd
            self.my_pipe_fd = self.pipe_reader
            self.exposed_fd = self.pipe_writer

            self.start()
        return self.pipe_writer

    def reader(self):
        if self.writing is None:
            self.daemon = True
            self.writing = False

            self.reading_from = self.fd
            self.writing_to = self.pipe_writer
            self.my_pipe_fd = self.pipe_writer
            self.exposed_fd = self.pipe_reader

            self.start()
        return self.pipe_reader

    def _copy_loop(self):
        while not self.aborting:
            self.info = 'reading'
            data = self.reading_from.read(self.BLOCKSIZE)
            if not self.aborting:
                self.info = 'writing'
                if len(data) == 0:
                    self.writing_to.write(self.callback(None) or '')
                    break
                else:
                    self.writing_to.write(self.callback(data))

    def run(self):
        okay = [AssertionError]
        if self.writing is False:
            # If we close early, we may get ValueErrors
            okay.append(ValueError)

        try:
            self.info = 'Starting: %s' % self.writing
            self._copy_loop()
        except tuple(okay):
            pass
        except:
            self.exc_info = sys.exc_info()
            traceback.print_exc()
            if self.error_callback:
                try:
                    self.error_callback()
                except:
                    pass
        finally:
            fd, self.my_pipe_fd = self.my_pipe_fd, None
            if fd is not None:
                fd.close()
            self.info = 'Dead'


class IOCoprocess(object):
    def __init__(self, command, fd, name=None, long_running=False):
        self.stderr = ''
        self._retval = None
        self._reading = False
        self.name = name
        if command:
            try:
                self._proc, self._fd = self._popen(command, fd, long_running)
            except:
                print 'Popen(%s, %s, %s)' % (command, fd, long_running)
                traceback.print_exc()
                print
                raise
        else:
            self._proc, self._fd = None, fd

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self, *args):
        if self._retval is None:
            proc, fd, self._proc, self._fd = self._proc, self._fd, None, None
            if proc and fd:
                fd.close(*args)
                # If we were reading from the process, not writing, then
                # closing our FD above may not be enough to terminate it,
                # and the following calls may hang. So kill kill kill.
                if self._reading:
                    proc.terminate()
                    time.sleep(0.1)
                    if proc.poll() is None:
                        proc.kill()
                self.stderr = proc.stderr.read()
                self._retval = proc.wait()
            else:
                self._retval = 0
        return self._retval


class OutputCoprocess(IOCoprocess):
    """
    This class will stream data to an external coprocess.
    """
    def _popen(self, command, fd, long_running):
        proc = Popen(command, stdin=PIPE, stdout=fd, stderr=PIPE,
                              bufsize=0, long_running=long_running)
        return proc, proc.stdin

    def _write_filter(self, data):
        return data

    def write(self, data, *args, **kwargs):
        return self._fd.write(self._write_filter(data), *args, **kwargs)


class InputCoprocess(IOCoprocess):
    """
    This class will stream data from an external coprocess.
    """
    def _popen(self, command, fd, long_running):
        self._reading = True
        proc = Popen(command, stdin=fd, stdout=PIPE, stderr=PIPE,
                              bufsize=0, long_running=long_running)
        return proc, proc.stdout

    def _read_filter(self, data):
        return data

    def __iter__(self, *args):
        return (self._read_filter(ln) for ln in self._fd.__iter__(*args))

    def readline(self, *args):
        return self._read_filter(self._fd.readline(*args))

    def readlines(self, *args):
        return [self._read_filter(ln) for ln in self._fd.readlines(*args)]

    def read(self, *args):
        return self._read_filter(self._fd.read(*args))


class ChecksummingStreamer(OutputCoprocess):
    """
    This checksums and streams data a named temporary file on disk, which
    can then be read back or linked to a final location.
    """
    def __init__(self, dir=None, name=None, long_running=False,
                       use_filter=FILTER_MD5):
        self.tempfile, self.temppath = self._mk_tempfile_and_path(dir)
        self.name = name

        self.outer_md5sum = None
        if use_filter:
            self.outer_md5 = hashlib.md5()
            self.md5filter = IOFilter(self.tempfile, self._md5_callback,
                                      name='%s/md5' % (self.name or 'css'))
            self.fd = self.md5filter.writer()
        else:
            self.outer_md5 = None
            self.fd = self.tempfile

        self.saved = False
        self.finished = False
        try:
            self._write_preamble()
            OutputCoprocess.__init__(self, self._mk_command(), self.fd,
                                     name=self.name,
                                     long_running=long_running)
        except:
            try:
                self.fd.close()
                if self.outer_md5 is not None:
                    self.md5filter.close()
                    self.tempfile.close()
                safe_remove(self.temppath)
            except (IOError, OSError):
                pass
            raise

    def _mk_tempfile_and_path(self, _dir):
        ntf = NamedTemporaryFile(dir=_dir, delete=False)
        return ntf, ntf.name

    def _mk_command(self):
        return None

    def finish(self):
        fin, self.finished = self.finished, True
        if fin:
            return
        # Stop sending output to our coprocess, wait for it to finish
        OutputCoprocess.close(self)

        # Write postamble (the md5filter), close that too
        self.tempfile.seek(0, 2)
        self._write_postamble()

        if self.outer_md5 is None:
            # If we weren't doing the MD5 on the fly, do it now.
            self.calculate_outer_md5sum()
        else:
            # Otherwise, close our coprocess to trigger the calculation
            self.fd.close()
            self.md5filter.close()

        # Reset our tempfile to the beginning for reading
        self.tempfile.seek(0, 0)

    def close(self):
        self.finish()
        self.tempfile.close()

    def save(self, filename, finish=True, mode='wb'):
        if finish:
            self.finish()

        # If no filename, return contents to caller
        if filename is None:
            if not self.saved:
                safe_remove(self.temppath)
                self.saved = True
            self.tempfile.seek(0, 0)
            return self.tempfile.read()

        # 1st save just renames the tempfile
        exists = os.path.exists(filename)
        if (not self.saved and
                (('a' not in mode) or not exists)):
            try:
                if exists:
                    os.remove(filename)
                os.rename(self.temppath, filename)
                self.saved = True
                return
            except (OSError, IOError):
                pass

        # 2nd save (or append to existing) creates a copy
        with open(filename, mode) as out:
            self.save_copy(out)
            if not self.saved:
                safe_remove(self.temppath)
        self.saved = True

    def calculate_outer_md5sum(self):
        self.tempfile.seek(0, 0)
        data = self.tempfile.read(4096)
        outer_md5 = hashlib.md5()
        while data != '':
            # We calculate the MD5 sum as if the data used the CRLF linefeed
            # convention, whether it's actually using that or not.
            outer_md5.update(data.replace('\r', '').replace('\n', '\r\n'))
            data = self.tempfile.read(4096)
        self.outer_md5sum = outer_md5.hexdigest()

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
    EXTRA_DATA = {}
    END_DATA = "-----END MAILPILE ENCRYPTED DATA-----\n"

    # We would prefer AES-256-GCM, but unfortunately openssl does not
    # (yet) behave well with it.
    DEFAULT_CIPHER = "aes-256-cbc"

    def __init__(self, key,
                 dir=None, cipher=None, name=None, header_data=None,
                 long_running=False, use_filter=FILTER_MD5):
        self.cipher = cipher or self.DEFAULT_CIPHER
        self.nonce, self.key = self._nonce_and_mutated_key(key)
        self.header_data = (header_data if header_data is not None
                            else self.EXTRA_DATA)

        ChecksummingStreamer.__init__(self, dir=dir, name=name,
                                      long_running=long_running,
                                      use_filter=use_filter)

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
        return [OPENSSL_COMMAND, "enc", "-e", "-a", "-%s" % self.cipher,
                "-pass", "stdin", "-bufsize", "0"]

    def _write_preamble(self):
        self.fd.write(self.BEGIN_DATA)
        self.fd.write('cipher: %s\n' % self.cipher)
        if self.nonce:
            self.fd.write('nonce: %s\n' % self.nonce)
        self.fd.write(MD5_SUM_PLACEHOLDER + '\n')
        if self.EXTRA_HEADERS:
            self.fd.write(self.EXTRA_HEADERS % self.header_data)
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
                     "Subject: %(subject)s\n")
    EXTRA_DATA = {'subject': 'Mailpile encrypted data'}
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
                 mep_key=None, gpg_pass=None, md5sum=None, cipher=None,
                 name=None, long_running=False):
        self.expected_outer_md5sum = md5sum
        self.expected_inner_md5sum = None
        self.name = name
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
            InputCoprocess.__init__(self, self._mk_command(), self.read_fd,
                                    name=name, long_running=long_running)
            self.startup_lock = None
        except:
            try:
                self.data_filter.join(aborting=True)
                self.data_filter.close()
            except (IOError, OSError):
                pass
            raise

    def _read_filter(self, data):
        if data:
            self.inner_md5.update(data)
        return data

    def close(self):
        self.data_filter.join()
        self.read_fd.close()
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
        elif testing and not self.expected_inner_md5sum:
            print 'No inner MD5 sum expected'
        if (self.expected_outer_md5sum and
                self.expected_outer_md5sum != self.outer_md5.hexdigest()):
            if testing:
                print 'Outer %s != %s' % (self.expected_outer_md5sum,
                                          self.outer_md5.hexdigest())
            if _raise:
                raise _raise('Invalid outer MD5 sum')
            return False
        elif testing and not self.expected_outer_md5sum:
            print 'No outer MD5 sum expected'
        return True

    def _mk_data_filter(self, fd, cb, ecb):
        return IOFilter(fd, cb, error_callback=ecb,
                        name='%s/filter' % (self.name or 'ds'))

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
                    self.gpg_pass.seek(0, 0)
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
            eim = self.expected_inner_md5sum = headers.get('md5sum')
            if eim == '00000000000000000000000000000000':
                self.expected_inner_md5sum = None
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
        return genkey(key or '', nonce)[:32].strip()

    def _mk_command(self):
        if self.state == self.STATE_RAW_DATA:
            return None
        elif self.state == self.STATE_PGP_DATA:
            gpg = [GPG_BINARY, "--batch"]
            if self.gpg_pass:
                gpg.extend(["--no-use-agent", "--passphrase-fd=0"])
            return gpg
        return [OPENSSL_COMMAND, "enc", "-d", "-a", "-%s" % self.cipher,
                "-pass", "stdin"]


class ReadLineIOFilter(IOFilter):
    """
    This is a line-based IOFilter, which can stop when it sees a
    particular marker to hand off processing to others.
    """
    def __init__(self, fd, callback,
                 start_data=None, stop_check=None, **kwargs):
        self.stop_check = stop_check
        self.start_data = start_data
        IOFilter.__init__(self, fd, callback, **kwargs)

    def _copy_loop(self):
        if self.start_data:
            self.info = 'writing'
            self.writing_to.write(self.callback(''.join(self.start_data)))

        self.info = 'reading'
        for data in self.reading_from:
            if self.aborting:
                break
            self.info = 'writing'
            self.writing_to.write(self.callback(data) or '')
            if self.aborting or (self.stop_check and self.stop_check(data)):
                break
            self.info = 'reading'

        if not self.aborting:
            self.info = 'writing'
            self.writing_to.write(self.callback(None) or '')


class PartialDecryptingStreamer(DecryptingStreamer):
    def __init__(self, start_data, *args, **kwargs):
        self.start_data = start_data
        DecryptingStreamer.__init__(self, *args, **kwargs)

    def _mk_data_filter(self, fd, cb, ecb):
        return ReadLineIOFilter(fd, cb,
                                start_data=self.start_data,
                                stop_check=self.EndEncrypted,
                                error_callback=ecb,
                                name='%s/filter' % (self.name or 'ds'))


if __name__ == "__main__":
     # Create a pipe, this tells us which FDs are available next
     fdpair1 = os.pipe()
     for fd in fdpair1:
         os.close(fd)
     def fdcheck(where):
         fdpair2 = os.pipe()
         try:
             for fd in fdpair2:
                 if fd not in fdpair1:
                     print 'Probably have an FD leak at %s!' % where
                     print 'Verify with: lsof -g %s' % os.getpid()
                     import time
                     time.sleep(900)
                     return False
             return True
         finally:
             for fd in fdpair2:
                 os.close(fd)

     bc = [0]
     def counter(data):
         bc[0] += len(data or '')
         return (data or '')

     # Cleanup...
     try:
         os.unlink('/tmp/iofilter.tmp')
     except OSError:
         pass

     print 'Test the IOFilter in write mode'
     with open('/tmp/iofilter.tmp', 'w') as bfd:
         with IOFilter(bfd, counter) as iof:
             iof.writer().write('Hello world!')
     with open('/tmp/iofilter.tmp', 'r') as iof:
         assert(iof.read() == 'Hello world!')
     assert(bc[0] == 12)
     assert(fdcheck('IOFilter in write mode'))

     print 'Test the IOFilter in read mode'
     bc[0] = 0
     with open('/tmp/iofilter.tmp', 'r') as bfd:
         with IOFilter(bfd, counter) as iof:
             data = iof.reader().read()
             assert(data == 'Hello world!')
             assert(bc[0] == 12)
     assert(fdcheck('IOFilter in read mode'))

     print 'Test the IOFilter in incomplete read mode'
     bc[0] = 0
     with open('/dev/urandom', 'r') as bfd:
         with IOFilter(bfd, counter) as iof:
             data = iof.reader().read(4096)
     assert(bc[0] >= 4096)
     assert(len(data) == 4096)
     assert(fdcheck('IOFilter in incomplete read mode'))

     print 'Test the ReadLineIOFilter in incomplete read mode'
     bc[0], daemonlogline = 0, ''
     with open('/etc/passwd', 'r') as bfd:
         with IOFilter(bfd, counter) as iof:
             for line in iof.reader():
                 if 'daemon' in line:
                     daemonlogline = line
                     break
     assert(bc[0] > 80)
     assert('daemon' in daemonlogline)
     assert(fdcheck('ReadLineIOFilter in incomplete read mode'))

     print 'Null decryption test, md5 verification only'
     with open('/tmp/iofilter.tmp', 'rb') as bfd:
         with DecryptingStreamer(bfd,
                                 mep_key='test key',
                                 md5sum='86fb269d190d2c85f6e0468ceca42a20'
                                 ) as ds:
             assert('Hello world!' == ds.read())
             assert(ds.verify(testing=True))
     assert(fdcheck('Decrypting test, md5 verification'))

     for delim in (True, False):
         for filter_md5 in (True, False):
             print ('Encryption test, delim=%s, filter_md5=%s'
                    ) % (delim, filter_md5)

             data = 'Hello world! This is great!\nHooray, lalalalla!\n'
             with EncryptingStreamer('test key', dir='/tmp',
                                     delimited=delim,
                                     use_filter=filter_md5) as es:
                 es.write(data)
                 es.finish()
                 fn = '/tmp/%s.aes' % es.outer_md5sum
                 with open(fn, 'wb') as fd:
                     fd.write('junk')  # Make sure overwriting works
                 es.save(fn)
             assert(fdcheck('Encrypted data, delimited=%s' % delim))

             print 'Decryption test, delim=%s' % delim
             with open(fn, 'rb') as bfd:
                 with DecryptingStreamer(bfd,
                                         mep_key='test key',
                                         md5sum=es.outer_md5sum) as ds:
                     new_data = ds.read()
                     assert(ds.close() == 0)
                     assert(data == new_data)
                     assert(ds.verify(testing=True))
             assert(fdcheck('Decrypting test, delimited=%s' % delim))

         # Cleanup
         os.unlink(fn)

     os.unlink('/tmp/iofilter.tmp')
     assert(fdcheck('All done'))
