#!/bin/bash
#
# Script to build Mailpile packages for a specific branch/repo.
#

REPO=${1:-nightly}
BRANCH=${2:-master}
FORCE=$3

(
  set -e
  set -x

  cd
  mkdir -p incoming/$REPO

  cd mailpile
  git checkout -f $BRANCH
  if [ "$FORCE$(git pull origin $BRANCH 2>&1 |grep -c up-to-date)" != 1 ]; then
    rm -rf dist/*
    make mrproper dpkg
    rm -f dist/mailpile.tar.gz
    cp dist/*.deb dist/*.tar.gz ~/incoming/$REPO
    dpkg-sig --sign builder ~/incoming/$REPO/*deb
  fi
) \
  >~/$REPO-last.log 2>&1
