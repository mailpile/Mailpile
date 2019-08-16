from __future__ import print_function
import time
import icalendar
from datetime import datetime

def calendar_parse(payload):
    c = icalendar.parser.Contentlines()
    lines = c.from_ical(payload)

    root = None
    obj = None

    for line in lines:
        if line == "":
            break
        parts = line.parts()
        if parts[0] == "BEGIN":
            t = vmap[parts[2]]()
            if not root: root = t
            if obj:
                obj.children.append(t)
                t.parent = obj
            obj = t

            root.stack.append(parts[2])
            continue
        if parts[0] == "END":
            obj = obj.parent
            root.stack.pop()
            continue

        obj.add_part(*parts)

    return root.to_json()

class VObject:
    def __init__(self):
        self.children = []
        self.parent = None
        self.stack = []
        self.parts = []

    def add_part(self, key, params, value):
        self.parts.append([key, params, value])

    def find_parts(self, key):
        res = []
        for p in self.parts:
            if p[0] == key:
                res.append(p)
        return res

    def find_one_part(self, key):
        res = self.find_parts(key)
        if len(res) == 0: return None
        r = {"value": res[0][2], "params": res[0][1] }
        return r

    def find_one_part_value(self, key, value=None):
        res = self.find_parts(key)
        if len(res) == 0: return value
        return res[0][2]

    def get_datetime(self, key):
        val = self.find_one_part_value(key)
        try:
            return datetime(*time.strptime(val, "%Y%m%dT%H%M%SZ")[:6])
        except:
            return datetime(*time.strptime(val, "%Y%m%dT%H%M%S")[:6])

    def to_raw_json(self):
        parts = {}
        for p in self.parts:
            if p[0] not in parts:
                parts[p[0]] = []
            parts[p[0]].append({"value": p[2], "parameters": p[1]})

        children = [x.to_raw_json() for x in self.children]
        return {
            "type": self.__class__.__name__,
            "children": children,
            "parts": parts,
        }

    def to_json(self):
        return to_raw_json()

class VTimeZone(VObject):
    pass

class VTZStandard(VObject):
    pass

class VTZDaylight(VObject):
    pass

class VAlarm(VObject):
    pass

class VEvent(VObject):
    def __init__(self):
        VObject.__init__(self)

    def to_json(self):
        summary = self.find_one_part_value("SUMMARY", "")
        description = self.find_one_part_value("DESCRIPTION", "").replace("\\n", "\n").replace("\n\n", "\n")
        dtstart = self.get_datetime("DTSTART")
        dtend = self.get_datetime("DTEND")
        location = self.find_one_part_value("LOCATION", "")
        attendees = [{"cn": x[1]["cn"], "email": x[2].split(":")[1]}
                     for x in self.find_parts("ATTENDEE")]
        o = self.find_one_part("ORGANIZER")
        organizer = { "cn": o["params"]["CN"], "email": o["value"].split(":")[1]}
        tzinfo = None

        return {
            "summary": summary,
            "description": description,
            "dtstart": dtstart,
            "dtend": dtend,
            "location": location,
            "timezone": tzinfo,
            "organizer": organizer,
            "attendees": attendees,
            "alarms": [],
        }

class VCalendar(VObject):
    def __init__(self):
        VObject.__init__(self)

    def print_events(self):
        for e in self.children:
            if isinstance(e, VEvent):
                print("%s invited you to %s" % (e.find_parts("ORGANIZER")[0][1]['CN'],
                 e.find_parts("SUMMARY")[0][2]))
                print("%s" % e.find_parts("DTSTART")[0][2])
                print("%s" % e.find_parts("LOCATION")[0][2])

    def to_json(self):
        events = []
        for e in self.children:
            # We are assuming VEvents will only occur immediately under the
            # VCalendar level. Haven't seen anything else in the wild.
            if isinstance(e, VEvent):
                events.append(e.to_json())

        return events


vmap = {
    "VALARM": VAlarm,
    "VTIMEZONE": VTimeZone,
    "VEVENT": VEvent,
    "VCALENDAR": VCalendar,
    "STANDARD": VTZStandard,
    "DAYLIGHT": VTZDaylight,
}

if __name__ == "__main__":
    cal = calendar_parse(open("calitem.cal").read())
    # cal.print_tree()
    print("------------------------------")
    cal.print_events()
    print("------------------------------")
