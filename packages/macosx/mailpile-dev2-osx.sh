#!/bin/bash
[ -e ~/.mailpile/osx-dev.pwd ] && cd "$(cat ~/.mailpile/osx-dev.pwd)"

export MAILPILE_BREW_ROOT="$(pwd)/Mailpile-Brew"
export MAILPILE_ROOT="$(pwd)/Mailpile"

export PATH="$MAILPILE_BREW_ROOT/bin:/usr/bin:/bin"
export PYTHONHOME="$MAILPILE_BREW_ROOT/Cellar/python/2.7.8/Frameworks/Python.framework/Versions/2.7/"
export OPENSSL_CONF="$MAILPILE_BREW_ROOT/etc/openssl/openssl.cnf"

cd "$MAILPILE_ROOT"

osascript <<EOF
tell app "Terminal"
   set custom title of first window to "Mailpile"
end tell
EOF

clear
exec ./scripts/setup-test.sh --mygpg
