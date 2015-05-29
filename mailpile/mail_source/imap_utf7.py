# This file comes from IMAPClient: <https://bitbucket.org/mjs0/imapclient>
#
## The IMAPClient license follows: 
#
# Copyright (c) 2014, Menno Smits
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of Menno Smits nor the names of its
#      contributors may be used to endorse or promote products derived
#      from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL MENNO SMITS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
##############################################################################

# The contents of this file has been derived code from the Twisted project
# (http://twistedmatrix.com/). The original author is Jp Calderone.

# Twisted project license follows:

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals


# We're lame and only support Python 2.7 for now. That .six thing looks
# pretty neat though!
binary_type = str
text_type = (str, unicode)
byte2int = lambda bs: ord(bs[0])
iterbytes = lambda buf: (ord(byte) for byte in buf)
#from .six import binary_type, text_type, byte2int, iterbytes, unichr


PRINTABLE = set(range(0x20, 0x26)) | set(range(0x27, 0x7f))

# TODO: module needs refactoring (e.g. variable names suck)

def encode(s):
    """Encode a folder name using IMAP modified UTF-7 encoding.

    Input is unicode; output is bytes (Python 3) or str (Python 2). If
    non-unicode input is provided, the input is returned unchanged.
    """
    if not isinstance(s, text_type):
        return s

    r = []
    _in = []

    def extend_result_if_chars_buffered():
        if _in:
            r.extend([b'&', modified_utf7(''.join(_in)), b'-'])
            del _in[:]

    for c in s:
        if ord(c) in PRINTABLE:
            extend_result_if_chars_buffered()
            r.append(c.encode('latin-1'))
        elif c == '&':
            extend_result_if_chars_buffered()
            r.append(b'&-')
        else:
            _in.append(c)

    extend_result_if_chars_buffered()

    return b''.join(r)


AMPERSAND_ORD = byte2int(b'&')
DASH_ORD = byte2int(b'-')

def decode(s):
    """Decode a folder name from IMAP modified UTF-7 encoding to unicode.

    Input is bytes (Python 3) or str (Python 2); output is always
    unicode. If non-bytes/str input is provided, the input is returned
    unchanged.
    """

    if not isinstance(s, binary_type):
        return s

    r = []
    _in = bytearray()
    for c in iterbytes(s):
        if c == AMPERSAND_ORD and not _in:
            _in.append(c)
        elif c == DASH_ORD and _in:
            if len(_in) == 1:
                r.append('&')
            else:
                r.append(modified_deutf7(_in[1:]))
            _in = bytearray()
        elif _in:
            _in.append(c)
        else:
            r.append(unichr(c))
    if _in:
        r.append(modified_deutf7(_in[1:]))
    return ''.join(r)


def modified_utf7(s):
    s_utf7 = s.encode('utf-7')
    return s_utf7[1:-1].replace(b'/', b',')


def modified_deutf7(s):
    s_utf7 = b'+' + s.replace(b',', b'/') + b'-'
    return s_utf7.decode('utf-7')

