from urlparse import parse_qs, urlparse

from mailpile.commands import COMMANDS


class UrlMap:
    """This class will map HTTP requests to Mailpile commands."""
    API_VERSIONS = (0, )

    def __init__(self, session):
        self.session = session

    def _prefix_to_query(self, path, query_data, post_data):
        """
        Turn a /variable/value prefix into a query-string argument and
        return a new path with the prefix stripped.

        >>> query_data = {}
        >>> path = urlmap._prefix_to_query('/var/val/stuff', query_data, {})
        >>> path, query_data
        ('/stuff', {'var': ['val']})
        """
        which, value, path = path[1:].split('/', 2)
        query_data[which] = [value]
        return '/'+path

    def _command(self, name, args=None, query_data=None, post_data=None):
        """
        Return an instantiated mailpile.command object or raise a ValueError.

        >>> urlmap._command('output', args=['html'])
        <mailpile.commands.Output instance at 0x...>
        >>> urlmap._command('bogus')
        Traceback (most recent call last):
            ...
        ValueError: Unknown command: bogus
        """
        match = [c for c in COMMANDS.values() if c[0] in (name, name+'=')]
        if len(match) != 1:
          raise ValueError('Unknown command: %s' % name)
        # FIXME: Create data
        data = {}
        return match[0][1](self.session, name, args, data=data)

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
            for suffix in ('.json', '.xml', '.vcf'):
               if fn.endswith(suffix):
                   fmt = suffix[1:]
        return self._command('output', [fmt])

    PREFIX = {
        'show': _prefix_to_query,
    }
    def _strip_prefixes(self, path, query_data, post_data):
        """
        Strip common prefixes, possibly modifying the query_data and
        post_data dictionaries in the process, depending on what the
        handler for a given prefix does.

        Returns a new path and path_parts list, with prefixes removed. 
        >>> query = {}
        >>> urlmap._strip_prefixes('/show/a/b', query, {})
        ('/b', ['b'])
        >>> query
        {'show': ['a']}
        """
        path_parts = path[1:].split('/')
        while path_parts[0] in self.PREFIX:
            path = self.PREFIX[path_parts[0]](self, path,
                                              query_data, post_data)
            path_parts = path[1:].split('/')
        return path, path_parts

    # FIXME: This should redirect, not serve directly
    def _map_root(self, request, path_parts, query_data, post_data):
        tag_search = ['tag:%s' % self.session.config.get_tag_id('inbox')]
        return [
            self._command('search', args=tag_search,
                                    query_data=query_data,
                                    post_data=post_data)
        ]

    # FIXME: This should come from the search plugin
    def _map_tag(self, request, path_parts, query_data, post_data):
        """
        Map the /in/ prefix to a tag search.

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
        Map the /thread/ prefix to a view command.

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

    MAP_API = 'api'
    MAP_PATHS = {
       '':       _map_root,
       'in':     _map_tag,
       'thread': _map_thread
    }
    def map(self, request, path, query_data, post_data):
        """
        Convert an HTTP request to a bunch mailpile.command objects.

        >>> urlmap.map(request, '/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]

        Standard prefix paths
        >>> urlmap.map(request, '/show/ugly/search/bjarni', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]

        The /api/ URL space is versioned and provides access to all the
        built-in commands. Requesting the wrong version or a bugs command
        throws exceptions.
        >>> urlmap.map(request, '/api/999/bogus', {}, {})
        Traceback (most recent call last):
            ...
        ValueError: Unknown API level: 999
        >>> urlmap.map(request, '/api/0/bogus', {}, {})
        Traceback (most recent call last):
            ...
        ValueError: Unknown command: bogus

        >>> urlmap.map(request, '/', {}, {})
        'FIXME: Should redirect'

        >>> urlmap.map(request, '/in/Inbox/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]

        >>> urlmap.map(request, '/thread/123/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.View...>]

        >>> urlmap.map(request, '/search/bjarni', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]
        """

        # Check the API first. Prefix paths are not supported in the API.
        if path.startswith('/%s/' % self.MAP_API):
            path_parts = path.split('/')
            if int(path_parts[2]) not in self.API_VERSIONS:
                raise ValueError('Unknown API level: %s' % path_parts[2])
            path_parts = path_parts[3:]
            return [
                self._choose_output(path_parts),
                self._command(path_parts[0], args=path_parts[1:],
                                             query_data=query_data,
                                             post_data=post_data)
            ]

        # For non-API calls, strip prefixes before further processing
        path, path_parts = self._strip_prefixes(path, query_data, post_data)
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


# Dummy config class for testing
if __name__ == "__main__":
        import doctest
        import mailpile.app
        import mailpile.ui
        session = mailpile.ui.Session(mailpile.app.ConfigManager())
        session.config['tag'] = {
          '0': 'New',
          '1': 'Inbox'
        }
        doctest.testmod(optionflags=doctest.ELLIPSIS, extraglobs={
            'urlmap': UrlMap(session),
            'request': None
        })
