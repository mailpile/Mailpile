#!/bin/sh

chown mailpile: /mailpile-data/ -R

su-exec mailpile "$@"
