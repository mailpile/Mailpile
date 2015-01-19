#!/bin/bash
#
# This script will repackage Mailpile for the mac, using the latest sources
# from github.  It's tested on an Ubnutu 14.04 box, YMMV.
#
set -e
cd $(dirname "$0")
SCRIPTDIR="$(pwd)"
WORKDIR="/tmp/mailpile-builder/"

OUTPUT="Mailpile-Beta.dmg"
if [ "$1" = "--output" -a "$2" != "" ]; then
    OUTPUT="$2"
    shift
    shift
fi
echo "=== Target file is: $OUTPUT"

echo '=== Install apps we depend on'
which genisoimage >/dev/null || sudo apt-get install genisoimage
which wget        >/dev/null || sudo apt-get install wget
which cmake       >/dev/null || sudo apt-get install cmake

echo '=== Fetch / update Mailpile itself'
mkdir -p $WORKDIR && cd $WORKDIR
[ -d Mailpile ] || git clone -b release/beta https://github.com/pagekite/Mailpile
(cd Mailpile && git pull && git checkout -f release/beta)

echo '=== Fetch / update tool for building the compressed DMG'
[ -d libdmg-hfsplus ] || git clone https://github.com/mailpile/libdmg-hfsplus
(cd libdmg-hfsplus && git pull && cmake . && cd dmg && make)

echo '=== Fetch the latest version of the Homebrew environment'
if [ "$(hostname)" = "mailpile.is" ]; then
    cp /home/mailpile/www/files/build/Mailpile-Brew.LATEST.tar.gz .
else
    wget -c $'https://www.mailpile.is/files/build/Mailpile-Brew.LATEST.tar.gz'
fi

echo '=== Create skeleton filesystem and app'
cd $WORKDIR
[ -d DMG ] && chmod -R +w DMG && rm -rf DMG/
mkdir -p DMG/
cd DMG
cp "$SCRIPTDIR/welcome-to-mailpile-bg1.png" .welcome.png
ln -s /Applications Applications
gunzip -c <"$SCRIPTDIR/dmg-DS_Store.gz" >.DS_Store
tar xfz "$SCRIPTDIR/Mailpile.app-platypus.tgz"

echo '=== Copy Mailpile and the Homebrew environment into the app'
cd "$WORKDIR/DMG/Mailpile.app/Contents/Resources/"
rm -f Mailpile Mailpile-Brew
cp -a "$WORKDIR/Mailpile" .
tar xfz "$WORKDIR"/Mailpile-Brew.LATEST.tar.gz
cp -f "Mailpile/packages/macosx/mp-in-terminal.sh" script

echo '=== Clean up and slim down...'
(cd Mailpile && make clean)
rm -rf Mailpile/.git Mailpile-Brew/.git
rm -rf Mailpile-Brew/Library/
rm -rf Mailpile-Brew/Cellar/git
rm -rf Mailpile-Brew/Cellar/makedepend
rm -rf Mailpile-Brew/Cellar/pkg-config
rm -rf Mailpile-Brew/Cellar/python/*/share/python/Extras/
rm -rf Mailpile-Brew/Cellar/*/*/share/locale/
rm -rf Mailpile-Brew/Cellar/*/*/share/man/
rm -rf Mailpile-Brew/share/locale/
rm -rf Mailpile-Brew/share/man/
rm -rf $(find Mailpile-Brew -name include -type d)
rm -rf Mailpile-Brew/Cellar/python/*/Frameworks/*/*/Current/lib/*/test/

echo -n '=== Generate our DMG: iso..'
cd "$WORKDIR/DMG/"
chmod -R go-w .
genisoimage -quiet -D -V 'Mailpile' -no-pad -r -apple -o ../DMG.iso .
echo -n ' dmg..'
cd "$WORKDIR/"
./libdmg-hfsplus/dmg/dmg dmg DMG.iso "$OUTPUT" >/dev/null
echo -n ' cleanup..'
rm DMG.iso
[ -d DMG ] && chmod -R +w DMG && rm -rf DMG/
echo ' done.'

echo
ls -lh "$OUTPUT"
echo

[ "$1" = "--copy" -a "$2" != "" ] && cp "$OUTPUT" "$2"
[ "$1" = "--move" -a "$2" != "" ] && mv "$OUTPUT" "$2"
