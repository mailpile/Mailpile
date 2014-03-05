#!/usr/bin/env python2
from datetime import date
from setuptools import setup, find_packages
from mailpile.defaults import APPVER
import os
from glob import glob

try:
    # This borks sdist.
    os.remove('.SELF')
except:
    pass

data_files = []

# Copy static UI files
for dir, dirs, files in os.walk('static'):
    data_files.append((dir, [os.path.join(dir, file_) for file_ in files]))

# Copy translation files
for dir, dirs, files in os.walk('locale'):
    data_files.append((dir, [os.path.join(dir, file_) for file_ in files]))


setup(
    name="mailpile",
    version=APPVER.replace('github',
                           'dev'+date.today().isoformat().replace('-', '')),
    license="AGPLv3+",
    author="Bjarni R. Einarsson",
    author_email="bre@klaki.net",
    url="http://www.mailpile.is/",
    description="""\
Mailpile is a personal tool for searching and indexing e-mail.""",
    long_description="""\
Mailpile is a tool for building and maintaining a tagging search
engine for a personal collection of e-mail.  It can be used as a
simple web-mail client.
""",
    packages=find_packages(),
    data_files=data_files,
    install_requires=[
        'lxml>=2.3.2',
        'jinja2',
        'spambayes>=1.1b1'
        ],
    entry_points={
        'console_scripts': [
            'mailpile = mailpile.__main__:main'
        ]},
)
