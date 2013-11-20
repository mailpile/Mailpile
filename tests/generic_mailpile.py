import unittest
import mailpile
import os
import shutil
import contextlib


@contextlib.contextmanager
def capture():
    import sys
    from cStringIO import StringIO
    oldout, olderr = sys.stdout, sys.stderr
    try:
        out = [StringIO(), StringIO()]
        sys.stdout, sys.stderr = out
        yield out
    finally:
        sys.stdout, sys.stderr = oldout, olderr
        out[0] = out[0].getvalue()
        out[1] = out[1].getvalue()


def setUp(self):
    cwd = os.getcwd()
    workdir = os.path.join(cwd, "testing", "tmp")
    test_data = os.path.join(cwd, "testing", "Maildir")
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    if not os.path.exists(os.path.join(test_data, "new")):
        os.mkdir(os.path.join(test_data, "new"))
    self.mp = mailpile.Mailpile(workdir=workdir)
    self.mp.add(test_data)
    self.mp.rescan()


class MailPileUnittest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)

    @classmethod
    def setUpClass(self):
        setUp(self)
