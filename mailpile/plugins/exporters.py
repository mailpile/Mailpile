import mailbox
import os
import time

import mailpile.plugins
import mailpile.config
from mailpile.util import *
from mailpile.commands import Command
from mailpile.mailutils import Email


##[ Configuration ]###########################################################

MAILBOX_FORMATS = ('mbox', 'maildir')
mailpile.plugins.register_config_variables('prefs', {
    'export_format': ['Default format for exporting mail',
                      MAILBOX_FORMATS, 'mbox'],
})


##[ Commands ]################################################################

class ExportMail(Command):
    """Export messages to an external mailbox"""
    SYNOPSIS = (None, 'export', None, '<msgs> [<fmt>:<path>]')
    ORDER = ('Searching', 99)

    def export_path(self, mbox_type):
         if mbox_type == 'mbox':
             return 'mailpile-%d.mbx' % time.time()
         else:
             return 'mailpile-%d'

    def create_mailbox(self, mbox_type, path):
        if mbox_type == 'mbox':
            return mailbox.mbox(path)
        elif mbox_type == 'maildir':
            return mailbox.Maildir(path)
        raise UsageError('Invalid mailbox type: %s' % mbox_type)

    def command(self, save=True):
        session, config, idx = self.session, self.session.config, self._idx()
        mbox_type = config.prefs.export_format

        if self.args and ':' in self.args[-1]:
            mbox_type, path = self.args.pop(-1).split(':', 1)
        else:
            path = self.export_path(mbox_type)

        if os.path.exists(path):
            return self._error('Already exists: %s' % path)

        msg_idxs = self._choose_messages(self.args)
        if not msg_idxs:
            session.ui.warning('No messages selected')
            return False

        mbox = self.create_mailbox(mbox_type, path)
        for msg_idx in msg_idxs:
            e = Email(idx, msg_idx)
            session.ui.mark('Exporting =%s ...' % e.msg_mid())
            m = e.get_msg()
            # FIXME: This doesn't work
            #tags = [t.slug for t in e.get_message_tags()]
            #print 'Tags: %s' % tags
            #m['X-Mailpile-Tags'] = ', '.join(tags)
            mbox.add(m)
        mbox.flush()

        session.ui.mark('Exported %d messages to %s' % (len(msg_idxs), path))
        return {
            'exported': len(msg_idxs),
            'created': path
        }

mailpile.plugins.register_commands(ExportMail)
