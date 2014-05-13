import os

from mailpile.mail_source import BaseMailSource


class MboxMailSource(BaseMailSource):
    """
    This is a mail source that watches over one or more Unix mboxes.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.mbox.MboxMailSource'

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.watching = -1

    def _unlocked_open(self):
        mailboxes = self.my_config.mailbox.values()
        if self.watching == len(mailboxes):
            return True
        else:
            self.watching = len(mailboxes)

        # Prepare the data section of our event, for keeping state.
        for d in ('mtimes', 'sizes'):
            if d not in self.event.data:
                self.event.data[d] = {}

        self._log_status(_('Watching %d mbox mailboxes') % self.watching)
        return True

    def _has_mailbox_changed(self, mbx, state):
        mt = state['mt'] = long(os.path.getmtime(mbx.path))
        sz = state['sz'] = long(os.path.getsize(mbx.path))
        return (mt != self.event.data['mtimes'].get(mbx._key) or
                sz != self.event.data['sizes'].get(mbx._key))

    def _mark_mailbox_rescanned(self, mbx, state):
        self.event.data['mtimes'][mbx._key] = state['mt']
        self.event.data['sizes'][mbx._key] = state['sz']

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
