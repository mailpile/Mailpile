import email
import email.errors
import email.message
import random
import re
import rfc822
import time
from urllib import quote, unquote

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils.header import decode_header
from mailpile.util import *


def safe_decode_hdr(msg=None, name=None, hdr=None, charset=None):
    """
    This method stubbornly tries to decode header data and convert
    to Pythonic unicode strings. The strings are guaranteed not to
    contain tab, newline or carriage return characters.

    If used with a message object, the header and the MIME charset
    will be inferred from the message headers.
    >>> msg = email.message.Message()
    >>> msg['content-type'] = 'text/plain; charset=utf-8'
    >>> msg['from'] = 'G\\xc3\\xadsli R \\xc3\\x93la <f@b.is>'
    >>> safe_decode_hdr(msg, 'from')
    u'G\\xedsli R \\xd3la <f@b.is>'

    The =?...?= MIME header encoding is also recognized and processed.

    >>> safe_decode_hdr(hdr='=?iso-8859-1?Q?G=EDsli_R_=D3la?=\\r\\n<f@b.is>')
    u'G\\xedsli R \\xd3la <f@b.is>'

    >>> safe_decode_hdr(hdr='"=?utf-8?Q?G=EDsli_R?= =?iso-8859-1?Q?=D3la?="')
    u'G\\xedsli R \\xd3la'

    And finally, guesses are made with raw binary data. This process
    could be improved, it currently only attempts utf-8 and iso-8859-1.

    >>> safe_decode_hdr(hdr='"G\\xedsli R \\xd3la"\\r\\t<f@b.is>')
    u'"G\\xedsli R \\xd3la"  <f@b.is>'

    >>> safe_decode_hdr(hdr='"G\\xc3\\xadsli R \\xc3\\x93la"\\n <f@b.is>')
    u'"G\\xedsli R \\xd3la"  <f@b.is>'

    # See https://bugs.python.org/issue1079

    # encoded word enclosed in parenthesis (comment syntax)
    >>> safe_decode_hdr(hdr='rene@example.com (=?utf-8?Q?Ren=C3=A9?=)')
    u'rene@example.com ( Ren\\xe9 )'

    # no space after encoded word
    >>> safe_decode_hdr(hdr='=?UTF-8?Q?Direction?=<dir@example.com>')
    u'Direction <dir@example.com>'
    """
    if hdr is None:
        value = msg and msg[name] or ''
        charset = charset or msg.get_content_charset() or 'utf-8'
    else:
        value = hdr
        charset = charset or 'utf-8'

    if not isinstance(value, unicode):
        # Already a str! Oh shit, might be nasty binary data.
        value = try_decode(value, charset, replace='?')

    # At this point we know we have a unicode string. Next we try
    # to very stubbornly decode and discover character sets.
    if '=?' in value and '?=' in value:
        try:
            # decode_header wants an unquoted str (not unicode)
            value = value.encode('utf-8').replace('"', '')
            # Decode!
            pairs = decode_header(value)
            value = ' '.join([try_decode(t, cs or charset)
                              for t, cs in pairs])
        except email.errors.HeaderParseError:
            pass

    # Finally, return the unicode data, with white-space normalized
    return value.replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')

def safe_parse_date(date_hdr):
    """Parse a Date: or Received: header into a unix timestamp."""
    try:
        if ';' in date_hdr:
            date_hdr = date_hdr.split(';')[-1].strip()
        msg_ts = long(rfc822.mktime_tz(rfc822.parsedate_tz(date_hdr)))
        if (msg_ts > (time.time() + 24 * 3600)) or (msg_ts < 1):
            return None
        else:
            return msg_ts
    except (ValueError, TypeError, OverflowError):
        return None

def safe_message_ts(msg, default=None, msg_mid=None, msg_id=None, session=None):
    """Extract a date, sanity checking against the Received: headers."""
    hdrs = [safe_decode_hdr(msg, 'date')] + (msg.get_all('received') or [])
    dates = [safe_parse_date(date_hdr) for date_hdr in hdrs]
    msg_ts = dates[0]
    nz_dates = sorted([d for d in dates if d])

    if nz_dates:
        a_week = 7 * 24 * 3600

        # Ideally, we compare with the date on the 2nd SMTP relay, as
        # the first will often be the same host as composed the mail
        # itself. If we don't have enough hops, just use the last one.
        #
        # We don't want to use a median or average, because if the
        # message bounces around lots of relays or gets resent, we
        # want to ignore the latter additions.
        #
        rcv_ts = nz_dates[min(len(nz_dates)-1, 2)]

        # Now, if everything is normal, the msg_ts will be at nz_dates[0]
        # and it won't be too far away from our reference date.
        if (msg_ts == nz_dates[0]) and (abs(msg_ts - rcv_ts) < a_week):
            # Note: Trivially true for len(nz_dates) in (1, 2)
            return msg_ts

        # Damn, dates are screwy!
        #
        # Maybe one of the SMTP servers has a wrong clock?  If the Date:
        # header falls within the range of all detected dates (plus a
        # week towards the past), still trust it.
        elif ((msg_ts >= (nz_dates[0]-a_week))
                and (msg_ts <= nz_dates[-1])):
            return msg_ts

        # OK, Date: is insane, use one of the early Received: lines
        # instead.  We picked the 2nd one above, that should do.
        else:
            if session and msg_mid and msg_id:
                session.ui.warning(_('=%s/%s using Received: instead of Date:'
                                     ) % (msg_mid, msg_id))
            return rcv_ts
    else:
        # If the above fails, we assume the messages in the mailbox are in
        # chronological order and just add 1 second to the date of the last
        # message if date parsing fails for some reason.
        if session and msg_mid and msg_id:
            session.ui.warning(_('=%s/%s has a bogus date'
                                 ) % (msg_mid, msg_id))
        return default

def safe_get_msg_id(msg):
    raw_msg_id = safe_decode_hdr(msg, 'message-id')
    if not raw_msg_id:
        # Create a very long pseudo-msgid for messages without a
        # Message-ID. This was a very badly behaved mailer, so if
        # we create duplicates this way, we are probably only
        # losing spam. Even then the Received line should save us.
        raw_msg_id = ('\t'.join([safe_decode_hdr(msg, 'date'),
                                 safe_decode_hdr(msg, 'subject'),
                                 safe_decode_hdr(msg, 'received'),
                                 safe_decode_hdr(msg, 'from'),
                                 safe_decode_hdr(msg, 'to')])
                      # This is to avoid truncation in encode_msg_id:
                      ).replace('<', '').strip()
    return raw_msg_id


if __name__ == '__main__':
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
