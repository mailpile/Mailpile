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
    name="mailpile",
    version=APPVER,
    license="AGPLv3+",
    author="Mailpile ehf.",
    author_email="team@mailpile.is",
    url="https://www.mailpile.is/",
    description="""\
An e-mail search engine and webmail client, with easy encryption and privacy.
""",
    long_description=open('README.md', 'r').read(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: JavaScript',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'License :: OSI Approved :: Apache Software License',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Communications :: Email :: Email Clients (MUA)',
        'Topic :: Security :: Cryptography',
        'Operating System :: POSIX',
        'Environment :: Console',
        'Environment :: Web Environment'],
    keywords='email webmail search pgp',
    packages=find_packages(
        exclude=["tests", "*.tests", "*.tests.*", "tests.*"]),
    include_package_data=True,
    install_requires=open('requirements.txt', 'r').read().strip().splitlines(),
    cmdclass={'build_py': Builder},
    entry_points={
        'console_scripts': [
            'mailpile = mailpile.__main__:main'
        ]},
    test_suite='nose.collector',
    tests_require=['nose'])
