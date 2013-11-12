#!/bin/bash

xgettext -d mailpile -L Python \
	$(find . -name "*.py") \
	$(find . -name "*.html") \
	--keyword=gettext_noop \
	--keyword=gettext_lazy \
	--keyword=ngettext_lazy:1,2 \
	--keyword=pgettext:1c,2 \
	--keyword=npgettext:1c,2,3 \
	--from-code UTF-8 \
	-o locale/mailpile.pot

# 	--omit-header

for L in $(find locale/* -type d	\
		| grep -v "LC_MESSAGES"	\
		| sed 's:locale/::'); do
	msgmerge -U locale/$L/LC_MESSAGES/mailpile.po locale/mailpile.pot
done;
