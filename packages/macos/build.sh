#!/bin/bash
#
# This script will use Homebrew to build a complete environment for packacing
# mailpile. This script is tested on macOS 10.13.4, with XCode 9.3.
#
set -e
export SOURCE_DIR=$(cd $(dirname "$0")/../..; pwd)
export HOME=$(cd ~; pwd)

# Target directories
export BUILD_DIR=${BUILD_DIR:-~/build}
export ICONSET_DIR=$BUILD_DIR/AppIcon.appiconset
export MAILPILE_BREW_ROOT="$BUILD_DIR/Mailpile.app/Contents/Resources/app"

# This has far-reaching and magical side-effects, including the use of
# brew's Python and pip, and those installing in turn to the homebrew tree
# instead of globally
export PATH="$MAILPILE_BREW_ROOT"/bin:$PATH

# Tools, versions
export GIT_SSL_NO_VERIFY=1
export HOMEBREW_CC=gcc-4.2
export MACOSX_DEPLOYMENT_TARGET=10.13
export PYTHON_MAJOR_VERSION=2
export PYTHON_VERSION=2.7
export GNUPG_VERSION=2.2
export OPENSSL_VERSION=1.0
export SYMLINKS_SRC="$SOURCE_DIR/packages/macos/brew/symlinks.rb"
export KEYCHAIN=~/Library/Keychains/login.keychain

# Use PeturIngi's GUI-o-Mac-Tic for now
export GUI_O_MAC_TIC_REPO=https://github.com/peturingi/gui-o-mac-tic
export GUI_O_MAC_TIC_BRANCH=master

# See this mailing list post: http://curl.haxx.se/mail/archive-2013-10/0036.html
export OSX_MAJOR_VERSION="$(sw_vers -productVersion | cut -d . -f 2)"
if [ $(echo "$OSX_MAJOR_VERSION  < 9" | bc) == 1 ]; then
   export CURL_CA_BUNDLE=/usr/share/curl/curl-ca-bundle.crt
fi

# Load user settings/overrides/credentials:
#
#    1. DMG_SIGNING_IDENTITY=... # Needed by GUI-o-Mac-Tic code signing
#    2. KEYCHAIN_PASSWORD=...    #  - ditto -
#    3. HOME=/Users/botuser      # Needed by Homebrew under launchd
#
[ -e ~/mailpile-build-settings ] && . ~/mailpile-build-settings

# Unlock the MacOS keychain
if [ "$KEYCHAIN_PASSWORD" = "" ]; then
  security unlock-keychain $KEYCHAIN
else
  security unlock-keychain -p "$KEYCHAIN_PASSWORD" $KEYCHAIN
fi

# Just run all the scripts in alphanumerical order.
cp /dev/null build.log
for script in $(ls -1 build-script/ |sort); do
  echo -n "$script "
  echo "===[ $script ]=====[ $(date +%Y-%m-%d/%H:%M) ]=" >>build.log
  ./build-script/$script 2>&1 |tee -a build.log |while read LINE; do
    echo -n .
  done
  RESULT="${PIPESTATUS[0]}"
  echo |tee -a build.log
  if [ "$RESULT" != 0 ]; then
    echo "FAILED[$RESULT]" |tee -a build.log
    exit 1
  fi
done
