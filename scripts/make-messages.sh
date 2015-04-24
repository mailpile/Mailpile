#!/bin/bash
set -x
set -e
cd "$(dirname $0)"/..

pybabel extract --project=mailpile \
    -F babel.cfg \
    -o mailpile/locale/mailpile.pot \
    .

for L in $(find mailpile/locale -type d |grep "LC_MESSAGES"); do
    msgmerge -U $L/mailpile.po mailpile/locale/mailpile.pot
done
