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
mailpile_send = os.path.join(mailpile_root, 'scripts', 'test-sendmail.sh')
mailpile_home = os.path.join(mailpile_test, 'tmp')
mailpile_sent = os.path.join(mailpile_home, 'sent.mbx')

# Add the root to our import path, import API and standard plugins
sys.path.append(mailpile_root)
from mailpile.plugins import *
from mailpile import Mailpile


##[ Black-box test script ]###################################################

FROM_BRE = [u'from:r\xfanar', u'from:bjarni']
MY_FROM = 'test@test.com'

# First, we set up a pristine Mailpile
os.system('rm -rf %s' % mailpile_home)
mp = Mailpile(workdir=mailpile_home)

def contents(fn):
    return open(fn, 'r').read()

def grep(w, fn):
    return '\n'.join([l for l in open(fn, 'r').readlines() if w in l])

def grepv(w, fn):
    return '\n'.join([l for l in open(fn, 'r').readlines() if w not in l])

def say(stuff):
    mp._session.ui.mark(stuff)
    mp._session.ui.reset_marks()

try:
    # Set up initial tags and such
    mp.setup()

    # Configure our fake mail sending setup
    mp.set('profiles/0/email = %s' % MY_FROM)
    mp.set('profiles/0/name = Test Account')
    mp.set('profiles/0/route = |%s -i %%(rcpt)s' % mailpile_send)
    mp.set('sys/debug = sendmail log compose')

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
                   ['mailbox:tests.mbx'] + FROM_BRE,
                   ['att:jpg', 'fimmtudaginn'],
                   ['subject:Moderation', 'kde-isl']):
        say('Searching for: %s' % search)
        results = mp.search(*search)
        assert(results.result['count'] == 1)

    # Make sure we are decoding weird headers correctly
    result_bre = mp.search(*FROM_BRE).result['messages'][0]
    result_bre = mp.view('=%s' % result_bre['mid']).result['messages'][0]
    say('Checking encoding: %s' % result_bre['from'])
    assert('=C3' not in result_bre['from'])
    say('Checking encoding: %s' % result_bre['message']['headers']['To'])
    assert('utf' not in result_bre['message']['headers']['To'])

    # Create a message...
    new_mid = mp.message_compose().result['messages'][0]['mid']
    assert(mp.search('tag:drafts').result['count'] == 0)
    assert(mp.search('tag:blank').result['count'] == 1)
    assert(mp.search('tag:sent').result['count'] == 0)
    assert(not os.path.exists(mailpile_sent))

    # Edit the message (moves from Blank to Draft, not findable in index)
    msg_data = {
      'from': [MY_FROM],
      'bcc': ['secret@test.com'],
      'mid': [new_mid],
      'subject': ['This the TESTMSG subject'],
      'body': ['Hello world!']
    }
    mp.message_update(**msg_data)
    assert(mp.search('tag:drafts').result['count'] == 1)
    assert(mp.search('tag:blank').result['count'] == 0)
    assert(mp.search('TESTMSG').result['count'] == 0)
    assert(not os.path.exists(mailpile_sent))

    # Send the message (moves from Draft to Sent, is findable via. search)
    del msg_data['subject']
    msg_data['body'] = ['Hello world: thisisauniquestring :)']
    mp.message_update_send(**msg_data)
    assert(mp.search('tag:drafts').result['count'] == 0)
    assert(mp.search('tag:blank').result['count'] == 0)
    assert('the TESTMSG subject' in contents(mailpile_sent))
    assert('thisisauniquestring' in contents(mailpile_sent))
    assert(MY_FROM in grep('X-Args', mailpile_sent))
    assert('secret@test.com' in grep('X-Args', mailpile_sent))
    assert('secret@test.com' not in grepv('X-Args', mailpile_sent))
    for search in (['tag:sent'],
                   ['bcc:secret@test.com'],
                   ['thisisauniquestring'],
                   ['subject:TESTMSG']):
        say('Searching for: %s' % search)
        assert(mp.search(*search).result['count'] == 1)
    os.remove(mailpile_sent)

    # Test the send method's "bounce" capability
    mp.message_send(mid=[new_mid], to=['nasty@test.com'])
    assert('thisisauniquestring' in contents(mailpile_sent))
    assert('secret@test.com' not in grepv('X-Args', mailpile_sent))
    assert('-i nasty@test.com' in contents(mailpile_sent))
    os.remove(mailpile_sent)

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
