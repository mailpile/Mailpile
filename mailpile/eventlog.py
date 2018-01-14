import copy
import datetime
import json
import os
import threading
import time
from email.utils import formatdate, parsedate_tz, mktime_tz

from mailpile.crypto.streamer import EncryptingStreamer, DecryptingStreamer
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import EventRLock, EventLock, CleanText, json_helper
from mailpile.util import safe_remove, thread_context


EVENT_COUNTER_LOCK = threading.Lock()
EVENT_COUNTER = 0



def NewEventId():
    """
    This is guaranteed to generate unique event IDs for up to 1 million
    events per second. Beyond that, all bets are off. :-P
    """
    global EVENT_COUNTER
    with EVENT_COUNTER_LOCK:
        EVENT_COUNTER = EVENT_COUNTER+1
        EVENT_COUNTER %= 0x100000
        return '%8.8x-%5.5x-%x' % (time.time(), EVENT_COUNTER, os.getpid())


def _ClassName(obj, ignore_regexps=False):
    if isinstance(obj, (str, unicode)):
        return str(obj).replace('mailpile.', '.')
    elif hasattr(obj, '__classname__'):
        return str(obj.__classname__).replace('mailpile.', '.')
    elif ignore_regexps and 'SRE_Pattern' in str(obj.__class__):
        return obj
    else:
        module = str(obj.__class__.__module__)
        if module.startswith('mailpile.'):
            module = module[len('mailpile'):]
        return '%s.%s' % (module, str(obj.__class__.__name__))


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
                   '<b class="event_message">%(message)s</b></li>')
    PRIVATE_HTML = PUBLIC_HTML
    POSTAMBLE_HTML = '</ul>'

    @classmethod
    def Parse(cls, json_string):
        try:
            return cls(*json.loads(json_string))
        except:
            return cls()

    def __init__(self,
                 ts=None, event_id=None, flags='c', message='',
                 source=None, data=None, private_data=None):
        self._data = [
            '',
            (event_id or NewEventId()).replace('.', '-'),
            flags,
            message,
            _ClassName(source),
            data or {},
            private_data or {},
        ]
        self._set_ts(ts or time.time())

    def __str__(self):
        return json.dumps(self._data, default=json_helper)

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
        try:
            module_name, class_name = CleanText(self.source,
                                                banned=CleanText.NONDNS
                                                ).clean.rsplit('.', 1)
            if module_name.startswith('.'):
                module_name = 'mailpile' + module_name
            module = __import__(module_name, globals(), locals(), class_name)
            return getattr(module, class_name)
        except (ValueError, AttributeError, ImportError):
            return None

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

    def as_text(self, private=True, compact=False):
        try:
            return self.source_class.EventAsText(self, private=private,
                                                       compact=True)
        except (AttributeError, NameError):
            if compact:
                return '%s=%s:%s %s' % (self.event_id,
                                        self.source.split('.')[-1],
                                        self.flags, self.message)
            else:
                return json.dumps(self.as_dict(private=private),
                                  default=json_helper)

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


def GetThreadEvent(create=False, message=None, source=None):
    ctx = thread_context()
    if ctx and 'event' in ctx[-1]:
        return ctx[-1]['event']
    elif create:
        return Event(message=message, source=source)
    else:
        return None


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

    def __init__(self, logdir, decryption_key_func, encryption_key_func,
                 rollover=1024):
        self.logdir = logdir
        self.decryption_key_func = decryption_key_func or (lambda: None)
        self.encryption_key_func = encryption_key_func or (lambda: None)
        self.rollover = rollover

        self._events = {}

        # Internals...
        self._watching_uis = []
        self._waiter = threading.Condition(EventRLock())
        self._lock = EventLock()
        self._log_fd = None

    def _notify_waiters(self):
        with self._waiter:
            self._waiter.notifyAll()

    def wait(self, timeout=None):
        with self._waiter:
            self._waiter.wait(timeout)

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
            self._log_fd = EncryptingStreamer(enc_key,
                                              dir=self.logdir,
                                              name='EventLog/ES',
                                              use_filter=False,
                                              long_running=True)
            self._log_fd.save(self._save_filename(), finish=False)
            self._log_write = self._log_fd.write_pad_and_flush
        else:
            self._log_fd = open(self._save_filename(), 'wb', 0)
            self._log_write = self._log_fd.write

        # Write any incomplete events to the new file
        for e in self.incomplete():
            self._log_write('%s\n')

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

    def _save_events(self, events, recursed=False):
        if not self._log_fd:
            self._open_log()
        events.sort(key=lambda ev: ev.ts)
        try:
            for event in events:
                self._log_write('%s\n' % event)
                self._events[event.event_id] = event
        except IOError:
            if recursed:
                raise
            else:
                self._unlocked_close()
                return self._save_events(events, recursed=True)

    def _load_logfile(self, lfn):
        enc_key = self.decryption_key_func()
        with open(os.path.join(self.logdir, lfn)) as fd:
            if enc_key:
                with DecryptingStreamer(fd, mep_key=enc_key,
                                        name='EventLog/DS(%s)' % lfn
                                        ) as streamer:
                    lines = streamer.read()
                    streamer.verify(_raise=IOError)
            else:
                lines = fd.read()
            if lines:
                for line in lines.splitlines():
                    event = Event.Parse(line.strip())
                    self._events[event.event_id] = event

    def _match(self, event, filters):
        def compare(val, rule):
            if isinstance(rule, (str, unicode)):
                return unicode(val) == unicode(rule)
            else:
                return rule.match(unicode(val)) is not None
        for kw, rule in filters.iteritems():
            if kw.endswith('!'):
                truth, okw, kw = False, kw, kw[:-1]
            else:
                truth, okw = True, kw
            if kw == 'source':
                if truth != compare(event.source,
                                    _ClassName(rule, ignore_regexps=True)):
                    return False
            elif kw == 'flag':
                if truth != (rule in event.flags):
                    return False
            elif kw == 'flags':
                if truth != compare(event.flags, rule):
                    return False
            elif kw == 'event_id':
                if truth != compare(event.event_id, rule):
                    return False
            elif kw == 'since':
                when = float(rule)
                if when < 0:
                    when += time.time()
                if truth != (event.ts > when):
                    return False
            elif kw.startswith('data_'):
                if truth != compare(event.data.get(kw[5:]), rule):
                    return False
            elif kw.startswith('private_data_'):
                if truth != compare(event.data.get(kw[13:]), rule):
                    return False
            else:
                # Unknown keywords match nothing...
                print 'Unknown keyword: `%s=%s`' % (okw, rule)
                return False
        return True

    def incomplete(self, **filters):
        """Return all the incomplete events, in order."""
        if 'event_id' in filters:
            ids = [filters['event_id']]
        else:
            ids = sorted(self._events.keys())
        for ek in ids:
            e = self._events.get(ek, None)
            if (e is not None and
                    Event.COMPLETE not in e.flags and
                    self._match(e, filters)):
                yield e

    def since(self, ts, **filters):
        """Return all events since a given time, in order."""
        if ts < 0:
            ts += time.time()
        if 'event_id' in filters and filters['event_id'][:1] != '!':
            ids = [filters['event_id']]
        else:
            ids = sorted(self._events.keys())
        for ek in ids:
            e = self._events.get(ek, None)
            if (e is not None and
                    e.ts >= ts and
                    self._match(e, filters)):
                yield e

    def events(self, **filters):
        return self.since(0, **filters)

    def get(self, event_id, default=None):
        return self._events.get(event_id, default)

    def log_event(self, event):
        """Log an Event object."""
        with self._lock:
            self._save_events([event])
            self._logged += 1
            self._maybe_rotate_log()
            self._notify_waiters()
            for ui in self._watching_uis:
                ui.notify(event.as_text(compact=True))
        return event

    def log(self, *args, **kwargs):
        """Log a new event."""
        return self.log_event(Event(*args, **kwargs))

    def close(self):
        with self._lock:
            return self._unlocked_close()

    def _unlocked_close(self):
        try:
            self._log_fd.close()
            self._log_fd = None
        except (OSError, IOError):
            pass

    def _prune_completed(self):
        for event_id in self._events.keys():
            if Event.COMPLETE in self._events[event_id].flags:
                del self._events[event_id]

    def ui_watch(self, ui):
        while ui.log_parent is not None:
            ui = ui.log_parent
        if ui not in self._watching_uis:
            self._watching_uis.append(ui)
            return True
        else:
            return False

    def ui_unwatch(self, ui):
        while ui.log_parent is not None:
            ui = ui.log_parent
        try:
            self._watching_uis.remove(ui)
        except ValueError:
            pass

    def load(self):
        with self._lock:
            self._open_log()
            for lf in self._list_logfiles()[-4:]:
                try:
                    self._load_logfile(lf)
                except (OSError, IOError):
                    # Nothing we can do, no point complaining...
                    pass
            self._prune_completed()
            self._save_events(self._events.values())
            return self

    def purge_old_logfiles(self, keep=None):
        keep = keep or self.KEEP_LOGS
        for lf in self._list_logfiles()[:-keep]:
            try:
                safe_remove(os.path.join(self.logdir, lf))
            except OSError:
                pass
