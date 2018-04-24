import copy
import datetime
import os
import random
import socket
import sys
from urllib import urlencode
from urllib2 import urlopen
from lxml import objectify

import mailpile.auth
import mailpile.security as security
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.config.defaults import CONFIG_RULES, APPVER
from mailpile.i18n import ListTranslations, ActivateTranslation, gettext
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.plugins import PLUGINS
from mailpile.plugins.contacts import AddProfile, ListProfiles
from mailpile.plugins.contacts import ListProfiles
from mailpile.plugins.migrate import Migrate
from mailpile.plugins.motd import MOTD_URL_TOR_ONLY_NO_MARS
from mailpile.plugins.setup_magic_ispdb import STATIC_ISPDB
from mailpile.plugins.tags import AddTag
from mailpile.commands import Command
from mailpile.crypto.gpgi import SignatureInfo, EncryptionInfo
from mailpile.eventlog import Event
from mailpile.httpd import BLOCK_HTTPD_LOCK, Idle_HTTPD
from mailpile.smtp_client import SendMail, SendMailError
from mailpile.urlmap import UrlMap
from mailpile.ui import Session, SilentInteraction
from mailpile.util import *


_ = lambda s: s
_plugins = PluginManager(builtin=__file__)


##[ Commands ]################################################################

class SetupMagic(Command):
    """Perform initial setup"""
    SYNOPSIS = (None, None, None, None)
    ORDER = ('Internals', 0)
    LOG_PROGRESS = True
    COMMAND_SECURITY = security.CC_CHANGE_CONFIG

    TAGS = {
        'New': {
            'type': 'unread',
            'label': False,
            'display': 'invisible',
            'icon': 'icon-new',
            'label_color': '03-gray-dark',
            'name': _('New'),
        },
        'Inbox': {
            'type': 'inbox',
            'display': 'priority',
            'display_order': 2,
            'icon': 'icon-inbox',
            'label_color': '06-blue',
            'notify_new': True,
            'name': _('Inbox'),
        },
        'Blank': {
            'type': 'blank',
            'flag_editable': True,
            'flag_msg_only': True,
            'flag_allow_add': False,
            'display': 'invisible',
            'template': 'outgoing',
            'name': _('Blank'),
        },
        'Drafts': {
            'type': 'drafts',
            'flag_editable': True,
            'flag_msg_only': True,
            'flag_allow_add': False,
            'display': 'priority',
            'display_order': 1,
            'template': 'drafts',
            'icon': 'icon-compose',
            'label_color': '03-gray-dark',
            'name': _('Drafts'),
        },
        'Outbox': {
            'type': 'outbox',
            'flag_msg_only': True,
            'flag_allow_add': False,
            'display': 'priority',
            'display_order': 3,
            'template': 'outbox',
            'icon': 'icon-outbox',
            'label_color': '06-blue',
            'name': _('Outbox'),
        },
        'Sent': {
            'type': 'sent',
            'flag_msg_only': True,
            'display': 'priority',
            'display_order': 4,
            'template': 'sent',
            'icon': 'icon-sent',
            'label_color': '03-gray-dark',
            'name': _('Sent'),
        },
        'Spam': {
            'slug': 'spam',
            'type': 'spam',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 5,
            'icon': 'icon-spam',
            'label_color': '10-orange',
            'name': _('Spam'),
            'auto_after': 30,
            'auto_action': '-spam +trash',
            'auto_tag': 'fancy'
        },
        'MaybeSpam': {
            'display': 'invisible',
            'icon': 'icon-spam',
            'label_color': '10-orange',
            'name': _('MaybeSpam'),
        },
        'Ham': {
            'type': 'ham',
            'display': 'invisible',
            'name': _('Ham'),
        },
        'Trash': {
            'slug': 'trash',
            'type': 'trash',
            'flag_hides': True,
            'display': 'priority',
            'display_order': 6,
            'template': 'trash',
            'icon': 'icon-trash',
            'label_color': '13-brown',
            'auto_after': 91,
            'auto_action': '!delete',
            'name': _('Trash'),
        },
        # These are magical tags that perform searches and show
        # messages in contextual views.
# FIXME: This is a good idea, but not quite ready to ship.
#       'Conversations': {
#           'type': 'replied',
#           'icon': 'icon-forum',
#           'label': False,
#           'label_color': '05-blue-light',
#           'name': _('Conversations'),
#           'display_order': 1001,
#       },
        'Photos': {
            'type': 'search',
            'icon': 'icon-photos',
            'label': False,
            'label_color': '08-green',
            'template': 'photos',
            'name': _('Photos'),
            'display_order': 1002,
            '_filters': ['att:jpg is:personal'],
        },
        'Documents': {
            'type': 'search',
            'icon': 'icon-document',
            'label': False,
            'label_color': '06-blue',
            'template': 'atts',
            'name': _('Documents'),
            'display_order': 1003,
            '_filters': ['has:document is:personal'],
        },
        # These are placeholder tags that perform searches - these are
        # generally to be avoided as they break the user expectation of
        # how tags behave. A normal tag + filter is almost always the
        # right choice!
        'All Mail': {
            'type': 'search',
            'icon': 'icon-logo',
            'label': False,
            'label_color': '06-blue',
            'search_terms': 'all:mail',
            'name': _('All Mail'),
            'display_order': 1100,
        },
        # These are internal tags, used for tracking user actions on
        # messages, as input for machine learning algorithms. These get
        # automatically added, and may be automatically removed as well
        # to keep the working sets reasonably small.
        'mp_rpl': {'type': 'replied', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_fwd': {'type': 'fwded', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_tag': {'type': 'tagged', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_read': {'type': 'read', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
        'mp_ham': {'type': 'ham', 'label': False, 'display': 'invisible',
                   'flag_msg_only': True},
    }

    def basic_app_config(self, session,
                         save_and_update_workers=True,
                         want_daemons=True):
        session.ui.notify(_('Disabling lockdown'))
        security.DISABLE_LOCKDOWN = True
        # Create local mailboxes
        session.config.open_local_mailbox(session)

        # Create standard tags and filters
        created = []
        for t, tag_settings in self.TAGS.iteritems():
            tag_settings = copy.copy(tag_settings)

            tid = session.config.get_tag_id(t.replace(' ', '-'))
            if not tid:
                AddTag(session, arg=[t]).run(save=False)
                tid = session.config.get_tag_id(t)
                created.append(t)
            if not tid:
                session.ui.notify(_('Failed to create tag: %s') % t)
                continue

            tag_info = session.config.tags[tid]

            # Delete any old filters...
            old_fids = [f for f, v in session.config.filters.iteritems()
                        if v.primary_tag == tid]
            if old_fids:
                session.config.filter_delete(*old_fids)

            # Create new ones?
            tag_filters = tag_settings.get('_filters', [])
            for search in tag_filters:
                session.config.filters.append({
                    'type': 'system',
                    'terms': search,
                    'tags': '+%s' % tid,
                    'primary_tag': tid,
                    'comment': t
                })
            if tag_filters:
                del tag_settings['_filters']
            for k in ('magic_terms', 'search_terms', 'search_order'):
                if k in tag_info:
                    del tag_info[k]
            tag_info.update(tag_settings)

        for stype, statuses in (('sig', SignatureInfo.STATUSES),
                                ('enc', EncryptionInfo.STATUSES)):
            for status in statuses:
                tagname = 'mp_%s-%s' % (stype, status)
                if not session.config.get_tag_id(tagname):
                    AddTag(session, arg=[tagname]).run(save=False)
                    created.append(tagname)
                session.config.get_tag(tagname).update({
                    'type': 'attribute',
                    'flag_msg_only': True,
                    'display': 'invisible',
                    'label': False,
                })

        if 'New' in created:
            session.ui.notify(_('Created default tags'))

        # Import all the basic plugins
        reload_config = False
        for plugin in PLUGINS:
            if plugin not in session.config.sys.plugins:
                session.config.sys.plugins.append(plugin)
                reload_config = True
        for plugin in session.config.plugins.WANTED:
            if plugin in session.config.plugins.available():
                session.config.sys.plugins.append(plugin)
        if reload_config:
            with session.config._lock:
                session.config.save()
                session.config.load(session)

        try:
            # If spambayes is not installed, this will fail
            import mailpile.plugins.autotag_sb
            if 'autotag_sb' not in session.config.sys.plugins:
                session.config.sys.plugins.append('autotag_sb')
                session.ui.notify(_('Enabling SpamBayes autotagger'))
        except ImportError:
            session.ui.warning(_('Please install SpamBayes '
                                 'for super awesome spam filtering'))

        vcard_importers = session.config.prefs.vcard.importers
        if not vcard_importers.gravatar:
            vcard_importers.gravatar.append({'active': True})
            session.ui.notify(_('Enabling Gravatar image importer'))
        if not vcard_importers.libravatar:
            vcard_importers.libravatar.append({'active': True})
            session.ui.notify(_('Enabling Libravatar image importer'))

        gpg_home = os.path.expanduser('~/.gnupg')
        if not vcard_importers.gpg:
            vcard_importers.gpg.append({'active': True,
                                        'gpg_home': gpg_home})
            session.ui.notify(_('Importing contacts from GPG keyring'))

        if ('autotag_sb' in session.config.sys.plugins and
                len(session.config.prefs.autotag) == 0):
            session.config.prefs.autotag.append({
                'match_tag': 'spam',
                'unsure_tag': 'maybespam',
                'tagger': 'spambayes',
                'trainer': 'spambayes'
            })
            session.config.prefs.autotag[0].exclude_tags[0] = 'ham'

        # Mark config as up-to-date
        session.config.version = APPVER

        if save_and_update_workers:
            session.config.save()
            session.config.prepare_workers(session, daemons=want_daemons)

        # Scan GnuPG keychain in background
        from mailpile.plugins.vcard_gnupg import PGPKeysImportAsVCards
        session.config.slow_worker.add_unique_task(
            session, 'initialpgpkeyimport',
            lambda: PGPKeysImportAsVCards(session).run())

        # Enable Tor in the background, if we have it...
        session.config.slow_worker.add_unique_task(
            session, 'tor-autoconfig', lambda: SetupTor.autoconfig(session))

        session.ui.notify(_('Reenabling lockdown'))
        security.DISABLE_LOCKDOWN = False

    def make_master_key(self):
        session = self.session
        if (session.config.prefs.gpg_recipient not in (None, '', '!CREATE')
                and not session.config.master_key
                and not session.config.prefs.obfuscate_index):
            #
            # This secret is arguably the most critical bit of data in the
            # app, it is used as an encryption key and to seed hashes in
            # a few places.  As such, the user may need to type this in
            # manually as part of data recovery, so we keep it reasonably
            # sized and devoid of confusing chars.
            #
            # They okay_random() function uses os.urandom() and mixes with
            # the seed data we provide (misc app state), as well as the
            # current full-resolution time.  The output is suitable for use
            # as a password (alphanumeric, avoiding O01l).
            #
            # It should give about 281 bits of randomness:
            #
            #   import math
            #   math.log((25 + 25 + 8) ** (12 * 4), 2) == 281.183...
            #
            session.config.master_key = okay_random(12 * 4,
                                                    '%s' % session.config,
                                                    '%s' % self.session,
                                                    '%s' % self.data)
            if self._idx() and self._idx().INDEX:
                session.ui.warning(_('Unable to obfuscate search index '
                                     'without losing data. Not indexing '
                                     'encrypted mail.'))
            else:
                session.config.prefs.obfuscate_index = True
                session.config.prefs.index_encrypted = True
                session.ui.notify(_('Obfuscating search index and enabling '
                                    'indexing of encrypted e-mail. Yay!'))
            return True
        else:
            return False

    @classmethod
    def URLGet(cls, session, url, data=None):
        if url.lower().startswith('https'):
            conn_needs = [ConnBroker.OUTGOING_HTTPS]
        else:
            conn_needs = [ConnBroker.OUTGOING_HTTP]
        session.ui.mark('Getting: %s' % url)
        with ConnBroker.context(need=conn_needs) as context:
            return urlopen(url, data=data, timeout=10).read()

    def _urlget(self, url, data=None):
        return self.URLGet(self.session, url, data=data)

    def setup_command(self, session):
        pass  # Overridden by children

    def command(self, *args, **kwargs):
        return self.setup_command(self.session, *args, **kwargs)


class TestableWebbable(SetupMagic):
    HTTP_AUTH_REQUIRED = 'Maybe'
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        '_path': 'Redirect path'
    }
    HTTP_POST_VARS = {
        'testing': 'Yes or No, if testing',
        'advance': 'Yes or No, advance setup flow',
    }

    def _advance(self):
        path = self.data.get('_path', [None])[0]
        data = dict([(k, v) for k, v in self.data.iteritems()
                     if k not in self.HTTP_POST_VARS
                     and k not in ('_method',)])

        nxt = Setup.Next(self.session.config, None, needed_auth=False)
        if nxt:
            url = '/%s/' % nxt.SYNOPSIS[2]
        elif path and path != '/%s/' % Setup.SYNOPSIS[2]:
            # Use the same redirection logic as the Authenticator
            mailpile.auth.Authenticate.RedirectBack(path, data)
        else:
            url = '/'

        qs = urlencode([(k, v) for k, vl in data.iteritems() for v in vl])
        raise UrlRedirectException(''.join([self.session.config.sys.http_path, url, '?%s' % qs if qs else '']))

    def _success(self, message, result=True, advance=False):
        if advance or truthy(self.data.get('advance', ['no'])[0], default=False):
            self._advance()
        return SetupMagic._success(self, message, result=result)

    def _testing(self):
        self._testing_yes(lambda: True)
        return (self.testing is not None)

    def _testing_yes(self, method, *args, **kwargs):
        testination = self.data.get('testing')
        if testination:
            self.testing = random.randint(0, 1)
            self.testing = truthy(testination[0], default=self.testing)
            return self.testing
        self.testing = None
        return method(*args, **kwargs)

    def _testing_data(self, method, tdata, *args, **kwargs):
        result = self._testing_yes(method, *args, **kwargs) or []
        return (result
                if (self.testing is None) else
                (self.testing and tdata or []))

    def setup_command(self, session):
        raise Exception('FIXME')


class SetupGetEmailSettings(TestableWebbable):
    """Lookup, guess, test server details for an e-mail address"""
    SYNOPSIS = (None, 'setup/email_servers', 'setup/email_servers',
                "<email> <password>")
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = dict_merge(TestableWebbable.HTTP_QUERY_VARS, {
        'email': 'E-mail address',
        'timeout': 'Seconds',
        'password': 'Account password',
        'track-id': 'Tracking ID for event log'
    })
    TEST_DATA = {
        'imap_host': 'imap.wigglebonk.com',
        'imap_port': 993,
        'imap_tls': True,
        'pop3_host': 'pop3.wigglebonk.com',
        'pop3_port': 110,
        'pop3_tls': False,
        'smtp_host': 'smtp.wigglebonk.com',
        'smtp_port': 465,
        'smtp_tls': False
    }
    ISPDB_URL = 'https://autoconfig.thunderbird.net/v1.1/%(domain)s'
    AUTOCONFIG_URL = '%(protocol)s://autoconfig.%(domain)s/mail/config-v1.1.xml?emailaddress=%(email)s'
    AUTOCONFIG_ALT_URL = '%(protocol)s://%(domain)s/.well-known/autoconfig/mail/config-v1.1.xml'

    def _progress(self, message):
        if self.event and self.tracking_id:
            self.event.private_data = {"track-id": self.tracking_id}
            if 'log' in self.event.data:
                self.event.data['log'].append([int(time.time()), message])
            else:
                self.event.data['log'] = [[int(time.time()), message]]
            self.event.message = message
            self._update_event_state(self.event.RUNNING, log=True)
        else:
            self.session.ui.mark(message)

    def _log_result(self, message):
        if self.event and self.tracking_id:
            if self.event.data.get('log'):
                self.event.data['log'][-1].append(message)
        else:
            self.session.ui.mark(message)

    def _username(self, val, email):
        lpart = email.split('@')[0]
        return str(val).replace('%EMAILADDRESS%', email
                                ).replace('%EMAILLOCALPART%', lpart)

    def _source_proto(self, insrv):
        sockettype = str(insrv.socketType)
        servertype = str(insrv.get('type', ''))
        if sockettype.lower() == 'ssl':
            servertype += '_ssl'
        elif sockettype.lower() == 'starttls':
            servertype += '_tls'
        else:
            print 'FIXME/SOURCE: %s/%s' % (sockettype, servertype)
        return servertype.lower()

    def _route_proto(self, outsrv):
        sockettype = str(outsrv.socketType)
        servertype = str(outsrv.get('type', 'smtp'))
        if sockettype.lower() == 'ssl':
            servertype += 'ssl'
        elif sockettype.lower() == 'starttls':
            servertype += 'tls'
        else:
            print 'FIXME/ROUTE: %s/%s' % (sockettype, servertype)
        return servertype.lower()

    def _rank(self, entry):
        rank = 0
        proto = entry.get('protocol', 'unknown').lower()
        auth = entry.get('auth_type', 'unknown').lower()
        for srch, score in [('pop3', 1),
                            ('imap', 2),
                            ('ssl', 10),
                            ('tls', 5),
                            ('oauth2', 10),
                            ('password', 0)]:
            if srch in proto or srch in auth:
                rank -= score
        return rank

    def _clean_domain(self, domain):
        domain = domain.lower()

        # Shortcuts, to save some cycles & speed things up...
        for shortcut in ('.google.com', ):
            if domain.endswith(shortcut):
                domain = shortcut[1:]
        for prefix in ('mx.', 'mx1.', 'mail.', 'smtp.'):
            if domain.startswith(prefix) and '.' in domain[len(prefix):]:
                domain = domain[len(prefix):]

        return domain

    def _get_xml_autoconfig(self, url, domain, email):
        try:
            result = {'sources': [], 'routes': []}

            xml_data = STATIC_ISPDB.get(domain)
            if not xml_data:
                xml_data = self._urlget(url)

            if xml_data:
                data = objectify.fromstring(xml_data)
# FIXME: Massage these so they match the format of the routes and
#        sources more closely. Also look out and report the visiturl to
#        handle GMail. OAuth2 is coming up as an auth mech, we will need to
#        support it: https://bugzilla.mozilla.org/show_bug.cgi?id=1166625
                try:
                    for enable in data.emailProvider.enable:
                        result['enable'] = result.get('enable', [])
                        result['enable'].append({
                            'url': enable.get('visiturl', ''),
                            'description': str(enable.instruction)
                        })
                except AttributeError:
                    pass
                try:
                    for docs in data.emailProvider.documentation:
                        result['docs'] = result.get('docs', [])
                        result['docs'].append({
                            'url': docs.get('url', ''),
                            'description': docs.descr.text
                        })
                except AttributeError:
                    pass
                for insrv in data.emailProvider.incomingServer:
                    for auth in insrv.authentication:
                        result['sources'].append({
                            'protocol': self._source_proto(insrv),
                            'username': self._username(insrv.username, email),
                            'auth_type': str(auth),
                            'host': str(insrv.hostname),
                            'port': str(insrv.port)})
                for outsrv in data.emailProvider.outgoingServer:
                    for auth in outsrv.authentication:
                        result['routes'].append({
                            'protocol': self._route_proto(outsrv),
                            'username': self._username(outsrv.username, email),
                            'auth_type': str(auth),
                            'host': str(outsrv.hostname),
                            'port': str(outsrv.port)})
                result['sources'].sort(key=self._rank)
                result['routes'].sort(key=self._rank)
                return result
        except (IOError, ValueError, AttributeError):
            return None

    def _get_ispdb(self, email, domain):
        domain = self._clean_domain(domain)

        if domain in ('localhost',):
            return None

        self._progress(_('Checking ISPDB for %s') % domain)
        settings = self._get_xml_autoconfig(
            self.ISPDB_URL % {'domain': domain}, domain, email)
        if settings:
            self._log_result(_('Found %s in ISPDB') % domain)
            return settings
        dparts = domain.split('.')
        if len(dparts) > 2:
            domain = '.'.join(dparts[1:])
            # FIXME: Make a longer list of 2nd-level public TLDs to ignore
            if domain not in ('co.uk', 'pagekite.me'):
                return self._get_xml_autoconfig(
                    self.ISPDB_URL % {'domain': domain}, domain, email)
        return None

    def _want_anonymity(self):
        return (self.session.config.sys.proxy.protocol in ('tor', 'tor-risky')
                and not self.session.config.sys.proxy.fallback)

    def _get_mx1(self, domain):
        if domain in ('localhost',):
            return None

        # This would bypasses the connection broker and is not secured or
        # anonymized, so if the user really wants anonymity we just punt.
        if self._want_anonymity():
            return None

        import DNS
        DNS.DiscoverNameServers()
        try:
            timeout = (self.deadline - time.time()) // 2
            mxlist = DNS.DnsRequest(name=domain, qtype=DNS.Type.MX,
                                    timeout=timeout).req()
            mxs = sorted([m['data'] for m in mxlist.answers if 'data' in m])
            return mxs[0][1] if mxs else None
        except socket.error:
            return None

    def _get_domain_autoconfig(self, email, domain, mx1, ssl=True):
        protocol = 'https'
        if not ssl:
            protocol = 'http'

        for url in (self.AUTOCONFIG_URL, self.AUTOCONFIG_ALT_URL):
            for dom in (domain, mx1):
                if dom:
                    self._progress(_('Checking for autoconfig on %s') % dom)
                    settings = self._get_xml_autoconfig(
                        url % {'protocol': protocol, 'domain': dom, 'email': email},
                        dom, email)
                    if settings:
                        self._log_result(_('Found autoconfig on %s') % dom)
                        return settings

        return None

    def _guess_service_domains(self, domain,
                               mx=None, service_domains=None):
        if domain in ('localhost',):
            return {'pop3': [domain], 'imap': [domain], 'smtp': [domain]}

        import socket
        seen_ips = {'pop3': set(), 'imap': set(), 'smtp': set()}
        service_domains = {} if (service_domains is None) else service_domains
        # FIXME: Also check DNS service records?
        for prefix, protos in (('pop',  ('pop3',)),
                               ('pop3', ('pop3',)),
                               ('imap', ('imap',)),
                               ('smtp', ('smtp',)),
                               ('mail', ('imap', 'pop3', 'smtp')),
                               (None, ('imap', 'pop3', 'smtp'))):
            try:
                if prefix:
                    name = '%s.%s' % (prefix, domain)
                else:
                    name = domain

                if not self._want_anonymity():
                    ip = socket.gethostbyname(name)
                else:
                    # We just try to connect to everything if anonymity
                    # was requested - otherwise we'd be leaking over DNS.
                    ip = '%s-%s' % (prefix, protos)

                if ip:
                    for proto in protos:
                        if ip not in seen_ips[proto]:
                            seen_ips[proto].add(ip)
                            if proto in service_domains:
                                if name not in service_domains[proto]:
                                    service_domains[proto].append(name)
                            else:
                                service_domains[proto] = [name]
            except socket.gaierror:
                pass
        if mx:
            isp_domain = self._clean_domain(mx)
            self._guess_service_domains(isp_domain,
                                        service_domains=service_domains)

        return service_domains

    def _probe_port(self, host, port, encrypted=False):
        import socket
        if encrypted:
            needs = [ConnBroker.OUTGOING_RAW, ConnBroker.OUTGOING_ENCRYPTED]
        else:
            needs = [ConnBroker.OUTGOING_RAW, ConnBroker.OUTGOING_CLEARTEXT]
        with ConnBroker.context(need=needs) as cb:
            try:
                # FIXME: magic number follows
                socket.create_connection((host, port), timeout=15).close()
                return True
            except (AssertionError, IOError, OSError, socket.error):
                pass
        return False

    def _guess_settings(self, email, domain, mx1):
        # Strategy:
        #
        # 1. Look up possible service names...
        # 2. Attempt connections on well-known service ports
        #
        # Passwords and usernames are checked later, as is STARTTLS.

        args_hash = {'domain': domain, 'email': email}
        self._progress(_('Guessing settings for %(email)s') % args_hash)

        service_domains = self._guess_service_domains(domain, mx=mx1)
        self._log_result(_('Found %d potential servers')
                         % len(service_domains))
        if not service_domains:
            return None

        self._progress(_('Probing for services...'))
        result = {'sources': [], 'routes': []}
        for section, service, port, proto in (
                ('sources', 'imap', '993', 'imap_ssl'),
                ('sources', 'pop3', '995', 'pop3_ssl'),
                ('sources', 'imap', '143', 'imap'),
                ('sources', 'pop3', '110', 'pop3'),
                ('routes', 'smtp', '465', 'smtpssl'),
                ('routes', 'smtp', '587', 'smtp'),
                ('routes', 'smtp', '25', 'smtp')):
            for host in service_domains.get(service, []):
                if len(result[section]) > 3:
                    break
                if self._probe_port(host, port, encrypted=('ssl' in proto)):
                    result[section].append({
                        'protocol': proto,
                        'host': str(host),
                        'port': str(port),
                    })
                    self._progress(_('Found %(service)s server on '
                                     '%(host)s:%(port)s')
                                   % {'service': service.upper(),
                                      'host': host,
                                      'port': port})

        return result

    def _get_email_settings(self, email):
        # Thunderbird does this:
        #  - tb-install-dir/isp/example.com.xml on the harddisk
        #  - check for autoconfig.example.com
        #  - look up of "example.com" in the ISPDB
        #  - look up "MX example.com" in DNS, and for mx1.mail.hoster.com,
        #    look up "hoster.com" in the ISPDB
        #  - try to guess (imap.example.com, smtp.example.com etc.)
        #
        # We mostly follow Thunderbird's design, except we give the ISPDB
        # priority: if it has an entry, don't try autoconfig.example.com.

        domain = email.split('@')[-1].lower()
        settings = None
        mx1 = None

        if not settings and self.deadline > time.time():
            # FIXME: actually we want mx1 here but since DNS lack security that
            #        would compromise security when ISPDB gives us a result
            settings = self._get_domain_autoconfig(email, domain, None, ssl=True)

        if not settings and self.deadline > time.time():
            settings = self._get_ispdb(email, domain)

        if not settings and self.deadline > time.time():
            mx1 = self._get_mx1(domain)
            if mx1 and not mx1.endswith('.' + domain):
                settings = self._get_ispdb(email, mx1)

        if not settings and self.deadline > time.time():
            settings = self._get_domain_autoconfig(email, None, mx1, ssl=True)

        # Try the unencrypted lookups next...
        if not settings and self.deadline > time.time():
            settings = self._get_domain_autoconfig(email, domain, mx1, ssl=False)
        if not settings and self.deadline > time.time():
            settings = self._get_domain_autoconfig(email, None, mx1, ssl=False)

        if not settings and self.deadline > time.time():
            settings = self._guess_settings(email, domain, mx1)

        if self.deadline < time.time():
            self._progress(_('Ran out of time, results may be incomplete'))

        return settings

    def _test_login_and_proto(self, email, settings):
        event = Event(data={})

        if settings['protocol'].startswith('smtp'):
            try:
                safe_assert(
                    SendMail(self.session, None,
                             [(email,
                               [email, 'test@mailpile.is'], None,
                               [event])],
                             test_only=True, test_route=settings))
                return True, True
            except (IOError, OSError, AssertionError, SendMailError):
                pass

        if settings['protocol'].startswith('imap'):
            from mailpile.mail_source.imap import TestImapSettings
            if TestImapSettings(self.session, settings, event):
                return True, True

        if settings['protocol'].startswith('pop3'):
            from mailpile.mail_source.pop3 import TestPop3Settings
            if TestPop3Settings(self.session, settings, event):
                return True, True

        if ('connection' in event.data and
                event.data['connection']['error'][0] == 'auth'):
            return False, True

        if ('last_error' in event.data and event.data.get('auth')):
            return False, True

        return False, False

    def _probe_account_settings(self, email, results):
        result = results[email]
        userpart = email.split('@')[0]
        user_info = {'userpart': userpart, 'email': email}
        login_errors_total = 0
        route_open_relay = False
        for cleartext, which in ((False, 'routes'),
                                 (False, 'sources'),
                                 (True, 'routes'),
                                 (True, 'sources')):
            login_errors = 0
            servers = result[which]
            if cleartext and ((not servers) or
                              (which == 'routes' and route_open_relay) or
                              servers[0].get('username')):
                # If we have already found combinations that work for both
                # incoming and outgoing, don't send the password over the
                # network in the clear; just stop here.
                continue

            self._progress(_('Probing %s, cleartext=%s')
                           % (which, cleartext))

            for details in servers:
                for starttls, userfmt in ((True, '%(email)s'),
                                          (True, '%(userpart)s'),
                                          (True, ''),
                                          (False, '%(email)s'),
                                          (False, '%(userpart)s'),
                                          (False, '')):
                    # Skip some combinations...
                    has_ssl = (('ssl' in details['protocol']) or
                               ('tls' in details['protocol']))
                    crypto = True if (starttls or has_ssl) else False
                    if starttls and has_ssl:
                        # No STARTTLS if this server already uses TLS
                        continue
                    if crypto is cleartext:
                        # Cleartext pass: ignore starttls and ssl conns
                        # Crypto pass: require starttls OR has_ssl
                        continue
                    if time.time() > self.deadline:
                        continue
                    if not userfmt and (details['protocol'][:4] != 'smtp'
                                        or login_errors_total == 0):
                        continue

                    server_info = copy.copy(details)
                    server_info['username'] = userfmt % user_info
                    if userfmt:
                        server_info['password'] = self.password
                    if starttls:
                        if server_info['protocol'] == 'smtp':
                            server_info['protocol'] += 'tls'
                        else:
                            server_info['protocol'] += '_tls'
                        pmsg = _('Testing %(protocol)4.4s '
                                 'on %(host)s:%(port)s '
                                 'with STARTTLS as %(username)s')
                    else:
                        pmsg = _('Testing %(protocol)4.4s '
                                 'on %(host)s:%(port)s '
                                 'as %(username)s')
                    if not crypto:
                        pmsg += ' (' + _('insecure') + ')'

                    # FIXME: Unsupported protocol...
                    if server_info['protocol'] == 'pop3_tls':
                        continue

                    self._progress(pmsg % server_info)
                    lok, pok = self._test_login_and_proto(email, server_info)
                    if lok and pok:
                        self._log_result(_('Success'))
                        details.update(server_info)
                        if not userfmt:
                            route_open_relay = True
                        break
                    elif pok:
                        self._log_result(_('Protocol is OK'))
                        details['protocol'] = server_info['protocol']
                    if not lok:
                        self._log_result(_('Login failed'))
                        login_errors += 1
            if login_errors:
                # Sort the results; prefer the ones with a successful login
                order = list(range(0, len(servers)))
                order.sort(key=lambda i: (
                    0 if servers[i].get('username') else 1,
                    0 if servers[i]['protocol'][-3:] in ('ssl', 'tls') else 1,
                    0 if 'imap' in servers[i]['protocol'] else 1,
                    i))
                servers[:] = [servers[i] for i in order]
                login_errors_total += login_errors
        return login_errors_total

    def setup_command(self, session):
        results = {}
        args = list(self.args)
        self.deadline = time.time() + float(self.data.get('timeout', [60])[0])
        self.tracking_id = self.data.get('track-id', [None])[0]
        self.password = self.data.get('password', [None])[0]
        if not self.password and len(args) > 1:
            self.password = args.pop(-1)

        emails = args + self.data.get('email', [])
        if self.password and len(emails) != 1:
            return self._error(_('Can only test settings for one account '
                                 'at a time'))

        for email in emails:
            settings = self._testing_data(self._get_email_settings,
                                          self.TEST_DATA, email)
            if settings:
                results[email] = settings
                if self.password and self.deadline > time.time():
                    errors = self._probe_account_settings(email, results)
                    if errors:
                        for k in ('routes', 'sources'):
                            if (settings.get(k) and
                                    not settings[k][0].get('username')):
                                results['login_failed'] = True

            if time.time() >= self.deadline:
                break
        if results:
            return self._success(
                _('Found settings for %d addresses') % len(results),
                result=results)
        else:
            return self._error(_('No settings found'))


class SetupWelcome(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/welcome', None)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'language': 'Language selection'
    })

    def bg_setup_stage_1(self):
        # Wait a bit, so the user has something to look at befor we
        # block the web server and do real work.
        time.sleep(2)

        # Intial configuration of app goes here...
        if not self.session.config.tags:
            with BLOCK_HTTPD_LOCK, Idle_HTTPD(allowed=0):
                self.basic_app_config(self.session)

    def configure_language(self, session, config, language, save=True):
        try:
            i18n = lambda: ActivateTranslation(session, config, language)
            if not self._testing_yes(i18n):
                raise ValueError('Failed to configure i18n')
            config.prefs.language = language
            if save and not self._testing():
                self._background_save(config='!FORCE')
            return True
        except ValueError:
            return self._error(_('Invalid language: %s') % language)

    def setup_command(self, session):
        config = session.config
        if self.data.get('_method') == 'POST' or self._testing():
            language = self.data.get('language', [''])[0]
            if language:
                rv = self.configure_language(session, config, language)
                if rv is not True:
                    return rv

            config.slow_worker.add_unique_task(
                session, 'Setup, Stage 1', lambda: self.bg_setup_stage_1())

        languages = [(l, n) for l, n in ListTranslations(config).iteritems()]
        languages.sort(key=lambda k: (k[1], k[0]))
        results = {
            'languages': languages,
            'language': config.prefs.language
        }
        return self._success(_('Welcome to Mailpile!'), results)


class CreatePassword(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/mkpass', None)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'dict': 'Word list to use'
    })
    PATHS = ['/etc/dictionaries-common', '/usr/dict', '/usr/share/dict']

    def find_dictionaries(self):
        dictionaries = set([])
        for path in (p for p in self.PATHS if os.path.exists(p)):
            for fn in (os.path.join(path, f) for f in os.listdir(path)):
                fpath = os.path.realpath(fn)
                ext = fpath.split('.')[-1]
                if (not os.path.isdir(fpath)
                        and ext not in ('aff', 'hash')):
                    stat = os.stat(fpath)
                    if stat.st_size > 100000:
                        dictionaries.add((stat.st_size, fpath))
        return sorted(list(dictionaries))

    def load_dictionary(self, dpath, maxlen=6):
        return list(w for w in open(dpath, 'rb')
                    if "'" not in w and ' ' not in w and len(w) <= (maxlen+1))

    def setup_command(self, session):
        from mailpile.crypto.aes_utils import getrandbits
        from math import log

        dictionaries = self.find_dictionaries()
        dictionary = dictionaries[-1][1]
        words = self.load_dictionary(dictionary, maxlen=6)
        wanted_bits = 64
        passphrase = []
        results = {
            'dictionaries': dictionaries,
            'dictionary': dictionary
        }

        # This is our random word generation; first we shuffle the
        # dictionary (poorly), because we're going to only use the first
        # power of 2 words.
        random.shuffle(words)

        # Figure out how many bits index neatly into the file
        filebits = int(log(len(words), 2))
        filemask = (2 ** filebits) - 1

        # Encode strongly random bits using the shuffled dictionary
        while wanted_bits > 0:
            wanted_bits -= filebits
            word = words[getrandbits(filebits) & filemask].strip().lower()
            passphrase.append(word.decode('utf-8'))

        results.update({
            'dictionary_bits': filebits,
            'passphrase': ' '.join(passphrase),
            'bits': filebits * len(passphrase)
        })
        return self._success(_('Welcome to Mailpile!'), results)


class SetupPassword(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/password', None)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS, {
        'existing': 'Old Mailpile password',
        'password1': 'New Mailpile password',
        'password2': 'Confirmation password'
    })

    PASSWORD_LOCK = CryptoLock()

    def setup_command(self, session):
        config = session.config
        current_passphrase = config.passphrases['DEFAULT']
        need_password = current_passphrase.is_set()
        incorrect = mismatch = done = False
        if self.data.get('_method') == 'POST' or self._testing():
            with SetupPassword.PASSWORD_LOCK:
                if need_password:
                    ex = self.data.get('existing', [''])[0]
                    if not current_passphrase.compare(ex):
                        incorrect = True
                        time.sleep(1)

                if not incorrect:
                    p1 = self.data.get('password1', [''])[0]
                    p2 = self.data.get('password2', [''])[0]
                    if p1 and p2 and p1 == p2:
                        config.passphrases['DEFAULT'].set_passphrase(p1)
                        config.prefs.gpg_recipient = '!PASSWORD'
                        self.make_master_key()
                        self._background_save(config='!FORCE')
                        mailpile.auth.LogoutAll()
                        done = True
                else:
                    mismatch = True

        results = {
            'need_password': need_password,
            'configured': done,
            'incorrect': incorrect,
            'mismatch': mismatch
        }
        return self._success(_('Welcome to Mailpile!'), results)


class SetupTestRoute(TestableWebbable):
    SYNOPSIS = (None, None, 'setup/test_route', None)

    HTTP_AUTH_REQUIRED = True
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = dict_merge(TestableWebbable.HTTP_POST_VARS,
                                dict((k, v[0]) for k, v in
                                     CONFIG_RULES['routes'][1].iteritems()),
                                {'route_id': 'ID of existing route'})
    TEST_DATA = {}

    def setup_command(self, session):

        if self.args:
            route_id = self.args[0]
        elif 'route_id' in self.data:
            route_id = self.data['route_id'][0]
        else:
            route_id = None

        if route_id:
            route = self.session.config.routes[route_id]
            safe_assert(route)
        else:
            route = {}
            for k in CONFIG_RULES['routes'][1]:
                if k not in self.data:
                    pass
                elif CONFIG_RULES['routes'][1][k][1] in (int, 'int'):
                    route[k] = int(self.data[k][0])
                else:
                    route[k] = self.data[k][0]

        fromaddr = route.get('username', '')
        if '@' not in fromaddr:
            fromaddr = self.session.config.get_profile()['email']
        if not fromaddr or '@' not in fromaddr:
            fromaddr = '%s@%s' % (route.get('username', 'test'),
                                  route.get('host', 'example.com'))
        safe_assert(fromaddr)

        error_info = {'error': _('Unknown error')}
        try:
            safe_assert(
                SendMail(self.session, None,
                         [(fromaddr,
                           [fromaddr, 'test@mailpile.is'],
                           None,
                           [self.event])],
                         test_only=True, test_route=route))
            return self._success(_('Route is working'),
                                 result=route)
        except OSError:
            error_info = {'error': _('Invalid command'),
                          'invalid_command': True}
        except SendMailError, e:
            error_info = {'error': e.message,
                          'sendmail_error': True}
            error_info.update(e.error_info)
        except:
            import traceback
            traceback.print_exc()

        return self._error(_('Route is not working'),
                           result=route, info=error_info)


class SetupTor(TestableWebbable):
    """Check for Tor and auto-configure if possible."""
    SYNOPSIS = (None, 'setup/tor', 'setup/tor', "[--auto]")
    HTTP_CALLABLE = ('POST',)

    @classmethod
    def autoconfig(cls, session):
        cls(session, arg=['--auto']).run()

    def auto_configure_tor(self, session, hostport=None):
        need_raw = [ConnBroker.OUTGOING_RAW]
        hostport = hostport or ('127.0.0.1', 9050)
        try:
            with ConnBroker.context(need=need_raw) as context:
                tor = socket.create_connection(hostport, timeout=10)
        except IOError:
            return  _('Failed to connect to Tor on %s:%s. Is it installed?'
                      ) % hostport

        # If that succeeded, we might have Tor!
        old_proto = session.config.sys.proxy.protocol
        session.config.sys.proxy.protocol = 'tor'
        session.config.sys.proxy.host = hostport[0]
        session.config.sys.proxy.port = hostport[1]
        session.config.sys.proxy.fallback = True

        # Configure connection broker, revert settings while we test
        ConnBroker.configure()
        session.config.sys.proxy.protocol = old_proto

        # Test it...
        need_tor = [ConnBroker.OUTGOING_HTTPS]
        try:
            with ConnBroker.context(need=need_tor) as context:
                motd = urlopen(MOTD_URL_TOR_ONLY_NO_MARS,
                               data=None, timeout=10).read()
                safe_assert(motd.strip().endswith('}'))
            session.config.sys.proxy.protocol = 'tor'
            message = _('Successfully configured and enabled Tor!')
        except (IOError, AssertionError):
            ConnBroker.configure()
            message = _('Failed to configure Tor on %s:%s. Is the network down?'
                        ) % hostport
        return message

    def setup_command(self, session):
        if ("--auto" not in self.args
                or session.config.sys.proxy.protocol == 'unknown'):
            message = self.auto_configure_tor(session)
        else:
            message = _('Proxy settings have already been configured.')

        if session.config.sys.proxy.protocol == 'tor':
            return self._success(message, result=session.config.sys.proxy)
        else:
            return self._error(message, result=session.config.sys.proxy)


class Setup(SetupWelcome):
    """Enter setup flow"""
    SYNOPSIS = (None, 'setup', 'setup', '')

    ORDER = ('Internals', 0)
    LOG_PROGRESS = True
    HTTP_POST_VARS = TestableWebbable.HTTP_POST_VARS
    HTTP_CALLABLE = ('GET',)
    HTTP_AUTH_REQUIRED = True

    # These are a global, may be modified...
    KEY_WORKER_LOCK = CryptoRLock()
    KEY_CREATING_THREAD = None
    KEY_EDITING_THREAD = None

    @classmethod
    def _CHECKPOINTS(self, config):
        return [
            # Stage 0: Welcome: Choose app language
            ('language', lambda: config.prefs.language, SetupWelcome),

            # Stage 1: Basic security - a password
            ('security', lambda: config.master_key, SetupPassword)
        ]

    @classmethod
    def Next(cls, config, default, needed_auth=True):
        if not config.loaded_config:
            return default

        for name, guard, step in cls._CHECKPOINTS(config):
            auth_required = (step.HTTP_AUTH_REQUIRED is True
                             or (config.prefs.gpg_recipient and
                                 step.HTTP_AUTH_REQUIRED == 'Maybe'))
            if not guard():
                if (not needed_auth) or (not auth_required):
                    return step

        return default

    def cli_setup_command(self, session):
        # Stop the workers...
        want_daemons = session.config.cron_worker is not None
        session.config.stop_workers()

        # Perform any required migrations
        Migrate(session).run(before_setup=True, after_setup=False)

        # Basic app config, tags, plugins, etc.
        self.basic_app_config(session,
                              save_and_update_workers=False,
                              want_daemons=want_daemons)

        # Set language from environment
        if not session.config.prefs.language:
            lang = os.getenv('LANG', '').split('.')[0] or 'en'
            if self.configure_language(session, session.config, lang,
                                       save=False) is True:
                session.ui.notify(_('Language set to: %s') % lang)

        # Ask the user for a password, if we don't have security already
        if (not session.config.passphrases['DEFAULT'].is_set() and
                not session.config.prefs.gpg_recipient):
            p1 = session.ui.get_password(_('Choose a password for Mailpile: '))
            if p1:
                p2 = session.ui.get_password(_('Confirm password: '))
            if p1 and p2 and p1 == p2:
                session.config.passphrases['DEFAULT'].set_passphrase(p1)
                session.config.prefs.gpg_recipient = '!PASSWORD'
                self.make_master_key()
            else:
                session.ui.error(
                    _('Passwords did not match! Please try again.'))

        # Perform any required migrations
        Migrate(session).run(before_setup=False, after_setup=True)

        session.config.save()
        session.config.prepare_workers(session, daemons=want_daemons)

        return self._success(_('Performed initial Mailpile setup'))

    def setup_command(self, session):
        if '_method' in self.data:
            return self._success(_('Entering setup flow'), result=dict(
                ((c[0], c[1]() and True or False)
                 for c in self._CHECKPOINTS(session.config)
            )))
        else:
            return self.cli_setup_command(session)


_ = gettext
_plugins.register_commands(SetupMagic,
                           SetupGetEmailSettings,
                           SetupWelcome,
                           CreatePassword,
                           SetupPassword,
                           SetupTestRoute,
                           SetupTor,
                           Setup)
