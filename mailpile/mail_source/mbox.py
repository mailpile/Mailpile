import os

from mailpile.mail_source import BaseMailSource
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n


class MboxMailSource(BaseMailSource):
    """
    This is a mail source that watches over one or more Unix mboxes.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.mbox.MboxMailSource'

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
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

    def _has_mailbox_changed(self, mbx, state):
        try:
            mt = state['mt'] = long(os.path.getmtime(self._path(mbx)))
            sz = state['sz'] = long(os.path.getsize(self._path(mbx)))
        except (OSError, IOError):
            mt = sz = state['mt'] = state['sz'] = -1
        mtsz = '%s/%s' % (mt, sz)
        return (mtsz != self.event.data.get('mailbox_state', {}).get(mbx._key))

    def _mark_mailbox_rescanned(self, mbx, state):
        mtsz = '%s/%s' % (state['mt'], state['sz'])
        if 'mailbox_state' in self.event.data:
            self.event.data['mailbox_state'][mbx._key] = mtsz
        else:
            self.event.data['mailbox_state'] = {mbx._key: mtsz}

    def is_mailbox(self, fn):
        try:
            with open(fn, 'rb') as fd:
                data = fd.read(2048)  # No point reading less...
                if data.startswith('From '):
                    # OK, this might be an mbox! Let's check if the first
                    # few lines look like RFC2822 headers...
                    headcount = 0
                    for line in data.splitlines(True)[1:]:
                        if (headcount > 3) and line in ('\n', '\r\n'):
                            return True
                        if line[-1:] == '\n' and line[:1] not in (' ', '\t'):
                            parts = line.split(':')
                            if (len(parts) < 2 or
                                    ' ' in parts[0] or '\t' in parts[0]):
                                return False
                            headcount += 1
                    return (headcount > 3)
        except (IOError, OSError):
            pass
        return False
