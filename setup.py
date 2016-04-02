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

########################################################
##################### PBR Fix ##########################
## Issue: https://bugs.launchpad.net/pbr/+bug/1530867 ##
## PR: https://review.openstack.org/#/c/263297/ ########
########################################################

import pbr.git

def _get_submodules(git_dir):
    submodules = pbr.git._run_git_command(['submodule', 'status'], git_dir)
    submodules = [s.strip().split(' ')[1]
                  for s in submodules.split('\n')
                  if s != '']
    return submodules

def _find_git_files(dirname='', git_dir=None):
    """Behave like a file finder entrypoint plugin.

    We don't actually use the entrypoints system for this because it runs
    at absurd times. We only want to do this when we are building an sdist.
    """
    file_list = []
    if git_dir is None:
        git_dir = pbr.git._run_git_functions()
    if git_dir:
        file_list = pbr.git._run_git_command(['ls-files', '-z'], git_dir)
        file_list += pbr.git._run_git_command(
            ['submodule', 'foreach', '--quiet', 'ls-files', '-z'],
            git_dir
        )
        # Users can fix utf8 issues locally with a single commit, so we are
        # strict here.
        file_list = file_list.split(b'\x00'.decode('utf-8'))
        submodules = _get_submodules(git_dir)
    return [f for f in file_list if f and f not in submodules]

pbr.git._find_git_files = _find_git_files

########## end of pbr fix ######

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
    line.strip() for line in open('mailpile/config/defaults.py', 'r')
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
