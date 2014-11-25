import contextlib
import os
import random
import shutil
import stat
import sys
import unittest
from cStringIO import StringIO

# Mailpile core
import mailpile
import mailpile.util
from mailpile.plugins.tags import AddTag, Filter
from mailpile.crypto.gpgi import GNUPG_HOMEDIR
from mailpile.ui import SilentInteraction

# Pull in all the standard plugins, plus the demos.
from mailpile.mailboxes import *
from mailpile.plugins import *

MP = None


def get_mailpile_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

TAGS = {
    'New': {
        'type': 'unread',
        'label': False,
        'display': 'invisible'
    },
    'Inbox': {
        'type': 'inbox',
        'display': 'priority',
        'display_order': 2,
    }
}


def _initialize_mailpile_for_testing(workdir, test_data):
    config = mailpile.app.ConfigManager(workdir=workdir,
                                        rules=mailpile.defaults.CONFIG_RULES)
    session = mailpile.ui.Session(config)
    session.config.load(session)
    session.main = True
    ui = session.ui = SilentInteraction(config)

    mailpile.util.TESTING = True
    config.sys.http_port = random.randint(33500, 34000)

    mp = mailpile.Mailpile(session=session)
    session.config.plugins.load('demos')
    mp.set('prefs.index_encrypted=true')

    # Add some mail, scan it.
    # Create local mailboxes
    session.config.open_local_mailbox(session)
    for t in TAGS:
        AddTag(session, arg=[t]).run(save=False)
        session.config.get_tag(t).update(TAGS[t])

    mp.add(test_data)
    mp.rescan()

    return mp, session, config, ui


def get_shared_mailpile():
    global MP
    if MP is not None:
        return MP

    sys.stderr.write('Preparing shared Mailpile test environment, '
                     'please wait. 8-)\n')

    rootdir = get_mailpile_root()
    datadir = os.path.join(rootdir, 'mailpile', 'tests', 'data')
    gpgdir = os.path.join(datadir, 'gpg-keyring')
    tmpdir = os.path.join(datadir, 'tmp')
    test_data = os.path.join(datadir, 'Maildir')

    # force usage of test keyring whenever the test mailpile instance is used
    os.chmod(gpgdir, stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR)
    global GNUPG_HOMEDIR
    GNUPG_HOMEDIR = gpgdir

    if os.path.exists(tmpdir):
        shutil.rmtree(tmpdir)
    if not os.path.exists(os.path.join(test_data, "new")):
        os.mkdir(os.path.join(test_data, "new"))

    MP = _initialize_mailpile_for_testing(tmpdir, test_data)
    return MP


@contextlib.contextmanager
def capture():
    oldout, olderr = sys.stdout, sys.stderr
    try:
        out = [StringIO(), StringIO()]
        sys.stdout, sys.stderr = out
        yield out
    finally:
        sys.stdout, sys.stderr = oldout, olderr
        out[0] = out[0].getvalue()
        out[1] = out[1].getvalue()


class MailPileUnittest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)

    @classmethod
    def setUpClass(cls):
        (cls.mp, cls.session, cls.config, cls.ui) = get_shared_mailpile()
