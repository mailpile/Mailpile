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
            self.my_config.name = _('Local mail')
        self.recently_changed = []
        self.my_config.protocol = 'local'  # We may be upgrading an old
                                           # mbox or maildir source.
        self.watching = -1

    def _sleeping_is_ok(self, slept):
        if slept > 5:
            #
            # If any of the most recently changed mailboxes has changed
            # again, cut our sleeps short after 5 seconds. By basing this
            # on recently changed mailboxes, we don't need to explicitly
            # ask the user which mailbox(es) are being used as Inboxes.
            #
            # The number 10 should be "big enough", without us going
            # nuts and scanning a gazillion mailboxes every second.
            #
            if len(self.recently_changed) > 10:
                self.recently_changed = self.recently_changed[-10:]
            for mbx in self.recently_changed:
                if self._has_mailbox_changed(mbx, {}):
                    return False
        return True

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

    def _data_paths(self, mbx):
        mbx_path = FilePath(self._path(mbx)).raw_fp
        if os.path.exists(mbx_path):
            yield mbx_path

        if os.path.isdir(mbx_path):
            # Maildir, WERVD
            for s in ('cur', 'new', 'tmp', 'wervd.ver'):
                sub_path = os.path.join(mbx_path, s)
                if os.path.exists(sub_path):
                    yield sub_path

            # Mac Maildir
            sub_path = self._get_macmaildir_data(mbx_path)
            if sub_path:
                yield sub_path

    def _mailbox_sort_key(self, mbx):
        # Sort mailboxes so the most recently modified get scanned first.
        mt = 0
        for p in self._data_paths(mbx):
            try:
                mt = max(mt, os.path.getmtime(p))
            except (OSError, IOError):
                pass
        if mt:
            return '%20.20d' % (0x10000000000 - long(mt))
        else:
            return BaseMailSource._mailbox_sort_key(self, mbx)

    def _has_mailbox_changed(self, mbx, state):
        mtszs = []
        for p in self._data_paths(mbx):
            try:
                mt = long(os.path.getmtime(p))
                sz = long(os.path.getsize(p))
                mtszs.append('%s/%s' % (mt, sz))
            except (OSError, IOError):
                pass

        if not mtszs:
            # Try to rescan even if the above fails for some reason
            mt = sz = (int(time.time()) // 7200)
            mtszs = ['%s/%s' % (mt, sz)]

        mtsz = state['mtsz'] = ','.join(mtszs)
        if (mtsz != self.event.data.get('mailbox_state', {}).get(mbx._key)):
            while mbx in self.recently_changed:
                self.recently_changed.remove(mbx)
            self.recently_changed.append(mbx)
            return True
        else:
            return False

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
