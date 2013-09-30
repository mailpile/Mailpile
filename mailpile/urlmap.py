from urlparse import parse_qs, urlparse
from urllib import quote

from mailpile.commands import Command, COMMANDS
import mailpile.plugins
from mailpile.util import *


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
    API_VERSIONS = (0, )

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
        return '/' + path

    def _api_commands(self, method, strict=False):
        return [c for c in COMMANDS
                        if (not method) or
                           (c.SYNOPSIS[2] and (method in c.HTTP_CALLABLE or
                                               not strict))]

    def _command(self, name, args=None, query_data=None, post_data=None,
                             method='GET'):
        """
        Return an instantiated mailpile.command object or raise a UsageError.

        >>> urlmap._command('output', args=['html'], method=False)
        <mailpile.commands.Output instance at 0x...>
        >>> urlmap._command('bogus')
        Traceback (most recent call last):
            ...
        UsageError: Unknown command: bogus
        """
        try:
            match = [c for c in self._api_commands(method)
                             if (method and name == c.SYNOPSIS[2]) or
                                (not method and name == c.SYNOPSIS[1])]
            if len(match) != 1:
                raise UsageError('Unknown command: %s' % name)
        except ValueError, e:
            raise UsageError(str(e))
        command = match[0]

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
        >>> path_parts = '/a/b/as.json'.split('/')
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
        Traceback (most recent call last):
          ...
        UsageError: Invalid output format: b
        """
        if len(path_parts) > 1 and not path_parts[-1]:
            path_parts.pop(-1)
        else:
            fn = path_parts.pop(-1)
            for suffix in ('.html', '.jhtml'):
                if fn.endswith(suffix):
                    # FIXME: We are passing user input here which may
                    #        have security implications.
                    return self._command('output', [fn], method=False)
            for suffix in ('as.json', 'as.xml', 'as.vcf'):
                if fn == suffix:
                    return self._command('output', [suffix[3:]], method=False)
            raise UsageError('Invalid output format: %s' % fn)
        return self._command('output', [fmt], method=False)

    def _map_root(self, request, path_parts, query_data, post_data):
        """Redirects to /in/Inbox/ for now.  (FIXME)"""
        return [UrlRedirect(self.session, 'redirect', arg=['/in/Inbox/'])]

    def _map_tag(self, request, path_parts, query_data, post_data):
        """
        Map /in/TAG_NAME/ to tag searches.

        >>> path = '/in/Inbox/as.json'
        >>> commands = urlmap._map_tag(request, path[1:].split('/'), {}, {})
        >>> commands
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]
        >>> commands[0].args
        ['json']
        >>> commands[1].args
        ['tag:1']
        """
        output = self._choose_output(path_parts)
        tag = '/'.join([p for p in path_parts[1:] if p])
        tag_search = ['tag:%s' % self.session.config.get_tag_id(tag)]
        return [
            output,
            self._command('search', args=tag_search,
                                    query_data=query_data,
                                    post_data=post_data)
        ]

    def _map_thread(self, request, path_parts, query_data, post_data):
        """
        Map /thread/METADATA_ID/... to view or extract commands.

        >>> path = '/thread/=123/'
        >>> commands = urlmap._map_thread(request, path[1:].split('/'), {}, {})
        >>> commands
        [<mailpile.commands.Output...>, <mailpile.plugins.search.View...>]
        >>> commands[1].args
        ['=123']
        """
        message_mid = path_parts[1]
        return [
            self._choose_output(path_parts),
            self._command('message', args=[message_mid],
                                     query_data=query_data,
                                     post_data=post_data)
        ]

    def _map_RESERVED(self, *args):
        """RESERVED FOR LATER."""

    def _map_api_command(self, method, path_parts,
                               query_data, post_data, fmt='html'):
        """Map a path to a command list, prefering the longest match.

        >>> urlmap._map_api_command('GET', ['http', 'redir', ''], {}, {})
        [<mailpile.commands.Output...>, <...UrlRedirect...>]
        """
        output = self._choose_output(path_parts, fmt=fmt)
        for bp in reversed(range(1, len(path_parts) + 1)):
            try:
                return [
                    output,
                    self._command('/'.join(path_parts[:bp]),
                                  args=path_parts[bp:],
                                  query_data=query_data,
                                  post_data=post_data,
                                  method=method)
                ]
            except (ValueError, UsageError):
                pass
        raise UsageError('Not available for %s: %s' % (method,
                                                       '/'.join(path_parts)))

    MAP_API = 'api'
    MAP_PATHS = {
       '':        _map_root,
       'in':      _map_tag,
       'thread':  _map_thread,
       'static':  _map_RESERVED,
    }

    def map(self, request, method, path, query_data, post_data):
        """
        Convert an HTTP request to a list of mailpile.command objects.

        >>> urlmap.map(request, 'GET', '/in/Inbox/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]

        The /api/ URL space is versioned and provides access to all the
        built-in commands. Requesting the wrong version or a bogus command
        throws exceptions.
        >>> urlmap.map(request, 'GET', '/api/999/bogus/', {}, {})
        Traceback (most recent call last):
            ...
        UsageError: Unknown API level: 999
        >>> urlmap.map(request, 'GET', '/api/0/bogus/', {}, {})
        Traceback (most recent call last):
            ...
        UsageError: Not available for GET: bogus

        The root currently just redirects to /in/Inbox/:
        >>> r = urlmap.map(request, 'GET', '/', {}, {})[0]
        >>> r, r.args
        (<...UrlRedirect instance at 0x...>, ['/in/Inbox/'])

        Tag searches have an /in/TAGNAME shorthand:
        >>> urlmap.map(request, 'GET', '/in/Inbox/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]

        Thread shortcuts are /thread/METADATAID/:
        >>> urlmap.map(request, 'GET', '/thread/123/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.View...>]

        Other commands use the command name as the first path component:
        >>> urlmap.map(request, 'GET', '/search/bjarni/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.search.Search...>]
        >>> urlmap.map(request, 'GET', '/message/compose/=123/', {}, {})
        [<mailpile.commands.Output...>, <mailpile.plugins.compose.Compose...>]
        """

        # Check the API first.
        if path.startswith('/%s/' % self.MAP_API):
            path_parts = path.split('/')
            if int(path_parts[2]) not in self.API_VERSIONS:
                raise UsageError('Unknown API level: %s' % path_parts[2])
            return self._map_api_command(method, path_parts[3:],
                                         query_data, post_data, fmt='json')

        path_parts = path[1:].split('/')
        try:
            return self._map_api_command(method, path_parts[:],
                                         query_data, post_data)
        except UsageError:
            # Finally check for the registered shortcuts
            if path_parts[0] in self.MAP_PATHS:
                mapper = self.MAP_PATHS[path_parts[0]]
                return mapper(self, request, path_parts, query_data, post_data)
            raise

    def _url(self, url, output='', qs=''):
        if output and '.' not in output:
            output = 'as.%s' % output
        return ''.join([url, output, qs and '?' or '', qs])

    def url_thread(self, message_id, output=''):
        """Map a message to it's short-hand thread URL."""
        return self._url('/thread/=%s/' % message_id, output)

    def url_compose(self, message_id, output=''):
        """Map a message to it's short-hand editing URL."""
        return self._url('/message/compose/=%s/' % message_id, output)

    def url_tag(self, tag_id, output=''):
        """
        Map a tag to it's short-hand URL.

        >>> urlmap.url_tag('Inbox')
        '/in/Inbox/'
        >>> urlmap.url_tag('Inbox', output='json')
        '/in/Inbox/as.json'
        >>> urlmap.url_tag('1')
        '/in/Inbox/'

        Unknown tags raise an exception.
        >>> urlmap.url_tag('99')
        Traceback (most recent call last):
            ...
        ValueError: Unknown tag: 99
        """
        if tag_id in self.session.config.get('tag', {}):
            return self._url('/in/%s/' % self.session.config['tag'][tag_id],
                             output)
        elif tag_id in self.session.config.get('tag', {}).values():
            return self._url('/in/%s/' % tag_id, output)
        raise ValueError('Unknown tag: %s' % tag_id)

    def url_sent(self, output=''):
        """Return the URL of the Sent tag"""
        return self.url_tag('Sent', output=output)

    def url_search(self, search_terms, tag=None, output=''):
        """
        Map a search query to it's short-hand URL, using Tag prefixes if
        there is exactly one tag in the search terms or we have tag context.

        >>> urlmap.url_search(['foo', 'bar', 'baz'])
        '/search/?q=foo%20bar%20baz'
        >>> urlmap.url_search(['foo', 'tag:Inbox', 'wtf'], output='json')
        '/in/Inbox/as.json?q=foo%20wtf'
        >>> urlmap.url_search(['foo', 'tag:Inbox', 'tag:New'], output='xml')
        '/search/as.xml?q=foo%20tag%3AInbox%20tag%3ANew'
        >>> urlmap.url_search(['foo', 'tag:Inbox', 'tag:New'], tag='Inbox')
        '/in/Inbox/?q=foo%20tag%3ANew'
        """
        tags = tag and [tag] or [t for t in search_terms
                                         if t.startswith('tag:')]
        if len(tags) == 1:
            prefix = self.url_tag(tags[0].replace('tag:', ''))
            search_terms = [t for t in search_terms
                                    if t not in tags and
                                       t.replace('tag:', '') not in tags]
        else:
            prefix = '/search/'
        return self._url(prefix, output, 'q=' + quote(' '.join(search_terms)))

    def map_as_markdown(self):
        """Describe the current URL map as markdown"""

        api_version = self.API_VERSIONS[-1]
        text = []

        def cmds(method):
            return sorted([(c.SYNOPSIS[2], c)
                           for c in self._api_commands(method, strict=True)])

        text.extend([
            '# Mailpile URL map (autogenerated by %s)' % __file__,
            '',
            '\n'.join([line.strip() for line
                       in UrlMap.__doc__.strip().splitlines()[2:]]),
            '',
            '## The API paths (version=%s, JSON output)' % api_version,
            '',
        ])
        api = '/api/%s' % api_version
        for method in ('GET', 'POST', 'UPDATE', 'DELETE'):
            commands = cmds(method)
            if commands:
                text.extend([
                    '### %s%s' % (method, method == 'GET' and
                                          ' (also accept POST)' or ''),
                    '',
                ])
            commands.sort()
            for command in commands:
                cls = command[1]
                query_vars = cls.HTTP_QUERY_VARS
                pos_args = (cls.SYNOPSIS[3] and
                            unicode(cls.SYNOPSIS[3]).replace(' ', '/') or '')
                padding = ' ' * (18 - len(command[0]))
                newline = '\n' + ' ' * (len(api) + len(command[0]) + 6)
                if query_vars:
                    qs = '?' + '&'.join(['%s=[%s]' % (v, query_vars[v])
                                         for v in query_vars])
                else:
                    qs = ''
                if qs:
                    qs = '%s%s' % (padding, qs)
                if pos_args:
                    pos_args = '%s%s/' % (padding, pos_args)
                    if qs:
                        qs = newline + qs
                text.append('    %s/%s/%s%s' % (api, command[0], pos_args, qs))
                if cls.HTTP_POST_VARS:
                    ps = '&'.join(['%s=[%s]' % (v, cls.HTTP_POST_VARS[v])
                                   for v in cls.HTTP_POST_VARS])
                    text.append('    ... POST only: %s' % ps)
            text.append('')
        text.extend([
            '',
            '## Pretty shortcuts (HTML output)',
            '',
        ])
        for path in sorted(self.MAP_PATHS.keys()):
            doc = self.MAP_PATHS[path].__doc__.strip().split('\n')[0]
            path = ('/%s/' % path).replace('//', '/')
            text.append('    %s %s %s' % (path, ' ' * (10 - len(path)), doc))
        text.extend([
            '',
            '## Default command URLs (HTML output)',
            '',
            '*These accept the same arguments as the API calls above.*',
            '',
        ])
        for command in sorted(list(set(cmds('GET') + cmds('POST')))):
            text.append('    /%s/' % (command[0], ))
        text.append('')
        return '\n'.join(text)

    def print_map_markdown(self):
        """Prints the current URL map to stdout in markdown"""
        print self.map_as_markdown()


class UrlRedirect(Command):
    """A stub command which just throws UrlRedirectException."""
    SYNOPSIS = (None, 'redirect', 'http/redir', '<url>')
    HTTP_CALLABLE = ('GET', 'POST', 'PUT', 'UPDATE')
    RAISES = (UrlRedirectException, )

    def command(self):
        raise UrlRedirectException(self.args[0])


class HelpUrlMap(Command):
    """Describe the current API and URL mapping"""
    SYNOPSIS = (None, 'help/urlmap', 'help/urlmap', None)

    class CommandResult(Command.CommandResult):
        def as_text(self):
            return self.result.get('urlmap', 'Missing')

        def as_html(self, *args, **kwargs):
            try:
                from markdown import markdown
                html = markdown(str(self.result['urlmap']))
            except:
                import traceback
                print traceback.format_exc()
                html = '<pre>%s</pre>' % escape_html(self.result['urlmap'])
            self.result['markdown'] = html
            return Command.CommandResult.as_html(self, *args, **kwargs)

    def command(self):
        return {'urlmap': UrlMap(self.session).map_as_markdown()}


if __name__ != "__main__":
    mailpile.plugins.register_commands(HelpUrlMap)

else:
    # If run as a python script, print map and run doctests.
    import doctest
    import mailpile.app
    import mailpile.plugins
    import mailpile.ui

    session = mailpile.ui.Session(mailpile.app.ConfigManager())
    session.config['tag'] = {
        '0': 'New',
        '1': 'Inbox'
    }
    urlmap = UrlMap(session)
    urlmap.print_map_markdown()

    # For the UrlMap._map_api_command test
    mailpile.plugins.register_commands(UrlRedirect)

    print
    print '<!-- %s -->' % (doctest.testmod(optionflags=doctest.ELLIPSIS,
                                           extraglobs={'urlmap': urlmap,
                                                       'request': None}), )
