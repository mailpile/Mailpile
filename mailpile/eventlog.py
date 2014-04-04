import copy
import datetime
import json
import os
import threading
import time
from email.utils import formatdate, parsedate_tz, mktime_tz

from mailpile.crypto.streamer import EncryptingStreamer, DecryptingStreamer
from mailpile.util import CleanText


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


def _ClassName(obj):
    if isinstance(obj, (str, unicode)):
        return str(obj).replace('mailpile.', '.')
    else:
        return str(obj.__class__).replace('mailpile.', '.')


class Event(object):
    """
    This is a single event in the event log. Actual interpretation and
    rendering of events should be handled by the respective source class.
    """
    RUNNING = 'R'
    COMPLETE = 'c'
    INCOMPLETE = 'i'
    FUTURE = 'F'

    # For now these live here, we may templatize this later.
    PREAMBLE_HTML = '<ul class="events">'
    PUBLIC_HTML = ('<li><span class="event_date">%(date)s</span> '
                   '<b class="event_message">%(message)s</b> '
                   '<i class="event_elapsed">%(elapsed)sms</i></li>')
    PRIVATE_HTML = PUBLIC_HTML
    POSTAMBLE_HTML = '</ul>'

    @classmethod
    def Parse(cls, json_string):
        return cls(*json.loads(json_string))

    def __init__(self,
                 ts=None, event_id=None, flags='C', message='',
                 source=None, data={}, private_data={}):
        self._data = [
            '',
            event_id or NewEventId(),
            flags,
            message,
            _ClassName(source),
            data,
            private_data,
        ]
        self._set_ts(ts or time.time())

    def __str__(self):
        return json.dumps(self._data)

    def _set_ts(self, ts):
        if hasattr(ts, 'timetuple'):
            self._ts = int(time.mktime(ts.timetuple()))
        elif isinstance(ts, (str, unicode)):
            self._ts = int(mktime_tz(parsedate_tz(ts)))
        else:
            self._ts = float(ts)
        self._data[0] = formatdate(self._ts)

    def _set(self, col, value):
        self._set_ts(time.time())
        self._data[col] = value

    def _get_source_class(self):
        module_name, class_name = CleanText(self.source,
                                            banned=CleanText.NONDNS
                                            ).clean.rsplit('.', 1)
        if module_name.startswith('.'):
            module_name = 'mailpile' + module_name
        module = __import__(module_name, globals(), locals(), class_name)
        return getattr(module, class_name)

    date = property(lambda s: s._data[0], lambda s, v: s._set_ts(v))
    ts = property(lambda s: s._ts, lambda s, v: s._set_ts(v))
    event_id = property(lambda s: s._data[1], lambda s, v: s._set(1, v))
    flags = property(lambda s: s._data[2], lambda s, v: s._set(2, v))
    message = property(lambda s: s._data[3], lambda s, v: s._set(3, v))
    source = property(lambda s: s._data[4],
                      lambda s, v: s._set(4, _ClassName(v)))
    data = property(lambda s: s._data[5], lambda s, v: s._set(5, v))
    private_data = property(lambda s: s._data[6], lambda s, v: s._set(6, v))
    source_class = property(_get_source_class)

    def as_dict(self, private=True):
        try:
            return self.source_class.EventAsDict(self, private=private)
        except (AttributeError, NameError):
            data = {
                'ts': self.ts,
                'date': self.date,
                'event_id': self.event_id,
                'message': self.message,
                'flags': self.flags,
                'source': self.source,
                'data': self.data
            }
            if private:
                data['private_data'] = self.private_data
            return data

    def as_json(self, private=True):
        try:
            return self.source_class.EventAsJson(self, private=private)
        except (AttributeError, NameError):
            return json.dumps(self.as_dict(private=private))

    def as_html(self, private=True):
        try:
            return self.source_class.EventAsHtml(self, private=private)
        except (AttributeError, NameError):
            if private:
                return self.PRIVATE_HTML % self.as_dict(private=True)
            else:
                return self.PUBLIC_HTML % self.as_dict(private=False)


class EventLog(object):
    """
    This is the Mailpile Event Log.

    The log is written encrypted to disk on an ongoing basis (rotated
    every N lines), but entries are kept in RAM as well. The event log
    allows for recording of incomplete events, to help different parts
    of the app "remember" tasks which have yet to complete or may need
    to be retried.
    """
    KEEP_LOGS = 2

    def __init__(self, logdir, encryption_key_func, rollover=10240):
        self.logdir = logdir
        self.encryption_key_func = encryption_key_func
        self.rollover = rollover

        self._events = {}

        # Internals...
        self._waiter = threading.Condition()
        self._lock = threading.Lock()
        self._log_fd = None

    def _notify_waiters(self):
        self._waiter.acquire()
        self._waiter.notifyAll()
        self._waiter.release()

    def wait(self, timeout=None):
        self._waiter.acquire()
        self._waiter.wait(timeout)
        self._waiter.release()

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
            self._events = kept_events
            self._open_log()
            self.purge_old_logfiles()

    def _list_logfiles(self):
        return sorted([l for l in os.listdir(self.logdir)
                       if not l.startswith('.')])

    def _save_events(self, events):
        if not self._log_fd:
            self._open_log()
        events.sort(key=lambda ev: ev.ts)
        for event in events:
            self._log_fd.write('%s\n' % event)
            self._events[event.event_id] = event

    def _load_logfile(self, lfn):
        enc_key = self.encryption_key_func()
        with open(os.path.join(self.logdir, lfn)) as fd:
            if enc_key:
                lines = fd.read()
            else:
                with DecryptingStreamer(enc_key, fd) as streamer:
                    lines = streamer.read()
            if lines:
                for line in lines.splitlines():
                    event = Event.Parse(line)
                    if Event.COMPLETE in event.flags:
                        if event.event_id in self._events:
                            del self._events[event.event_id]
                    else:
                        self._events[event.event_id] = event
        self._save_events(self._events.values())

    def _match(self, event, filters):
        for kw, rule in filters.iteritems():
            if kw.endswith('!'):
                truth, okw, kw = False, kw, kw[:-1]
            else:
                truth, okw = True, kw
            if kw == 'source':
                if truth != (event.source == _ClassName(rule)):
                    return False
            elif kw == 'flag':
                if truth != (rule in event.flags):
                    return False
            elif kw == 'flags':
                if truth != (event.flags == rule):
                    return False
            elif kw == 'since':
                if truth != (event.ts > float(rule)):
                    return False
            elif kw.startswith('data_'):
                if truth != (str(event.data.get(kw[5:])) == str(rule)):
                    return False
            elif kw.startswith('private_data_'):
                if truth != (str(event.data.get(kw[13:])) == str(rule)):
                    return False
            else:
                # Unknown keywords match nothing...
                print 'Unknown keyword: `%s=%s`' % (okw, rule)
                return False
        return True

    def incomplete(self, **filters):
        """Return all the incomplete events, in order."""
        for ek in sorted(self._events.keys()):
            e = self._events.get(ek, None)
            if (e is not None and
                    Event.COMPLETE not in e.flags and
                    self._match(e, filters)):
                yield e

    def since(self, ts, **filters):
        """Return all events since a given time, in order."""
        for ek in sorted(self._events.keys()):
            e = self._events.get(ek, None)
            if (e is not None and
                    e.ts >= ts and
                    self._match(e, filters)):
                yield e

    def events(self, **filters):
        return self.since(0, **filters)

    def log_event(self, event):
        """Log an Event object."""
        self._lock.acquire()
        try:
            self._save_events([event])
            self._logged += 1
            self._maybe_rotate_log()
            self._notify_waiters()
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

    def load(self):
        self._lock.acquire()
        try:
            self._open_log()
            for lf in self._list_logfiles()[-4:]:
                try:
                    self._load_logfile(lf)
                except (OSError, IOError):
                    import traceback
                    traceback.print_exc()
            return self
        finally:
            self._lock.release()

    def purge_old_logfiles(self, keep=None):
        keep = keep or self.KEEP_LOGS
        for lf in self._list_logfiles()[:-keep]:
            try:
                os.remove(os.path.join(self.logdir, lf))
            except OSError:
                pass
