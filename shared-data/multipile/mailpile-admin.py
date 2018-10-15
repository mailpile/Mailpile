#!/usr/bin/env python2.7
#
# This is the Mailpile admin tool! It can do these things:
#
#  - Configure Apache for use with Mailpile (multi-user, proxying)
#  - Start or stop a user's Mailpile (in a screen session)
#  - Function as a CGI script to start Mailpile and reconfigure Apache
#
import argparse
import cgi
import ConfigParser
import copy
import distutils.spawn
import getpass
import json
import os
import pwd
import random
import re
import socket
import subprocess
import sys
import time


# Default paths
DEFAULT_CONFIG_FILE = '/etc/mailpile/multipile.rc'
DEFAULT_CONFIG_SECTION = 'Multipile'
MAILPILE_PIDS_PATH = "/var/lib/mailpile/pids"
APACHE_DEFAULT_WEBROOT = "/mailpile"
APACHE_REWRITEMAP_PATH = "/var/lib/mailpile/apache/usermap.txt"
APACHE_SUDOERS_PATH = "/etc/sudoers.d/mailpile-apache"


MAILPILE_STOP_SCRIPT = [
    # Ask it to shut down nicely, remove pid-file if not running.
    'kill "%(pid)s" || (rm -f "%(pidfile)s"; false)',
    'sleep 10',
    # Remove pid-file iff shutdown succeeded.
    'kill "%(pid)s" || (rm -f "%(pidfile)s"; true)']

MAILPILE_FORCE_STOP_SCRIPT = [
    # If still running, wait 20 more seconds and then force things.
    'kill -INT "%(pid)s" && (sleep 20; kill -9 "%(pid)s") || true',
    # Clean up!
    'rm -f "%(pidfile)s"']

MAILPILE_START_SCRIPT = [
    # We start Mailpile in a screen session named "mailpile"
    'screen -S mailpile -d -m "%(mailpile)s"'
        ' "--www=%(host)s:%(port)s%(path)s"'
        ' "--idlequit=%(idlequit)s"'
        ' "--pid=%(pidfile)s"'
        ' --interact']

MAILPILE_LAUNCH_SCRIPT = [
    'sudo %(mailpile-launcher)s %(user)s'
        ' %(idlequit)s %(host)s:%(port)s%(path)s']

MAILPILE_DELETE_SCRIPT = [
    'rm -rf ~%(user)s/.local/share/Mailpile/default']


CONFIGURE_APACHE_SCRIPT = [
    '"%(packager)s" install screen sudo',
    '"%(a2enmod)s" headers rewrite proxy proxy_http cgi',
    'mkdir -p /var/lib/mailpile/apache/ /var/lib/mailpile/pids/',
    'touch /var/lib/mailpile/apache/usermap.txt',
    'touch %(multipile-www)s/admin.cgi',
    'chmod +x %(multipile-www)s/admin.cgi',
    '"%(a2enconf)s" mailpile',
    '"%(apache2ctl)s" restart']

FIX_PERMS_SCRIPT = [
    'chown -R %(apache-user)s:%(apache-group)s /var/lib/mailpile/apache',
    'chmod go+rwxt /var/lib/mailpile/pids',]


# This is the Apache config template
APACHE_CONFIG_TEMPLATE = """\
#
# This is the Mailpile multi-user Apache config
#
Alias "%(webroot)s/default-theme" "%(mailpile-theme)s"
Alias "%(webroot)s" "%(multipile-www)s"

RewriteEngine On
RewriteMap mailpile_u2hp "txt:%(rewritemap)s"

<Directory "%(mailpile-theme)s">
    Require all granted
</Directory>
<Directory "%(multipile-www)s">
    AllowOverride All
    Options FollowSymLinks ExecCGI
    AddHandler cgi-script .cgi
    LogLevel alert rewrite:trace8
    Require all granted

    # Show a helpful error if we're incorrectly configured
    RewriteCond ${mailpile_u2hp:apache_map_test} !=ok
    RewriteCond %%{REQUEST_URI} !.*/apache-broken.html$
    RewriteRule .* %(webroot)s/apache-broken.html [L,R=302,E=nolcache:1]

    # Redirect users
    RewriteCond %%{REQUEST_FILENAME} !-f
    RewriteRule ^([^/]+)(/.*) http://${mailpile_u2hp:$1}%(webroot)s/$1$2 [L,P,QSA]

    # Redirect any proxy errors or 404 errors to our login page
    ErrorDocument 503 %(webroot)s/not-running.html
    ErrorDocument 502 %(webroot)s/not-running.html
    ErrorDocument 404 %(webroot)s/not-running.html
    RewriteRule ^not-running.html %(webroot)s/ [L,R=302,E=nolcache:1]

    # Avoid caching our error pages
    Header always set Cache-Control "no-store, no-cache, must-revalidate" env=nocache
    Header always set Expires "Thu, 01 Jan 1970 00:00:00 GMT" env=nocache
</Directory>
"""

# This is what allows Apache to launch Mailpile on behalf of other users.
APACHE_SUDOERS_TEMPLATE = """\
www-data\tALL = NOPASSWD: %(mailpile-launcher)s
"""


# This is needed to ensure that we run mailpile-admin with the
# right python interpreter
CGI_SCRIPT_TEMPLATE = """\
#!/bin/bash
exec %(interpreter)s "$(dirname $0)"/../mailpile-admin.py "$@"
"""


# We prefer rewritemaps whenever possible!
APACHE_REWRITEMAP_LINE = "%(user)s %(host)s:%(port)s"
APACHE_REWRITEMAP_TEMPLATE = """\
##
## usermap.txt - User map to mailpile port
##

%(rewriterules)s
apache_map_test ok

## EOF
"""


def _escape(string):
    return json.dumps(unicode(string).encode('utf-8'))[1:-1]


def _escaped(idict):
    return dict((k, _escape(v)) for k, v in idict.iteritems())


def app_arguments_config_arg(ap):
    ap.add_argument(
        '--config', default='', help='Path to a configuration file')


def app_arguments():
    ap = argparse.ArgumentParser(
        description="Mailpile administration and system integration tool")

    ga = ap.add_mutually_exclusive_group(required=True)
    ga.add_argument(
        '--list', action='store_true',
        help='List running Mailpiles')
    ga.add_argument(
        '--start', action='store_true',
        help='Launch new Mailpile in a screen session')
    ga.add_argument(
        '--launch', action='store_true',
        help='Launch exiting Mailpile in a screen session')
    ga.add_argument(
        '--stop', action='store_true',
        help='Stop a running Mailpile')
    ga.add_argument(
        '--delete', action='store_true',
        help='Delete a user\'s Mailpile data (requires --force)')
    ga.add_argument(
        '--configure-apache', action='store_true',
        help='Configure Apache for use with Mailpile (run with sudo)')
    ga.add_argument(
        '--configure-apache-usermap', action='store_true',
        help='Update the Apache user/rewrite map (run with sudo)')
    ga.add_argument(
        '--generate-apache-config', action='store_true',
        help='Print the apache config')
    ga.add_argument(
        '--generate-apache-sudoers', action='store_true',
        help='Print the apache sudoers config')
    ga.add_argument(
        '--generate-apache-usermap', action='store_true',
        help='Prints a rewritemap file (use --blank for an empty one)')

    app_arguments_config_arg(ap)
    ap.add_argument('--force', action='store_true',
        help='With --stop, will kill -9 a running Mailpile')
    ap.add_argument('--user', default=None,
        help='Choose user, for use with --stop and --start')
    ap.add_argument('--port', default=None,
        help='Choose port, for use with --stop and --start')
    ap.add_argument('--host', default='localhost',
        help='Choose host, for use with --stop and --start')
    ap.add_argument('--idlequit', default=(7*24*3600),
        help='Mailpile shutdown after idling this many seconds')
    ap.add_argument('--webroot', default=APACHE_DEFAULT_WEBROOT,
        help='Parent web directory for Mailpile instances')
    ap.add_argument('--mailpile', default=None,
        help='Path to the Mailpile app itself')
    ap.add_argument('--mailpile-share', default=None,
        help='Location of Mailpile shared data')
    ap.add_argument('--mailpile-theme', default=None,
        help='Location of Mailpile theme files')
    ap.add_argument('--multipile-www', default=None,
        help='Location of Mailpile/Multipile files')
    ap.add_argument('--apache-sudoers', default=APACHE_SUDOERS_PATH,
        help='Sudoers config: path to Mailpile/Apache sudoers file')
    ap.add_argument('--rewritemap', default=APACHE_REWRITEMAP_PATH,
        help='Apache config: path to rewrite-map file')
    ap.add_argument('--blank', action='store_true',
        help='Apache config: blank slate; ignore running Mailpiles')
    ap.add_argument('--discover', action='store_true',
        help='Apache config: discover running Mailpiles')
    ap.add_argument('--packager', default=None,
        help='Apache config: OS packaging tool (apt-get)')
    ap.add_argument('--interpreter', default=None,
        help='Python interpreter: python interpreter to use')
    ap.add_argument('--a2enmod', default=None,
        help='Apache config: path to a2enmod utility')
    ap.add_argument('--a2enconf', default=None,
        help='Apache config: path to a2enmod utility')
    ap.add_argument('--apache2ctl', default=None,
        help='Apache config: path to apache2ctl utility')
    ap.add_argument('--apache-user', default=None,
        help='Apache config: Apache process unix username')
    ap.add_argument('--apache-group', default=None,
        help='Apache config: Apache process unix group')
    ap.add_argument('--apache-confs', default=None,
        help='Apache config: /etc/apache2/conf-available/ ?')

    return ap


def usage(ap, reason, code=3):
    print 'error: %s' % reason
    ap.print_usage()
    sys.exit(code)


def parse_config(app_args,
                 conf_parsed=None,
                 config=DEFAULT_CONFIG_FILE,
                 section=DEFAULT_CONFIG_SECTION):
    conf_file = config
    if config:
        if os.path.exists(conf_file):
            config = ConfigParser.SafeConfigParser()
            config.read([conf_file])
            app_args.set_defaults(**dict(config.items(section)))
        elif conf_parsed and conf_parsed.config:
            usage(app_args, 'Config file not found: %s' % conf_file)


def parse_arguments_and_config(app_args,
                               config=DEFAULT_CONFIG_FILE,
                               section=DEFAULT_CONFIG_SECTION):
    # We create a separate parser just to check for --config
    conf_parser = argparse.ArgumentParser(add_help=False)
    app_arguments_config_arg(conf_parser)
    conf_parsed, unused_rest = conf_parser.parse_known_args()

    # Okay, if we have a config file, parse it!
    parse_config(app_args, conf_parsed,
                 config=conf_parsed.config or config,
                 section=section)

    return app_args.parse_args()


def _parse_ps():
    ps = subprocess.Popen(['ps', 'auxw'], stdout=subprocess.PIPE)
    ps_re = re.compile('^(\S+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+(\S+)'
                       '.*\s(?:(?:python[\d\.]*|pypy) +)?'
                       '(?:\S+/)?(mailpile)(?:\s+|$)')
    for line in ps.communicate()[0].splitlines():
        m = re.match(ps_re, line)
        if m:
            yield (m.group(1), m.group(2), m.group(3), m.group(4))


def _parse_netstat():
    ns = subprocess.Popen(['netstat', '-ant', '--program'],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ns_re = re.compile('^tcp\s+\S+\s+\S+\s+(\S+:\d+)\s+(\S+:.)'
                       '\s+.*?\s(\d+)\/(\S+)\s*$')
    for line in ns.communicate()[0].splitlines():
        m = re.match(ns_re, line)
        if m:
            lhp, rhp, pid, proc = m.group(1), m.group(2), m.group(3), m.group(4)
            yield lhp, rhp, pid, proc


def _get_random_port():
    ns = _parse_netstat()
    for tries in range(0, 100):
       port = '%s' % random.randint(34110, 64110)
       cport = ':' + port
       for lhp, rhp, pid, proc in ns:
           if lhp.endswith(cport):
               port = None
               break
       if port:
           return port
    assert(not 'All the ports appear taken!')


def get_mailpile_shared_datadir():
    # IMPORTANT: This code is duplicated in mailpile/config.py.
    #            If it needs changing please change both places!
    #
    # Why? The code is duplicated here, so when running in CGI mode
    # we don't have to load & parse the full Mailpile app just to
    # find this path.
    #
    env_share = os.getenv('MAILPILE_SHARED')
    if env_share is not None:
        return env_share

    # Check if we are running in a virtual env
    # http://stackoverflow.com/questions/1871549/python-determine-if-running-inside-virtualenv
    # We must also check that we are installed in the virtual env,
    # not just that we are running in a virtual env.
    if (hasattr(sys, 'real_prefix') or hasattr(sys, 'base_prefix')) and __file__.startswith(sys.prefix):
        return os.path.join(sys.prefix, 'share', 'mailpile')

    # Check if we've been installed to /usr/local (or equivalent)
    usr_local = os.path.join(sys.prefix, 'local')
    if __file__.startswith(usr_local):
        return os.path.join(usr_local, 'share', 'mailpile')

    # Check if we are in /usr/ (sys.prefix)
    if __file__.startswith(sys.prefix):
        return os.path.join(sys.prefix, 'share', 'mailpile')

    # Else assume dev mode, source tree layout
    # NOTE: This differs from mailpile/config.py!
    return os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))


def find_mailpile_executable():
    mailpile = distutils.spawn.find_executable(
        'mailpile',
        os.path.join(sys.prefix, 'bin') + ':' + os.environ.get('PATH')
    )

    if mailpile:
        return mailpile

    # NOTE: mp_root is only correct when running from source!
    mp_root = os.path.join(os.path.join(os.path.dirname(__file__), '..', '..'))
    mp_root = os.path.realpath(mp_root)
    return os.path.join(mp_root, 'mp')


def get_os_settings(args):
    # FIXME: Detect OS, choose settings; these are the Ubuntu/Debian defaults.

    mp_share = args.mailpile_share or get_mailpile_shared_datadir()

    return {
        'packager': args.packager or 'apt-get',
        'interpreter': args.interpreter or sys.executable,
        'a2enmod': args.a2enmod or 'a2enmod',
        'a2enconf': args.a2enconf or 'a2enconf',
        'apache2ctl': args.apache2ctl or 'apache2ctl',
        'apache-user': args.apache_user or 'www-data',
        'apache-group': args.apache_group or 'www-data',
        'apache-confs': args.apache_confs or '/etc/apache2/conf-available',
        'webroot': args.webroot,
        'rewritemap': args.rewritemap,
        'apache-sudoers': args.apache_sudoers,
        'mailpile': args.mailpile or find_mailpile_executable(),
        'mailpile-launcher': os.path.join(mp_share,
                                          'multipile', 'mailpile-launcher.py'),
        'mailpile-admin': os.path.realpath(sys.argv[0]),
        'mailpile-theme': (args.mailpile_theme
                           or os.path.join(mp_share, 'default-theme')),
        'multipile-www': (args.multipile_www
                          or os.path.join(mp_share, 'multipile', 'www'))}


def get_user_settings(args, user=None, mailpiles=None):
    settings = get_os_settings(args)
    user = user or pwd.getpwuid(os.getuid()).pw_name
    assert('.' not in user and '/' not in user)
    pidfile = os.path.join(MAILPILE_PIDS_PATH, user + '.pid')

    port = args.port
    if mailpiles and not port:
        ports = [int(m[2]) for m in mailpiles.values() if m[0] == user]
        if ports:
            port = '%s' % min(ports)
    if not port:
        port = _get_random_port()

    return {
        'user': user,
        'mailpile': settings['mailpile'],
        'mailpile-launcher': settings['mailpile-launcher'],
        'host': '127.0.0.1',
        'port': port,
        'path': ('%s/%s/' % (args.webroot, user)).replace('//', '/'),
        'pidfile': pidfile,
        'idlequit': args.idlequit,
        'pid': os.path.exists(pidfile) and open(pidfile, 'r').read().strip()}


def discover_mailpiles(mailpiles=None):
    mailpiles = mailpiles if (mailpiles is not None) else {}

    # Check the process table for running Mailpiles
    processes = {}
    for username, pid, rss, proc in _parse_ps():
        processes[pid] = [username, proc, rss]

    # Add the listening host:port details from netstat
    for listening_hostport, rhp, pid, proc in _parse_netstat():
        if pid in processes:
            processes[pid].append(listening_hostport)

    for pid, details in processes.iteritems():
        username, proc, rss, listening = (details[0], details[1],
                                          details[2], details[3:])
        if listening:
            hostport = sorted(listening)[0]
            host, port = hostport.split(':')
            if hostport not in mailpiles:
                mailpiles[hostport] = (username, host, port, False, pid, rss)
            else:
                mailpiles[hostport][4] = pid
                mailpiles[hostport][5] = rss

    return mailpiles


def _rewritemap(mailpiles):
    rules = []
    added = {}
    count = 1
    for hostport, details in mailpiles.iteritems():
        user, host, port = details[0:3]
        suffix = ''
        if user in added:
            print 'WARNING: User %s has multiple Mailpiles!' % user
            suffix = '.%d' % (added[user] + 1)

        rules.append(
            APACHE_REWRITEMAP_LINE % {
                'user': _escape(user)+suffix,
                'host': host,
                'port': port})
        added[user] = added.get(user, 0) + 1

    return '\n'.join(rules)


def parse_rewritemap(args, os_settings, mailpiles=None):
    mailpiles = mailpiles if (mailpiles is not None) else {}
    try:
        parse = re.compile('^(?P<user>[^#]+) (?P<host>[^:]+):(?P<port>.+)')
        with open(args.rewritemap, 'r') as fd:
            for line in fd:
                m = re.match(parse, line)
                if m:
                    user = m.group('user')
                    host = m.group('host')
                    port = m.group('port')
                    mailpiles['%s:%s' % (host, port)] = [
                        user, host, port, True, None, None]
    except (OSError, IOError, KeyError), err:
        print 'WARNING: %s' % err
    return mailpiles


def save_rewritemap(args, os_settings, mailpiles):
    with open(args.rewritemap + '.new', 'w') as fd:
        os_settings['rewriterules'] = _rewritemap(mailpiles)
        fd.write(APACHE_REWRITEMAP_TEMPLATE % os_settings)

    if os.path.exists(args.rewritemap):
        os.remove(args.rewritemap)

    os.rename(args.rewritemap + '.new', args.rewritemap)


def parse_usermap(args, os_settings, mailpiles=None):
    return parse_rewritemap(args, os_settings, mailpiles=mailpiles)


def save_usermap(args, os_settings, mailpiles):
    return save_rewritemap(args, os_settings, mailpiles)


def save_cgi(os_settings):
    with open(os.path.join(os_settings['multipile-www'], 'admin.cgi'), 'w') as fd:
        fd.write(CGI_SCRIPT_TEMPLATE % os_settings)


def save_apache_sudoers(os_settings):
    with open(os_settings['apache-sudoers'], 'w') as fd:
        fd.write(APACHE_SUDOERS_TEMPLATE % os_settings)


def run_script(args, settings, script):
    for line in script:
        line = line % _escaped(settings)
        print '==> %s' % line
        rv = os.system(line)
        if 0 != rv:
            print '==[ FAILED! Exit code: %s ]==' % rv
            return
    print '===[ SUCCESS! ]==='


def _get_mailpiles(args, os_settings, discover=False):
    mailpiles = {}
    if not args.blank:
        parse_usermap(args, os_settings, mailpiles=mailpiles)
        if args.discover or discover:
            discover_mailpiles(mailpiles=mailpiles)
    return mailpiles


def list_mailpiles(args):
    os_settings = get_os_settings(args)
    mailpiles = _get_mailpiles(args, os_settings, discover=True)
    fmt =  '%-8.8s %6.6s %6.6s %-6.6s %5.5s %s'
    user_counts = {}
    print fmt % ('USER', 'PID', 'RSS', 'ACCESS', 'PORT', 'URL')
    for hostport in sorted(mailpiles.keys()):
        user, host, port, in_usermap, pid, rss = mailpiles[hostport]
        user_counts[user] = user_counts.get(user, 0) + 1
        status = []
        if in_usermap:
            url = 'http://%s%s/%s/' % (socket.gethostname(),
                                      os_settings['webroot'], user)
        else:
            url = 'http://%s:%s/' % (host, port)
        print fmt % (
            user, pid or '?', rss or '',
            'apache' if in_usermap else 'direct', port, url)

def generate_apache_usermap(app_args, args):
    mailpiles = _get_mailpiles(args, get_os_settings(args))
    print(APACHE_REWRITEMAP_TEMPLATE % {'rewriterules': _rewritemap(mailpiles)})

def generate_apache_sudoers(app_args, args):
    print(APACHE_SUDOERS_TEMPLATE % get_os_settings(args))

def generate_apache_config(app_args, args):
    print (APACHE_CONFIG_TEMPLATE % get_os_settings(args))

def configure_apache(app_args, args):
    if os.getuid() == 0:
        os_settings = get_os_settings(args)
        with open(os.path.join(os_settings['apache-confs'], 'mailpile.conf'),
                  'w') as fd:
            fd.write(APACHE_CONFIG_TEMPLATE % os_settings)

        run_script(args, os_settings, CONFIGURE_APACHE_SCRIPT)
        save_cgi(os_settings)
        save_apache_sudoers(os_settings)
        save_usermap(args, os_settings, _get_mailpiles(args, os_settings))
        run_script(args, os_settings, FIX_PERMS_SCRIPT)
    else:
        usage(app_args, 'Please run this as root!')

def configure_apache_usermap(app_args, args):
    if os.getuid() == 0:
        os_settings = get_os_settings(args)
        save_usermap(args, os_settings, _get_mailpiles(args, os_settings))
    else:
        usage(app_args, 'Please run this as root!')


def start_mailpile(app_args, args):
    os_settings = get_os_settings(args)
    mailpiles = parse_usermap(args, os_settings)
    user_settings = get_user_settings(args, user=args.user, mailpiles=mailpiles)
    assert(re.match('^[0-9]+$', user_settings['port']) is not None)
    assert(re.match('^[a-z0-9\.]+$', user_settings['host']) is not None)
    if args.user:
        command = '%s "%s" --start --port="%s" --host="%s"' % (
            _escape(os_settings['interpreter']),
            _escape(os_settings['mailpile-admin']),
            _escape(user_settings['port']),
            _escape(user_settings['host']))
        script = ['sudo -iHu "%(user)s" -- ' + command]
    else:
        script = MAILPILE_START_SCRIPT

    if script:
        run_script(args, user_settings, script)

    if args.user:
        hostport = '%s:%s' % (user_settings['host'], user_settings['port'])
        mailpiles[hostport] = (user_settings['user'],
                               user_settings['host'],
                               user_settings['port'],
                               False, None, None)
        save_usermap(args, os_settings, mailpiles)
        run_script(args, os_settings, FIX_PERMS_SCRIPT)


def launch_mailpile(app_args, args):
    assert(args.user)
    os_settings = get_os_settings(args)
    mailpiles = parse_usermap(args, os_settings)
    user_settings = get_user_settings(args, user=args.user, mailpiles=mailpiles)
    run_script(args, user_settings, MAILPILE_LAUNCH_SCRIPT)


def stop_mailpile(app_args, args):
    user_settings = get_user_settings(args, user=args.user)
    if not user_settings.get('pid'):
        usage(app_args, 'No PID found, cannot stop Mailpile', code=0)

    script = MAILPILE_STOP_SCRIPT
    if args.force:
        script += MAILPILE_FORCE_STOP_SCRIPT

    run_script(args, user_settings, script)


def delete_mailpile(app_args, args):
    user_settings = get_user_settings(args, user=args.user)
    if user_settings.get('pid'):
        usage(app_args, 'PID found, please stop Mailpile first', code=0)
    if not args.force:
        usage(app_args, 'This command is scary, use --force if sure', code=0)

    run_script(args, user_settings, MAILPILE_DELETE_SCRIPT)


def main():
    app_args = app_arguments()
    parsed_args = parse_arguments_and_config(app_args)

    if parsed_args.list:
        list_mailpiles(parsed_args)

    elif parsed_args.configure_apache:
        configure_apache(app_args, parsed_args)

    elif parsed_args.configure_apache_usermap:
        configure_apache_usermap(app_args, parsed_args)

    elif parsed_args.generate_apache_config:
        generate_apache_config(app_args, parsed_args)

    elif parsed_args.generate_apache_sudoers:
        generate_apache_sudoers(app_args, parsed_args)

    elif parsed_args.generate_apache_usermap:
        generate_apache_usermap(app_args, parsed_args)

    elif parsed_args.start:
        start_mailpile(app_args, parsed_args)

    elif parsed_args.launch:
        launch_mailpile(app_args, parsed_args)

    elif parsed_args.stop:
        stop_mailpile(app_args, parsed_args)

    elif parsed_args.delete:
        delete_mailpile(app_args, parsed_args)


def handle_cgi_post():
    app_args = app_arguments()
    parse_config(app_args)
    try:
        request = cgi.FieldStorage()
        username = request.getfirst('username').split('@')[0]

        # Sanity checks; these will raise on invalid/missing username
        assert(username)
        pwd.getpwnam(username)

        # Generate argument and settings objects for use below
        parsed_args = app_args.parse_args(['--launch', '--user', username])
        settings = get_os_settings(parsed_args)

        # Send headers now, so output doesn't confuse Apache
        print 'Location: %s/%s/' % (settings['webroot'], username)
        print 'Expires: 0'
        print

        # Launch Mailpile?
        rv = launch_mailpile(app_args, parsed_args)

        time.sleep(5)
    except:
        parsed_args = app_args.parse_args(['--launch'])
        settings = get_os_settings(parsed_args)
        print 'Location: %s/?error=yes' % settings['webroot']
        print 'Expires: 0'
        print


if __name__ == "__main__":
    if os.getenv('REQUEST_METHOD') == 'POST':
        assert(len(sys.argv) == 1)
        handle_cgi_post()
    else:
        main()
