import mailbox
import os
import time

import mailpile.security as security
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils.emails import Email
from mailpile.plugins import PluginManager
from mailpile.util import *


_plugins = PluginManager(builtin=os.path.basename(__file__)[:-3])


##[ Configuration ]###########################################################

MAILBOX_FORMATS = ('mbox', 'maildir')

_plugins.register_config_variables('prefs', {
    'export_format': ['Default format for exporting mail',
                      MAILBOX_FORMATS, 'mbox'],
})


##[ Commands ]################################################################

class ExportMail(Command):
    """Export messages to an external mailbox"""
    SYNOPSIS = (None, 'export', None, '[-flat] [-notags] <msgs> [<fmt>:<path>]')
    ORDER = ('Searching', 99)
    COMMAND_SECURITY = security.CC_ACCESS_FILESYSTEM

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
        raise UsageError('Invalid mailbox type: %s (must be mbox or maildir)'
                         % mbox_type)

    def command(self, save=True):
        session, config, idx = self.session, self.session.config, self._idx()
        mbox_type = config.prefs.export_format

        args = list(self.args)
        if args and ':' in args[-1]:
            mbox_type, path = args.pop(-1).split(':', 1)
        else:
            path = self.export_path(mbox_type)

        flat = notags = False
        while args and args[0][:1] == '-':
            option = args.pop(0).replace('-', '')
            if option == 'flat':
                flat = True
            elif option == 'notags':
                notags = True

        if os.path.exists(path):
            return self._error('Already exists: %s' % path)

        msg_idxs = list(self._choose_messages(args))
        if not msg_idxs:
            session.ui.warning('No messages selected')
            return False

        # Exporting messages without their threads barely makes any
        # sense.
        if not flat:
            for i in reversed(range(0, len(msg_idxs))):
                mi = msg_idxs[i]
                msg_idxs[i:i+1] = [int(m[idx.MSG_MID], 36)
                                   for m in idx.get_conversation(msg_idx=mi)]

        # Let's always export in the same order. Stability is nice.
        msg_idxs.sort()

        try:
            mbox = self.create_mailbox(mbox_type, path)
        except (IOError, OSError):
            mbox = None
        if mbox is None:
            if not os.path.exists(os.path.dirname(path)):
                reason = _('Parent directory does not exist.')
            else:
                reason = _('Is the disk full? Are permissions lacking?')
            return self._error(_('Failed to create mailbox: %s') % reason)

        exported = {}
        failed = []
        while msg_idxs:
            msg_idx = msg_idxs.pop(0)
            if msg_idx not in exported:
                e = Email(idx, msg_idx)
                session.ui.mark(_('Exporting message =%s ...') % e.msg_mid())
                fd = e.get_file()
                if fd is None:
                    failed.append(e.msg_mid())
                    session.ui.warning(_('Message =%s is unreadable! Skipping.'
                                         ) % e.msg_mid())
                    continue
                try:
                    data = fd.read()
                    if not notags:
                        tags = [tag.slug for tag in
                                (self.session.config.get_tag(t) or t for t
                                 in e.get_msg_info(idx.MSG_TAGS).split(',')
                                 if t)
                                if hasattr(tag, 'slug')]
                        lf = '\r\n' if ('\r\n' in data[:200]) else '\n'
                        header, body = data.split(lf+lf, 1)
                        data = str(lf.join([
                            header,
                            'X-Mailpile-Tags: ' + '; '.join(sorted(tags)
                                                            ).encode('utf-8'),
                            '',
                            body
                        ]))
                    mbox.add(data.replace('\r\n', '\n'))
                    exported[msg_idx] = 1
                finally:
                    fd.close()

        mbox.flush()
        result = {
            'exported': len(exported),
            'created': path
        }
        if failed:
            result['failed'] = failed
        return self._success(
            _('Exported %d messages to %s') % (len(exported), path),
            result)

_plugins.register_commands(ExportMail)
