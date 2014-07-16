#!/bin/bash

MAILPILE_PATH='/srv/Mailpile'
MAILPILE_HOME='/home/vagrant/.mailpile'
AS_VAGRANT='sudo -u vagrant'

echo 'Running bootstrap for Vagrant'
echo '.. installing python libraries'
apt-get update
apt-get install -y python-imaging python-jinja2 python-lxml libxml2-dev libxslt1-dev
ln -s /usr/bin/python2.7 /usr/bin/python2

cd $MAILPILE_PATH

echo '.. initial setup (creates folders and tags)'
$AS_VAGRANT ./mp --setup

echo '.. adding a test mailbox'
$AS_VAGRANT ./mp --add $MAILPILE_PATH/testing
echo -n

echo '.. rescanning everything'
echo -n
$AS_VAGRANT ./mp rescan
echo

if [ $? -eq 0 ]; then
  echo 'Done. To start the web interface, enter the following command:'
  echo '$ vagrant ssh -c "cd /srv/Mailpile && ./mp --www=0.0.0.0:33411 --wait"'
else
  echo 'Something failed.'

fi
