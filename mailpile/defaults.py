from mailpile.config import PathDict, TagDict, FilterDict


DEFAULT_CONFIG_RULES = {

    'sys': ['Technical system settings', False,
    {
        'fd_cache_size':  ('Max files kept open at once', int,            500),
        'history_length': ('History length (lines, <0 = no save)', int,   100),
        'http_port':      ('Listening port for web UI', int,            33144),
        'postinglist_kb': ('Posting list target size in KB', int,          64),
        'sort_max':       ('Max results we sort "well"', int,            2500),
        'snippet_max':    ('Max length of metadata snippets', int,        250),
        'debug':          ('Debugging flags', str,                         ''),
        'gpg_keyserver':  ('Host:port of GPG key server', str,             ''),
        'http_host':      ('Listening host for web UI', str,      'localhost'), 
        'local_mailbox':  ('Local read/write Maildir', str,                ''), 
        'mailindex_file': ('Metadata index file', str,                     ''), 
        'postinglist_dir': ('Search index directory', str,                 ''), 
        'obfuscate_index': ('Key to use to scramble the index', str,       ''), 
        'mailbox':        ['Mailboxes we index', str,                      []], 
        'path':           ['Locations of assorted data', PathDict,         []],
    }],
    'prefs': ["User preferences", False,
    {
        'num_results':     ('Search results per page', int,                15),
        'rescan_interval': ('New mail check frequency', int,                0),
        'gpg_clearsign':   ('Inline PGP signatures or attached', bool,  False),
        'default_order':   ('Default sort order', str,             'rev-date'),
        'gpg_recipient':   ('Encrypt local data to ...', str,              ''),
        'rescan_command':  ('Command run before rescanning', str,          ''),
    }],
    'user': ['User profiles and identities', None, {
    }],
    'tag': ['Mailpile tags', TagDict, []],
    'filter': ['Mailpile filters', FilterDict, []],
}


if __name__ == "__main__":
    import doctest
    from mailpile.config import ConfigDict
    print '%s' % ConfigDict(_rules=DEFAULT_CONFIG_RULES)
