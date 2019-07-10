from __future__ import print_function
import cgi
import time
from urlparse import parse_qs, urlparse
from urllib import quote, urlencode

import mailpile.auth
import mailpile.security as security
from mailpile.commands import Command, COMMANDS
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.util import *


class BadMethodError(Exception):
    pass


class BadDataError(Exception):
    pass


class _FancyString(str):
    def __init__(self, *args):
        str.__init__(self, *args)
        self.filename = None


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

    def __init__(self, session=None, config=None):
        self.config = config or session.config
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
                if ((not method)
                    or (c.SYNOPSIS[2] and (method in c.HTTP_CALLABLE
                                           or not strict)))]

    def _command(self, name,
                 args=None, query_data=None, post_data=None,
                 method='GET', async=False):
        """
        Return an instantiated mailpile.command object or raise a UsageError.

        >>> urlmap._command('output', args=['html'], method=False)
        <mailpile.plugins.core.Output...>
        >>> urlmap._command('bogus')
        Traceback (most recent call last):
            ...
        UsageError: Unknown command: bogus
        >>> urlmap._command('message/update', method='GET')
        Traceback (most recent call last):
            ...
        BadMethodError: Invalid method (GET): message/update
        >>> urlmap._command('message/update', method='POST',
        ...                                   query_data={'evil': '1'})
        Traceback (most recent call last):
            ...
        BadDataError: Bad variable (evil): message/update
        >>> urlmap._command('search', args=['html'],
        ...                 query_data={'ui_': '1', 'q[]': 'foobar'})
        <mailpile.plugins.search.Search...>
        """
        try:
            match = [c for c in self._api_commands(method, strict=False)
                     if ((method and name == c.SYNOPSIS[2]) or
                         (not method and name == c.SYNOPSIS[1]))]
            if len(match) != 1:
                raise UsageError('Unknown command: %s' % name)
        except ValueError as e:
            raise UsageError(str(e))
        command = match[0]

        if method and (method not in command.HTTP_CALLABLE):
            raise BadMethodError('Invalid method (%s): %s' % (method, name))

        # FIXME: Move this somewhere smarter
        SPECIAL_VARS = ('csrf', 'arg', 'context')

        if command.HTTP_STRICT_VARS:
            prefixes = ['ui_'] + [vn[:-1] for vn in
                                  (command.HTTP_QUERY_VARS.keys() +
                                   command.HTTP_POST_VARS.keys())
                                  if vn[-1:] == '*']

            copy_q = []
            for var in (query_data or []):
                var = var.replace('[]', '')
                if (var not in command.HTTP_QUERY_VARS and
                        (var not in SPECIAL_VARS) and
                        (not [v for v in prefixes if var.startswith(v)])):
                    raise BadDataError('Bad variable (%s): %s' % (var, name))
                else:
                    copy_q.append(var)

            copy_p = []
            for var in (post_data or []):
                var = var.replace('[]', '')
                if ((var not in command.HTTP_QUERY_VARS) and
                        (var not in command.HTTP_POST_VARS) and
                        (var not in SPECIAL_VARS) and
                        (not [v for v in prefixes if var.startswith(v)])):
                    raise BadDataError('Bad variable (%s): %s' % (var, name))
                else:
                    copy_p.append(var)

            copy_vars = [(copy_q, query_data),
                         (copy_p, post_data),
                         (['arg'], query_data)]
        else:
            for var in command.HTTP_BANNED_VARS:
                var = var.replace('[]', '')
                if ((query_data and var in query_data) or
                        (post_data and var in post_data)):
                    raise BadDataError('Bad variable (%s): %s' % (var, name))

            copy_vars = (((query_data or {}).keys(), query_data),
                         ((post_data or {}).keys(), post_data),
                         (['arg'], query_data))

        data = {
            '_method': method
        }
        for vlist, src in copy_vars:
            for var in vlist:
                varBB = var + '[]'
                if src and (var in src or varBB in src):
                    sdata = src[var] if (var in src) else src[varBB]
                    if isinstance(sdata, cgi.FieldStorage):
                        if hasattr(sdata, 'filename'):
                            data[var] = [_FancyString(sdata.value)]
                            data[var][0].filename = sdata.filename
                        else:
                            data[var] = [sdata.value.decode('utf-8')]
                    else:
                        data[var] = [d.decode('utf-8') for d in sdata]

        return command(self.session, name, args, data=data, async=async)

    OUTPUT_SUFFIXES = ['.css', '.html', '.js',  '.json', '.rss', '.txt',
                       '.text', '.vcf', '.xml', '.csv',
                       # These are the template-based ones which can
                       # be embedded in JSON.
                       '.jcss', '.jhtml', '.jjs', '.jrss', '.jtxt',
                       '.jxml']

    def _choose_output(self, path_parts, fmt='html'):
        """
        Return an output command based on the URL filename component.

        As a side-effect, the filename component will be removed from the
        path_parts list.
        >>> path_parts = '/a/b/as.json'.split('/')
        >>> command = urlmap._choose_output(path_parts)
        >>> (path_parts, command)
        (['', 'a', 'b'], <mailpile.plugins.core.Output...>)

        If there is no filename part, the path_parts list is unchanged
        aside from stripping off the trailing empty string if present.
        >>> path_parts = '/a/b/'.split('/')
        >>> command = urlmap._choose_output(path_parts)
        >>> (path_parts, command)
        (['', 'a', 'b'], <mailpile.plugins.core.Output...>)

        >>> path_parts = '/a/b'.split('/')
        >>> command = urlmap._choose_output(path_parts)
        Traceback (most recent call last):
          ...
        UsageError: Invalid output format: b

        >>> path_parts = '/a/b/%%%%%bogon.json'.split('/')
        >>> command = urlmap._choose_output(path_parts)
        Traceback (most recent call last):
          ...
        UsageError: Invalid output format: %%%%%bogon.json
        """
        if len(path_parts) > 1 and not path_parts[-1]:
            path_parts.pop(-1)
        else:
            om = path_parts.pop(-1)
            if re.match(r'^[a-zA-Z0-9\.!_-]+$', om):
                fn = om.split('!')[0]  # Strip off !mode suffixes
                for suffix in self.OUTPUT_SUFFIXES:
                    if fn.endswith(suffix) or suffix == ('.' + fn):
                        return self._command('output', [om], method=False)
            raise UsageError('Invalid output format: %s' % om)
        return self._command('output', [fmt], method=False)

    def _map_root(self, request, path_parts, query_data, post_data):
        """Redirects to /profiles/ for now.  (FIXME)"""
        destination = '%s/profiles/' % self.config.sys.http_path
        return [UrlRedirect(self.session, 'redirect', arg=[destination])]

    def _map_tag(self, request, path_parts, query_data, post_data):
        """
        Map /in/TAG_NAME/[@<pos>]/ to tag searches.

        >>> path = '/in/inbox/@20/as.json'
        >>> commands = urlmap._map_tag(request, path[1:].split('/'), {}, {})
        >>> commands
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.search.Search...>]
        >>> commands[0].args
        ('as.json',)
        >>> commands[1].args
        ('@20', 'in:inbox')
        """
        output = self._choose_output(path_parts)

        pos = None
        while path_parts and (path_parts[-1][0] in ('@', )):
            pos = path_parts[-1].startswith('@') and path_parts.pop(-1)

        tag_slug = '/'.join([p for p in path_parts[1:] if p])
        tag = self.config.get_tag(tag_slug)
        tag_search = [term for term in (tag.search_terms % tag).split()
                      if term] if tag is not None else ["in:%s" % tag_slug]
        if tag is not None and tag.search_order and 'order' not in query_data:
            query_data['order'] = [tag.search_order]

        if pos:
            tag_search[:0] = [pos]

        return [
            output,
            self._command('search',
                          args=tag_search,
                          query_data=query_data,
                          post_data=post_data)
        ]

    def _map_thread(self, request, path_parts, query_data, post_data):
        """
        Map /thread/METADATA_ID/... to view or extract commands.

        >>> path = '/thread/=123/'
        >>> commands = urlmap._map_thread(request, path[1:].split('/'), {}, {})
        >>> commands
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.search.View...>]
        >>> commands[1].args
        ('=123',)
        """
        message_mids, i = [], 1
        while path_parts[i].startswith('='):
            message_mids.append(path_parts[i])
            i += 1
        return [
            self._choose_output(path_parts),
            self._command('message',
                          args=message_mids,
                          query_data=query_data,
                          post_data=post_data)
        ]

    def _map_RESERVED(self, *args):
        """RESERVED FOR LATER."""

    def _map_api_command(self, method, path_parts,
                         query_data, post_data, fmt='html', async=False):
        """Map a path to a command list, prefering the longest match.

        >>> urlmap._map_api_command('GET', ['message', 'draft', ''], {}, {})
        [<mailpile.plugins.core.Output...>, <...Draft...>]
        >>> urlmap._map_api_command('POST', ['message', 'update', ''], {}, {})
        [<mailpile.plugins.core.Output...>, <...Update...>]
        >>> urlmap._map_api_command('GET', ['message', 'update', ''], {}, {})
        Traceback (most recent call last):
            ...
        UsageError: Not available for GET: message/update
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
                                  method=method,
                                  async=async)
                ]
            except UsageError:
                pass
            except BadMethodError:
                break
        raise UsageError('Not available for %s: %s' % (method,
                                                       '/'.join(path_parts)))

    MAP_API = 'api'
    MAP_ASYNC_API = 'async'
    MAP_PATHS = {
        '': _map_root,
        'in': _map_tag,
        'thread': _map_thread,
        'static': _map_RESERVED,
    }

    def map(self, request, method, path, query_data, post_data,
            authenticate=False):
        """
        Convert an HTTP request to a list of mailpile.command objects.

        >>> urlmap.map(request, 'GET', '/in/inbox/', {}, {})
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.search.Search...>]

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

        This is the async version of the API.
        >>> urlmap.map(request, 'GET', '/async/0/search/', {}, {})
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.search.Search...>]

        The root currently just redirects to /profiles/:
        >>> r = urlmap.map(request, 'GET', '/', {}, {})[0]
        >>> r, r.args
        (<...UrlRedirect...>, ('/profiles/',))

        Tag searches have an /in/TAGNAME shorthand:
        >>> urlmap.map(request, 'GET', '/in/inbox/', {}, {})
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.search.Search...>]

        Thread shortcuts are /thread/METADATAID/:
        >>> urlmap.map(request, 'GET', '/thread/123/', {}, {})
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.search.View...>]

        Other commands use the command name as the first path component:
        >>> urlmap.map(request, 'GET', '/search/bjarni/', {}, {})
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.search.Search...>]
        >>> urlmap.map(request, 'GET', '/message/draft/=123/', {}, {})
        [<mailpile.plugins.core.Output...>, <mailpile.plugins.compose.Draft...>]
        """

        if self.session:
            sid = self.session.ui.html_variables.get('http_session')
            user_session = (mailpile.auth.SESSION_CACHE.get(sid)
                            if sid else None)
        else:
            sid = user_session = None

        is_async = path.startswith('/%s/' % self.MAP_ASYNC_API)
        is_api = path.startswith('/%s/' % self.MAP_API)

        if authenticate:
            def auth(commands, user_session):
                if user_session:
                    if user_session.is_expired():
                        mailpile.auth.SESSION_CACHE.delete_expired()
                        user_session = None
                    else:
                        user_session.update_ts()
                    if user_session and method == 'POST':
                        if isinstance(post_data, cgi.FieldStorage):
                            try:
                                csrf = post_data['csrf'].value
                            except KeyError:
                                csrf = ''
                        else:
                            csrf = post_data.get('csrf', [''])[0]
                        if not security.valid_csrf_token(
                                request.server.secret, sid, csrf):
                            user_session = None
                if not user_session or not user_session.auth:
                    for c in commands:
                        if (c.HTTP_AUTH_REQUIRED is True or
                               (c.HTTP_AUTH_REQUIRED == 'Maybe' and
                                self.session.config.prefs.gpg_recipient)):
                            if is_async or is_api:
                                raise AccessError()
                            self.redirect_to_auth_or_setup(method, path,
                                                           query_data)
                return commands
        else:
            def auth(commands, user_session):
                return commands

        # Check the API first.
        if is_api or is_async:
            path_parts = path.split('/')
            if int(path_parts[2]) not in self.API_VERSIONS:
                raise UsageError('Unknown API level: %s' % path_parts[2])
            return auth(self._map_api_command(method, path_parts[3:],
                                              query_data, post_data,
                                              fmt='json', async=is_async),
                        user_session)

        path_parts = path[1:].split('/')
        try:
            return auth(self._map_api_command(method, path_parts[:],
                                              query_data, post_data),
                        user_session)
        except UsageError:
            # Finally check for the registered shortcuts
            if path_parts[0] in self.MAP_PATHS:
                # Just redirect potentially mapped paths straightaway
                if authenticate and (not user_session or
                                     not user_session.auth):
                    self.redirect_to_auth_or_setup(method, path, query_data)

                mapper = self.MAP_PATHS[path_parts[0]]
                return auth(mapper(self, request, path_parts,
                                   query_data, post_data),
                            user_session)
            raise

    def _url(self, url, output='', qs=''):
        if output and '.' not in output:
            output = 'as.%s' % output
        return ''.join([self.config.sys.http_path,
                        url, output, qs and '?' or '', qs])

    def url_thread(self, message_id, output=''):
        """Map a message to it's short-hand thread URL."""
        return self._url('/thread/=%s/' % message_id, output)

    def url_source(self, message_id, output=''):
        """Map a message to it's raw message source URL."""
        return self._url('/message/raw/=%s/as.text' % message_id, output)

    def url_edit(self, message_id, output=''):
        """Map a message to it's short-hand editing URL."""
        return self._url('/message/draft/=%s/' % message_id, output)

    def redirect_to_auth_or_setup(self, method, path, query_data, setup=True):
        """Redirect to the /auth/ or a /setup/* endpoint"""
        from mailpile.plugins.setup_magic import Setup

        if method.lower() == 'get':
            qd = [(k, v) for k, vl in query_data.iteritems() for v in vl]
            if '_path' not in query_data:
                qd.append(('_path', path))
        else:
            qd = []

        if setup:
            nxt = Setup.Next(self.session.config, mailpile.auth.Authenticate)
            if nxt.HTTP_AUTH_REQUIRED is True:
                nxt = mailpile.auth.Authenticate
            path = '/%s/' % nxt.SYNOPSIS[2]
        else:
            path = '/%s/' % mailpile.auth.Authenticate.SYNOPSIS[2]

        raise UrlRedirectException(self._url(path, qs=urlencode(qd)))

    def redirect_to_auth(self, method, path, query_data):
        return self.redirect_to_auth_or_setup(method, path, query_data,
                                              setup=False)

    def url_tag(self, tag_id, output=''):
        """
        Map a tag to it's short-hand URL.

        >>> urlmap.url_tag('Inbox')
        '/in/inbox/'
        >>> urlmap.url_tag('inbox', output='json')
        '/in/inbox/as.json'
        >>> urlmap.url_tag('1')
        '/in/inbox/'

        Unknown tags raise an exception.
        >>> urlmap.url_tag('99')
        Traceback (most recent call last):
            ...
        ValueError: Unknown tag: 99
        """
        try:
            tag = self.config.tags[tag_id]
            if tag is None:
                raise KeyError('oops')
        except (KeyError, IndexError):
            tag = [t for t in self.config.tags.values()
                   if t.slug == tag_id.lower()]
            tag = tag and tag[0]
        if tag:
            return self._url('/in/%s/' % tag.slug, output)
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
        '/in/inbox/as.json?q=foo%20wtf'
        >>> urlmap.url_search(['foo', 'in:Inbox', 'wtf'], output='json')
        '/in/inbox/as.json?q=foo%20wtf'
        >>> urlmap.url_search(['foo', 'in:Inbox', 'tag:New'], output='xml')
        '/search/as.xml?q=foo%20in%3AInbox%20tag%3ANew'
        >>> urlmap.url_search(['foo', 'tag:Inbox', 'in:New'], tag='Inbox')
        '/in/inbox/?q=foo%20in%3ANew'
        """
        tags = tag and [tag] or [t for t in search_terms
                                 if (t.startswith('tag:') or
                                     t.startswith('in:'))]
        if len(tags) == 1:
            prefix = self.url_tag(
                tags[0].replace('tag:', '').replace('in:', ''))
            search_terms = [t for t in search_terms
                            if (t not in tags and
                                t.replace('tag:', '').replace('in:', '')
                                not in tags)]
        else:
            prefix = '/search/'
        return self._url(prefix, output, 'q=' + quote(' '.join(search_terms)))

    def canonical_url(self, cls):
        """Return the full versioned URL for a command"""
        return '/api/%s/%s/' % (cls.API_VERSION or self.API_VERSIONS[-1],
                                cls.SYNOPSIS[2])

    def ui_url(self, cls):
        """Return the full user-facing URL for a command"""
        return '/%s/' % cls.SYNOPSIS[2]

    def context_url(self, cls):
        """Return the UI context URL for a command"""
        return '/%s/' % (cls.UI_CONTEXT or cls.SYNOPSIS[2])

    def map_as_markdown(self, prefix=None):
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
            commands = [c for c in cmds(method)
                        if not prefix or (c[0] and c[0].startswith(prefix))]
            if commands:
                text.extend([
                    '### %s%s' % (method, method == 'GET' and
                                  ' (also accept POST)' or ''),
                    '',
                ])
            commands.sort()
            for command in commands:
                cls = command[1]
                url = self.canonical_url(cls)
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
                text.append('    %s%s%s' % (url, pos_args, qs))
                if cls.HTTP_POST_VARS:
                    ps = '&'.join(['%s=[%s]' % (v, cls.HTTP_POST_VARS[v])
                                   for v in cls.HTTP_POST_VARS])
                    text.append('    ... POST only: %s' % ps)
            text.append('')

        if not prefix:
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
            if prefix and not command[0].startswith(prefix):
                continue
            text.append('    /%s/' % (command[0], ))
        text.append('')
        return '\n'.join(text)

    def print_map_markdown(self):
        """Prints the current URL map to stdout in markdown"""
        print(self.map_as_markdown())


class UrlRedirect(Command):
    """A stub command which just throws UrlRedirectException."""
    SYNOPSIS = (None, None, 'http/redirect', '<url>')
    HTTP_CALLABLE = ()

    def command(self):
        raise UrlRedirectException(self.args[0])


class UrlRedirectEdit(Command):
    """A stub command which just throws UrlRedirectException."""
    SYNOPSIS = (None, None, 'http/redirect/url_edit', '<mid>')
    HTTP_CALLABLE = ()

    def command(self):
        mid = self.args[0]
        raise UrlRedirectException(UrlMap(self.session).url_edit(mid))


class UrlRedirectThread(Command):
    """A stub command which just throws UrlRedirectException."""
    SYNOPSIS = (None, None, 'http/redirect/url_thread', '<mid>')
    HTTP_CALLABLE = ()

    def command(self):
        mid = self.args[0]
        raise UrlRedirectException(UrlMap(self.session).url_thread(mid))


class HelpUrlMap(Command):
    """Describe the current API and URL mapping"""
    SYNOPSIS = (None, 'help/urlmap', 'help/urlmap', '[<prefix>]')

    class CommandResult(Command.CommandResult):
        def as_text(self):
            return self.result.get('urlmap', 'Missing')

        def as_html(self, *args, **kwargs):
            try:
                from markdown import markdown
                html = markdown(str(self.result['urlmap']))
            except:
                import traceback
                print(traceback.format_exc())
                html = '<pre>%s</pre>' % escape_html(self.result['urlmap'])
            self.result['markdown'] = html
            return Command.CommandResult.as_html(self, *args, **kwargs)

    def command(self):
        prefix = self.args[0] if self.args else None
        return {'urlmap': UrlMap(self.session).map_as_markdown(prefix=prefix)}


plugin_manager = PluginManager(builtin=True)
if __name__ != "__main__":
    plugin_manager.register_commands(HelpUrlMap, UrlRedirect,
                                     UrlRedirectEdit, UrlRedirectThread)

else:
    # If run as a python script, print map and run doctests.
    import doctest
    import sys
    import mailpile.app
    import mailpile.config.defaults as defaults
    import mailpile.config.manager as cfg_manager
    import mailpile.plugins
    import mailpile.ui

    # Import all the default plugins
    from mailpile.plugins import *

    rules = defaults.CONFIG_RULES
    config = cfg_manager.ConfigManager(rules=rules)
    config.tags.extend([
        {'name': 'New',   'slug': 'New'},
        {'name': 'Inbox', 'slug': 'Inbox'},
    ])
    session = mailpile.ui.Session(config)
    urlmap = UrlMap(session)
    if '-nomap' in sys.argv:
        # For the UrlMap._map_api_command test
        plugin_manager.register_commands(UrlRedirect)

        results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                                  extraglobs={'urlmap': urlmap,
                                              'request': None})
        print('%s' % (results, ))
        if results.failed:
            sys.exit(1)
    else:
        urlmap.print_map_markdown()
