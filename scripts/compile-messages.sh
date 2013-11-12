#!/bin/bash

for L in $(find locale/* -type d        \
                | grep -v "LC_MESSAGES" \
                | sed 's:locale/::'); do
        msgfmt locale/$L/LC_MESSAGES/mailpile.po -o locale/$L/LC_MESSAGES/mailpile.mo
done;
