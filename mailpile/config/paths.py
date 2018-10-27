import os
import sys

import mailpile.platforms

try:
    from appdirs import AppDirs
except ImportError:
    AppDirs = None


def _ensure_exists(path, mode=0700):
    if not os.path.exists(path):
        head, tail = os.path.split(path)
        _ensure_exists(head)
        os.mkdir(path, mode)
    return path


def LEGACY_DEFAULT_WORKDIR(profile):
    if profile == 'default':
        # Backwards compatibility: If the old ~/.mailpile exists, use it.
        workdir = os.path.expanduser('~/.mailpile')
        if os.path.exists(workdir) and os.path.isdir(workdir):
            return workdir

    return os.path.join(
        mailpile.platforms.GetAppDataDirectory(), 'Mailpile', profile)


def DEFAULT_WORKDIR():
    # The Mailpile environment variable trumps everything
    workdir = os.getenv('MAILPILE_HOME')
    if workdir:
        return _ensure_exists(workdir)

    # Which profile?
    profile = os.getenv('MAILPILE_PROFILE', 'default')

    # Check if we have a legacy setup we need to preserve
    workdir = LEGACY_DEFAULT_WORKDIR(profile)
    if not AppDirs or (os.path.exists(workdir) and os.path.isdir(workdir)):
        return _ensure_exists(workdir)

    # Use platform-specific defaults
    # via https://github.com/ActiveState/appdirs
    dirs = AppDirs("Mailpile", "Mailpile ehf")
    return _ensure_exists(os.path.join(dirs.user_data_dir, profile))


def DEFAULT_SHARED_DATADIR():
    # IMPORTANT: This code is duplicated in mailpile-admin.py.
    #            If it needs changing please change both places!
    env_share = os.getenv('MAILPILE_SHARED')
    if env_share is not None:
        return env_share

    # Check if we are running in a virtual env
    # http://stackoverflow.com/questions/1871549/python-determine-if-running-inside-virtualenv
    # We must also check that we are installed in the virtual env,
    # not just that we are running in a virtual env.
    if ((hasattr(sys, 'real_prefix') or hasattr(sys, 'base_prefix'))
            and __file__.startswith(sys.prefix)):
        return os.path.join(sys.prefix, 'share', 'mailpile')

    # Check if we've been installed to /usr/local (or equivalent)
    usr_local = os.path.join(sys.prefix, 'local')
    if __file__.startswith(usr_local):
        return os.path.join(usr_local, 'share', 'mailpile')

    # Check if we are in /usr/ (sys.prefix)
    if __file__.startswith(sys.prefix):
        return os.path.join(sys.prefix, 'share', 'mailpile')

    # Else assume dev mode, source tree layout
    return os.path.join(
        os.path.dirname(__file__), '..', '..', 'shared-data')


def DEFAULT_LOCALE_DIRECTORY():
    """Get the gettext translation object, no matter where our CWD is"""
    return os.path.join(DEFAULT_SHARED_DATADIR(), "locale")


def LOCK_PATHS(workdir=None):
    if workdir is None:
        workdir = DEFAULT_WORKDIR()
    return (
        os.path.join(workdir, 'public-lock'),
        os.path.join(workdir, 'workdir-lock'))
