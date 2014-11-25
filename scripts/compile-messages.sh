#!/bin/bash
set -e
cd "$(dirname $0)"/..
for L in $(find mailpile/locales -type d |grep "LC_MESSAGES"); do
    msgfmt $L/mailpile.po -o $L/mailpile.mo
done;
