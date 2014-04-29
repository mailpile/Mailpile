import os
import random
import threading
import traceback
import time

from mailpile.eventlog import Event
from mailpile.mailboxes import *


# Brainstorming:  What does a mail source have to do?
#
# It's a thread that watches for new mail. It can do so using one account
# and one data type, so it can be specialized for the task. For example an
# IMAP source. That one connects to the remote server whenever it can,
# checks which remote folders exist and which have messages we haven't
# yet seen. It downloads the ones we're missing, indexes and assigns
# tags to them. Unless they've been deleted locally, then if we're
# syncing it deletes them from the server as well.
#
# So... we have a thread. Inna loop:
#   It connects.
#   A watcher/syncer subroutine starts up.
#     Inna loop:
#       Folders are discovered. Post/update an event if we see folders
#       that we haven't seen before and can't figure out what they are meant
#       to be. Use IDLE or poll for mail. Download new mail, add to index.
#
# Pointers to mail:
#    Indexed mail is identified by a pointer. Currently that's a combo
#    of mailbox ID and an ID within the mailbox.  When the rest of the
#    app wants to load a message, it currently assumes it can access
#    something that looks like a Python mailbox. We aren't actually using
#    much of that interface, so we could rip it out and replace it.
#    Making the ID reference mail sources instead, and delegating to
#    the mail source read/write mail ops might make sense.
#
#
# ... so how do I get there?  Migration:
#
#    Goal: sys.mailbox goes away.
#    Migration: create a bunch of sources, one per mailbox type or
#               group by were in the FS they are.
#    ... so a mbox mail source.
#    ... and a maildir mail source.
#    So we start with Maildir. WERVD and IMAP inherit from that anyway.
#


class BaseMailSource(threading.Thread):
    """
    MailSources take care of managing a group of mailboxes, synchronizing
    the source with Mailpile's local metadata and/or caches.
    """
    DEFAULT_JITTER = 15
    SAVE_STATE_INTERVAL = 3600
    INTERNAL_ERROR_SLEEP = 900

    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.BaseMailSource'

    def __init__(self, session, my_config):
        threading.Thread.__init__(self)
        self.lock = threading.Condition()
        self.my_config = my_config
        self.session = session
        self.alive = None
        self.event = None
        self.jitter = self.DEFAULT_JITTER
        self._last_saved = time.time()  # Saving right away would be silly

    def _pfn(self):
        return 'mail-source.%s' % self.my_config._key

    def _load_state(self):
        config, my_config = self.session.config, self.my_config
        self.lock.acquire()
        try:
            events = list(config.event_log.incomplete(source=self,
                                                      data_id=my_config._key))
            if events:
                self.event = events[0]
            else:
                self.event = config.event_log.log(source=self,
                                                  flags=Event.RUNNING,
                                                  message=_('Starting up'),
                                                  data={'id': my_config._key})
        finally:
            self.lock.release()

    def _save_state(self):
        self.session.config.event_log.log_event(self.event)

    def log_status(self, message):
        self.event.message = message
        self.session.config.event_log.log_event(self.event)

    def _wake_up(self):
        self._sleeping = 0
        #self.lock.acquire()
        #self.lock.notify()
        #self.lock.release()

    def _open(self):
        """Open mailboxes or connect to the remote mail source."""
        raise NotImplemented('Please override _open in %s' % self)

    def _sync_mail(self):
        """Open mailboxes or connect to the remote mail source."""
        raise NotImplemented('Please override _sync_mail in %s' % self)

    def _jitter(self, seconds):
        return seconds + random.randint(0, self.jitter)

    def sleep(self, seconds):
        self._sleeping = seconds
        while self.alive and self._sleeping > 0:
            time.sleep(min(1, self._sleeping))
            self._sleeping -= 1
        return self.alive

    def rescan_mailbox(self, mailbox, force=False):
        return False

    def run(self):
        self.alive = True
        self._load_state()
        self.event.flags = Event.RUNNING
        while self.sleep(self._jitter(self.my_config.interval)):
            try:
                if 'traceback' in self.event.data:
                    del self.event.data['traceback']
                if self._open():
                    self._sync_mail()
                if (self.alive and time.time() >= self._last_saved +
                                                  self.SAVE_STATE_INTERVAL):
                    self._save_state()
            except:
                self.event.data['traceback'] = traceback.format_exc()
                print self.event.data['traceback']
                self.log_status(_('Internal error!  Sleeping...'))
                self.sleep(self.INTERNAL_ERROR_SLEEP)
                # FIXME: Release any held locks?
        self.event.flags = Event.INCOMPLETE
        self.event.message = _('Shutting down')
        self._save_state()

    def quit(self):
        self.alive = False
        self._wake_up()
        

class MboxMailSource(BaseMailSource):
    """
    This is a mail source that watches over one or more Unix mboxes.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.MboxMailSource'

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.watching = -1
        self.mboxes = {}

    def _open(self):
        mailboxes = self.my_config.mailbox.values()
        if self.watching == len(mailboxes):
            return True
        else:
            self.watching = len(mailboxes)

        # Prepare the data section of our event, for keeping state.
        for d in ('mtimes', 'sizes'):
            if d not in self.event.data:
                self.event.data[d] = {}

        self.log_status(_('Watching %d mbox mailboxes') % self.watching)

    def _sync_mail(self):
        """This checks all the mailboxes for new mail!"""
        config = self.session.config
        rescanned = errors = 0
        for mbx in self.my_config.mailbox.values():
            try:
                mt = long(os.path.getmtime(mbx.path))
                sz = long(os.path.getsize(mbx.path))
                if (mt != self.event.data['mtimes'].get(mbx._key) or
                        sz != self.event.data['sizes'].get(mbx._key)):
                    self.lock.acquire()
                    happy = True
                    try:
                        self.event.data['mtimes'][mbx._key] = mt
                        self.event.data['sizes'][mbx._key] = sz
                        self.log_status(_('Reading mailbox %s') % mbx.path)

                        mailbox = config.open_mailbox(self.session, mbx._key)
                        if self.rescan_mailbox(mailbox):
                            rescanned += 1
                        else:
                            errors += 1
                    finally:
                        self.lock.release()
            except (NoSuchMailboxError, IOError, OSError):
                errors += 1
        if errors:
            self.log_status(_('Rescanned %d mailboxes, failed to rescan %d'
                              ) % (rescanned, errors))
        elif rescanned:
            self.log_status(_('Rescanned %d mailboxes') % rescanned)


class MaildirMailSource(BaseMailSource):
    """
    This is a mail source that watches over one or more Maildirs.
    """
    # This is a helper for the events.
    __classname__ = 'mailpile.mail_source.MaildirMailSource'

    def __init__(self, *args, **kwargs):
        BaseMailSource.__init__(self, *args, **kwargs)
        self.watching = -1
        self.mboxes = {}

    def _open(self):
        return True

    def _sync_mail(self):
        return True


def MailSource(session, my_config):
    # FIXME: check the plugin and instanciate the right kind of mail source
    #        for this config section.
    pass
