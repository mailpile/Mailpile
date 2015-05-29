#!/bin/bash
[ -e "$HOME/Library/Application Support/Mailpile/osx.pwd" ] \
    && cd $(cat "$HOME/Library/Application Support/Mailpile/osx.pwd")

export MAILPILE_BREW_ROOT="$(pwd)/Mailpile-Brew"
export MAILPILE_ROOT="$(pwd)/Mailpile"

export PATH="$MAILPILE_BREW_ROOT/bin:/usr/bin:/bin"
export PYTHONHOME="$MAILPILE_BREW_ROOT/Cellar/python/2.7.8/Frameworks/Python.framework/Versions/2.7/"
export OPENSSL_CONF="$MAILPILE_BREW_ROOT/etc/openssl/openssl.cnf"

cd "$MAILPILE_ROOT"

echo -n -e "\033]0;Mailpile CLI\007"
osascript <<EOF
tell app "Terminal"
   set miniaturized of the front window to true
end tell
EOF
#   set custom title of first window to "Mailpile CLI"

clear
./mp --www= --interact

osascript <<EOF &
delay 0.3
tell app "Terminal"
   close (every window whose name contains "Mailpile CLI")
end tell
#delay 0.3
#tell application "System Events" to click UI element "Close" of sheet 1 of application process "Terminal"
EOF
