import unittest
import mailpile
import re
import json
import os
import threading
import time

from nose.tools import raises
from mailpile.tests import MailPileUnittest


EVENT_ID_RE = re.compile("[a-f0-9]{8}\.[a-f0-9]{5}\.[a-f0-9]+")

mailpile_root = os.path.join(os.path.dirname(__file__), "..", "..")
mailpile_tmp  = os.path.join(mailpile_root, "mailpile", "tests", "data", "tmp")

class TestEventlog(MailPileUnittest):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    #
    # eventlog.NewEventId should generate unique event ids
    #
    # FIXME: threading?
    def test_NewEventId(self):
        events = []
        for i in range(100):
            eid = mailpile.eventlog.NewEventId()
            self.assertFalse(events.__contains__(eid))
            self.assertIsNotNone( EVENT_ID_RE.match(eid) )
            events.append(eid)


    #
    # eventlog._ClassName should return the class name of an object and remove mailpile from its inheritance hierarchy
    #
    def test_ClassName(self):
        evt = mailpile.eventlog.Event()
        str_klass_name = str(evt.__class__)
        kn = mailpile.eventlog._ClassName(evt)
        self.assertGreater(str_klass_name.find("mailpile"), 0)
        self.assertGreater(kn.find("eventlog.Event"), 0)
        self.assertEqual(kn.find("mailpile"), -1)

    def test_ClassName_unicode(self):
        evt = mailpile.eventlog.Event()
        u_klass_name = unicode(evt.__class__)
        kn = mailpile.eventlog._ClassName(u_klass_name)
        self.assertGreater( u_klass_name.find("mailpile"), 0)
        self.assertGreater( kn.find("eventlog.Event"), 0)
        self.assertEqual( kn.find("mailpile"), -1)


    #
    # eventlog.Event should create an event for a given object with the following attributes:
    #   event_id
    #   ts
    #   date
    #   message
    #   data
    #   private_data
    #   flags
    #   source
    #

    def test_event_Parse(self):
        evt_id = mailpile.eventlog.NewEventId()
        msg = "test: A Test Event Message"
        cmd = ".commands.Load"
        data = { "test" : "test data" }
        date = "Sun, 27 Apr 2014 14:32:08 -0000"
        evt_string =[date, evt_id, "c", msg, cmd, data, {}]
        json_data = json.dumps(evt_string)
        e = mailpile.eventlog.Event.Parse(json_data)
        self.assertEqual( e.data, data)
        self.assertEqual( e.event_id, evt_id )
        self.assertEqual( e.source, cmd )
        self.assertEqual( e.message, msg )

    def test_event_Parse_invalid(self):
        e = mailpile.eventlog.Event.Parse("all exceptions are caught")
        self.assertEqual(e.__class__, mailpile.eventlog.Event)

    def test_event_as_dict(self):
        cmd = self.mp.help()
        evt = mailpile.eventlog.Event(source=cmd, data={ 'name' : 'testing'}, message="hello world", private_data={ 'x' : 22})
        res = evt.as_dict()
        self.assertEqual(res['message'], "hello world")
        self.assertEqual(res['data'], { 'name' : 'testing'})
        self.assertIsNotNone( EVENT_ID_RE.match(res['event_id']) )
        self.assertEqual(res['private_data'], { 'x' : 22})
        self.assertIsNotNone( res['flags'] )
        self.assertIsNotNone( res['source'] )
        self.assertIsNotNone( res['date'] )
        self.assertTrue( isinstance(res['ts'], float) )

    def test_event_as_dict_no_private(self):
        cmd = self.mp.help()
        evt = mailpile.eventlog.Event(source=cmd, data={ 'name' : 'testing'}, message="hello world", private_data={ 'x' : 22})
        res = evt.as_dict(private=False)
        self.assertFalse( "private_data" in res )


    def test_event_as_json(self):
        cmd = self.mp.help()
        evt = mailpile.eventlog.Event(source=cmd, data={ 'name' : 'testing'}, message="hello world", private_data={ 'x' : 22})
        json_res = evt.as_json()
        res = json.loads(json_res)
        self.assertEqual(res['message'], "hello world")
        self.assertEqual(res['data'], { 'name' : 'testing'})
        self.assertIsNotNone( EVENT_ID_RE.match(res['event_id']) )
        self.assertEqual(res['private_data'], { 'x' : 22})
        self.assertIsNotNone( res['flags'] )
        self.assertIsNotNone( res['source'] )
        self.assertIsNotNone( res['date'] )
        self.assertTrue( isinstance(res['ts'], float) )

    def test_event_as_json_no_private(self):
        cmd = self.mp.help()
        evt = mailpile.eventlog.Event(source=cmd, data={ 'name' : 'testing'}, message="hello world", private_data={ 'x' : 22})
        json_res = evt.as_json(private=False)
        res = json.loads(json_res)
        self.assertFalse( "private_data" in res )

    #
    # Event.as_html() should return a html string containing the date and message
    #
    def test_event_as_html(self):
        cmd = self.mp.help()
        evt = mailpile.eventlog.Event(source=cmd, data={ 'name' : 'testing'}, message="hello world", private_data={ 'x' : 22})
        raw_html_private = evt.as_html()
        raw_html_public  = evt.as_html(False)
        self.assertGreater(raw_html_private.find(evt.date), 0)
        self.assertGreater(raw_html_private.find(evt.message), 0)
        self.assertGreater(raw_html_public.find(evt.date), 0)
        self.assertGreater(raw_html_public.find(evt.message), 0)

    #
    # EventLog should be written encrypted to disk, rotated every N lines and stored in RAM
    #
    def test_eventlog(self):
        rotate_lines = 100
        evt_log = mailpile.eventlog.EventLog(mailpile_tmp,
                                             lambda: False,
                                             lambda: False, rotate_lines)
        self.assertEqual(len(evt_log._events), 0)
        evt = mailpile.eventlog.Event(source=self.mp.help(), data={},
                                      message="test-event")
        evt_log.log_event(evt)
        self.assertEqual(len(evt_log._events), 1)
