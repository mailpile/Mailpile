#!/bin/bash


export MAILPILE_HOME="$(pwd)/testing/setup-tmp"
if [ "$1" != "--mygpg" ]; then
    export GNUPGHOME="$MAILPILE_HOME"
fi

rm -rf "$MAILPILE_HOME"
mkdir "$MAILPILE_HOME"
chmod 700 "$MAILPILE_HOME"

./mp --set 'sys.debug = log http' \
     --www 'localhost:33433' \
     --interact

rm -rf "$MAILPILE_HOME"
