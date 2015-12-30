#!/bin/bash

CLEANUP=Mailpile.$(date +%Y%m%d-%H%M).$$
cd 
mkdir -p $CLEANUP
mv -v 'Library/Application Support/Mailpile' .gnupg $CLEANUP
echo " "
echo "Moved Mailpile and GnuPG data to: $CLEANUP"
echo " "
echo "Feel free to delete that folder if you are sure nothing"
echo "important was lost!"
