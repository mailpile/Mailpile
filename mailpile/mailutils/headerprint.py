# vim: set fileencoding=utf-8 :
#
import re
from mailpile.util import md5_hex


MUA_ML_HEADERS = (# Mailing lists are sending MUAs in their own right
                  'list-id', 'list-subscribe', 'list-unsubscribe')

MUA_HP_HEADERS = ('date', 'from', 'to', 'reply-to',
                  # We omit the Subject, because for some reason it seems
                  # to jump around a lot. Same for CC.
                  'message-id', 'return-path', 'precedence', 'organization',
                  'mime-version', 'content-type',
                  'user-agent', 'x-mailer',
                  'x-mimeole', 'x-msmail-priority', 'x-priority',
                  'x-originating-ip', 'x-message-info',
                  'openpgp', 'x-openpgp',
                  # Common services
                  'x-github-recipient', 'feedback-id', 'x-facebook')

MUA_ID_HEADERS = ('x-mailer', 'user-agent', 'x-mimeole')

HP_MUA_ID_SPACE = re.compile(r'(\s+)')
HP_MUA_ID_IGNORE = re.compile(r'(\[[a-fA-F0-9%:]+\]|<\S+@\S+>'
                              '|(mail|in)-[^\.]+|\d+)')
HP_MUA_ID_SPLIT = re.compile(r'[\s,/;=()]+')
HP_RECVD_PARSE = re.compile(r'(by\s+)'
                             '[a-z0-9_\.-]*?([a-z0-9_-]*?\.?[a-z0-9_-]+\s+.*'
                             'with\s+.*)\s+id\s+.*$',
                            flags=(re.MULTILINE + re.DOTALL))


def HeaderPrintMTADetails(message):
    """Extract details about the sender's outgoing SMTP server."""
    details = []
    # We want the first "non-local" received line. This can of course be
    # trivially spoofed, but looking at this will still protect against
    # all but the most targeted of spear phishing attacks.
    for rcvd in reversed(message.get_all('received') or []):
        if ('local' not in rcvd
                and ' mapi id ' not in rcvd
                and '127.0.0' not in rcvd
                and '[::1]' not in rcvd):
            parsed = HP_RECVD_PARSE.search(rcvd)
            if parsed:
                by = parsed.group(1) + parsed.group(2)
                by = HP_MUA_ID_SPACE.sub(' ', HP_MUA_ID_IGNORE.sub('x', by))
                details = ['Received ' + by]
                break
    for h in ('DKIM-Signature', 'X-Google-DKIM-Signature'):
        for dkim in (message.get_all(h) or []):
            attrs = [HP_MUA_ID_SPACE.sub('', a)
                     for a in dkim.split(';') if a.strip()[:1] in 'vacd']
            details.extend([h, '; '.join(sorted(attrs))])
    return details


def HeaderPrintMUADetails(message, mta=None):
    """Summarize what the message tells us directly about the MUA."""
    details = []
    for header in MUA_ID_HEADERS:
        value = message.get(header)
        if value:
            # We want some details about the MUA, but also some stability.
            # Thus the HP_MUA_ID_IGNORE regexp...
            value = ' '.join([v for v in HP_MUA_ID_SPLIT.split(value.strip())
                              if not HP_MUA_ID_IGNORE.search(v)])
            details.extend([header, value.strip()])

    if not details:
        # FIXME: We could definitely make more educated guesses!
        if mta and mta[0].startswith('Received by google.com'):
            details.extend(['Guessed', 'GMail'])
        elif ('x-ms-tnef-correlator' in message or
                'x-ms-has-attach' in message):
            details.extend(['Guessed', 'Exchange'])
        elif '@mailpile' in message.get('message-id', ''):
            details.extend(['Guessed', 'Mailpile'])

    return details


def HeaderPrintGenericDetails(message, which=MUA_HP_HEADERS):
    """Extract message details which may help identify the MUA."""
    return [k for k, v in message.items() if k.lower() in which]


def HeaderPrints(message):
    """Generate fingerprints from message headers which identifies the MUA."""
    m = HeaderPrintMTADetails(message)
    u = HeaderPrintMUADetails(message, mta=m)[:20]
    g = HeaderPrintGenericDetails(message)[:50]
    mua = (u[1] if u else None)
    if mua and mua.startswith('Mozilla '):
        mua = mua.split()[-1]
    return {
        # The sender-ID headerprints includes MTA info
        'sender': md5_hex('\n'.join(m+u+g)),
        # Tool-chain headerprints ignore the MTA details
        'tools': md5_hex('\n'.join(u+g)),
        # Our best guess about what the MUA actually is; may be None
        'mua': mua}


if __name__ == "__main__":
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
