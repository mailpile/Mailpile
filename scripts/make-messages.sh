#!/bin/bash

pybabel extract --project=mailpile \
    -F babel.cfg \
    -o locale/mailpile.pot \
    .
#	--omit-header

for L in $(find locale/* -type d	\
		| grep -v "LC_MESSAGES"	\
		| sed 's:locale/::'); do
	msgmerge -U locale/$L/LC_MESSAGES/mailpile.po locale/mailpile.pot
done;
