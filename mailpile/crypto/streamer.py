#
# This is code to stream data to or from encrypted storage. If the invoking
# code us correctly written, it should be able to work with data far in
# excess of available RAM.
#
# The storage format "Mailpile Encrypted Storage" takes pains to be either
# valid RFC2822 (for direct storage in IMAP servers) or a delimited format
# similar to OpenPGP armour. Files must use one style or the other, not a
# mixture of both.
#
# By default this code prefers to use AES-128-CTR. This cipher is malleable,
# which means that data corruption is localized and does not affect the
# rest of the file (unlike CBC, for example). In order to detect corruption
# or attacks, a SHA256-based MAC can be calculated on the plaintext or
# the ciphertext (or both). When verifying the plaintext, the sum is written
# into the header of the file, when verifying the ciphertext the sum is
# expected to be stored somewhere else.
#
##############################################################################
# FIXME:
#
# The decryption routines here support "MEP v1" which used AES-256-CBC
# and MD5 sums (not a proper MAC).
#
# Very few people have data in this format, it would be nice to just
# delete all of that code once users have had time to migrate. But
# for that to happen there needs to be a migration that finds old data
# and re-encrypts it automatically. We don't have that yet!
#
##############################################################################
#
import base64
import os
import hashlib
import sys
import re
import threading
import time
import traceback
from datetime import datetime
from tempfile import NamedTemporaryFile

import mailpile.platforms
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.crypto.gpgi import GPG_BINARY
from mailpile.safe_popen import Popen, PIPE
from mailpile.util import CryptoLock, safe_remove, safe_assert
from mailpile.util import sha512b64 as genkey

from mailpile.crypto.aes_utils import getrandbits
from mailpile.crypto.aes_utils import aes_ctr_encryptor, aes_ctr_decryptor

PREFERRED_CIPHER = 'aes-128-ctr'


# This is for backwards compatibility with v1 of our storage format; we have
# since corrected our silliness and v2 uses a SHA256-based MAC.
LEN_MD5_SUM = len(hashlib.md5('testing').hexdigest())
MD5_SUM_FORMAT = 'md5sum: %s'
MD5_SUM_PLACEHOLDER = MD5_SUM_FORMAT % ('0' * LEN_MD5_SUM)
MD5_SUM_RE = re.compile('(?m)^' + MD5_SUM_FORMAT % (r'[^\n]+',))

LEN_SHA_256 = len(hashlib.sha256('testing').hexdigest())
SHA_256_FORMAT = 'sha256: %s'
SHA_256_PLACEHOLDER = SHA_256_FORMAT % ('0' * LEN_SHA_256)
SHA_256_RE = re.compile('(?m)^' + SHA_256_FORMAT % (r'[^\n]+',))

BLANK_LINE_RE = re.compile('^\s*$')


# This gets populated with all the obsolete data we see during
# decryption, the app can check for this to trigger migrations.
PREFERRED_FORMAT = 'v2:%s' % PREFERRED_CIPHER
DETECTED_OBSOLETE_FORMATS = set([])

OPENSSL_COMMAND = mailpile.platforms.GetDefaultOpenSSLCommand()

# FIXME: Why does Windows require this? Move to mailpile.platforms when
#        we understand the underlying issue.
if sys.platform.startswith("win"):
    FILTER_MD5 = True
else:
    FILTER_MD5 = False


def mac_sha256(key, data):
    mac = hashlib.sha256(key or '')
    mac.update(data or '')
    return mac.hexdigest()


class IOFilter(threading.Thread):
    """
    This class will wrap a filehandle and spawn a background thread to
    filter either the input or output.
    """
    BLOCKSIZE = 16 * 1024

    def __init__(self, fd, callback,
                 name=None, error_callback=None, blocksize=None):
        threading.Thread.__init__(self)
        self.callback = callback
        self.error_callback = error_callback
        self.exc_info = None

        self.blocksize = blocksize or self.BLOCKSIZE
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
            data = self.reading_from.read(self.blocksize)
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


class ReadLineIOFilter(IOFilter):
    """
    This is a line-based IOFilter, which can stop when it sees a
    particular marker to hand off processing to others.
    """
    def __init__(self, fd, callback,
                 start_data=None, stop_check=None, **kwargs):
        self.stop_check = stop_check
        self.buffered = list(start_data)
        self.buf_bytes = sum(len(s) for s in start_data)
        IOFilter.__init__(self, fd, callback, **kwargs)

    def _maybe_flush(self, eof=False):
        if eof or (self.buf_bytes >= self.blocksize):
            i, self.info = self.info, 'writing'
            self.writing_to.write(self.callback(''.join(self.buffered)))
            self.buffered = []
            self.buf_bytes = 0
            if eof:
                self.writing_to.write(self.callback(None) or '')
            self.info = i

    def _copy_loop(self):
        self.info = 'reading'
        for line in self.reading_from:
            if self.aborting: return

            self.buffered.append(line)
            if not re.match(BLANK_LINE_RE, line):
                # Don't count blank lines
                self.buf_bytes += len(line)
                self._maybe_flush()

            if self.aborting or (self.stop_check and self.stop_check(line)):
                break

        if not self.aborting:
            self._maybe_flush(eof=True)


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

    def flush(self):
        return self._fd.flush()


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
    This checksums and streams data to a named temporary file on disk, which
    can then be read back or linked to a final location.
    """
    FILTER_BLOCKSIZE = None

    def __init__(self, dir=None, name=None, long_running=False,
                       use_filter=FILTER_MD5):
        self.tempfile, self.temppath = self._mk_tempfile_and_path(dir)
        self.name = name

        self.outer_sha256 = None
        if use_filter:
            self.outer_sha = hashlib.sha256()
            self.shafilter = IOFilter(self.tempfile, self._sha256_callback,
                                      name='%s/sha256' % (self.name or 'css'),
                                      blocksize=self.FILTER_BLOCKSIZE)
            self.fd = self.shafilter.writer()
        else:
            self.outer_sha = None
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
                if self.outer_sha is not None:
                    self.shafilter.close()
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

        # Write postamble (the shafilter), close that too
        self.tempfile.seek(0, 2)
        self._write_postamble()

        if self.outer_sha is None:
            # If we weren't doing the SHA256 on the fly, do it now.
            self.calculate_outer_sha256()
        else:
            # Otherwise, close our coprocess to trigger the calculation
            self.fd.close()
            self.shafilter.close()

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

    def calculate_outer_sha256(self):
        self.tempfile.seek(0, 0)
        data = self.tempfile.read(4096)
        self.outer_sha = outer_sha = hashlib.sha256()
        while data != '':
            # We calculate the MD5 sum as if the data used the CRLF linefeed
            # convention, whether it's actually using that or not.
            outer_sha.update(data.replace('\r', '').replace('\n', '\r\n'))
            data = self.tempfile.read(4096)
        self.outer_sha256 = outer_sha.hexdigest()

    def outer_mac_sha256(self):
        # Hm, we have no key, so this is a bit pointless
        return mac_sha256('', self.outer_sha.digest())

    def save_copy(self, ofd):
        self.tempfile.seek(0, 0)
        data = self.tempfile.read(4096)
        while data != '':
            ofd.write(data)
            data = self.tempfile.read(4096)

    def _sha256_callback(self, data):
        if data is None:
            # EOF...
            self.outer_sha256 = self.outer_sha.hexdigest()
            return ''
        else:
            # We calculate the MD5 sum as if the data used the CRLF linefeed
            # convention, whether it's actually using that or not.
            self.outer_sha.update(data.replace('\r', '').replace('\n', '\r\n'))
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
    EXTRA_HEADERS = "X-Mailpile-Encrypted-Data: v2\n"
    EXTRA_DATA = {}
    END_DATA = "-----END MAILPILE ENCRYPTED DATA-----\n"

    PREFERRED_CIPHER = None
    FILTER_BLOCKSIZE = 19 * 3 * 16  # Make AES and Base64 happy

    def __init__(self, key,
                 dir=None, cipher=None, name=None, header_data=None,
                 long_running=False, use_filter=FILTER_MD5):
        self.cipher = cipher or self.PREFERRED_CIPHER or PREFERRED_CIPHER
        self.nonce, self.key = self._nonce_and_mutated_key(key)
        self.header_data = (header_data if header_data is not None
                            else self.EXTRA_DATA)

        self.encode_buffer = ''
        if self.cipher == 'aes-128-ctr':
            self.encryptor = aes_ctr_encryptor(self.key, self.nonce)
            self.encoder = base64.encodestring
            self.encode_batches = self.FILTER_BLOCKSIZE
        elif self.cipher == 'none':
            self.encryptor = lambda d: d
            self.encoder = base64.encodestring
            self.encode_batches = self.FILTER_BLOCKSIZE
        elif self.cipher == 'broken':
            self.encoder = self.encryptor = lambda d: d
            self.encode_batches = None
        else:
            self.encoder = self.encryptor = None
            self.encode_batches = None

        ChecksummingStreamer.__init__(self, dir=dir, name=name,
                                      long_running=long_running,
                                      use_filter=use_filter)

        # These are necessary for two reasons:
        #
        # 1. Prevent the public checksum from revealing what was encrypted.
        # 2. When using malleable encryption modes (such as CTR), make it
        #    infeasable for attackers to generate a checksum that validates
        #    modified data.
        #
        # As this is for data at rest, we are not particularly concerned with
        # oracle attacks. If an attacker has access to your mailpile on disk
        # while it is in use (so they can inject new messages), there are
        # other attacks which are both easier and more severe.
        #
        self.inner_sha256 = None
        self.inner_sha = hashlib.sha256()
        self.inner_sha.update(self.key)
        self.inner_sha.update(self.nonce or '')

        self._send_key()

    def _write_filter(self, data):
        if data:
            self.inner_sha.update(data)
        if self.encryptor and (data or self.encode_buffer):
            if self.encode_batches:
                eof = not data
                if data: self.encode_buffer += data
                data = ''
                for i in (512, 128, 8, 1):
                    batch = i * self.encode_batches
                    while eof or (len(self.encode_buffer) >= batch):
                        d = self.encode_buffer[:batch]
                        b = self.encode_buffer[batch:]
                        self.encode_buffer = b
                        data += self.encoder(self.encryptor(d))
                        eof = False
        return data

    def _sha256_callback(self, data):
        return ChecksummingStreamer._sha256_callback(self, data)

    def outer_mac_sha256(self):
        return mac_sha256(self.key or '', self.outer_sha.digest())

    def write_pad_and_flush(self, data, pad=' '):
        if self.encryptor and (data or self.encode_buffer):
            if self.encode_batches:
                remainder = len(self.encode_buffer) + len(data)
                remainder %= self.encode_batches
                padding = self.encode_batches - remainder
                data += (pad * padding)
        self.write(data)
        self.flush()

    def finish(self, *args, **kwargs):
        if not self.finished:
            while self.encode_buffer:
                self.write('')
            rv = ChecksummingStreamer.finish(self, *args, **kwargs)
            self._write_inner_sha256()
            return rv
        else:
            return ChecksummingStreamer.finish(self, *args, **kwargs)

    def _write_inner_sha256(self):
        if not self.inner_sha256:
            self.inner_sha256 = mac_sha256(self.key, self.inner_sha.digest())
            pos = self.tempfile.tell()
            self.tempfile.seek(0, 0)
            old_data = self.tempfile.read(4096)

            sha_256_header = SHA_256_FORMAT % (self.inner_sha256, )
            new_data = re.sub(SHA_256_RE, sha_256_header, old_data)
            if old_data != new_data:
                self.tempfile.seek(0, 0)
                self.tempfile.write(new_data)

            self.tempfile.seek(pos, 0)

    def _nonce_and_mutated_key(self, key):
        # This generates a nonce which may be used as a salt, IV, or
        # counter-prefix depending the algorithm and mode in use. We
        # also use it to derive a mutated key for each message, thus
        # reducing the risks of the (key, iv) pairs ever repeating even
        # if a mistake is made somewhere else.
        nonce = '%32.32x' % getrandbits(32 * 4)
        return nonce, genkey(key, nonce)[:32].strip()

    def _send_key(self):
        # We talk directly to the underlying FD, to avoid corrupting the
        # inner MD5 sum (calculated using the _write_filter() above).
        if not self.encryptor:
            self._fd.write('%s\n' % self.key)

    def _mk_command(self):
        if self.encryptor:
            return None
        return [OPENSSL_COMMAND, "enc", "-e", "-a", "-%s" % self.cipher,
                "-pass", "stdin", "-bufsize", "0"]

    def _write_preamble(self):
        self.fd.write(self.BEGIN_DATA)
        self.fd.write('cipher: %s\n' % self.cipher)
        if self.nonce:
            self.fd.write('nonce: %s\n' % self.nonce)
        self.fd.write(SHA_256_PLACEHOLDER + '\n')
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
    BEGIN_DATA = "X-Mailpile-Encrypted-Data: v2\n"
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
    BEGIN_MED = "-----BEGIN MAILPILE ENCRYPTED DATA-----"
    BEGIN_MED2 = "X-Mailpile-Encrypted-Data: "
    END_MED = "-----END MAILPILE ENCRYPTED DATA-----"
    PREFERRED_CIPHER = None

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
        return (line.startswith(cls.BEGIN_MED) or
                line.startswith(cls.BEGIN_MED2) or
                line.startswith(cls.BEGIN_PGP))

    @classmethod
    def EndEncrypted(cls, line):
        return (line.startswith(cls.END_MED) or
                line.startswith(cls.END_PGP))

    def __init__(self, fd,
                 mep_key=None, gpg_pass=None, sha256=None, cipher=None,
                 name=None, long_running=False, gpgi=None):
        self.expected_outer_sha256 = sha256
        self.expected_inner_sha256 = None
        self.expected_inner_md5sum = None
        self.name = name
        self.outer_sha = hashlib.sha256()
        self.inner_sha = hashlib.sha256()
        self.inner_md5 = hashlib.md5()
        self.cipher = self.PREFERRED_CIPHER or PREFERRED_CIPHER
        self.state = self.STATE_BEGIN
        self.buffered = ''
        self.mep_version = None
        self.mep_mutated = None
        self.mep_key = mep_key
        self.gpg_pass = gpg_pass
        self.gpgi = gpgi
        self.decryptor = None
        self.decoder = None
        self.decoder_data_bytes = 0  # Not counting white-space

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
            if self.expected_inner_sha256:
                self.inner_sha.update(data)
            if self.expected_inner_md5sum:
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

        if self.expected_inner_sha256:
            mac = mac_sha256(self.mep_mutated, self.inner_sha.digest())
            if self.expected_inner_sha256 != mac:
                if testing:
                    print 'Inner %s != %s' % (self.expected_inner_sha256, mac)
                if _raise:
                    raise _raise('Invalid inner SHA256')
                return False
        elif self.expected_inner_md5sum:
            if self.expected_inner_md5sum != self.inner_md5.hexdigest():
                if testing:
                    print 'Inner %s != %s' % (self.expected_inner_md5sum,
                                              self.inner_md5.hexdigest())
                if _raise:
                    raise _raise('Invalid inner MD5 sum')
                return False
        elif testing and not self.expected_inner_md5sum:
            print 'No inner MD5 sum or SHA256 expected'

        if self.expected_outer_sha256:
            mac = mac_sha256(self.mep_mutated, self.outer_sha.digest())
            if self.expected_outer_sha256 != mac:
                if testing:
                    print 'Outer %s != %s' % (self.expected_outer_sha256, mac)
                if _raise:
                    raise _raise('Invalid outer SHA256')
                return False
        elif testing and not self.expected_outer_sha256:
            print 'No outer SHA256 expected'
        return True

    def _mk_data_filter(self, fd, cb, ecb):
        return IOFilter(fd, cb, error_callback=ecb,
                        name='%s/filter' % (self.name or 'ds'))

    def _read_data(self, data):
        def process(data):
            if self.decryptor is not None:
                eof = not data
                if self.decoder_data_bytes and data:
                    self.buffered += ''.join([c for c in data if c not in
                                              (' ', '\t', '\r', '\n')])
                else:
                    self.buffered += (data or '')
                data = ''
                for i in (256, 64, 8, 1):
                    batch = max(1, i * self.decoder_data_bytes)
                    while eof or (len(self.buffered) >= batch):
                        if self.decoder_data_bytes:
                            d = self.buffered[:batch]
                            b = self.buffered[batch:]
                            self.buffered = b
                        else:
                            d, self.buffered = self.buffered, ''
                        try:
                            data += self.decryptor(self.decoder(d))
                            eof = False
                        except TypeError:
                            raise IOError('%s: Bad data, failed to decode'
                                          % self.name)
            return (data or '')

        if data is None:
            # EOF!
            if self.state in (self.STATE_BEGIN, self.STATE_HEADER):
                self.state = self.STATE_RAW_DATA
                self.startup_lock.release()
                data, self.buffered = self.buffered, ''
                return process(data) + process(None)
            return process(None)

        if self.expected_outer_sha256:
            # The outer MD5 sum is calculated over all data, but with any
            # CRLF sequences normalized to only LF and the sha256 header
            # itself replaced with a placeholder.
            if self.state in (self.STATE_BEGIN, self.STATE_HEADER):
                sum_data = re.sub(MD5_SUM_RE, MD5_SUM_PLACEHOLDER,
                                  re.sub(SHA_256_RE, SHA_256_PLACEHOLDER, data))
            else:
                sum_data = data
            sum_data = sum_data.replace('\r', '').replace('\n', '\r\n')
            self.outer_sha.update(sum_data)

        if self.state in (
               self.STATE_RAW_DATA, self.STATE_PGP_DATA, self.STATE_ONLY_DATA):
            return process(data)

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
            # State: header and data have been set, header is complete.
            self.buffered = ''

            headers = dict([l.split(': ', 1) for l in headlines if ': ' in l])
            nonce = headers.get('nonce', '')
            self.mep_mutated = self._mutate_key(self.mep_key, nonce)
            self.mep_version = headers.get('X-Mailpile-Encrypted-Data', 'v1')
            self.cipher = headers.get('cipher', self.cipher)

            data_fmt = '%s:%s' % (self.mep_version, self.cipher)
            if data_fmt != PREFERRED_FORMAT:
                DETECTED_OBSOLETE_FORMATS.add(data_fmt)

            eim = self.expected_inner_md5sum = headers.get('md5sum')
            if eim and eim == ('0' * LEN_MD5_SUM):
                self.expected_inner_md5sum = None
            if self.expected_inner_md5sum:
                self.inner_md5.update(self.mep_mutated)
                self.inner_md5.update(nonce)

            eis = self.expected_inner_sha256 = headers.get('sha256')
            if eis and eis == ('0' * LEN_SHA_256):
                self.expected_inner_sha256 = None
            if self.expected_inner_sha256:
                self.inner_sha.update(self.mep_mutated)
                self.inner_sha.update(nonce)

            if self.buffered.startswith(self.BEGIN_MED2):
                self.state = self.STATE_ONLY_DATA
            else:
                self.state = self.STATE_DATA

            if self.cipher == 'aes-128-ctr':
                self.decryptor = aes_ctr_decryptor(self.mep_mutated, nonce)
                self.decoder = base64.b64decode
                # Decode data in chunks this big (multiple of 4 and 16);
                # guarantees workable chunks for both AES-CTR and base64.
                self.decoder_data_bytes = 32 * 1024
            elif self.cipher == 'none':
                self.decryptor = lambda d: d
                self.decoder = base64.b64decode
                self.decoder_data_bytes = 32 * 1024
            elif self.cipher == 'broken':
                self.decryptor = lambda d: d
                self.decoder = lambda d: d
                self.expected_inner_md5sum = None
                self.expected_inner_sha256 = None
            else:
                self.decryptor = None
                data = '\n'.join((self.mep_mutated, data))

            self.startup_lock.release()

        if self.state == self.STATE_ONLY_DATA:
            return process(data)

        if self.state == self.STATE_DATA:
            for delim in (self.END_MED, self.END_PGP):
                if delim in data:
                    for pf in ('\r\n', '\n', ''):
                        if pf + delim in data:
                            data = data.split(pf + delim, 1)[0]
                            self.state = self.STATE_END
                            return process(data)
            return process(data)

        # Error, end and unknown states...
        return ''

    def _mutate_key(self, key, nonce):
        return genkey(key or '', nonce)[:32].strip()

    def _mk_command(self):
        if self.state == self.STATE_RAW_DATA:
            return None
        elif self.decryptor is not None:
            return None
        elif self.state == self.STATE_PGP_DATA:
            safe_assert(self.gpgi is not None)
            if self.gpg_pass:
                return self.gpgi.common_args(will_send_passphrase=True)
            else:
                return self.gpgi.common_args()
        return [OPENSSL_COMMAND, "enc", "-d", "-a", "-%s" % self.cipher,
                "-pass", "stdin"]


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
    import random  # See! Not in the main module!
    import StringIO

    LEGACY_TEST_KEY = 'test key'
    LEGACY_PLAINTEXT = 'Hello world! This is great!\nHooray, lalalalla!\n'
    LEGACY_TEST_1 = """\
X-Mailpile-Encrypted-Data: v1
cipher: aes-256-cbc
nonce: SEefbOfc9UQmZeWWGWQMrb0n6czXY2Uv
md5sum: b07d3ed58b79a69ab5496cffcab5d878
From: Mailpile <encrypted@mailpile.is>
Subject: Mailpile encrypted data

U2FsdGVkX18zVuMErdegtGziWDLhSvNRb7YRRxmYKMmygI1H3bp+mXffToii6lGB
Z7Vlo78g20D8NAO6dpJfmA==
"""
    LEGACY_TEST_2 = """\
-----BEGIN MAILPILE ENCRYPTED DATA-----
cipher: aes-256-cbc
nonce: SB+fmmM72oFpf/FO4wnaHhFBvhgzpbwW
md5sum: 90dfb2850da49c8a6027415521dadb3c

U2FsdGVkX19U8G7SKp8QygUusdHZThlrLcI04+jZ9U5kwfsw7bJJ2721dwgIpCUh
3wpQjsYtFF2dcKBjrG7xyw==

-----END MAILPILE ENCRYPTED DATA-----
"""

    # Do this before checking for fd leaks, as it may open up /dev/urandom
    # and keep it open.
    b = getrandbits(128)

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

    print 'Null decryption test, sha256 verification only'
    outer_mac_sha256 = '7982970534e089b839957b7e174725ce1878731ed6d700766e59cb16f1c25e27'
    with open('/tmp/iofilter.tmp', 'rb') as bfd:
        with DecryptingStreamer(bfd,
                                mep_key='test key',
                                sha256=outer_mac_sha256
                                ) as ds:
            assert('Hello world!' == ds.read())
            assert(ds.verify(testing=True))
    assert(fdcheck('Decrypting test, sha256 verification'))

    print 'Legacy (MEP v1) decryption test'
    for legacy in (LEGACY_TEST_1, LEGACY_TEST_2):
        lfd = StringIO.StringIO(legacy)
        with PartialDecryptingStreamer([], lfd,
                                       mep_key=LEGACY_TEST_KEY) as ds:
            plaintext = ''
            d = ds.read(9999)
            while d:
                plaintext += d
                d = ds.read(random.randint(10, 1024))
            assert(ds.close() == 0)
            assert(ds.verify(testing=True))
            assert(plaintext == LEGACY_PLAINTEXT)

    for cipher in ('none', 'broken', 'aes-128-ctr', 'aes-256-cbc'):
      for filter_sha256 in (True, False):
        for delim in (True, False):
            print ('Encryption test, cipher=%s, delim=%s, filter_sha256=%s'
                   ) % (cipher, delim, filter_sha256)

            fn = '/tmp/enc-%s-%s-%s.tmp' % (cipher, delim, filter_sha256)
            with open(fn, 'wb') as fd:
                fd.write('junk')  # Make sure overwriting works

            t0 = time.time()
            mul = 123400
            data = 'Hello world! This is great!\nHooray, lalalalla!\n' * mul
            parts = [(data, 'wb')]
            if delim:
                for i in (2, 5, 10, mul // 10, mul):
                    more = 'part two, yeaaaah\n' * (mul // i)
                    parts.append((more, 'ab'))
                    data += more
            encrypted = []
            for part, mode in parts:
                with EncryptingStreamer('test key', dir='/tmp',
                                        delimited=delim,
                                        cipher=cipher,
                                        use_filter=filter_sha256) as es:
                    d = part
                    while d:
                        i = min(len(d), random.randint(10, max(11, len(d))))
                        es.write(d[:i])
                        d = d[i:]
                    es.finish()
                    es.save(fn, mode=mode)
                    encrypted.append(es.outer_mac_sha256())
            assert(fdcheck('Encrypted data, delimited=%s' % delim))

            t1 = time.time()
            print 'Decryption test, delim=%s' % delim
            with open(fn, 'rb') as bfd:
                new_data = ''
                for ms in encrypted:
                    if delim:
                        ds = PartialDecryptingStreamer(
                            [], bfd, mep_key='test key', sha256=ms)
                    else:
                        ds = DecryptingStreamer(
                            bfd, mep_key='test key', sha256=ms)
                    with ds:
                        d = ds.read(9999)
                        while d:
                            new_data += d
                            d = ds.read(random.randint(10, 102400))
                        assert(ds.close() == 0)
                        assert(ds.verify(testing=True))
                try:
                    assert(data == new_data)
                except:
                    print 'OLD %d bytes vs. NEW %d bytes: \n%s\n' % (
                        len(data), len(new_data), new_data[-100:])
                    raise
            assert(fdcheck('Decrypting test, delimited=%s' % delim))
            t2 = time.time()
            print (' => Elapsed: %.3fs + %.3fs = %.3fs (%.2f MB/s)'
                   % (t1-t0, t2-t1, t2-t0, len(new_data)/(1024*1024*(t2-t0))))

        # Cleanup
        os.unlink(fn)
      print

    assert(len(DETECTED_OBSOLETE_FORMATS) > 0)
    print 'Obsolete formats detected: %s' % DETECTED_OBSOLETE_FORMATS

    os.unlink('/tmp/iofilter.tmp')
    assert(fdcheck('All done'))
