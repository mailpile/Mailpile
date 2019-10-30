from __future__ import print_function
APPVER = "1.0.0rc6"
ABOUT = """\
Mailpile.py              a tool             Copyright 2013-2018, Mailpile ehf
 v%8.0008s         for searching and               <https://www.mailpile.is/>
               organizing piles of e-mail

This program is free software: you can redistribute it and/or modify it under
the terms of either the GNU Affero General Public License as published by the
Free Software Foundation. See the file COPYING.md for details.
""" % APPVER
#############################################################################
import os
import sys
import time

from mailpile.config.base import PathDict
from mailpile.config.base import ConfigRule as c
from mailpile.config.base import CriticalConfigRule as X
from mailpile.config.base import PublicConfigRule as p
from mailpile.config.base import KeyConfigRule as k


_ = lambda string: string


DEFAULT_SENDMAIL = '|/usr/sbin/sendmail -i %(rcpt)s'
CONFIG_PLUGINS = []
CONFIG_RULES = {
    'version': p(_('Mailpile program version'), str, APPVER),
    'homedir': p(_('Location of Mailpile data'), False, '(unset)'),
    'timestamp': [_('Configuration timestamp'), int, int(time.time())],
    'master_key': k(_('Master symmetric encryption key'), str, ''),
    'sys': p(_('Technical system settings'), False, {
        'fd_cache_size': p(_('Max files kept open at once'), int,         500),
        'minfree_mb':    p(_('Required free disk space (MB)'), int,      1024),
        'history_length': (_('History length (lines, <0=no save)'), int,  100),
        'http_host':     p(_('Listening host for web UI'),
                           'hostname', 'localhost'),
        'http_port':     p(_('Listening port for web UI'), int,         33411),
        'http_path':     p(_('HTTP path of web UI'), 'webroot',            ''),
        'http_no_auth':  X(_('Disable HTTP authentication'),      bool, False),
        'ajax_timeout':   (_('AJAX Request timeout'), int,              10000),
        'postinglist_kb': (_('Posting list target size in KB'), int,       64),
        'sort_max':       (_('Max results we sort "well"'), int,         2500),
        'snippet_max':    (_('Max length of metadata snippets'), int,     275),
        'debug':         p(_('Debugging flags'), str,                      ''),
        'experiments':    (_('Enabled experiments'), str,                  ''),
        'gpg_keyserver':  (_('Host:port of PGP keyserver'),
                           str, 'pool.sks-keyservers.net'),
        'gpg_home':      p(_('Override the home directory of GnuPG'),
                           'dir', None),
        'gpg_binary':    p(_('Override the default GPG binary path'),
                           'file', None),
        'local_mailbox_id': (_('Local read/write Maildir'), 'b36',         ''),
        'mailindex_file':   (_('Metadata index file'), 'file',             ''),
        'postinglist_dir': (_('Search index directory'), 'dir',            ''),
        'mailbox':        [_('Mailboxes we index'), 'bin',                 []],
        'plugins_early': p(_('Plugins to load before login'),
                           CONFIG_PLUGINS, []),
        'plugins':        [_('Plugins to load after login'),
                           CONFIG_PLUGINS, []],
        'path':           [_('Locations of assorted data'), False, {
            'html_theme': [_('User interface theme'), 'dir', 'default-theme'],
            'vcards':     [_('Location of vCards'), 'dir', 'vcards'],
            'event_log':  [_('Location of event log'), 'dir', 'logs'],
        }],
        'lockdown':      p(_('Demo mode, disallow changes'), str,          ''),
        'login_banner':  p(_('A custom banner for the login page'), str,   ''),
        'proxy':         p(_('Proxy settings'), False, {
            'protocol':  p(_('Proxy protocol'),
                           ["tor", "tor-risky", "socks5", "socks4", "http",
                            "none", "system", "unknown"], "system"),
            'fallback':  p(_('Allow fallback to direct conns'), bool, False),
            'username':   (_('User name'), str, ''),
            'password':   (_('Password'), str, ''),
            'host':      p(_('Host'), str, ''),
            'port':      p(_('Port'), int, 8080),
            'no_proxy':  p(_('List of hosts to avoid proxying'), str,
                           'localhost, 127.0.0.1, ::1')
        }),
        'tor': p(_('Tor settings'), False, {
            'binary':    p(_('Override the default Tor binary path'),
                           'file', None),
            'systemwide':p(_('Use shared system-wide Tor (not our own)'),
                                                                   bool, True),
            'socks_host':p(_('Socks host'), str, ''),
            'socks_port':p(_('Socks Port'), int, 0),
            'ctrl_port': p(_('Control Port'), int, 0),
            'ctrl_auth': p(_('Control Password'), str, '')
        })
    }),
    'prefs': p(_("User preferences"), False, {
        'num_results':     (_('Search results per page'), int,             20),
        'rescan_interval': (_('Misc. data refresh frequency'), int,       900),
        'open_in_browser': p(_('Open in browser on startup'), bool,      True),
        'auto_mark_as_read':(_('Automatically mark e-mail as read'),
                                                                   bool, True),
        'web_content':     (_('Download content from the web'),
                            ["off", "anon", "on"],                  "unknown"),
        'html5_sandbox':   (_('Use HTML5 sandboxes'), bool,              True),
        'attachment_urls': (_('URLs to treat as attachments (regex)'), str, []),
        'weak_crypto_max_age': (
               _('Accept weak crypto in messages older than this (unix time)'),
                                                                  int,      0),
        'encrypted_block_html': (_('Never display HTML from encrypted mail'),
                                                                   bool, True),
        'encrypted_block_web': (_('Never fetch web content from encrypted mail'),
                                                                   bool, True),
        'gpg_use_agent':   (_('Use the local GnuPG agent'), bool,       False),
        'gpg_clearsign':  X(_('Inline PGP signatures or attached'),
                            bool, False),
        'gpg_recipient':   (_('Encrypt local data to ...'), 'gpgkeyid',    ''),
        'gpg_email_key':   (_('Enable e-mail based public key distribution'),
                            bool, True),
        'gpg_html_wrap':   (_('Wrap keys and signatures in helpful HTML'),
                            bool, True),
        'antiphishing':    (_("Enable experimental anti-phishing heuristics "),
                                                                  bool, False),
        'key_tofu':        (_("Key Import Behaviour"), False, {
            'autocrypt':   (_('Auto-import keys using Autocrypt state machine'),
                            bool, True),
            'historic':    (_('Auto-import keys using communication history'),
                            bool, True),
            'hist_min':    (_('Require this many signed- or encrypted e-mails'),
                            int, 3),
            'hist_recent': (_('Consider the most recent N e-mails (per sender)'),
                            int, 6),
            'hist_origins':(_('Origins to auto-import keys from (historic)'),
                            str, 'e-mail, wkd, koo'),
            'min_interval': (_('Interval between TOFU checks (per sender)'),
                            int, 1800),
        }),
        'key_trust':       (_("Key Trust Model"), False, {
            'threshold':    (_('Minimum number of signatures required'),
                             int, 5),
            'window_days':  (_('Window of time (days) to evaluate trust'),
                             int, 180),
            'sig_warn_pct': (_('Signed ratio (%) above which we expect sigs'),
                             int, 80),
            'key_trust_pct':(_('Ratio of key use (%) above which we trust key'),
                             int, 90),
            'key_new_pct':  (_('Consider key new below this ratio (%) of sigs'),
                             int, 10)
        }),
        'openpgp_header': X(_('Advertise PGP preferences in a header?'),
                            ['', 'sign', 'encrypt', 'signencrypt'],
                            'signencrypt'),
        'crypto_policy':  X(_('Default encryption policy for outgoing mail'),
                            str, 'none'),
        'inline_pgp':      (_('Use inline PGP when possible'), bool,     True),
        'encrypt_subject': (_('Encrypt subjects by default'), bool,      True),
        'default_order':   (_('Default sort order'), str,          'rev-date'),
        'obfuscate_index':X(_('Key to use to scramble the index'), str,    ''),
        'index_encrypted':X(_('Make encrypted content searchable'),
                            bool, False),
        'encrypt_mail':   X(_('Encrypt locally stored mail'), bool,     False),
        'encrypt_index':  X(_('Encrypt the local search index'), bool,  False),
        'encrypt_vcards': X(_('Encrypt the contact database'), bool,     True),
        'encrypt_events': X(_('Encrypt the event log'), bool,            True),
        'encrypt_misc':   X(_('Encrypt misc. local data'), bool,         True),
        'allow_deletion': X(_('Allow permanent deletion of e-mails'),
                                                                  bool, False),
        'deletion_ratio': X(_('Max fraction of source mail to delete per pass'),
                                                                 float,  0.75),
# FIXME:
#       'backup_to_web':  X(_('Backup settings and keys to mobile web app'),
#                                                                  bool, True),
#       'backup_to_email':X(_('Backup settings and keys to e-mail'),  str, ''),
        'rescan_command':  (_('Command run before rescanning'), str,       ''),
        'default_email':   (_('Default outgoing e-mail address'), 'email', ''),
        'default_route':   (_('Default outgoing mail route'), str, ''),
        'line_length':     (_('Target line length, <40 disables reflow'),
                            int, 65),
        'always_bcc_self': (_('Always BCC self on outgoing mail'), bool, True),
        'default_messageroute': (_('Default outgoing mail route'), str,    ''),
        'language':       p(_('User interface language'), str,             ''),
        'vcard':           [_("vCard import/export settings"), False, {
            'importers':   [_("vCard import settings"), False,             {}],
            'exporters':   [_("vCard export settings"), False,             {}],
            'context':     [_("vCard context helper settings"), False,     {}],
        }],
        'friendly_pipes':  (_("Enable sh-like pipes in the CLI"), bool,  True),
    }),
    'web': (_("Web Interface Preferences"), False, {
        'keybindings':     (_('Enable keyboard short-cuts'), bool, False),
        'developer_mode':  (_('Enable developer-only features'), bool, False),
        'friendly_dates':  (_('UI uses "friendly" date/times'), bool,    True),
        'setup_complete':  (_('User completed setup experience'), bool, False),
        'display_density': (_('Display density of interface'), str, 'comfy'),
        'quoted_reply':    (_('Quote replies to messages'), str, 'unset'),
        'nag_backup_key':   (_('Nag user to backup their key'), int, 0),
        'subtags_collapsed': (_('Collapsed subtags in sidebar'), str, []),
        'donate_visibility': (_('Display donate link in topbar?'), bool, True),
        'email_html_hint':   (_('Display HTML hints?'), bool, True),
        'email_crypto_hint': (_('Display crypto hints?'), bool, True),
        'email_reply_hint':  (_('Display reply hints?'), bool, True),
        'email_tag_hint':    (_('Display tagging hints?'), bool, True),
        'release_notes':     (_('Display release notes?'), bool, True)
    }),
    'logins': [_('Credentials allowed to access Mailpile'), {
        'password':        (_('Salted and hashed password'), str, '')
    }, {}],
    'secrets': [_('Secrets the user wants saved'), {
        'password':        (_('A secret'), str, ''),
        'policy':          (_('Security policy'),
                            ["store", "cache-only", "fail", "protect"],
                            'store')
    }, {}],
    'tls': [_('Settings for TLS certificate validation'), {
        'server':          (_('Server hostname:port'), str, ''),
        'accept_certs':    (_('SHA256 of acceptable certs'), str, []),
        'use_web_ca':      (_('Use web certificate authorities'), bool, True)
    }, {}],
    'routes': [_('Outgoing message routes'), {
        'name':            (_('Route name'), str, ''),
        'protocol':        (_('Messaging protocol'),
                            ["smtp", "smtptls", "smtpssl", "local"],
                            'smtp'),
        'username':        (_('User name'), str, ''),
        'password':        (_('Password'), str, ''),
        'auth_type':       (_('Authentication scheme'), str, 'password-cleartext'),
        'command':         (_('Shell command'), str, ''),
        'host':            (_('Host'), str, ''),
        'port':            (_('Port'), int, 587)
    }, {}],
    'sources': [_('Incoming message sources'), {
        'name':            (_('Source name'), str, ''),
        'profile':         (_('Profile this source belongs to'), str, ''),
        'enabled':         (_('Is this mail source enabled?'), bool, True),
        'protocol':        (_('Mail source protocol'),
                            ["local",
                             "imap", "imap_ssl", "imap_tls",
                             "pop3", "pop3_ssl",
                             # These are all obsolete, handled as local:
                             "mbox", "maildir", "macmaildir", "gmvault"],
                            ''),
        'pre_command':     (_('Shell command run before syncing'), str, ''),
        'post_command':    (_('Shell command run after syncing'), str, ''),
        'interval':        (_('How frequently to check for mail'), int, 300),
        'username':        (_('User name'), str, ''),
        'password':        (_('Password'), str, ''),
        'auth_type':       (_('Authentication scheme'), str, 'password'),
        'host':            (_('Host'), str, ''),
        'port':            (_('Port'), int, 993),
        'keepalive':       (_('Keep server connections alive'), bool, False),
        'discovery':       (_('Mailbox discovery policy'), False, {
            'paths':       (_('Paths to watch for new mailboxes'), 'bin', []),
            'policy':      (_('Default mailbox policy'),
                            ['unknown', 'ignore', 'watch',
                             'read', 'move', 'sync'], 'unknown'),
            'local_copy':  (_('Copy mail to a local mailbox?'), bool, False),
            'parent_tag':  (_('Parent tag for mailbox tags'), str, '!CREATE'),
            'guess_tags':  (_('Guess which local tags match'), bool, True),
            'create_tag':  (_('Create a tag for each mailbox?'), bool, True),
            'visible_tags':(_('Make tags visible by default?'), bool, True),
            'process_new': (_('Is a potential source of new mail'), bool, True),
            'apply_tags':  (_('Tags applied to messages'), str, []),
            'max_mailboxes':(_('Max mailboxes to add'), int, 100),
        }),
        'mailbox': (_('Mailboxes'), {
            'name':        (_('The name of this mailbox'), str, ''),
            'path':        (_('Mailbox source path'), str, ''),
            'policy':      (_('Mailbox policy'),
                            ['unknown', 'ignore', 'read', 'move', 'sync',
                             'inherit'], 'inherit'),
            'local':       (_('Local mailbox path'), 'bin', ''),
            'process_new': (_('Is a source of new mail'), bool, True),
            'primary_tag': (_('A tag representing this mailbox'), str, ''),
            'apply_tags':  (_('Tags applied to messages'), str, []),
        }, {})
    }, {}]
}


if __name__ == "__main__":
    import mailpile.config.defaults
    from mailpile.config.base import ConfigDict

    print('%s' % (ConfigDict(_name='mailpile',
                             _comment='Base configuration',
                             _rules=mailpile.config.defaults.CONFIG_RULES
                             ).as_config_bytes(), ))
