"""
This module tries to centralize most of the platform-specific code in use by
Mailpile. If you find yourself checking which platform the app runs on, adding
a function here instead is probably The Right Thing.
"""
import copy
import os
import subprocess
import sys


# This is a cache of discovered binaries and their paths.
BINARIES = {}


# These are the binaries we want, and the test we use to detect whether
# they are available/working.
BINARIES_WANTED = {
    'GnuPG':    ['gpg', '--version'],
    'GnuPG/dm': ['dirmngr', '--version'],
    'GnuPG/ga': ['gpg-agent', '--version'],
    'OpenSSL':  ['openssl', 'version'],
    'Tor':      ['tor', '--version']}


def _assert_file_exists(path):
    if not os.path.exists(path):
        raise OSError('Not found: %s' % path)
    return path


def DetectBinaries(
        which=None, use_cache=True, preferred={}, skip=None, _raise=None):
    import mailpile.util
    import mailpile.safe_popen
    import traceback

    global BINARIES
    if which and use_cache:
        if which in BINARIES:
            return BINARIES[which]
        env_bin = os.getenv('MAILPILE_%s' % which.upper(), '')
        if env_bin:
            BINARIES[which] = env_bin
            return env_bin

    if skip is None:
        skip = os.getenv('MAILPILE_IGNORE_BINARIES', '').split()

    def _run_bintest(bt):
        p = mailpile.safe_popen.Popen(bt,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
        return p.communicate()

    for binary, binary_test in BINARIES_WANTED.iteritems():
        if binary in skip:
            continue
        if (which is None) or (binary == which):
            if preferred.get(binary):
                binary_test = copy.copy(binary_test)
                binary_test[0] = preferred[binary]
            else:
                env_bin = os.getenv('MAILPILE_%s' % binary.upper(), '')
                if env_bin:
                    BINARIES[binary] = env_bin
                    continue
            try:
                mailpile.util.RunTimed(5.0, _run_bintest, binary_test)
                BINARIES[binary] = binary_test[0]
                if (not os.path.dirname(BINARIES[binary])
                        and not sys.platform.startswith('win')):
                    try:
                        path = subprocess.check_output(['which',
                                                        BINARIES[binary]])
                        if path:
                            BINARIES[binary] = path.strip()
                    except (OSError, subprocess.CalledProcessError):
                        pass
            except (OSError, subprocess.CalledProcessError, mailpile.util.TimedOut):
                if binary in BINARIES:
                    del BINARIES[binary]

    if which:
        if _raise not in (None, False):
            if not BINARIES.get(which):
                raise _raise('%s not found' % which)
        return BINARIES.get(which)

    elif _raise not in (None, False):
        for binary, binary_test in BINARIES_WANTED.iteritems():
            if binary in skip:
                continue
            if not BINARIES.get(binary):
                raise _raise('%s not found' % binary)

    return BINARIES


def GetDefaultGnuPGCommand(_raise=OSError):
    return DetectBinaries(which='GnuPG', _raise=_raise)


def GetDefaultOpenSSLCommand(_raise=OSError):
    return DetectBinaries(which='OpenSSL', _raise=_raise)


def GetDefaultTorPath(_raise=OSError):
    return DetectBinaries(which='Tor', _raise=_raise)


def InDesktopEnvironment():
    """
    Returns True if we're running in a desktop environment of some sort.
    """
    # FIXME: Detect if we are somehow in the background on Windows or OS X.
    return (sys.platform[:3] in ('dar', 'win') or os.getenv('DISPLAY'))


def RenameCannotOverwrite():
    """
    The os.rename() function will not overwrite existing files on Windows.
    """
    return sys.platform.startswith('win')


def NeedExplicitPortCheck():
    """
    Our HTTP worker doesn't detect port reuse on Windows, need explicit checks.
    """
    return sys.platform.startswith('win')


def TerminalSupportsAnsiColors():
    """
    Windows doesn't like ANSI colors. Also, we want a TTY.
    """
    return (sys.stdout.isatty() and sys.platform[:3] != "win")


def WindowsPopenSemantics():
    """
    The safe_popen module implements slightly different semantics on Windows.
    """
    return sys.platform.startswith('win')


def GetAppDataDirectory():
    if sys.platform.startswith('win'):
        # Obey Windows conventions (more or less?)
        return os.getenv('APPDATA', os.path.expanduser('~'))
    elif sys.platform.startswith('darwin'):
        # Obey Mac OS X conventions
        return os.path.expanduser('~/Library/Application Support')
    else:
        # Assume other platforms are Unixy
        return os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))


def RestrictReadAccess(path):
    """
    Restrict access to a file or directory so only the user can read it.
    """
    # FIXME: Windows code goes here!
    if os.path.isdir(path):
        os.chmod(path, 0o700)
    else:
        os.chmod(path, 0o600)


def RandomListeningPort(count=1, host='127.0.0.1'):
    socks = []
    ports = []
    try:
        import socket
        for port in range(0, count):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, 0))
            socks.append(sock)
            ports.append(sock.getsockname()[1])
        if count == 1:
            return ports[0]
        else:
            return ports
    finally:
        for sock in socks:
            sock.close()
