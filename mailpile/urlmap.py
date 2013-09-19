from urlparse import parse_qs, urlparse

import mailpile.commands
import mailpile.plugins


class UrlMap:
    """
    This class will map URLs/requests to Mailpile commands and back.

    The URL space is divided into three main classes:

       1. Versioned API endpoints
       2. Nice looking shortcuts to common data
       3. Shorthand paths to API endpoints (current version only)

    Depending on the endpoint, it is often possible to request alternate
    rendering templates or generate output in a variety of machine readable
    formats, such as JSON, XML or VCard. This is done by appending a
    psuedo-filename to the path. If ending in `.html`, the full filename is
    used to choose an alternate rendering template, for other extensions the
    name is ignored but the extension used to choose an output format.

    The default rendering for API endpoints is JSON, for other endpoints
    it is HTML. It is strongly recommended that only the versioned API
    endpoints be used for automation.
    """
    API_VERSIONS = (20130900, )

    def __init__(self, session):
        self.session = session

    def _prefix_to_query(self, path, query_data, post_data):
        """
        Turns the /var/value prefix into a query-string argument.
        Returns a new path with the prefix stripped.

        >>> query_data = {}
        >>> path = urlmap._prefix_to_query('/var/val/stuff', query_data, {})
        >>> path, query_data
        ('/stuff', {'var': ['val']})
        """
        which, value, path = path[1:].split('/', 2)
        query_data[which] = [value]
        return '/'+path

    def _api_commands(self, method=True):
        return [c for c in mailpile.commands.COMMANDS.values()
                        if (method in c[1].HTTP_CALLABLE) or not method]

    def _command(self, name, args=None, query_data=None, post_data=None,
                             method='GET'):
        """
        Return an instantiated mailpile.command object or raise a ValueError.

        >>> urlmap._command('output', args=['html'], method=False)
        <mailpile.commands.Output instance at 0x...>
        >>> urlmap._command('bogus')
        Traceback (most recent call last):
            ...
        ValueError: Unknown command: bogus
        """
        match = [c for c in self._api_commands(method)
                         if c[0] in (name, name+'=')]
        if len(match) != 1:
          raise ValueError('Unknown command: %s' % name)
        command = match[0][1]

        data = {}
        for vlist, src in ((command.HTTP_QUERY_VARS, query_data),
                           (command.HTTP_QUERY_VARS, post_data),
                           (command.HTTP_POST_VARS, post_data)):
          for var in vlist:
            if var in src:
              data[var] = src[var]

        return command(self.session, name, args, data=data)

    def _choose_output(self, path_parts, fmt='html'):
        """
        Return an output command based on the URL filename component.

        As a side-effect, the filename component will be removed from the
        path_parts list.
        >>> path_parts = '/a/b/c.json'.split('/')
        >>> command = urlmap._choose_output(path_parts)
        >>> (path_parts, command)
        (['', 'a', 'b'], <mailpile.commands.Output instance at 0x...>)

        If there is no filename part, the path_parts list is unchanged
        aside from stripping off the trailing empty string if present.
        >>> path_parts = '/a/b/'.split('/')
        >>> command = urlmap._choose_output(path_parts)
        >>> (path_parts, command)
        (['', 'a', 'b'], <mailpile.commands.Output instance at 0x...>)
        >>> path_parts = '/a/b'.split('/')
        >>> command = urlmap._choose_output(path_parts)
        >>> (path_parts, command)
        (['', 'a', 'b'], <mailpile.commands.Output instance at 0x...>)
        """
        if len(path_parts) > 1 and not path_parts[-1]:
            path_parts.pop(-1)
        elif '.' in path_parts[-1]:
            fn = path_parts.pop(-1)
            for suffix in ('.html', '.jhtml'):
                if fn.endswith(suffix):
                    fmt = fn
            for suffix in ('.json', '.xml', '.vcf'):
                if fn.endswith(suffix):
                    fmt = suffix[1:]
        return self._command('output', [fmt], method=False)

    def _map_root(self, request, path_parts, query_data, post_data):
        """Redirects to /in/Inbox/ for now.  (FIXME)"""
        return [self._command('_redirect', args=['/in/Inbox/'], method=False)]

    # FIXME: This should come from the search plugin
    def _map_tag(self, request, path_parts, query_data, post_data):
        """
        Map /in/TAG_NAME/ to tag searches.

        >>> path = '/in/Inbox/'
        >>> commands = urlmap._map_tag(request, path[1:].split('/'), {}, {})
        >>> commands
        [<mailpile.plugins.search.Search...>]
        >>> commands[0].args
        ['tag:1']
        """
        tag = '/'.join([p for p in path_parts[1:] if p])
        tag_search = ['tag:%s' % self.session.config.get_tag_id(tag)]
        return [
            self._command('search', args=tag_search,
                                    query_data=query_data,
                                    post_data=post_data)
        ]

    # FIXME: This should come from the search plugin
    def _map_thread(self, request, path_parts, query_data, post_data):
        """
        Map /thread/METADATA_ID/ to view commands.

        >>> path = '/thread/123/'
        >>> commands = urlmap._map_thread(request, path[1:].split('/'), {}, {})
        >>> commands
        [<mailpile.plugins.search.View...>]
        >>> commands[0].args
        ['=123']
        """
        message_mid = path_parts[1]
        return [
            self._command('view', args=['=%s' % message_mid],
                                  query_data=query_data,
                                  post_data=post_data)
        ]

    def _map_RESERVED(self, *args):
      """RESERVED FOR LATER."""

    MAP_API = 'api'
    MAP_PATHS = {
       '':        _map_root,
       'in':      _map_tag,
       'thread':  _map_thread,
       'message': _map_RESERVED
    }
    def map(self, request, path, query_data, post_data):
        """
        Convert an HTTP request to a list of mailpile.command objects.

        >>> urlmap.map(request, '/in/Inbox/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]

        The /api/ URL space is versioned and provides access to all the
        built-in commands. Requesting the wrong version or a bogus command
        throws exceptions.
        >>> urlmap.map(request, '/api/999/bogus', {}, {})
        Traceback (most recent call last):
            ...
        ValueError: Unknown API level: 999
        >>> urlmap.map(request, '/api/20130900/bogus', {}, {})
        Traceback (most recent call last):
            ...
        ValueError: Unknown command: bogus

        The root currently just redirects to /in/Inbox/:
        >>> o, r = urlmap.map(request, '/', {}, {})
        >>> r, r.args
        (<...UrlRedirect instance at 0x...>, ['/in/Inbox/'])

        Tag searches have an /in/TAGNAME shorthand:
        >>> urlmap.map(request, '/in/Inbox/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]

        Thread shortcuts are /thread/METADATAID/:
        >>> urlmap.map(request, '/thread/123/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.View...>]

        Other commands use the command name as the first path component:
        >>> urlmap.map(request, '/search/bjarni', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]
        >>> urlmap.map(request, '/compose/=123/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.compose.Compose...>]
        """

        # Check the API first.
        if path.startswith('/%s/' % self.MAP_API):
            path_parts = path.split('/')
            if int(path_parts[2]) not in self.API_VERSIONS:
                raise ValueError('Unknown API level: %s' % path_parts[2])
            path_parts = path_parts[3:]
            return [
                self._choose_output(path_parts, fmt='json'),
                self._command(path_parts[0], args=path_parts[1:],
                                             query_data=query_data,
                                             post_data=post_data)
            ]

        # For non-API calls, strip prefixes before further processing
        path_parts = path[1:].split('/')
        output = [self._choose_output(path_parts)]

        # Check for the registered priority shortcuts
        if path_parts[0] in self.MAP_PATHS:
            method = self.MAP_PATHS[path_parts[0]]
            return output + method(self, request, path_parts,
                                         query_data, post_data)

        # Fall back to API-style
        return output + [self._command(path_parts[0], args=path_parts[1:],
                                                      query_data=query_data,
                                                      post_data=post_data)]

    def url_thread(self, message_id):
        pass

    def url_compose(self, message_id):
        pass

    def url_tag(self, tag_id):
        pass

    def url_search(self, search_terms):
        pass

    def print_map_markdown(self):
        """Prints the current URL map to stdout as markdown."""
        api_version = self.API_VERSIONS[-1]
        def cmds(method):
            return sorted([(c[0].replace('=', ''), c[1])
                           for c in self._api_commands(method=method)])
        print '# Mailpile URL map (autogenerated by %s)' % __file__
        print
        print '\n'.join([line.strip() for line
                         in UrlMap.__doc__.strip().splitlines()[2:]])
        print
        print '## The API paths (version=%s, JSON output)' % api_version
        print
        api = '/api/%s' % api_version
        for method in ('GET', 'POST', 'UPDATE', 'DELETE'):
            commands = cmds(method)
            if commands:
                print '### %s%s' % (method, method == 'GET' and
                                            ' (also accept POST)' or '')
                print
            # FIXME: Subcommands?
            for command in commands:
                cls = command[1]
                if cls.HTTP_QUERY_VARS:
                    qs = '?' + '&'.join(['%s=[%s]' % (v, cls.HTTP_QUERY_VARS[v])
                                         for v in cls.HTTP_QUERY_VARS])
                else:
                    qs = ''
                print '    %s/%s/%s' % (api, command[0], qs)
                if cls.HTTP_POST_VARS:
                    ps = '&'.join(['%s=[%s]' % (v, cls.HTTP_POST_VARS[v])
                                   for v in cls.HTTP_POST_VARS])
                    print '    ... POST only: %s' % ps
            print
        print
        print '## Pretty shortcuts (HTML output)'
        print
        for path in sorted(self.MAP_PATHS.keys()):
            doc = self.MAP_PATHS[path].__doc__.strip().split('\n')[0]
            path = ('/%s/' % path).replace('//', '/')
            print '    %s %s %s' % (path, ' ' * (10-len(path)), doc)
        print
        print '## Default command URLs (HTML output)'
        print
        for command in sorted(list(set(cmds('GET') + cmds('POST')))):
            print '    /%s/' % (command[0], )
        print


class UrlRedirectException(Exception):
    """An exception indicating we need to redirecting to another URL."""
    def __init__(self, url):
        Exception.__init__(self, 'Should redirect to: %s' % url)
        self.url = url


class _UrlRedirect(mailpile.commands.Command):
    """A stub command which just throws UrlRedirectException."""
    ORDER = ('', )
    HTTP_CALLABLE = ( )
    def command(self):
        raise UrlRedirectException(self.args[0])


if __name__ != "__main__":
    # If loaded as a module, register our redirect command
    try:
        mailpile.plugins.register_command('_urlrdr', '_redirect', _UrlRedirect)
    except mailpile.plugins.PluginError:
        pass
else:
    # If run as a python script, print map and run doctests.
    import doctest
    import mailpile.app
    import mailpile.ui
    session = mailpile.ui.Session(mailpile.app.ConfigManager())
    session.config['tag'] = {
        '0': 'New',
        '1': 'Inbox'
    }
    urlmap = UrlMap(session)
    urlmap.print_map_markdown()
    print
    print '<!-- %s -->' % (doctest.testmod(optionflags=doctest.ELLIPSIS,
                                           extraglobs={'urlmap': urlmap,
                                                       'request': None}), )

