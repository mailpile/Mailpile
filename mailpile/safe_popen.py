from __future__ import print_function
#
# This module implements a safer version of Popen and a safe wrapper around
# os.pipe(), to avoid deadlocks caused by file descriptors being shared
# between processes and threads.
#
# The subprocess.Popen semantics are changed in the following ways:
#
#   * close_fds=True is mandatory on all Unix operating systems
#   * keep_open=[] can be passed to explicitly keep other FDs open
#   * preexec_fn will call os.setpgrp on all Unix operating systems
#
# On Windows, close_fds and preexec_fn are unavailable in Python 2.7, so
# instead we do the following:
#
#   * close_fds=False, most of the time
#   * creationflags=CREATE_NEW_PROCESS_GROUP is set
#   * subprocesses hold a global lock for as long as is "reasonable"
#
# The os.pipe() wrapper simply makes sure pipe file handles are wrapped
# in Python file objects so Python's garbage collector and intelligent
# handling of close() are taken advantage of, and adds a couple of
# convenience functions and properties to make piping code more readable.
#
import os
import subprocess
import sys
import thread
import threading

import mailpile.platforms


Unsafe_Popen = subprocess.Popen
PIPE = subprocess.PIPE

SERIALIZE_POPEN_STRICT = True
SERIALIZE_POPEN_ALWAYS = False
SERIALIZE_POPEN_LOCK = threading.Lock()

THREAD_LOCAL = threading.local()


def PresetSafePopenArgs(**kwargs):
    """
    Make it possible to preset Popen arguments, for injecting tweaks into
    third-party code. We do this using thread-local data, so as to avoid
    the need for yet another lock.
    """
    if hasattr(THREAD_LOCAL, 'preset_args'):
        THREAD_LOCAL.preset_args.append(kwargs)
    else:
        THREAD_LOCAL.preset_args = [kwargs]


class Safe_Pipe(object):
    """
    Creates a pipe consisting of two Python file objects.

    This prevents leaks and prevents weird thread bugs cuased by closing
    the underlying FD more than once, because Python's objects are smart
    (as opposed to dumb ints).
    """
    def __init__(self):
        p = os.pipe()
        self.read_end = os.fdopen(p[0], 'r')
        self.write_end = os.fdopen(p[1], 'w')

    def write(self, *args, **kwargs):
        return self.write_end.write(*args, **kwargs)

    def read(self, *args, **kwargs):
        return self.read_end.read(*args, **kwargs)

    def close(self):
        self.read_end.close()
        self.write_end.close()


class Safe_Popen(Unsafe_Popen):
    def _preset_args(self):
        if hasattr(THREAD_LOCAL, 'preset_args') and THREAD_LOCAL.preset_args:
            return THREAD_LOCAL.preset_args.pop(-1)
        else:
            return {}

    def __init__(self, args, bufsize=0,
                             executable=None,
                             stdin=None,
                             stdout=None,
                             stderr=None,
                             preexec_fn=None,
                             close_fds=None,
                             shell=False,
                             cwd=None,
                             env=None,
                             universal_newlines=False,
                             startupinfo=None,
                             creationflags=None,
                             keep_open=None,
                             long_running=False):

        self._internal_fds = []

        # Windows-work around: Console Handles can't be inherited, so if no
        # source is passed, simulate stdin as a closed pipe. Not ideal, but
        # stops pythonw crashing.
        #
        # See: https://bugs.python.org/issue3905
        #
        if stdin is None:
            stdin = open(os.devnull, 'r')
            self._internal_fds.append(stdin)

        if stdout is None:
            stdout = open(os.devnull, 'w')
            self._internal_fds.append(stdout)

        if stderr is None:
            stderr = open(os.devnull, 'w')
            self._internal_fds.append(stderr)

        # This lets us inject Popen args into libraries
        preset = self._preset_args()
        if preset: print('PRESET[%s]: %s' % (args, preset))
        cwd = preset.get('cwd', cwd)
        env = preset.get('env', env)
        stdin = preset.get('stdin', stdin)
        stdour = preset.get('stdout', stdout)
        stderr = preset.get('stderr', stderr)
        bufsize = preset.get('bufsize', bufsize)
        close_fds = preset.get('close_fds', close_fds)
        executable = preset.get('executable', executable)
        long_running = preset.get('long_running', long_running)

        # Set our default locking strategy
        self._SAFE_POPEN_hold_lock = SERIALIZE_POPEN_ALWAYS

        # Raise assertions if people try to explicitly use the API in
        # an unsafe way.  These all have different meanings on differnt
        # platforms, so we don't allow the programmer to configure them
        # at all.
        if SERIALIZE_POPEN_STRICT:
            if not ((preexec_fn is None) and
                    (close_fds is None) and
                    (startupinfo is None) and
                    (creationflags is None)):
                raise AssertionError("Unsafe use of POpen API!")

        # The goal of the following sections is to achieve two things:
        #
        #    1. Prevent file descriptor leaks from causing deadlocks
        #    2. Prevent signals from propagating
        #
        if mailpile.platforms.WindowsPopenSemantics():
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # 2.
            if (stdin is not None or
                    stdout is not None or
                    stderr is not None or
                    keep_open):
                close_fds = False
#               self._SAFE_POPEN_hold_lock = True  # 1.
            else:
                close_fds = True  # 1.

        else:
            creationflags = 0
            if keep_open:
                # Always leave stdin, stdout and stderr alone so we don't
                # end up with different assumptions from subprocess.Popen.
                keep_open.extend([0, 1, 2])
                for i in range(0, len(keep_open)):
                    if hasattr(keep_open[i], 'fileno'):
                        keep_open[i] = keep_open[i].fileno()
                close_fds = False
            else:
                close_fds = True  # 1.

            def pre_exec_magic():
                try:
                    os.setpgrp()  # 2.
                except (OSError, NameError):
                    pass
                # FIXME: some platforms may give us more FDs...
                if not close_fds:
                    for i in set(range(0, 1024)) - set(keep_open):
                        try:
                            os.close(i)
                        except OSError:
                            pass

            preexec_fn = pre_exec_magic

        if self._SAFE_POPEN_hold_lock:
            SERIALIZE_POPEN_LOCK.acquire()
        try:
            Unsafe_Popen.__init__(self, args,
                                  bufsize=bufsize,
                                  executable=executable,
                                  stdin=stdin,
                                  stdout=stdout,
                                  stderr=stderr,
                                  preexec_fn=preexec_fn,
                                  close_fds=close_fds,
                                  shell=shell,
                                  cwd=cwd,
                                  env=env,
                                  universal_newlines=universal_newlines,
                                  startupinfo=startupinfo,
                                  creationflags=creationflags)
        except:
            self._SAFE_POPEN_unlock()
            raise

        if long_running:
            self._SAFE_POPEN_unlock()

    def _SAFE_POPEN_unlock(self):
        if self._SAFE_POPEN_hold_lock:
            self._SAFE_POPEN_hold_lock = False
            try:
                SERIALIZE_POPEN_LOCK.release()
            except thread.error:
                pass

    def communicate(self, *args, **kwargs):
        rv = Unsafe_Popen.communicate(self, *args, **kwargs)
        self._SAFE_POPEN_unlock()
        return rv

    def wait(self, *args, **kwargs):
        rv = Unsafe_Popen.wait(self, *args, **kwargs)
        self._SAFE_POPEN_unlock()
        return rv

    def __del__(self):
        for handle in self._internal_fds:
            handle.close()
        if Unsafe_Popen is not None:
            Unsafe_Popen.__del__(self)
        self._SAFE_POPEN_unlock()


# This is a vain attempt to monkeypatch, whether it works or not will
# depend on module load order.
def MakePopenUnsafe():
    subprocess.Popen = Unsafe_Popen


def MakePopenSafe():
    THREAD_LOCAL.preset_args = []
    subprocess.Popen = Safe_Popen
    return Safe_Popen

Popen = MakePopenSafe()
