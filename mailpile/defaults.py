import os
import time
from gettext import gettext as _

from mailpile.config import PathDict


DEFAULT_SENDMAIL = '|/usr/sbin/sendmail -i %(rcpt)s'
CONFIG_PLUGINS = []
CONFIG_RULES = {
    'version': [_('Mailpile program version'), int, 1],
    'timestamp': [_('Configuration timestamp'), int, int(time.time())],
    'sys': [_('Technical system settings'), False, {
        'fd_cache_size':  (_('Max files kept open at once'), int,         500),
        'history_length': (_('History length (lines, <0=no save)'), int,  100),
        'http_port':      (_('Listening port for web UI'), int,         33411),
        'postinglist_kb': (_('Posting list target size in KB'), int,       64),
        'sort_max':       (_('Max results we sort "well"'), int,         2500),
        'snippet_max':    (_('Max length of metadata snippets'), int,     250),
        'debug':          (_('Debugging flags'), str,                      ''),
        'gpg_keyserver':  (_('Host:port of PGP keyserver'),
                           str, 'pool.sks-keyservers.net'),
        'http_host':      (_('Listening host for web UI'),
                           'hostname', 'localhost'),
        'local_mailbox_id': (_('Local read/write Maildir'), 'b36',         ''),
        'mailindex_file': (_('Metadata index file'), 'file',               ''),
        'postinglist_dir': (_('Search index directory'), 'dir',            ''),
        'mailbox':        [_('Mailboxes we index'), 'path',                []],
        'plugins':        [_('Plugins to load on startup'),
                           CONFIG_PLUGINS, []],
        'path':           [_('Locations of assorted data'), False, {
            'html_theme': [_('Default theme'),
                           'dir', os.path.join('static', 'default')],
            'vcards':     [_('Location of vcards'), 'dir', 'vcards'],
        }],
    }],
    'prefs': [_("User preferences"), False, {
        'num_results':     (_('Search results per page'), int,             20),
        'rescan_interval': (_('New mail check frequency'), int,             0),
        'gpg_clearsign':   (_('Inline PGP signatures or attached'),
                            bool, False),
        'gpg_recipient':   (_('Encrypt local data to ...'), str,           ''),
        'openpgp_header':  (_('Advertise GPG preferences in a header?'),
                            ['', 'sign', 'encrypt', 'signencrypt'],
                            'signencrypt'),
        'crypto_policy':   (_('Default encryption policy for outgoing mail'),
                            str, 'none'),
        'default_order':   (_('Default sort order'), str,          'rev-date'),
        'obfuscate_index': (_('Key to use to scramble the index'), str,    ''),
        'index_encrypted': (_('Make encrypted content searchable'),
                            bool, False),
        'rescan_command':  (_('Command run before rescanning'), str,       ''),
        'default_email':   (_('Default outgoing e-mail address'), 'email', ''),
        'default_route':   (_('Default outgoing mail route'),
                            'mailroute', DEFAULT_SENDMAIL),
        'language':        (_('User interface language'), str,             ''),
        'vcard':           [_("VCard import/export settings"), False, {
            'importers':   [_("VCard import settings"), False,             {}],
            'exporters':   [_("VCard export settings"), False,             {}],
            'context':     [_("VCard context helper settings"), False,     {}],
        }],
    }],
    'profiles': [_('User profiles and personalities'), {
        'name':            (_('Account name'), 'str', ''),
        'email':           (_('E-mail address'), 'email', ''),
        'signature':       (_('Message signature'), 'multiline', ''),
        'route':           (_('Outgoing mail route'), 'mailroute', ''),
    }, []]
}


if __name__ == "__main__":
    import mailpile.defaults
    from mailpile.config import ConfigDict

    print '%s' % (ConfigDict(_name='mailpile',
                             _comment='Base configuration',
                             _rules=mailpile.defaults.CONFIG_RULES
                             ).as_config_bytes(), )
