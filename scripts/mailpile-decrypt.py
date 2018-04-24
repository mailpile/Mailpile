#!/usr/bin/python2.7
"""
This tool will (attempt to) decrypt files encrypted by Mailpile.

Two argument form:
    mailpile-decrypt.py encrypted.mep decrypted.mep

Multiple argument form:
    mailpile-decrypt.py encrypted1.mep encrypted2.mep path/to/directory/

Loading keys from a non-standard location:
    export MAILPILE_HOME=/path/to/Mailpile/data
    mailpile-decrypt.py ...

In the multiple argument form, the tool will name output files the same
as input files, with `.txt` appended. The tool will refuse to overwrite
pre-existing files in both cases, printing a warning and skipping that
input file.

"""
import os
import sys
from mailpile.config.defaults import CONFIG_RULES
from mailpile.config.manager import ConfigManager
from mailpile.i18n import gettext as _
from mailpile.ui import Session, UserInteraction
from mailpile.util import decrypt_and_parse_lines
from mailpile.auth import VerifyAndStorePassphrase


# Check our arguments
infiles = outfiles = []
try:
    infiles = sys.argv[1:-1]
    outpath = sys.argv[-1]
except:
    pass
if ((not infiles or not outpath) or
        (os.path.exists(outpath) and not os.path.isdir(outpath)) or
        (len(infiles) > 1 and not os.path.isdir(outpath))):
    sys.stderr.write(__doc__)
    sys.exit(1)


# Basic app bootstrapping
config = ConfigManager(rules=CONFIG_RULES)
session = Session(config)
session.ui = UserInteraction(config)


# Get the password, verify it, decrypt config
fails = 0
for tries in range(1, 4):
    try:
        VerifyAndStorePassphrase(
            config, passphrase=session.ui.get_password(_('Your password: ')))
        break
    except:
        if tries < 3:
            sys.stderr.write('Incorrect, try again?')
        fails = tries
if fails == tries:
    sys.exit(1)
sys.stderr.write('\n')


# Go decrypt stuff! Or try at least.
for in_fn in infiles:
    if os.path.isdir(outpath):
        out_fn = os.path.join(outpath, os.path.basename(in_fn) + '.txt')
    else:
        out_fn = outpath

    if os.path.exists(out_fn):
        sys.stderr.write('SKIPPED, already exists: %s\n' % out_fn)
    else:
        try:
            in_fd = open(in_fn, 'rb')
        except:
            sys.stderr.write('SKIPPED, open failed: %s\n' % in_fn)
 
        with open(out_fn, 'wb') as out_fd:
            def parser(lines):
                for line in lines:
                    out_fd.write(line.encode('utf-8'))
            decrypt_and_parse_lines(in_fd, parser, config, newlines=True)
            sys.stderr.write(
                'Decrypted %s => %s\n' % (os.path.basename(in_fn), out_fn))

        in_fd.close()
