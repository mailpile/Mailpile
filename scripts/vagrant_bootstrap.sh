#!/bin/bash

echo 'Running bootstrap for Vagrant'
echo '.. installing python libraries'
apt-get install python-imaging python-jinja2 python-lxml libxml2-dev libxslt1-dev

echo '.. setting http host to listen on 0.0.0.0 (unsafe for production scenarios, use only in dev!)'
cd /srv/Mailpile && ./mp --set sys.http_host=0.0.0.0

echo 'Done. To start the web interface, enter the following command:'
echo '  $ vagrant ssh -c "cd /srv/Mailpile && ./mp --www"'
