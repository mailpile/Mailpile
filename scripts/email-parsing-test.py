#!/usr/bin/python
#
# This is code which tries very hard to interpret the From:, To: and Cc:
# lines found in real-world e-mail addresses and make sense of them.
#
# The general strategy of this script is to:
#    1. parse header into tokens
#    2. group tokens together into address + name constructs
#    3. normalize each group to a standard format
#
# In practice, we do this in two passes - first a strict pass where we try
# to parse things semi-sensibly.  If that fails, there is a second pass
# where we try to cope with certain types of weirdness we've seen in the
# wild. The wild can be pretty wild.
#
# This parser is NOT fully RFC2822 compliant - in particular it will get
# confused by nested comments (see FIXME in tests below).
#
import re
import os
import sys
import quopri
import base64
import traceback


TEST_INPUT = """\
bre@klaki.net  ,
  bre@klaki.net Bjarni ,
bre@klaki.net bre@klaki.net,
bre@klaki.net (bre@notmail.com),
bre@klaki.net ((nested) bre@notmail.com comment),
(FIXME: (nested) bre@wrongmail.com parser breaker) bre@klaki.net,
undisclosed-recipients-gets-ignored:,
Bjarni [mailto:bre@klaki.net],
bre@klaki.net (Bjarni Runar Einar's son);
Bjarni =?iso-8859-1?Q?Runar?=Einarsson<' bre'@ klaki.net>,
"""
TEST_EXPECT = """\
<bre@klaki.net>,
"Bjarni" <bre@klaki.net>,
"bre@klaki.net" <bre@klaki.net>,
"bre@notmail.com" <bre@klaki.net>,
"(nested bre@notmail.com comment)" <bre@klaki.net>,
"(FIXME: nested parser breaker) bre@klaki.net" <bre@wrongmail.com>,
"Bjarni" <bre@klaki.net>,
"Bjarni Runar Einar\\'s son" <bre@klaki.net>,
"Bjarni Runar Einarsson" <bre@klaki.net>
"""


QUOTE_RE = '=\\?([^\\?\\s]+)\\?([QqBb])\\?([^\\?\\s]+)\\?='
QUOTE_RE_NG = QUOTE_RE.replace('(', '(?:')
TOKENSPACERS = [re.compile('(\S)(<)'),
                re.compile('(\S)(=\\?)')]
TOKENIZER = re.compile('(<[^<>]*>'                      # <stuff>
                       '|\\([^\\(\\)]*\\)'              # (stuff)
                       '|\\[[^\\[\\]]*\\]'              # [stuff]
                       '|"(?:\\\\\\\\|\\\\"|[^"])*"'    # "stuff"
                       "|'(?:\\\\\\\\|\\\\'|[^'])*'"    # 'stuff'
                       '|' + QUOTE_RE_NG +              # =?stuff?=
                       '|,'                             # ,
                       '|;'                             # ;
                       '|\\s+'                          # white space
                       '|[^\\s;,]+'                     # non-white space
                       ')')

MUNGE_STRIP = re.compile('[\\s"\']')

ESCAPES = re.compile('\\\\([\\\\"\'])')
QUOTED = re.compile(QUOTE_RE)
SHOULD_ESCAPE = re.compile('([\\\\"\'])')
MAYBE_EMAIL = re.compile('^[^()<>@,;:\\\\"\\[\\]\\s\000-\031]+'
                         '@[a-zA-Z0-9_\\.-]+$')


def unquote(string, charsets=None):
    def uq(m):
        cs, how, data = m.group(1), m.group(2), m.group(3)
        if how in ('b', 'B'):
            return base64.b64decode(data).decode(cs).encode('utf-8')
        else:
            return quopri.decodestring(data, header=True
                                       ).decode(cs).encode('utf-8')

    for cs in charsets or ('iso-8859-1', 'utf-8'):
         try:
             string = string.decode(cs).encode('utf-8')
             break
         except UnicodeDecodeError:
             pass

    return re.sub(QUOTED, uq, string)

def unescape(string):
    return re.sub(ESCAPES, lambda m: m.group(1), string)

def escape(string):
    string = re.sub(SHOULD_ESCAPE, lambda m: '\\'+m.group(0), string)
    # If not plain ASCII, encode.
    return string


def tokenize(string, spacers=None):
    for ts in spacers or []:
         string = re.sub(ts, '\\1 \\2', string)
    return re.findall(TOKENIZER, string)

def cleaner(token):
    if token[:1] in ('"', "'"):
        if token[:1] == token[-1:]:
            return unescape(token[1:-1])
    elif token.startswith('[mailto:') and token[-1:] == ']':
        # Just convert [mailto:...] crap into a <address>
        return '<%s>' % token[8:-1]
    elif (token[:1] == '[' and token[-1:] == ']'):
        return token[1:-1]
    return token

def group(tokens):
    groups = [[]]
    for token in tokens:
        token = token.strip()
        if token in (',', ';'):
            # Those tokens SHOULD separate groups, but we don't like to
            # create groups that have no e-mail addresses at all.
            if groups[-1]:
                if [g for g in groups[-1] if '@' in g]:
                    groups.append([])
                    continue
                # However, this stuff is just begging to be ignored.
                elif [g for g in groups[-1] if 'undisclosed' in g.lower()]:
                    groups[-1] = []
                    continue
        if token:
            groups[-1].append(unquote(cleaner(token)))
    if not groups[-1]:
        groups.pop(-1)
    return groups

def normalize(g, _raise=False, munge=False):
    if g:
        g = g[:]
    else:
        return ''

    def email_at(i):
        for j in range(0, len(g)):
            if g[j][:1] == '(' and g[j][-1:] == ')':
                g[j] = g[j][1:-1]
        rest = ' '.join([g[j] for j in range(0, len(g)) if j != i
                         ]).replace(' ,', ',').replace(' ;', ';')
        if rest:
            return '"%s" %s' % (escape(rest.strip()), g[i])
        else:
            return g[i]

    def munger(string):
        if munge:
            return re.sub(MUNGE_STRIP, '', string)
        else:
            return string

    for i in range(0, len(g)):
        if g[i][:1] == '<' and g[i][-1:] == '>':
            maybemail = munger(g[i][1:-1])
            if re.match(MAYBE_EMAIL, maybemail):
                g[i] = '<%s>' % maybemail
                return email_at(i)

    for i in range(0, len(g)):
        maybemail = munger(g[i])
        if re.match(MAYBE_EMAIL, maybemail):
            g[i] = '<%s>' % maybemail
            return email_at(i)

    if _raise: raise ValueError('No email found in %s' % (g,))
    return None

def normalize_all(string, _raise=False):
    try:
        nv = [normalize(g, _raise=True) for g in group(tokenize(string))]
    except ValueError:
        nv = [normalize(g, _raise=_raise, munge=True)
              for g in group(tokenize(string, spacers=TOKENSPACERS))]
    return [n for n in nv if n]


# Run tests
test_result = ',\n'.join(normalize_all(TEST_INPUT))
if test_result.strip() != TEST_EXPECT.strip():
    sys.stderr.write('--- TEST FAILED, GOT ---\n%s\n' % test_result)
    sys.exit(1)


# Parse input
headers, header, inheader = {}, None, False
for line in sys.stdin:
    if inheader:
        if line in ('\n', '\r\n'):
            for hdr in ('from', 'to', 'cc'):
                val = headers.get(hdr, '').replace('\n', ' ').strip()
                if val:
                    try:
                        norm = normalize_all(val, _raise=True)
                        nv = ', '.join([n for n in norm if n])
                        if '\\' in nv:
                            print 'ESCAPED: %s: %s (was %s)' % (hdr, nv, val)
                        else:
                            print '%s: %s' % (hdr, nv)
                    except ValueError:
                        print 'FAILED: %s: %s -- %s' % (hdr, val,
                            traceback.format_exc().replace('\n', '  '))
            headers, header, inheader = {}, None, False
        elif line[:1] in (' ', '\t') and header:
            headers[header] = headers[header].rstrip() + line[1:]
        else:
            try:
                header, value = line.split(': ', 1)
                header = header.lower()
                headers[header] = headers.get(header, '') + ' ' + value
            except ValueError:
                headers, header, inheader = {}, None, False
    else:
        if line.startswith('From '):
            inheader = True

