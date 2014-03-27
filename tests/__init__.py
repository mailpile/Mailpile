import contextlib
import os
import random
import shutil
import sys
import unittest
from cStringIO import StringIO

# Mailpile core
import mailpile
from mailpile.ui import SilentInteraction

# Pull in all the standard plugins, plus the demos.
from mailpile.mailboxes import *
from mailpile.plugins import *


MP = None


def get_shared_mailpile():
    global MP
    if MP is not None:
        return MP

    cwd = os.getcwd()
    workdir = os.path.join(cwd, "testing", "tmp")
    test_data = os.path.join(cwd, "testing", "Maildir")

    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    if not os.path.exists(os.path.join(test_data, "new")):
        os.mkdir(os.path.join(test_data, "new"))

    sys.stderr.write('Preparing shared Mailpile test environment, '
                     'please wait. 8-)\n')

    MP = mailpile.Mailpile(workdir=workdir, ui=SilentInteraction)
    MP._session.config.plugins.load('demos')

    # Add some mail, scan it.
    MP._config.sys.http_port = random.randint(40000, 45000)
    MP.add(test_data)
    MP.rescan()
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
    def setUpClass(self):
        self.mp = get_shared_mailpile()
