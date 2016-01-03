#!/usr/bin/env python2
from datetime import date
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
import datetime
import os
import re
import subprocess
from glob import glob

here = os.path.abspath(os.path.dirname(__file__))

## This figures out what version we want to call ourselves ###################
try:
    GIT_HEAD = open('.git/HEAD').read().strip().split('/')[-1]
    BRANCH = {
       'master': 'dev',
       'release': ''
    }.get(GIT_HEAD, GIT_HEAD)
except (OSError, IOError):
    BRANCH = None
if BRANCH:
    BRANCHVER = '.%s%s' % (BRANCH, str(datetime.date.today()).replace('-', ''))
else:
    BRANCHVER = ''

APPVER = '%s%s' % (next(
    line.strip() for line in open('mailpile/defaults.py', 'r')
    if re.match(r'^APPVER\s*=', line)
).split('"')[1], BRANCHVER)


## Cleanup ###################################################################
try:
    assert(0 == subprocess.call(['make', 'clean'], cwd=here))
except:
    print "Faild to run 'make clean'. Bailing out."
    exit(1)


## Install ###################################################################

class Builder(build_py):
    def run(self):
        try:
            assert(0 == subprocess.call(['make', 'bdist-prep'], cwd=here))
        except:
            print "Error building package. Try running 'make'."
            exit(1)
        else:
            build_py.run(self)


## "Main" ####################################################################

setup(
    setup_requires=['pbr'],
    version=APPVER,
    pbr=True,
    cmdclass={'build_py': Builder},
)
