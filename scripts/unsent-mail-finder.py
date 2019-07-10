#!/usr/bin/env python2.7

from __future__ import print_function
import json
import sys

print(("""I am an unsent mail finder, due to buggy bug bugness.
Run me like so:

    cat /home/USER/.mailpile/logs/* | %s

... and I might tell you which messages didn't get sent. Adjust the
path above to match where your mailpile really is. Sorry this is so
lame!  If you ran me wrong, press CTRL+C to abort right about now.

""") % sys.argv[0])

sendits = {}
for line in sys.stdin.readlines():
  try:
    data = json.loads(line)

    d, eid, status, msg, cls = data[:5]
    if cls == '.plugins.compose.Sendit':
        if eid not in sendits and 'mid' in data[5]:
            sendits[eid] = data
        elif msg.startswith('Connecting'):
            sendits[eid][5]['OK'] = True
  except ValueError:
    print('Unparsable: %s' % line)

for eid, data in sendits.iteritems():
    if 'OK' not in data[5]:
        print('On %s, failed to send %s' % (data[0], data[5]['mid']))
