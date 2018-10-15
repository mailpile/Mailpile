#!/usr/bin/python
#
# IMPORTANT: This script runs as root and is invoked by the web server via sudo.
#            So it's pretty security-sensitive: simple is better than clever!
#
DOC="""\

This is a script to launch Mailpile as a specific user.
The user must already have Mailpile configured.

Usage: mailpile-launcher.py USERNAME IDLE-QUIT-SECONDS URL

"""
import os
import pwd
import re
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
    if len(sys.argv) != 4:
        usage(1)

    mailpile_user = sys.argv[1]
    idlequit = int(sys.argv[2])
    url = sys.argv[3]

    if not mailpile_user or mailpile_user == 'root':
        usage(2, "Please specify a (non-root) user to launch Mailpile.")
    if not re.match(r'^[a-zA-Z0-9\._-]+$', mailpile_user):
        usage(2, "That is a strange looking username.")
    mailpile_user = pwd.getpwnam(mailpile_user)
    if not mailpile_user:
        usage(2, "Please specify a (non-root) user to launch Mailpile.")
    if not re.match(r'^[a-zA-Z0-9\.:/]+$', url):
        usage(2, "That is a strange looking URL.")

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
            ['/bin/su', '-', mailpile_user.pw_name, '-c', (
                'screen -S mailpile -d -m '
                'mailpile --idlequit=%d --pid=%s/%s.pid --www=%s --interact'
                ) % (idlequit, MAILPILE_PIDS_PATH, mailpile_user.pw_name, url)])
