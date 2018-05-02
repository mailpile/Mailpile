#!/bin/sh
# This script shall returns a stage 1 configuration and one or more stage 2 commands.
# Returns a stage 1 sample configuration.
export PYTHONPATH=`pwd`/app/lib/python2.7/site-packages
./app/bin/python app/share/mailpile/mailpile-gui/mailpile-gui.py --script
