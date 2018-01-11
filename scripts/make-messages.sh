#!/bin/bash
set -x
set -e
cd "$(dirname $0)"/..

export PYTHONPATH=$(pwd)

pybabel extract --project=mailpile \
    -F babel.cfg \
    -o shared-data/locale/mailpile.pot.tmp \
    .

sed -e 's/ORGANIZATION/Mailpile ehf/' \
    -e 's/FIRST AUTHOR <EMAIL@ADDRESS>/Mailpile Team <team@mailpile.is>/' \
    < shared-data/locale/mailpile.pot.tmp \
    > shared-data/locale/mailpile.pot \
    && rm -f shared-data/locale/mailpile.pot.tmp

for L in $(find shared-data/locale -type d |grep "LC_MESSAGES"); do
    msgmerge -U $L/mailpile.po shared-data/locale/mailpile.pot
done
