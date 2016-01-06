#!/bin/bash
set -x
set -e
cd "$(dirname $0)"/..

pybabel extract --project=mailpile \
    -F babel.cfg \
    -o mailpile/locale/mailpile.pot.tmp \
    .

sed -e 's/ORGANIZATION/Mailpile ehf/' \
    -e 's/FIRST AUTHOR <EMAIL@ADDRESS>/Mailpile Team <team@mailpile.is>/' \
    < mailpile/locale/mailpile.pot.tmp \
    > mailpile/locale/mailpile.pot \
    && rm -f mailpile/locale/mailpile.pot.tmp

for L in $(find mailpile/locale -type d |grep "LC_MESSAGES"); do
    msgmerge -U $L/mailpile.po mailpile/locale/mailpile.pot
done
