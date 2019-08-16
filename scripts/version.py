#!/usr/bin/env python2.7
from __future__ import print_function
import datetime
import os
import re
import time


ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
try:
    GIT_HEAD = open('%s/.git/HEAD' % ROOT).read().strip().split('/')[-1]
    BRANCH = {
       'master': 'dev',
       'release': ''
    }.get(GIT_HEAD, GIT_HEAD)
except (OSError, IOError):
    BRANCH = None


now = os.getenv('SOURCE_DATE_EPOCH', time.time())
today = datetime.datetime.fromtimestamp(float(now))

if BRANCH:
    ts = str(today).replace('-', '').replace(' ', '').replace(':', '')
    BRANCHVER = '~%s%s' % (BRANCH, ts[:12])
else:
    BRANCHVER = ''


APPVER = '%s%s' % (next(
    line.strip() for line in open('%s/mailpile/config/defaults.py' % ROOT, 'r')
    if re.match(r'^APPVER\s*=', line)
).split('"')[1], BRANCHVER)


# Tweak the appver to make upgrades less of a concern.
APPVER = APPVER.replace('1.0.0rc', '0.99.')


if __name__ == "__main__":
    print('%s' % APPVER)
