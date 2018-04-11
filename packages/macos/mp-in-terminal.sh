#!/bin/bash

# This is necessary, since some version/configurations of Terminal will
# change to a different CWD.  We record where we are now, in a place we
# are sure to be able to find it later.
mkdir -p "$HOME/Library/Application Support/Mailpile"
chmod 700 "$HOME/Library/Application Support/Mailpile"
pwd > "$HOME/Library/Application Support/Mailpile/osx.pwd"

# This checks if Mailpile is already running and just opens a new browser
# window/tab if it is...
(
    export MAILPILE_BREW_ROOT="$(pwd)/Mailpile-Brew"
    export MAILPILE_ROOT="$(pwd)/Mailpile"

    export PATH="$MAILPILE_BREW_ROOT/bin:/usr/bin:/bin"
    export PYTHONHOME="$MAILPILE_BREW_ROOT/Cellar/python/2.7.8/Frameworks/Python.framework/Versions/2.7/"
    export OPENSSL_CONF="$MAILPILE_BREW_ROOT/etc/openssl/openssl.cnf"

    cd Mailpile
    exec ./mp --browse_or_launch 2>/dev/null >/dev/null

) && exec /usr/bin/open \
     -a /Applications/Utilities/Terminal.app \
     Mailpile/packages/macosx/mailpile-osx.sh
