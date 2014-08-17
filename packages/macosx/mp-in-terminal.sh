#!/bin/bash

# This is necessary, since some version/configurations of Terminal will
# change to a different CWD.  We record where we are now, in a place we
# are sure to be able to find it later.
mkdir -p ~/.mailpile
chmod 700 ~/.mailpile
pwd > ~/.mailpile/osx.pwd

# This checks if Mailpile is already running and just opens a new browser
# window/tab if it is...
(
   cd Mailpile
   exec ./mp --browse_or_launch 2>/dev/null >/dev/null

) && exec /usr/bin/open \
     -a /Applications/Utilities/Terminal.app \
     Mailpile/packages/macosx/mailpile-osx.sh
