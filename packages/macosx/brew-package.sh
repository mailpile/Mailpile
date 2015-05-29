#!/bin/bash
set -e
export MAILPILE_BREW_ROOT="$(cd; pwd)/Mailpile-Brew"
##############################################################################
cat <<tac

This script will use Homebrew to build a complete environment for
packaging Mailpile, here: $MAILPILE_BREW_ROOT

This script is tested on Mac OS X 10.5.8, with XCode 3.1.6.

tac
##############################################################################
echo -n 'Press ENTER to continue, CTRL-C to bail out... '; read

export CURL_CA_BUNDLE=/usr/share/curl/curl-ca-bundle.crt
export PATH="$MAILPILE_BREW_ROOT"/bin:$PATH
export GIT_SSL_NO_VERIFY=1
export HOMEBREW_CC=gcc-4.2
export MACOX_DEPLOYMENT_TARGET=10.5

mkdir -p "$MAILPILE_BREW_ROOT"
cd "$MAILPILE_BREW_ROOT"


#
# Install basic tools
#
[ -e bin/brew ] || \
    curl -kL https://github.com/Homebrew/homebrew/tarball/master \
    | tar xz --strip 1
echo
brew install git
brew install gnupg
brew install openssl
brew link --force openssl
brew install libjpeg
brew install python
brew install tor


#
# Install Python packages
#
_ptest() {
    echo "import $1" | python 2>/dev/null && echo "$1 is already installed"
}
_pip() {
    _PM=$1
    shift
    _ptest $_PM || pip install "$@"
}
echo
_pip   DNS       pydns
_pip   jinja2    jinja2
_pip   pexpect   pexpect
_pip   pgpdump   pgpdump
_pip   markdown  markdown
_pip   spambayes http://pypi.python.org/packages/source/s/spambayes/spambayes-1.1b1.tar.gz
_pip   PIL       pillow
_ptest lxml ||   STATIC_DEPS=true pip install lxml
_pip   objc      pyobjc || echo 'Incomplete pyobjc build'


#
# Make library paths relative
#
_readlink() {
    FN="$1"
    LN="$(readlink $1)"
    while [ "$LN" != "" -a "$LN" != "$FN" ]; do
        FN="$LN"
        LN="$(readlink $1)"
    done
    echo "$FN"
}
_relpath() {
    TARGET="$1"
    SOURCE="$2"
    cat <<tac |python
import os, sys
source, target = os.path.abspath('$SOURCE').split('/'), '$TARGET'.split('/')
while target and source and target[0] == source[0]:
    target.pop(0)
    source.pop(0)
print '/'.join(['..' for i in source] + target)
tac
}
_fixup_lib_names() {
    bin="$1"
    typ="$2"
    otool -L "$bin" |grep "$MAILPILE_BREW_ROOT" |while read lib JUNK; do
        bin_path="$(_readlink "$bin")"
        new=$(_relpath "$lib" $(dirname "$bin_path"))
        chmod u+w "$bin" "$lib"
        echo install_name_tool -change "$lib" "$typ/$new" "$bin_path"
        install_name_tool -change "$lib" "$typ/$new" "$bin_path"
        install_name_tool -id $(basename "$lib") "$lib"
        chmod u-w "$bin" "$lib"
    done
}
cd "$MAILPILE_BREW_ROOT/bin"
for bin in *; do
    _fixup_lib_names "$bin" "@executable_path"
done
cd "$MAILPILE_BREW_ROOT"
(
    find . -type f -name 'Python'
    find Cellar opt -type f -name '*.dylib'
    find Cellar opt -type f -name '*.so'
) | while read bin; do
    _fixup_lib_names "$bin" "@loader_path"
done


#
# Make symbolic links relative
#
if [ ! -e "$MAILPILE_BREW_ROOT"/bin/symlinks ]; then
    TDIR=/tmp/symlinks-mailpile.$$
    mkdir $TDIR
    cd $TDIR
    curl -O http://pkgs.fedoraproject.org/repo/pkgs/symlinks/symlinks-1.2.tar.gz/b4bab0a5140e977c020d96e7811cec61/symlinks-1.2.tar.gz
    [ "$(md5 symlinks-1.2.tar.gz|cut -f4 -d\ )" = \
      "b4bab0a5140e977c020d96e7811cec61" ] || exit 1
    tar xvfz symlinks-1.2.tar.gz
    cd symlinks-1.2
    perl -pi.bak -e 's/malloc.h/stdlib.h/' symlinks.c
    make
    cp symlinks "$MAILPILE_BREW_ROOT"/bin/
    cd "$MAILPILE_BREW_ROOT"
    rm -rf $TDIR
else
    cd "$MAILPILE_BREW_ROOT"
fi
# This needs to run twice... just because
./bin/symlinks -s -c -r "$MAILPILE_BREW_ROOT"
./bin/symlinks -s -c -r "$MAILPILE_BREW_ROOT"

#
# Fix brew's Python to not hardcode the full path
#
cd "$MAILPILE_BREW_ROOT"
for target in /lib/python2.7/site-packages/sitecustomize.py \
              /Cellar/python/2.7.8/Frameworks/Python.framework/Versions/2.7/lib/python2.7/_sysconfigdata.py \
; do
    perl -pi.bak -e \
        "s|'$MAILPILE_BREW_ROOT|__file__.replace('$target', '') + '|g" \
        .$target
done

#
# Fix Python's launcher to avoid the rocket ship
#
LSUIELEM="<key>LSUIElement</key><string>1</string>"
perl -pi.bak -e \
    "s|(\\s+)(<key>CFBundleDocumentTypes)|\\1$LSUIELEM\\2|" \
    ./Cellar/python/*/Frame*/Python*/V*/C*/Res*/Python.app/Cont*/Info.plist


#
# Pre-test, slim down: remove *.pyo and *.pyc files
#
cd "$MAILPILE_BREW_ROOT"
find . -name *.pyc -or -name *.pyo -or -name *.a | xargs rm -f


#
# Test our installation, make sure it works
#
echo
mv "$MAILPILE_BREW_ROOT" "$MAILPILE_BREW_ROOT".RELOC
cd "$MAILPILE_BREW_ROOT".RELOC
echo |./bin/openssl 2>/dev/null && echo ... is OK
./bin/gpg --list-keys >/dev/null 2>&1 && echo 'GnuPG is OK'
cat << tac | ./bin/python
import DNS
import jinja2
import pexpect
import pgpdump
import markdown
import spambayes
import PIL
import lxml
import objc
import hashlib
print "Python is OK"
tac
cd
mv "$MAILPILE_BREW_ROOT".RELOC "$MAILPILE_BREW_ROOT"
echo "== Tests passed, we are happy =="


#
# Finally, slim down again: remove *.pyo and *.pyc files created
# by the test-run above.
#
cd "$MAILPILE_BREW_ROOT"
find . -name *.pyc -or -name *.pyo -or -name *.a | xargs rm -f

