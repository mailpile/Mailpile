#!/usr/bin/python
DOC="""\

This is a script to launch Mailpile as a specific user.
The user must already have Mailpile configured.

Usage: mailpile-launcher.py USERNAME [IDLE-QUIT-SECONDS]

"""
import os
import pwd
import sys
from fasteners import InterProcessLock


# FIXME: Hard-coding this stuff is lame. But KISS is good.
MAILPILE_PIDS_PATH = "/var/lib/mailpile/pids"
MAILPILE_HOME_PATH = '%s/.local/share/Mailpile/default/'
MAILPILE_WORK_LOCK = 'workdir-lock'



def usage(code, msg=''):
    print DOC, msg, "\n"
    sys.exit(code)


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        usage(1)

    # Quit after 7 days idle, by default.
    idlequit = int(sys.argv[2]) if (len(sys.argv) == 3) else 7*24*3600

    mailpile_user = sys.argv[1]
    if not mailpile_user or mailpile_user == 'root':
        usage(2, "Please specify a (non-root) user to launch Mailpile.")
    mailpile_user = pwd.getpwnam(mailpile_user)
    if not mailpile_user:
        usage(2, "Please specify a (non-root) user to launch Mailpile.")

    mailpile_home = MAILPILE_HOME_PATH % mailpile_user.pw_dir
    if not os.path.exists(mailpile_home):
        usage(3, "That user has never run Mailpile. Aborting.")

    mp_lockfile = os.path.join(mailpile_home, MAILPILE_WORK_LOCK)
    mp_lock = InterProcessLock(mp_lockfile)
    if not mp_lock.acquire(blocking=False):
        # We are happy with this result, don't raise an error.
        sys.stderr.write(
            "Mailpile is already running for that user. Doing Nothing.\n")
    else:
        # We will release the lock on exec(), but make sure the user owns
        # the lockfile and will be able to take over.
        os.chown(mp_lockfile, mailpile_user.pw_uid, mailpile_user.pw_gid)
        os.execv('/bin/su',
            ['/bin/su',
             '-', mailpile_user.pw_name, '-c',
             ('screen -S mailpile -d -m '
              'mailpile --idlequit=%d --pid=%s/%s.pid --interact'
              ) % (idlequit, MAILPILE_PIDS_PATH, mailpile_user.pw_name)])
