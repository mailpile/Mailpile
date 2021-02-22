# SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
# SPDX-License-Identifier: AGPL-3.0-or-later

try:
    import ssl
except ImportError:
    ssl = None

try:
    import sockschain as socks
except ImportError:
    try:
        import socks
    except ImportError:
        socks = None
