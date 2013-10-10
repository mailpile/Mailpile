#!/usr/bin/python
from datetime import date
from setuptools import setup
from mailpile.app import APPVER
import os
from glob import glob

try:
  # This borks sdist.
  os.remove('.SELF')
except:
  pass

data_files = []
for dir, dirs, files in os.walk('static'):
    data_files.append((dir, [os.path.join(dir, file_) for file_ in files]))


setup(
    name="mailpile",
    version=APPVER.replace('github',
                           'dev'+date.today().isoformat().replace('-', '')),
    license="AGPLv3+",
    author="Bjarni R. Einarsson",
    author_email="bre@klaki.net",
    url="http://www.mailpile.is/",
    description="""Mailpile is a personal tool for searching and indexing e-mail.""",
    long_description="""\
Mailpile is a tool for building and maintaining a tagging search
engine for a personal collection of e-mail.  It can be used as a
simple web-mail client.
""",
    packages=['mailpile','mailpile.plugins'],
    data_files = data_files,
    entry_points = {
     'console_scripts': [
       'mailpile = mailpile.__main__:main'
     ]
    },
)


