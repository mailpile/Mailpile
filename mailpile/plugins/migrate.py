import mailpile.config
from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mail_source.mbox import MboxMailSource
from mailpile.mail_source.maildir import MaildirMailSource
from mailpile.plugins import PluginManager
from mailpile.util import *
from mailpile.vcard import *


_plugins = PluginManager(builtin=__file__)

# We might want to do this differently at some point, but
# for now it's fine.


def migrate_routes(session):
    # Migration from route string to messageroute structure
    def route_parse(route):
        if route.startswith('|'):
            command = route[1:].strip()
            return {
                "name": command.split()[0],
                "protocol": "local",
                "command": command
            }
        else:
            res = re.split(
                "([\w]+)://([^:]+):([^@]+)@([\w\d.]+):([\d]+)[/]{0,1}", route)
            if len(res) >= 5:
                return {
                    "name": _("%(user)s on %(host)s"
                              ) % {"user": res[2], "host": res[4]},
                    "protocol": res[1],
                    "username": res[2],
                    "password": res[3],
                    "host": res[4],
                    "port": res[5]
                }
            else:
                session.ui.warning(_('Could not migrate route: %s') % route)
        return None

    def make_route_name(route_dict):
        # This will always return the same hash, no matter how Python
        # decides to order the dict internally.
        return md5_hex(str(sorted(list(route_dict.iteritems()))))[:8]

    if session.config.prefs.get('default_route'):
        route_dict = route_parse(session.config.prefs.default_route)
        if route_dict:
            route_name = make_route_name(route_dict)
            session.config.routes[route_name] = route_dict
            session.config.prefs.default_messageroute = route_name

    for profile in session.config.profiles:
        if profile.get('route'):
            route_dict = route_parse(profile.route)
            if route_dict:
                route_name = make_route_name(route_dict)
                session.config.routes[route_name] = route_dict
                profile.messageroute = route_name

    return True


def migrate_mailboxes(session):
    config = session.config

    def _common_path(paths):
        common_head, junk = os.path.split(paths[0])
        for path in paths:
            head, junk = os.path.split(path)
            while (common_head and common_head != '/' and
                   head and head != '/' and
                   head != common_head):
                # First we try shortening the target path...
                while head and head != '/' and head != common_head:
                    head, junk = os.path.split(head)
                # If that failed, lop one off the common path and try again
                if head != common_head:
                    common_head, junk = os.path.split(common_head)
                    head, junk = os.path.split(path)
        return common_head

    mboxes = []
    maildirs = []
    macmaildirs = []
    thunderbird = []

    spam_tids = [tag._key for tag in config.get_tags(type='spam')]
    trash_tids = [tag._key for tag in config.get_tags(type='trash')]
    inbox_tids = [tag._key for tag in config.get_tags(type='inbox')]

    # Iterate through config.sys.mailbox, sort mailboxes by type
    for mbx_id, path, src in config.get_mailboxes():
        if (path == '/dev/null' or
                path.startswith('src:') or
                src is not None or
                config.is_editable_mailbox(mbx_id)):
            continue
        elif os.path.exists(os.path.join(path, 'Info.plist')):
            macmaildirs.append((mbx_id, path))
        elif os.path.isdir(path):
            maildirs.append((mbx_id, path))
        elif 'thunderbird' in path.lower():
            thunderbird.append((mbx_id, path))
        else:
            mboxes.append((mbx_id, path))

    # macmail: library/mail/v2

    if thunderbird:
        # Create basic mail source...
        if 'tbird' not in config.sources:
            config.sources['tbird'] = {
                'name': 'Thunderbird',
                'protocol': 'mbox',
            }
            config.sources.tbird.discovery.create_tag = True

        config.sources.tbird.discovery.policy = 'read'
        config.sources.tbird.discovery.process_new = True
        tbird_src = MboxMailSource(session, config.sources.tbird)

        # Configure discovery policy?
        root = _common_path([path for mbx_id, path in thunderbird])
        if 'thunderbird' in root.lower():
            # FIXME: This is wrong, we should create a mailbox entry
            #        with the policy 'watch'.
            tbird_src.my_config.discovery.path = root

        # Take over all the mailboxes
        for mbx_id, path in thunderbird:
            mbx = tbird_src.take_over_mailbox(mbx_id)
            if 'inbox' in path.lower():
                mbx.apply_tags.extend(inbox_tids)
            elif 'spam' in path.lower() or 'junk' in path.lower():
                mbx.apply_tags.extend(spam_tids)
            elif 'trash' in path.lower():
                mbx.apply_tags.extend(trash_tids)

        tbird_src.my_config.discovery.policy = 'unknown'

    for name, mailboxes, proto, description, cls in (
        ('mboxes', mboxes, 'mbox', 'Unix mbox files', MboxMailSource),
        ('maildirs', maildirs, 'maildir', 'Maildirs', MaildirMailSource),
    ):
        if mailboxes:
            # Create basic mail source...
            if name not in config.sources:
                config.sources[name] = {
                    'name': description,
                    'protocol': proto
                }
                config.sources[name].discovery.create_tag = False
            config.sources[name].discovery.policy = 'read'
            config.sources[name].discovery.process_new = True
            config.sources[name].discovery.apply_tags = inbox_tids[:]
            src = cls(session, config.sources[name])
            for mbx_id, path in mailboxes:
                mbx = src.take_over_mailbox(mbx_id)
            config.sources[name].discovery.policy = 'unknown'

    return True


def migrate_profiles(session):
    config, vcards = session.config, session.config.vcards

    for profile in config.profiles:
        if profile.email:
            vcard = vcards.get_vcard(profile.email)
            if vcard and vcard.email == profile.email:
                vcards.deindex_vcard(vcard)
            else:
                vcard = MailpileVCard(
                    VCardLine(name='EMAIL', value=profile.email, type='PREF'),
                    VCardLine(name='FN', value=profile.name or profile.email))
            vcard.kind = 'profile'
            if profile.signature:
                vcard.signature = profile.signature
            if profile.messageroute:
                vcard.route = profile.messageroute
            vcards.add_vcards(vcard)

    config.profiles = {}
    return True


def migrate_cleanup(session):
    config = session.config

    # Clean the autotaggers
    autotaggers = [t for t in config.prefs.autotag.values() if t.tagger]
    config.prefs.autotag = autotaggers

    # Clean the profiles
    profiles = [p for p in config.profiles.values() if p.email or p.name]
    config.profiles = profiles

    # Clean the vcards:
    #   - Prefer vcards with valid key info
    #   - De-dupe everything based on name/email combinations
    def cardprint(vc):
        emails = set([v.value for v in vc.get_all('email')])
        return '/'.join([vc.fn] + sorted(list(emails)))
    vcards = all_vcards = set(config.vcards.values())
    keepers = set()
    for vc in vcards:
        keys = vc.get_all('key')
        for k in keys:
            try:
                mime, fp = k.value.split('data:')[1].split(',')
                if fp:
                    keepers.add(vc)
            except (ValueError, IndexError):
                pass
    for p in (1, 2):
        prints = set([cardprint(vc) for vc in keepers])
        for vc in vcards:
            cp = cardprint(vc)
            if cp not in prints:
                keepers.add(vc)
                prints.add(cp)
        vcards = keepers
        keepers = set()
    # Deleted!!
    config.vcards.del_vcards(*list(all_vcards - vcards))

    return True


MIGRATIONS_BEFORE_SETUP = [migrate_routes]
MIGRATIONS_AFTER_SETUP = [migrate_profiles, migrate_cleanup]
MIGRATIONS = {
    'routes': migrate_routes,
    'sources': migrate_mailboxes,
    'profiles': migrate_profiles,
    'cleanup': migrate_cleanup
}


class Migrate(Command):
    """Perform any needed migrations"""
    SYNOPSIS = (None, 'setup/migrate', None,
                '[' + '|'.join(sorted(MIGRATIONS.keys())) + ']')
    ORDER = ('Internals', 0)

    def command(self, before_setup=True, after_setup=True):
        session = self.session
        err = cnt = 0

        if self.session.config.sys.lockdown:
            return self._error(_('In lockdown, doing nothing.'))

        migrations = []
        for a in self.args:
            if a in MIGRATIONS:
                migrations.append(MIGRATIONS[a])
            else:
                raise UsageError(_('Unknown migration: %s (available: %s)'
                                   ) % (a, ', '.join(MIGRATIONS.keys())))

        if not migrations:
            migrations = ((before_setup and MIGRATIONS_BEFORE_SETUP or []) +
                          (after_setup and MIGRATIONS_AFTER_SETUP or []))

        for mig in migrations:
            try:
                if mig(session):
                    cnt += 1
                else:
                    err += 1
            except:
                self._ignore_exception()
                err += 1

        self._background_save(config=True)
        return self._success(_('Performed %d migrations, failed %d.'
                               ) % (cnt, err))


_plugins.register_commands(Migrate)
