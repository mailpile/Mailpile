APPVER = "0.2.0"
ABOUT = """\
Mailpile.py          a tool                 Copyright 2013-2014, Mailpile ehf
               for searching and                   <https://www.mailpile.is/>
           organizing piles of e-mail

This program is free software: you can redistribute it and/or modify it under
the terms of either the GNU Affero General Public License as published by the
Free Software Foundation or the Apache License 2.0 as published by the Apache
Software Foundation. See the file COPYING.md for details.
"""
#############################################################################
import os
import time
from gettext import gettext as _

from mailpile.config import PathDict


DEFAULT_SENDMAIL = '|/usr/sbin/sendmail -i %(rcpt)s'
CONFIG_PLUGINS = []
CONFIG_RULES = {
    'version': [_('Mailpile program version'), False, APPVER],
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
        'gpg_home':       (_('Override the home directory of GnuPG'), 'dir',
                           None),
        'http_host':      (_('Listening host for web UI'),
                           'hostname', 'localhost'),
        'local_mailbox_id': (_('Local read/write Maildir'), 'b36',         ''),
        'mailindex_file': (_('Metadata index file'), 'file',               ''),
        'postinglist_dir': (_('Search index directory'), 'dir',            ''),
        'mailbox':        [_('Mailboxes we index'), 'str',                 []],
        'plugins':        [_('Plugins to load on startup'),
                           CONFIG_PLUGINS, []],
        'path':           [_('Locations of assorted data'), False, {
            'html_theme': [_('Default theme'),
                           'dir', os.path.join('static', 'default')],
            'vcards':     [_('Location of vcards'), 'dir', 'vcards'],
            'event_log':  [_('Location of event log'), 'dir', 'logs'],
        }],
        'lockdown':       [_('Demo mode, disallow changes'), bool,      False],
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
        'default_route':   (_('Default outgoing mail route'), str, ''),
        'always_bcc_self': (_('Always BCC self on outgoing mail'), bool, True),
        'default_messageroute': (_('Default outgoing mail route'), str,    ''),
        'language':        (_('User interface language'), str,             ''),
        'vcard':           [_("VCard import/export settings"), False, {
            'importers':   [_("VCard import settings"), False,             {}],
            'exporters':   [_("VCard export settings"), False,             {}],
            'context':     [_("VCard context helper settings"), False,     {}],
        }],
    }],
    'routes': [_('Outgoing message routes'), {
        'name':            (_('Route name'), str, ''),
        'protocol':        (_('Messaging protocol'),
                            ["smtp", "smtptls", "smtpssl", "local"],
                            'smtp'),
        'username':        (_('User name'), str, ''),
        'password':        (_('Password'), str, ''),
        'command':         (_('Shell command'), str, ''),
        'host':            (_('Host'), str, ''),
        'port':            (_('Port'), int, 587)
    }, {}],
    'sources': [_('Incoming message sources'), {
        'name':            (_('Source name'), str, ''),
        'protocol':        (_('Mailbox protocol or format'),
                            ["mbox", "maildir", "macmaildir", "gmvault",
                             "imap", "imap_ssl", "pop3"],
                            ''),
        'pre_command':     (_('Shell command run before syncing'), str, ''),
        'post_command':    (_('Shell command run after syncing'), str, ''),
        'interval':        (_('How frequently to check for mail'), int, 300),
        'username':        (_('User name'), str, ''),
        'password':        (_('Password'), str, ''),
        'host':            (_('Host'), str, ''),
        'port':            (_('Port'), int, 993),
        'discovery':       (_('Mailbox discovery policy'), False, {
            'paths':       (_('Paths to watch for new mailboxes'), str, []),
            'policy':      (_('Default mailbox policy'),
                            ['unknown', 'ignore', 'watch',
                             'read', 'move', 'sync'], 'unknown'),
            'local_copy':  (_('Copy mail to a local mailbox?'), bool, False),
            'create_tag':  (_('Create a tag for each mailbox?'), bool, True),
            'process_new': (_('Is a potential source of new mail'), bool, True),
            'apply_tags':  (_('Tags applied to messages'), str, []),
        }),
        'mailbox': (_('Mailboxes'), {
            'path':        (_('Mailbox source path'), str, ''),
            'policy':      (_('Mailbox policy'),
                            ['unknown', 'ignore', 'read', 'move', 'sync'],
                            'ignore'),
            'local':       (_('Local mailbox path'), str, ''),
            'process_new': (_('Is a source of new mail'), bool, True),
            'primary_tag': (_('A tag representing this mailbox'), str, ''),
            'apply_tags':  (_('Tags applied to messages'), str, []),
        }, {})
    }, {}],

    ### OLD CRAP, JUST HERE SO AS NOT TO KILL CONFIG FILES
    'profiles': [_('DEPRECATED: User profiles and personalities'), {
        'name':            (_('Account name'), 'str', ''),
        'email':           (_('E-mail address'), 'email', ''),
        'signature':       (_('Message signature'), 'multiline', ''),
        'route':           (_('DEPRECATED, DO NOT USE'), str, ''),
        'messageroute':    (_('Outgoing mail route'), str, ''),
    }, []]
}


if __name__ == "__main__":
    import mailpile.defaults
    from mailpile.config import ConfigDict

    print '%s' % (ConfigDict(_name='mailpile',
                             _comment='Base configuration',
                             _rules=mailpile.defaults.CONFIG_RULES
                             ).as_config_bytes(), )
