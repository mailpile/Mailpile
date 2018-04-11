#!/bin/bash
export MAILPILE_BREW_ROOT="$(cd; pwd)/Mailpile-Brew"
export MAILPILE_ROOT="$(cd; pwd)/Mailpile"

export PATH="$MAILPILE_BREW_ROOT/bin:/usr/bin:/bin"
export PYTHONHOME=$MAILPILE_BREW_ROOT/Cellar/python/2.7.8/Frameworks/Python.framework/Versions/2.7/
export OPENSSL_CONF=$MAILPILE_BREW_ROOT/etc/openssl/openssl.cnf

cd $MAILPILE_ROOT
./scripts/setup-test.sh
