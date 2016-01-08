#!/bin/bash

export MAILPILE_HOME="$(pwd)/setup-tmp"
if [ "$1" = "--mygpg" ]; then
    shift
else
    export GNUPGHOME="$MAILPILE_HOME"
fi

if [ -d '/usr/local/Cellar/gnupg/1.4.16/bin' ]; then
    export PATH=/usr/local/Cellar/gnupg/1.4.16/bin:$PATH
fi

if [ "$1" = "--gpg" ]; then
    shift
    exec gpg "$@"
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

$PYTHON ./mp --set 'sys.debug = log http' \
             --www 'localhost:33433' \
             "$@" --interact

[ "xCLEANUP" = "1" ] && rm -rf "$MAILPILE_HOME"
