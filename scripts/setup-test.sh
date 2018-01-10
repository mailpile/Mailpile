#!/bin/bash

export MAILPILE_HOME="$(pwd)/setup-tmp"
if [ "$1" = "--mygpg" ]; then
    shift
else
    export GNUPGHOME="$MAILPILE_HOME"
fi

if [ "$VIRTUAL_ENV" -a -e "$VIRTUAL_ENV/bin/gpg2" ]; then
    GPG_BINARY="$VIRTUAL_ENV/bin/gpg2"
else
    if [ -d '/usr/local/Cellar/gnupg/1.4.16/bin' ]; then
        export PATH=/usr/local/Cellar/gnupg/1.4.16/bin:$PATH
    fi
    GPG_BINARY=$(which gpg)
fi

if [ "$1" = "--gpg" ]; then
    shift
    exec $GPG_BINARY "$@"
fi
if [ "$1" = "--dbg" ]; then
    shift
    ulimit -c unlimited
    PYTHON=python2.7-dbg
else
    PYTHON=python2.7
fi

if [ "$1" = "--keep" ]; then
    shift
else
    rm -rf "$MAILPILE_HOME"
fi
mkdir -p "$MAILPILE_HOME"
chmod 700 "$MAILPILE_HOME"

if [ "$1" = "--cleanup" ]; then
    shift
    CLEANUP=1
fi

[ "$1" = "" ] && IA="--interact" || IA=""
$PYTHON -OOR ./mp \
             --set 'sys.debug = log http' \
             --set "sys.gpg_binary = $GPG_BINARY" \
             --pidfile "$MAILPILE_HOME/mailpile.pid" \
             --www 'localhost:33433' \
             "$@" $IA

[ "xCLEANUP" = "1" ] && rm -rf "$MAILPILE_HOME"
