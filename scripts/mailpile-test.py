#!/usr/bin/env python2
#
# This script runs a set of black-box tests on Mailpile using the test
# messages found in `testing/`.
#
# If run with -i as the first argument, it will then drop to an interactive
# python shell for experimenting and manual testing.
#
import os
import sys
import time
import traceback


# Set up some paths
mailpile_root = os.path.join(os.path.dirname(__file__), '..')
mailpile_test = os.path.join(mailpile_root, 'mailpile', 'tests', 'data')
mailpile_send = os.path.join(mailpile_root, 'scripts', 'test-sendmail.sh')
mailpile_home = os.path.join(mailpile_test, 'tmp')
mailpile_gpgh = os.path.join(mailpile_test, 'gpg-keyring')
mailpile_sent = os.path.join(mailpile_home, 'sent.mbx')

# Set the GNUGPHOME variable to our test key
os.environ['GNUPGHOME'] = mailpile_gpgh

# Add the root to our import path, import API and demo plugins
sys.path.append(mailpile_root)
from mailpile.mail_source.local import LocalMailSource
from mailpile import Mailpile


##[ Black-box test script ]###################################################

FROM_BRE = [u'from:r\xfanar', u'from:bjarni']
ICELANDIC = u'r\xfanar'
IS_CHARS = (u'\xe1\xe9\xed\xf3\xfa\xfd\xfe\xe6\xf6\xf0\xc1\xc9\xcd\xd3'
            u'\xda\xdd\xde\xc6\xd6\xd0')
MY_FROM = 'team+testing@mailpile.is'
MY_NAME = 'Mailpile Team'
MY_KEYID = '0x7848252F'

# First, we set up a pristine Mailpile
os.system('rm -rf %s' % mailpile_home)
mp = Mailpile(workdir=mailpile_home)
cfg = config = mp._session.config
ui = mp._session.ui

if '-v' not in sys.argv:
    from mailpile.ui import SilentInteraction
    mp._session.ui = SilentInteraction(config)

cfg.plugins.load('demos', process_manifest=True)
cfg.plugins.load('hacks', process_manifest=True)
cfg.plugins.load('experiments', process_manifest=True)
cfg.plugins.load('smtp_server', process_manifest=True)


def contents(fn):
    return open(fn, 'r').read()


def grep(w, fn):
    return '\n'.join([l for l in open(fn, 'r').readlines() if w in l])


def grepv(w, fn):
    return '\n'.join([l for l in open(fn, 'r').readlines() if w not in l])


def say(stuff):
    mp._session.ui.mark(stuff)
    mp._session.ui.reset_marks()
    if '-v' not in sys.argv:
        sys.stderr.write('.')


def do_setup():
    # Set up initial tags and such
    mp.setup()
    mp.profiles_add(MY_FROM, '=', MY_NAME)
    mp.rescan('vcards:gpg')

    # Setup GPG access credentials and TELL EVERYONE!
    config.sys.login_banner = 'Pssst! The password is: mailpile'
    #config.gnupg_passphrase.set_passphrase('mailpile')
    #config.prefs.gpg_recipient = '3D955B5D7848252F'

    config.vcards.get(MY_FROM).fn = MY_NAME
    config.prefs.default_email = MY_FROM
    config.prefs.encrypt_index = True
    config.prefs.index_encrypted = True
    config.prefs.inline_pgp = False

    # Configure our fake mail sending setup
    config.sys.http_port = 33414
    config.sys.smtpd.host = 'localhost'
    config.sys.smtpd.port = 33415
    config.prefs.openpgp_header = 'encrypt'
    config.prefs.crypto_policy = 'openpgp-sign'

    if '-v' in sys.argv:
        config.sys.debug = 'log http vcard rescan sendmail log compose'

    # Set up dummy conctact importer for testing, disable Gravatar
    mp.set('prefs/vcard/importers/demo/0/name = Mr. Rogers')
    mp.set('prefs/vcard/importers/gravatar/0/active = false')
    mp.set('prefs/vcard/importers/gpg/0/active = false')

    # Make sure that actually worked
    assert(not mp._config.prefs.vcard.importers.gpg[0].active)
    assert(not mp._config.prefs.vcard.importers.gravatar[0].active)

    # Copy the test Maildir...
    for mailbox in ('Maildir', 'Maildir2'):
        path = os.path.join(mailpile_home, mailbox)
        os.system('cp -a %s/Maildir %s' % (mailpile_test, path))

    # Add the test mailboxes
    for mailbox in ('tests.mbx', ):
        mp.add(os.path.join(mailpile_test, mailbox))
    mp.add(os.path.join(mailpile_home, 'Maildir'))


def test_vcards():
    say("Testing vcards")

    # Do we have a Mr. Rogers contact?
    mp.rescan('vcards')
    assert(mp.contacts_view('mr@rogers.com'
                            ).result['contact']['fn'] == u'Mr. Rogers')
    assert(len(mp.contacts('rogers').result['contacts']) == 1)


def test_load_save_rescan():
    say("Testing load/save/rescan")
    mp.rescan('mailboxes')

    # Save and load the index, just for kicks
    messages = len(mp._config.index.INDEX)
    assert(messages > 5)
    mp._config.index.save(mp._session)
    mp._session.ui.reset_marks()
    mp._config.index.load(mp._session)
    mp._session.ui.reset_marks()
    assert(len(mp._config.index.INDEX) == messages)

    # Rescan AGAIN, so we can test for the presence of duplicates and
    # verify that the move-detection code actually works.
    os.system('rm -f %s/Maildir/*/*' % mailpile_home)
    mp.add(os.path.join(mailpile_home, 'Maildir2'))
    mp.rescan('mailboxes')

    # Search for things, there should be exactly one match for each.
    mp.order('rev-date')
    for search in (FROM_BRE,
                   ['agirorn'],
                   ['subject:emerging'],
                   ['from:twitter', 'brennan'],
                   ['dates:2013-09-17', 'feministinn'],
                   ['mailbox:tests.mbx'] + FROM_BRE,
                   ['att:jpg', 'fimmtudaginn'],
                   ['subject:Moderation', 'kde-isl', '-is:unread'],
                   ['from:bjarni', 'subject:testing', 'subject:encryption',
                    'should', 'encrypted', 'message', 'tag:mp_enc-decrypted'],
                   ['from:bjarni', 'subject:inline', 'subject:encryption',
                    'grand', 'tag:mp_enc-mixed-decrypted'],
                   ['from:bjarni', 'subject:signatures', '-is:unread',
                    'tag:mp_sig-expired'],
                   ['from:brennan', 'subject:encrypted',
                    'testing', 'purposes', 'only', 'tag:mp_enc-decrypted'],
                   ['from:brennan', 'subject:signed',
                    'tag:mp_sig-unverified'],
                   ['from:barnaby', 'subject:testing', 'soup',
                    'tag:mp_sig-unknown', 'tag:mp_enc-decrypted'],
                   ['from:square', 'subject:here', '-has:attachment'],
                   [u'subject:' + IS_CHARS, 'subject:8859'],
                   [u'subject:' + IS_CHARS, 'subject:UTF'],
                   ['use_libusb', 'unsubscribe', 'vger'],
                   ):
        say('Searching for: %s' % search)
        results = mp.search(*search)
        assert(results.result['stats']['count'] == 1)

    say('Checking size of inbox')
    mp.order('flat-date')
    assert(mp.search('tag:inbox').result['stats']['count'] == 20)

    say('FIXME: Make sure message signatures verified')

def test_message_data():
    say("Testing message contents")

    # Load up a message and take a look at it...
    search_md = mp.search('subject:emerging').result
    result_md = search_md['data']['metadata'][search_md['thread_ids'][0]]
    view_md = mp.view('=%s' % result_md['mid']).result

    # That loaded?
    message_md = view_md['data']['messages'][result_md['mid']]
    assert('athygli' in message_md['text_parts'][0]['data'])

    # Load up another message and take a look at it...
    search_bre = mp.search(*FROM_BRE).result
    result_bre = search_bre['data']['metadata'][search_bre['thread_ids'][0]]
    view_bre = mp.view('=%s' % result_bre['mid']).result

    # Make sure message threading is working (there are message-ids and
    # references in the test data).
    assert(len(view_bre['thread_ids']) == 3)

    # Make sure we are decoding weird headers correctly
    metadata_bre = view_bre['data']['metadata'][view_bre['message_ids'][0]]
    message_bre = view_bre['data']['messages'][view_bre['message_ids'][0]]
    from_bre = search_bre['data']['addresses'][metadata_bre['from']['aid']]
    say('Checking encoding: %s' % from_bre)
    assert('=C3' not in from_bre['fn'])
    assert('=C3' not in from_bre['address'])
    for key, val in message_bre['header_list']:
        if key.lower() not in ('from', 'to', 'cc'):
            continue
        say('Checking encoding: %s: %s' % (key, val))
        assert('utf' not in val)

    # This message broke our HTML engine that one time
    search_md = mp.search('from:heretic', 'subject:outcome').result
    result_md = search_md['data']['metadata'][search_md['thread_ids'][0]]
    view_md = mp.view('=%s' % result_md['mid'])
    assert('Outcome' in view_md.as_html())


def test_composition():
    say("Testing composition")

    # Create a message...
    new_mid = mp.message_compose().result['thread_ids'][0]
    assert(mp.search('tag:drafts').result['stats']['count'] == 0)
    assert(mp.search('tag:blank').result['stats']['count'] == 1)
    assert(mp.search('tag:sent').result['stats']['count'] == 0)
    assert(not os.path.exists(mailpile_sent))

    # Edit the message (moves from Blank to Draft, not findable in index)
    msg_data = {
        'to': ['%s#%s' % (MY_FROM, MY_KEYID)],
        'bcc': ['secret@test.com#%s' % MY_KEYID],
        'mid': [new_mid],
        'subject': ['This the TESTMSG subject'],
        'body': ['Hello world!'],
        'attach-pgp-pubkey': ['yes']
    }
    mp.message_update(**msg_data)
    assert(mp.search('tag:drafts').result['stats']['count'] == 1)
    assert(mp.search('tag:blank').result['stats']['count'] == 0)
    assert(mp.search('TESTMSG').result['stats']['count'] == 1)
    assert(not os.path.exists(mailpile_sent))

    # Send the message (moves from Draft to Sent, is findable via. search)
    del msg_data['subject']
    msg_data['body'] = [
        ('Hello world... thisisauniquestring :) '+ICELANDIC)
    ]
    mp.message_update_send(**msg_data)
    assert(mp.search('tag:drafts').result['stats']['count'] == 0)
    assert(mp.search('tag:blank').result['stats']['count'] == 0)

    # First attempt to send should fail & record failure to event log
    config.prefs.default_messageroute = 'default'
    config.routes['default'] = {"command": '/no/such/file'}
    mp.sendmail()
    events = mp.eventlog('source=mailpile.plugins.compose.Sendit',
                         'data_mid=%s' % new_mid).result['events']
    assert(len(events) == 1)
    assert(events[0]['flags'] == 'i')
    assert(len(mp.eventlog('incomplete').result['events']) == 1)

    # Second attempt should succeed!
    config.routes.default.command = '%s -i %%(rcpt)s' % mailpile_send
    mp.sendmail()
    events = mp.eventlog('source=mailpile.plugins.compose.Sendit',
                         'data_mid=%s' % new_mid).result['events']
    assert(len(events) == 1)
    assert(events[0]['flags'] == 'c')
    assert(len(mp.eventlog('incomplete').result['events']) == 0)

    # Verify that it actually got sent correctly
    assert('the TESTMSG subject' in contents(mailpile_sent))
    # This is the base64 encoding of thisisauniquestring
    assert('dGhpc2lzYXVuaXF1ZXN0cmluZ' in contents(mailpile_sent))
    assert('encryption: ' not in contents(mailpile_sent).lower())
    assert('attach-pgp-pubkey: ' not in contents(mailpile_sent).lower())
    assert('x-mailpile-' not in contents(mailpile_sent))
    assert(MY_KEYID not in contents(mailpile_sent))
    assert(MY_FROM in grep('X-Args', mailpile_sent))
    assert('secret@test.com' in grep('X-Args', mailpile_sent))
    assert('secret@test.com' not in grepv('X-Args', mailpile_sent))
    for search in (['tag:sent'],
                   ['bcc:secret@test.com'],
                   ['thisisauniquestring'],
                   ['thisisauniquestring'] + MY_FROM.split(),
                   ['thisisauniquestring',
                    'in:mp_sig-verified', 'in:mp_enc-none', 'in:sent'],
                   ['subject:TESTMSG']):
        say('Searching for: %s' % search)
        assert(mp.search(*search).result['stats']['count'] == 1)
    # This is the base64 encoding of thisisauniquestring
    assert('dGhpc2lzYXVuaXF1ZXN0cmluZ' in contents(mailpile_sent))
    assert('OpenPGP: id=CF5E' in contents(mailpile_sent))
    assert('Encryption key for' in contents(mailpile_sent))
    assert('; preference=encrypt' in contents(mailpile_sent))
    assert('secret@test.com' not in grepv('X-Args', mailpile_sent))
    os.remove(mailpile_sent)

    # Test the send method's "bounce" capability
    mp.message_send(mid=[new_mid], to=['nasty@test.com'])
    mp.sendmail()
    # This is the base64 encoding of thisisauniquestring
    assert('dGhpc2lzYXVuaXF1ZXN0cmluZ' in contents(mailpile_sent))
    assert('OpenPGP: id=CF5E' in contents(mailpile_sent))
    assert('; preference=encrypt' in contents(mailpile_sent))
    assert('secret@test.com' not in grepv('X-Args', mailpile_sent))
    assert('-i nasty@test.com' in contents(mailpile_sent))


def test_smtp():
    config.prepare_workers(mp._session, daemons=True)
    new_mid = mp.message_compose().result['thread_ids'][0]
    msg_data = {
        'from': ['%s#%s' % (MY_FROM, MY_KEYID)],
        'mid': [new_mid],
        'subject': ['This the OTHER TESTMSG...'],
        'body': ['Hello SMTP world!']
    }
    config.prefs.default_messageroute = 'default'
    config.prefs.always_bcc_self = False
    config.routes['default'] = {
        'protocol': 'smtp',
        'host': 'localhost',
        'port': 33415
    }
    mp.message_update(**msg_data)
    mp.message_send(mid=[new_mid], to=['nasty@test.com'])
    mp.sendmail()
    config.stop_workers()

def test_html():
    say("Testing HTML")

    mp.output("jhtml")
    assert('&lt;bang&gt;' in '%s' % mp.search('in:inbox').as_html())
    mp.output("text")


try:
    do_setup()
    if '-n' not in sys.argv:
        test_vcards()
        test_load_save_rescan()
        test_message_data()
        test_html()
        test_composition()
        test_smtp()
        if '-v' not in sys.argv:
            sys.stderr.write("\nTests passed, woot!\n")
        else:
            say("Tests passed, woot!")
except:
    sys.stderr.write("\nTests FAILED!\n")
    print
    traceback.print_exc()


##[ Interactive mode ]########################################################

if '-i' in sys.argv:
    mp.set('prefs/vcard/importers/gravatar/0/active = true')
    mp.set('prefs/vcard/importers/gpg/0/active = true')
    mp._session.ui = ui
    print '%s' % mp.help_splash()
    mp.Interact()


##[ Cleanup ]#################################################################
os.system('rm -rf %s' % mailpile_home)
