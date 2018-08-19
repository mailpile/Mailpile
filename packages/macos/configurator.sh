#!/bin/sh
# This script shall returns a stage 1 configuration and one or more stage 2 commands.
# Returns a stage 1 sample configuration.
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd)/app/opt/mailpile"
export PATH="$(pwd)/app/bin:$PATH"
exec ./app/bin/python \
  ./app/opt/mailpile/shared-data/mailpile-gui/mailpile-gui.py \
  --script --trust-os-path
