import json
import os
import threading
import time

from mailpile.crypto.streamer import EncryptingStreamer, DecryptingStreamer


EVENT_COUNTER_LOCK = threading.Lock()
EVENT_COUNTER = 0


def NewEventId():
    """
    This is guaranteed to generate unique event IDs for up to 1 million
    events per second. Beyond that, all bets are off. :-P
    """
    global EVENT_COUNTER
    try:
        EVENT_COUNTER_LOCK.acquire()
        EVENT_COUNTER = EVENT_COUNTER+1
        EVENT_COUNTER %= 0x100000
        return '%8.8x.%5.5x.%x' % (time.time(), EVENT_COUNTER, os.getpid())
    finally:
        EVENT_COUNTER_LOCK.release()


class Event(object):
    """
    This is a single event in the event log.
    """
    COMPLETE = 'C'
    PENDING = 'P'

    @classmethod
    def Parse(cls, json_string):
        return cls(*json.loads(json_string))

    def __init__(self,
                 ts=None, event_id=None, message='', flags='C',
                 action='', args=[], kwargs={}):
        self.data = [
            int(ts or time.time()),
            event_id or NewEventId(),
            message,
            flags,
            action,
            args,
            kwargs
        ]

    def __str__(self):
        return json.dumps(self.data)

    def _set(self, col, value):
        self.data[0] = int(time.time())
        self.data[col] = value

    ts = property(lambda s: s.data[0], lambda s, v: s.data.__setitem__(0, v))
    event_id = property(lambda s: s.data[1], lambda s, v: s._set(1, v))
    message = property(lambda s: s.data[2], lambda s, v: s._set(2, v))
    flags = property(lambda s: s.data[3], lambda s, v: s._set(3, v))
    action = property(lambda s: s.data[4], lambda s, v: s._set(4, v))
    args = property(lambda s: s.data[5], lambda s, v: s._set(5, v))
    kwargs = property(lambda s: s.data[6], lambda s, v: s._set(6, v))


class EventLog(object):
    """
    This is the Mailpile Event Log.

    The log is written encrypted to disk on an ongoing basis (rotated
    every N lines), but entries are kept in RAM as well. The event log
    allows for recording of incomplete events, to help different parts
    of the app "remember" tasks which have yet to complete or may need
    to be retried.
    """

    def __init__(self, logdir, encryption_key_func, rollover=10240):
        self.logdir = logdir
        self.encryption_key_func = encryption_key_func
        self.rollover = rollover

        self.events = {}

        # Internals...
        self._lock = threading.Lock()
        self._log_fd = None

    def _save_filename(self):
        return os.path.join(self.logdir, self._log_start_id)

    def _open_log(self):
        if self._log_fd:
            self._log_fd.close()

        if not os.path.exists(self.logdir):
            os.mkdir(self.logdir)

        self._log_start_id = NewEventId()
        enc_key = self.encryption_key_func()
        if enc_key:
            self._log_fd = EncryptingStreamer(enc_key, dir=self.logdir)
            self._log_fd.save(self._save_filename(), finish=False)
        else:
            self._log_fd = open(self._save_filename(), 'w', 0)

        # Write any incomplete events to the new file
        for e in self.incomplete():
            self._log_fd.write('%s\n' % e)

        # We're starting over, incomplete events don't count
        self._logged = 0

    def _maybe_rotate_log(self):
        if self._logged > self.rollover:
            self._log_fd.close()
            kept_events = {}
            for e in self.incomplete():
                kept_events[e.event_id] = e
            self.events = kept_events
            self.open_log()

    def _match(self, event, filters):
        return True

    def incomplete(self, **filters):
        """Return all the incomplete events, in order."""
        for ek in sorted(self.events.keys()):
            e = self.events.get(ek, None)
            if (e is not None and
                    e.state != Event.COMPLETE and
                    self._match(e, filters)):
                yield e

    def since(self, ts, **filters):
        """Return all events since a given time, in order."""
        for ek in sorted(self.events.keys()):
            e = self.events.get(ek, None)
            if (e is not None and
                    e.ts >= ts and
                    self._match(e, filters)):
                yield e

    def log_event(self, event):
        """Log an Event object."""
        self._lock.acquire()
        try:
            if not self._log_fd:
                self._open_log()
            self._log_fd.write('%s\n' % event)
            self.events[event.event_id] = event
            self._logged += 1
            self._maybe_rotate_log()
        finally:
            self._lock.release()
        return event

    def log(self, *args, **kwargs):
        """Log a new event."""
        return self.log_event(Event(*args, **kwargs))

    def close(self):
        self._lock.acquire()
        try:
            self._log_fd.close()
            self._log_fd = None
        finally:
            self._lock.release()
