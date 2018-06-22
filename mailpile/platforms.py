"""
This module tries to centralize most of the platform-specific code in use by
Mailpile. If you find yourself checking which platform the app runs on, adding
a function here instead is probably The Right Thing.
"""
import os
import sys


def _assert_file_exists(path):
    if not os.path.exists(path):
        raise OSError('Not found: %s' % path)
    return path



def GetDefaultGnuPGCommand():
    return 'gpg'


def GetDefaultOpenSSLCommand():
    # Rely on the PATH to find the way
    return 'openssl'


def GetDefaultTorPath():
    # FIXME: Detect if we are running from a package, use bundled binaries.
    return 'tor'


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

