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

# Set up some paths
mailpile_root = os.path.join(os.path.dirname(__file__), '..')
mailpile_test = os.path.join(mailpile_root, 'testing')
mailpile_home = os.path.join(mailpile_test, 'tmp')

# Add the root to our import path, import API and standard plugins
sys.path.append(mailpile_root)
from mailpile.plugins import *
from mailpile import Mailpile


##[ Black-box test script ]###################################################
try:
    # First, we set up a pristine Mailpile
    os.system('rm -rf %s' % mailpile_home)
    mp = Mailpile(workdir=mailpile_home)

    # Set up initial tags and such
    mp.setup()

    # Add the mailboxes, scan them
    for mailbox in ('tests.mbx', 'Maildir'):
      mp.add(os.path.join(mailpile_test, mailbox))
    mp.rescan()

    print "\nTests passed, woot!\n"
except:
    print "\nTests FAILED:\n" 
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
