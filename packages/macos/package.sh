#!/bin/bash

cd "$(dirname "$0")"
APPDMG_TEMPLATE=appdmg.json.template
BUILD_DIR=~/build
TARGET=~/build/Mailpile.dmg
ASSETS_DIR=`pwd`
BACKGROUND=$ASSETS_DIR/background/background.png
APP=$BUILD_DIR/Mailpile.app

# Ensure dependencies are met.
command -v appdmg >/dev/null 2>&1 || {
	echo >&2 "This script depends on 'appdmg'.\
appdmg was not found on PATH; please ensure appdmg is installed and on PATH.
For more information, see https://github.com/LinusU/node-appdmg. \
Aborting."
	exit 1;
}

# Check if the ID of the key, to be used for signing, is set.
if [ -z ${DMG_SIGNING_IDENTITY+x} ]
then
	echo "The environment variable DMG_SIGNING_IDENTITY must be set \
to the ID of a certificate, which is located within Keychain Access.app, which \
is to be used to sign the .dmg. \
Example: To use a certificate with the common name 'Mac Developer: John Appleseed \
(4P78A94863)', set DMG_SIGNING_IDENTITY to 4P78A94863. Aborting."
	exit 1
fi

APPDMG_CONFIG=`/usr/bin/mktemp -d`/appdmg.json
/usr/bin/sed "s|DMG_SIGNING_IDENTITY|$DMG_SIGNING_IDENTITY|g; s|BACKGROUND|$BACKGROUND|g; s|APP|$APP|g" appdmg.json.template > $APPDMG_CONFIG
appdmg $APPDMG_CONFIG $TARGET
rm $APPDMG_CONFIG
