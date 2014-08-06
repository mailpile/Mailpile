#!/bin/bash

# This is necessary, since some version/configurations of Terminal will
# change to a different CWD.  We record where we are now, in a place we
# are sure to be able to find it later.
mkdir -p ~/.mailpile
chmod 700 ~/.mailpile
pwd > ~/.mailpile/osx.pwd

exec /usr/bin/open \
     -a /Applications/Utilities/Terminal.app \
     Mailpile/packages/macosx/mailpile-osx.sh
