#!/usr/bin/python
import sys
import re

msgid_re = re.compile('(?im)^message-id:')
messages = []
msgids = []
buf = '\n'
pos = -1

def find_message_id(buf, LE, LFLF):
    be = buf.find(LFLF)
    mp = buf[:be].find('\nMessage-I')
    if mp >= 0 and buf[mp + 10:mp + 12].lower() == 'd:':
        return buf[mp + 1:mp + buf[mp + 1:mp + 150].find(LE) + 1]

    mp = buf[:be].lower().find('\nmessage-id:')
    if mp >= 0:
        return buf[mp + 1:mp + buf[mp + 1:mp + 150].find(LE) + 1]

    return None


DELIM = '\nFrom '
READS = 4 * 64 * 1024
with open(sys.argv[1], 'rb') as fd:
    chunk = fd.read(READS)
    LE, LFLF = ('\r', '\r\n\r\n') if ('\r\n' in chunk) else ('\n', '\n\n')
    while len(chunk) > 0:
        buf += chunk
        if msgids and not msgids[-1]:
            # Search for Message-ID again if it wasn't found on last pass
            msgids[-1] = find_message_id(buf, LE, LFLF)

        # Make a note of all messages in this buffer...
        splits = buf.split(DELIM)
        buf = splits.pop(0)
        for split in splits:
            pos += len(buf) + len(DELIM) 
            buf = split
            messages.append(pos - len(DELIM) + 1)
            msgids.append(find_message_id(buf, LE, LFLF))

        pos += len(buf) - min(128, len(buf))
        buf = buf[-128:]
        assert(fd.tell() == pos + len(buf))
        chunk = fd.read(READS)


print ('Done, found %d messages, %d msgids'
       ) % (len(messages), len([1 for mi in msgids if mi]))
for i in range(0, 20):
    print '%d/%d = %s' % (i * 13, messages[i], msgids[i * 13])
