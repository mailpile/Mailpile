from gettext import gettext as _

import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import *
from mailpile.search import *
from mailpile.util import *
from mailpile.vcard import *


class Hacks(Command):
    """Various hacks ..."""
    SYNOPSIS = (None, 'hacks', None, None)
    ORDER = ('Internals', 9)
    HTTP_CALLABLE = ()


class FixIndex(Hacks):
    """Do various things to try and fix broken indexes"""
    SYNOPSIS = (None, 'hacks/fixindex', None, None)
    LOG_PROGRESS = True

    def command(self):
        session, index = self.session, self._idx()

        session.ui.mark('Checking index for duplicate MSG IDs...')
        found = {}
        for i in range(0, len(index.INDEX)):
            msg_id = index.get_msg_at_idx_pos(i)[index.MSG_ID]
            if msg_id in found:
                found[msg_id].append(i)
            else:
                found[msg_id] = [i]

        session.ui.mark('Attempting to fix dups with bad location...')
        for msg_id in found:
            if len(found[msg_id]) > 1:
                good, bad = [], []
                for idx_pos in found[msg_id]:
                    msg = Email(index, idx_pos).get_msg()
                    if msg:
                        good.append(idx_pos)
                    else:
                        bad.append(idx_pos)
                if good and bad:
                    good_info = index.get_msg_at_idx_pos(good[0])
                    for bad_idx in bad:
                        bad_info = index.get_msg_at_idx_pos(bad_idx)
                        bad_info[index.MSG_PTRS] = good_info[index.MSG_PTRS]
                        index.set_msg_at_idx_pos(bad_idx, bad_info)

        session.ui.mark('Done!')
        return True


class PyCLI(Hacks):
    """Launch a Python REPL"""
    SYNOPSIS = (None, 'hacks/pycli', None, None)
    LOG_PROGRESS = True

    def command(self):
        import code
        import readline
        from mailpile import Mailpile

        variables = globals()
        variables['session'] = self.session
        variables['config'] = self.session.config
        variables['index'] = self.session.config.index
        variables['mp'] = Mailpile(session=self.session)

        self.session.config.stop_workers()
        self.session.ui.block()
        code.InteractiveConsole(locals=variables).interact("""\
This is Python inside of Mailpile inside of Python.

   - The `mp` variable is a Pythonic API to the current pile of mail.
   - The `session` variable is the current UI session.
   - The `config` variable contains the current configuration.
   - Press CTRL+D to return to the normal CLI.
""")
        self.session.ui.unblock()
        self.session.config.prepare_workers(self.session, daemons=True)

        return 'That was fun!'


class ViewMetadata(Hacks):
    """Display the raw metadata for a message"""
    SYNOPSIS = (None, 'hacks/metadata', None, '[<message>]')

    def _explain(self, i):
        idx = self._idx()
        info = idx.get_msg_at_idx_pos(i)
        return {
            'mid': info[idx.MSG_MID],
            'ptrs': info[idx.MSG_PTRS],
            'id': info[idx.MSG_ID],
            'date': info[idx.MSG_DATE],
            'from': info[idx.MSG_FROM],
            'to': info[idx.MSG_TO],
            'cc': info[idx.MSG_CC],
            'kb': info[idx.MSG_KB],
            'subject': info[idx.MSG_SUBJECT],
            'body': info[idx.MSG_BODY],
            'tags': info[idx.MSG_TAGS],
            'replies': info[idx.MSG_REPLIES],
            'thread_mid': info[idx.MSG_THREAD_MID],
        }

    def command(self):
        return [self._explain(i) for i in self._choose_messages(self.args)]


mailpile.plugins.register_commands(Hacks, FixIndex, PyCLI, ViewMetadata)
