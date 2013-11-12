import os
import time
from mailpile.config import PathDict

def _(x): return x

DEFAULT_SENDMAIL = '|/usr/sbin/sendmail -i %(rcpt)s'
CONFIG_RULES = {
    'version': [_('Mailpile program version'), int, 1],
    'timestamp': [_('Configuration timestamp'), int, int(time.time())],
    'sys': [_('Technical system settings'), False,
    {
        'fd_cache_size':  (_('Max files kept open at once'), int,            500),
        'history_length': (_('History length (lines, <0 = no save)'), int,   100),
        'http_port':      (_('Listening port for web UI'), int,            33411),
        'postinglist_kb': (_('Posting list target size in KB'), int,          64),
        'sort_max':       (_('Max results we sort "well"'), int,            2500),
        'snippet_max':    (_('Max length of metadata snippets'), int,        250),
        'debug':          (_('Debugging flags'), str,                         ''),
'gpg_keyserver':(_('Host:port of PGP keyserver'), str, 'pool.sks-keyservers.net'),
        'http_host':    (_('Listening host for web UI'), 'hostname', 'localhost'),
        'local_mailbox_id': (_('Local read/write Maildir'), 'b36',            ''),
        'mailindex_file': (_('Metadata index file'), 'file',                  ''),
        'postinglist_dir': (_('Search index directory'), 'dir',               ''),
        'mailbox':        [_('Mailboxes we index'), 'path',                   []],
        'path':           [_('Locations of assorted data'), False, {
             'html_theme': [_('Default theme'), 'dir',    os.path.join('static',
                                                                   'default')],
             'vcards':     [_('Location of vcards'), 'dir',             'vcards'],
         }],
    }],
    'prefs': [_("User preferences"), False,
    {
        'num_results':     (_('Search results per page'), int,                20),
        'rescan_interval': (_('New mail check frequency'), int,                0),
        'gpg_clearsign':   (_('Inline PGP signatures or attached'), bool,  False),
        'default_order':   (_('Default sort order'), str,             'rev-date'),
        'gpg_recipient':   (_('Encrypt local data to ...'), str,              ''),
        'obfuscate_index': (_('Key to use to scramble the index'), str,       ''),
        'rescan_command':  (_('Command run before rescanning'), str,          ''),
        'default_email':   (_('Default outgoing e-mail address'), 'email',    ''),
        'default_route':   (_('Default outgoing mail route'),
                                                'mailroute', DEFAULT_SENDMAIL),
        'language':        (_('User interface language'), str,                ''),
    }],
    'profiles': [_('User profiles and personalities'), {
        'name':            (_('Account name'), 'str', ''),
        'email':           (_('E-mail address'), 'email', ''),
        'signature':       (_('Message signature'), 'multiline', ''),
        'route':           (_('Outgoing mail route'), 'mailroute', ''),
    }, []]
}

del _

if __name__ == "__main__":
    import mailpile.defaults
    from mailpile.plugins import *
    from mailpile.config import ConfigDict

    print '%s' % (ConfigDict(_name='mailpile',
                             _comment=_('Default configuration'),
                             _rules=mailpile.defaults.CONFIG_RULES
                             ).as_config_bytes(), )
