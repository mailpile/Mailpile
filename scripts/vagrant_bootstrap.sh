#!/bin/bash
set -ex

MAILPILE_PATH='/srv/Mailpile'
MAILPILE_HOME='/home/vagrant/.mailpile'
AS_VAGRANT='sudo -u vagrant'

echo 'Running bootstrap for Vagrant'
echo '.. installing python libraries'
apt-get update
apt-get install -y python-imaging python-jinja2 python-lxml libxml2-dev libxslt1-dev python-pip nginx

apt-get install -y gnupg openssl

cp $MAILPILE_PATH/scripts/nginx.conf /etc/nginx/sites-enabled/mailpile
service nginx restart


cd $MAILPILE_PATH
pip install -r requirements-dev.txt



echo '.. initial setup (creates folders and tags)'
$AS_VAGRANT ./mp --setup

echo '.. adding a test mailbox'
$AS_VAGRANT ./mp --add $MAILPILE_PATH/mailpile/tests/data
echo -n

echo '.. rescanning everything'
echo -n
$AS_VAGRANT ./mp rescan
echo


echo '.. set subdirectory'
echo -n
$AS_VAGRANT ./mp set sys.http_path  /mailpile
echo


if [ $? -eq 0 ]; then
  echo 'Done. To start the web interface, enter the following command:'
  echo '$ vagrant ssh -c "cd /srv/Mailpile && ./mp --www=0.0.0.0:33411 --wait"'
else
  echo 'Something failed.'

fi
