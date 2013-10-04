#!/usr/bin/env python
#
# This script runs a set of black-box tests on Mailpile using the test
# messages found in `testing/`.
#
# If run with -i as the first argument, it will then drop to an interactive
# python shell for experimenting and manual testing.
#
import os
import sys
import traceback


# Set up some paths
mailpile_root = os.path.join(os.path.dirname(__file__), '..')
mailpile_test = os.path.join(mailpile_root, 'testing')
mailpile_home = os.path.join(mailpile_test, 'tmp')

# Add the root to our import path, import API and standard plugins
sys.path.append(mailpile_root)
from mailpile.plugins import *
from mailpile import Mailpile


##[ Black-box test script ]###################################################

FROM_BRE = [u'from:r\xfanar', u'from:bjarni']
try:
    # First, we set up a pristine Mailpile
    os.system('rm -rf %s' % mailpile_home)
    mp = Mailpile(workdir=mailpile_home)

    def say(stuff):
        mp._session.ui.mark(stuff)
        mp._session.ui.reset_marks()

    # Set up initial tags and such
    mp.setup()

    # Add the mailboxes, scan them
    for mailbox in ('tests.mbx', 'Maildir'):
        mp.add(os.path.join(mailpile_test, mailbox))
    mp.rescan()

    # Save and load the index, just for kicks
    mp._config.index.save()
    mp._config.index.load()

    # Rescan AGAIN, so we can test for the presence of duplicates.
    mp.rescan()

    # Search for things, there should be exactly one match for each.
    mp.order('flat-date')
    for search in (FROM_BRE,
                   ['agirorn'],
                   ['subject:emerging'],
                   ['from:twitter', 'brennan'],
                   ['dates:2013-09-17', 'feministinn'],
                   ['att:jpg', 'fimmtudaginn'],
                   ['subject:Moderation', 'kde-isl']):
        say('Searching for: %s' % search)
        results = mp.search(*search)
        assert(len(results.result) == 1)
        assert(results.result[0]['count'] == 1)

    # Make sure we are decoding weird headers correctly
    from_data = mp.search(*FROM_BRE).result[0]['messages'][0]['from']
    say('Checking encoding: %s' % from_data)
    assert('=C3' not in from_data)

    say("Tests passed, woot!")
except:
    say("Tests FAILED!")
    print
    traceback.print_exc()


##[ Interactive mode ]########################################################

if '-i' in sys.argv:
    import code
    import readline
    code.InteractiveConsole(locals=globals()).interact("""

Welcome to the Mailpile test shell. You can interact pythonically with the
Mailpile object `mp`, or drop to the Mailpile CLI with `mp.Interact()`.
    """)


##[ Cleanup ]#################################################################
os.system('rm -rf %s' % mailpile_home)
