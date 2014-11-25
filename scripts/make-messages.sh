#!/bin/bash
set -x
set -e
cd "$(dirname $0)"/..

pybabel extract --project=mailpile \
    -F babel.cfg \
    -o mailpile/locales/mailpile.pot \
    .

for L in $(find mailpile/locales -type d |grep "LC_MESSAGES"); do
    msgmerge -U $L/mailpile.po mailpile/locales/mailpile.pot
done
