import time
import os

from mailpile.mail_source import BaseMailSource
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.vfs import FilePath


class LocalMailSource(BaseMailSource):
    """
    This is a mail source that watches over one or more local mailboxes.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.local.LocalMailSource'

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        if not self.my_config.name:
            self.my_config.name = _('Local mailboxes')
        self.my_config.protocol = 'local'  # We may be upgrading an old
                                           # mbox or maildir source.
        self.watching = -1

    def close(self):
        pass

    def open(self):
        with self._lock:
            mailboxes = self.my_config.mailbox.values()
            if self.watching == len(mailboxes):
                return True
            else:
                self.watching = len(mailboxes)

            # Prepare the data section of our event, for keeping state.
            for d in ('mailbox_state', ):
                if d not in self.event.data:
                    self.event.data[d] = {}

        self._log_status(_('Watching %d mbox mailboxes') % self.watching)
        return True

    def _get_macmaildir_data(self, path):
        ds = [d for d in os.listdir(path) if not d.startswith('.')
              and os.path.isdir(os.path.join(path, d))]
        return (len(ds) == 1) and os.path.join(path, ds[0], 'Data')

    def _has_mailbox_changed(self, mbx, state):
        mbx_path = FilePath(self._path(mbx)).raw_fp

        # This is common to all local mailboxes, check the mtime/size
        try:
            mt = long(os.path.getmtime(mbx_path))
            sz = long(os.path.getsize(mbx_path))
        except (OSError, IOError):
            mt = sz = (int(time.time()) // 7200)  # Guarantee rescans
        mtsz = state['mtsz'] = '%s/%s' % (mt, sz)

        # Check more carefully if it's a Maildir, Mac Maildir or WERVD.
        if os.path.isdir(mbx_path):
            for sub in ('cur', 'new', 'tmp', 'Info.plist', 'wervd.ver'):
                if sub == 'Info.plist':
                    sub_path = self._get_macmaildir_data(mbx_path)
                    if not sub_path:
                        continue
                else:
                    sub_path = os.path.join(mbx_path, sub)
                try:
                    mt = long(os.path.getmtime(sub_path))
                    sz = long(os.path.getsize(sub_path))
                    sub_mtsz = '%s/%s' % (mt, sz)
                    mtsz += ',' + sub_mtsz
                    state['mtsz'] += ',' + sub_mtsz
                except (OSError, IOError):
                    pass

        return (mtsz != self.event.data.get('mailbox_state', {}).get(mbx._key))

    def _mark_mailbox_rescanned(self, mbx, state):
        if 'mailbox_state' in self.event.data:
            self.event.data['mailbox_state'][mbx._key] = state['mtsz']
        else:
            self.event.data['mailbox_state'] = {mbx._key: state['mtsz']}

    def _is_mbox(self, fn):
        try:
            with open(fn, 'rb') as fd:
                data = fd.read(2048)  # No point reading less...
                if data.startswith('From '):
                    # OK, this might be an mbox! Let's check if the first
                    # few lines look like RFC2822 headers...
                    headcount = 0
                    for line in data.splitlines(True)[1:]:
                        if (headcount > 2) and line in ('\n', '\r\n'):
                            return True
                        if line[-1:] == '\n' and line[:1] not in (' ', '\t'):
                            parts = line.split(':')
                            if (len(parts) < 2 or
                                    ' ' in parts[0] or '\t' in parts[0]):
                                return False
                            headcount += 1
                    return (headcount > 2)
        except (IOError, OSError):
            pass
        return False

    def _is_maildir(self, fn):
        if not os.path.isdir(fn):
            return False
        for sub in ('cur', 'new', 'tmp'):
            subdir = os.path.join(fn, sub)
            if not os.path.exists(subdir) or not os.path.isdir(subdir):
                return False
        return True

    def _is_macmaildir(self, path):
        infoplist = os.path.join(path, 'Info.plist')
        if not os.path.isdir(path) or not os.path.exists(infoplist):
            return False
        data = self._get_macmaildir_data(path)
        return data and os.path.isdir(data)

    def is_mailbox(self, fn):
        fn = FilePath(fn).raw_fp
        return (self._is_maildir(fn) or
                self._is_macmaildir(fn) or
                self._is_mbox(fn))
