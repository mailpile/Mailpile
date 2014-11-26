#!/bin/bash
set -e
cd "$(dirname $0)"/..
for L in $(find mailpile/locale -type d |grep "LC_MESSAGES"); do
    echo msgfmt $L/mailpile.po -o $L/mailpile.mo
    msgfmt $L/mailpile.po -o $L/mailpile.mo
done;
