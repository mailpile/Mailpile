from __future__ import print_function
# Plugins!
import imp
import inspect
import json
import os
import sys
import traceback

import mailpile.commands
import mailpile.config.defaults
import mailpile.vcard
from mailpile.i18n import i18n_disabled
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import register as register_mailbox
from mailpile.util import *


##[ Plugin discovery ]########################################################


# These are the plugins we ship/import by default
__all__ = [
    'core',
    'eventlog', 'search', 'tags', 'contacts', 'compose', 'groups',
    'dates', 'sizes', 'autotag', 'cryptostate', 'crypto_gnupg', 'gui',
    'setup_magic', 'oauth', 'exporters', 'plugins', 'motd', 'backups',
    'vcard_carddav', 'vcard_gnupg', 'vcard_gravatar', 'vcard_libravatar',
    'vcard_mork', 'html_magic', 'migrate', 'smtp_server', 'crypto_policy',
    'keylookup', 'webterminal', 'crypto_autocrypt'
]
PLUGINS = __all__


class EmailTransform(object):
    """Base class for e-mail transforms"""
    def __init__(self, config):
        self.config = config

    def _get_sender_profile(self, sender, kwargs):
        profile = kwargs.get('sender_profile')
        if not profile:
            profile = self.config.get_profile(sender)
        return profile

    def _get_first_part(self, msg, mimetype):
        for part in msg.walk():
             if not part.is_multipart():
                 mimetype = (part.get_content_type() or 'text/plain').lower()
                 if mimetype == 'text/plain':
                     return part
        return None

    def TransformIncoming(self, *args, **kwargs):
        return list(args[:]) + [False]

    def TransformOutgoing(self, *args, **kwargs):
        return list(args[:]) + [False, True]


class PluginError(Exception):
    pass


class PluginManager(object):
    """
    Manage importing and loading of plugins. Note that this class is
    effectively a singleton, as it works entirely with globals within
    the mailpile.plugins module.
    """
    DEFAULT = __all__
    BUILTIN = (DEFAULT + [
        'autotag_sb'
    ])

    # These are plugins which we consider required
    REQUIRED = [
        'core',
        'eventlog', 'search', 'tags', 'contacts', 'compose', 'groups',
        'dates', 'sizes', 'cryptostate', 'setup_magic', 'oauth', 'html_magic',
        'plugins', 'keylookup', 'motd', 'backups', 'gui'
    ]
    # Plugins we want, if they are discovered
    WANTED = [
        'autoajax', 'print', 'hints'
    ]
    # Plugins that have been renamed from past releases
    RENAMED = {
        'crypto_utils': 'crypto_gnupg'
    }
    DISCOVERED = {}
    LOADED = []

    def __init__(self, plugin_name=None, builtin=False, deprecated=False,
                 config=None, session=None):
        if builtin and isinstance(builtin, (str, unicode)):
            builtin = os.path.basename(builtin)
            for ignore in ('.py', '.pyo', '.pyc'):
                if builtin.endswith(ignore):
                    builtin = builtin[:-len(ignore)]
            if builtin not in self.LOADED:
                self.LOADED.append(builtin)

        self.loading_plugin = plugin_name
        self.loading_builtin = plugin_name and builtin
        self.builtin = builtin
        self.deprecated = deprecated
        self.session = session
        self.config = config
        self.manifests = []

    def _listdir(self, path):
        try:
            return [d for d in os.listdir(path) if not d.startswith('.')]
        except OSError:
            return []

    def _uncomment(self, json_data):
        return '\n'.join([l for l in json_data.splitlines()
                          if not l.strip().startswith('#')])

    def discover(self, paths, update=False):
        """
        Scan the plugin directories for plugins we could load.
        This updates the global PluginManager state and returns the
        PluginManager itself (for chaining).
        """
        plugins = self.BUILTIN[:]
        for pdir in paths:
            for subdir in self._listdir(pdir):
                pname = subdir.lower()
                if pname in self.BUILTIN:
                    print('Cannot overwrite built-in plugin: %s' % pname)
                    continue
                if pname in self.DISCOVERED and not update:
                    # FIXME: this is lame
                    # print 'Ignoring duplicate plugin: %s' % pname
                    continue
                plug_path = os.path.join(pdir, subdir)
                manifest_filename = os.path.join(plug_path, 'manifest.json')
                try:
                    with open(manifest_filename) as mfd:
                        manifest = json.loads(self._uncomment(mfd.read()))
                        safe_assert(manifest.get('name') == subdir)
                        # FIXME: Need more sanity checks
                        self.DISCOVERED[pname] = (plug_path, manifest)
                except (ValueError, AssertionError):
                    print('Bad manifest: %s' % manifest_filename)
                except (OSError, IOError):
                    pass

        return self

    def available(self):
        return self.BUILTIN[:] + self.DISCOVERED.keys()

    def loadable(self):
        return self.BUILTIN[:] + self.RENAMED.keys() + self.DISCOVERED.keys()

    def loadable_early(self):
        return [k for k, (n, m) in self.DISCOVERED.iteritems()
                if not m.get('require_login', True)]

    def _import(self, full_name, full_path):
        # create parents as necessary
        parents = full_name.split('.')[2:] # skip mailpile.plugins
        module = "mailpile.plugins"
        for parent in parents:
            mp = '%s.%s' % (module, parent)
            if mp not in sys.modules:
                sys.modules[mp] = imp.new_module(mp)
                sys.modules[module].__dict__[parent] = sys.modules[mp]
            module = mp
        safe_assert(module == full_name)

        # load actual module
        sys.modules[full_name].__file__ = full_path
        with i18n_disabled:
            with open(full_path, 'r') as mfd:
                exec(mfd.read(), sys.modules[full_name].__dict__)

    def _load(self, plugin_name, process_manifest=False, config=None):
        full_name = 'mailpile.plugins.%s' % plugin_name
        if full_name in sys.modules:
            return self

        self.loading_plugin = full_name
        if plugin_name in self.BUILTIN:
            # The builtins are just normal Python code. If they have a
            # manifest, they'll invoke process_manifest themselves.
            self.loading_builtin = True
            module = __import__(full_name)

        elif plugin_name in self.DISCOVERED:
            dirname, manifest = self.DISCOVERED[plugin_name]
            self.loading_builtin = False

            # Load the Python requested by the manifest.json
            files = manifest.get('code', {}).get('python', [])
            try:
                for filename in files:
                    path = os.path.join(dirname, filename)
                    if filename == '.':
                        self._import(full_name, dirname)
                        continue
                    elif filename.endswith('.py'):
                        subname = filename[:-3].replace('/', '.')
                        # FIXME: Is this a good idea?
                        if full_name.endswith('.'+subname):
                            self._import(full_name, path)
                            continue
                    elif os.path.isdir(path):
                        subname = filename.replace('/', '.')
                    else:
                        continue
                    self._import('.'.join([full_name, subname]), path)
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc(file=sys.stderr)
                print('FIXME: Loading %s failed, tell user!' % full_name)
                if full_name in sys.modules:
                    del sys.modules[full_name]
                return None

            spec = (full_name, manifest, dirname)
            self.manifests.append(spec)
            if process_manifest:
                self._process_manifest_pass_one(*spec)
                self._process_manifest_pass_two(*spec)
                self._process_startup_hooks(*spec)
        else:
            print('Unrecognized plugin: %s' % plugin_name)
            return self

        if plugin_name not in self.LOADED:
            self.LOADED.append(plugin_name)
        return self

    def load(self, *args, **kwargs):
        try:
            return self._load(*args, **kwargs)
        finally:
            self.loading_plugin = None
            self.loading_builtin = False

    def process_shutdown_hooks(self):
        for plugin_name in self.DISCOVERED.keys():
            try:
                package = 'mailpile.plugins.%s' % plugin_name
                _, manifest = self.DISCOVERED[plugin_name]

                if package in sys.modules:
                    for method_name in self._mf_path(manifest,
                                                     'lifecycle', 'shutdown'):
                        method = self._get_method(package, method_name)
                        method(self.config)
            except:
                # ignore exceptions here as mailpile is going to shut down
                traceback.print_exc(file=sys.stderr)

    def process_manifests(self):
        failed = []
        for process in (self._process_manifest_pass_one,
                        self._process_manifest_pass_two,
                        self._process_startup_hooks):
            for spec in self.manifests:
                try:
                    if spec[0] not in failed:
                        process(*spec)
                except Exception as e:
                    print('Failed to process manifest for %s: %s' % (spec[0], e))
                    failed.append(spec[0])
                    traceback.print_exc()
        return self

    def _mf_path(self, mf, *path):
        for p in path:
            mf = mf.get(p, {})
        return mf

    def _mf_iteritems(self, mf, *path):
        return self._mf_path(mf, *path).iteritems()

    def _get_method(self, full_name, method):
        full_method_name = '.'.join([full_name, method])
        package, method_name = full_method_name.rsplit('.', 1)

        module = sys.modules[package]
        return getattr(module, method_name)

    def _get_class(self, full_name, class_name):
        full_class_name = '.'.join([full_name, class_name])
        mod_name, class_name = full_class_name.rsplit('.', 1)
        module = __import__(mod_name, globals(), locals(), class_name)
        return getattr(module, class_name)

    def _process_manifest_pass_one(self, full_name,
                                   manifest=None, plugin_path=None):
        """
        Pass one of processing the manifest data. This updates the global
        configuration and registers Python code with the URL map.
        """
        if not manifest:
            return

        manifest_path = lambda *p: self._mf_path(manifest, *p)
        manifest_iteritems = lambda *p: self._mf_iteritems(manifest, *p)

        # Register config variables and sections
        for section, rules in manifest_iteritems('config', 'sections'):
            self.register_config_section(*(section.split('.') + [rules]))
        for section, rules in manifest_iteritems('config', 'variables'):
            self.register_config_variables(*(section.split('.') + [rules]))

        # Register commands
        for command in manifest_path('commands'):
            cls = self._get_class(full_name, command['class'])

            # FIXME: This is all a bit hacky, we probably just want to
            #        kill the SYNOPSIS attribute entirely.
            if 'input' in command:
                name = url = '%s/%s' % (command['input'], command['name'])
                cls.UI_CONTEXT = command['input']
            else:
                name = command.get('name', cls.SYNOPSIS[1])
                url = command.get('url', cls.SYNOPSIS[2])
            cls.SYNOPSIS = tuple([cls.SYNOPSIS[0], name, url,
                                  cls.SYNOPSIS_ARGS or cls.SYNOPSIS[3]])

            self.register_commands(cls)

        # Register worker threads
        for thr in manifest_path('threads'):
            self.register_worker(self._get_class(full_name, thr))

        # Register mailboxes
        package = str(full_name)
        for mailbox in manifest_path('mailboxes'):
            cls = self._get_class(package, mailbox['class'])
            priority = int(mailbox['priority'])
            register_mailbox(priority, cls)

    def _process_manifest_pass_two(self, full_name,
                                   manifest=None, plugin_path=None):
        """
        Pass two of processing the manifest data. This maps templates and
        data to API commands and links registers classes and methods as
        hooks here and there. As these things depend both on configuration
        and the URL map, this happens as a second phase.
        """
        if not manifest:
            return

        manifest_path = lambda *p: self._mf_path(manifest, *p)
        manifest_iteritems = lambda *p: self._mf_iteritems(manifest, *p)

        # Register javascript classes
        for fn in manifest.get('code', {}).get('javascript', []):
            class_name = fn.replace('/', '.').rsplit('.', 1)[0]
            # FIXME: Is this a good idea?
            if full_name.endswith('.'+class_name):
                parent, class_name = full_name.rsplit('.', 1)
            else:
                parent = full_name
            self.register_js(parent, class_name,
                             os.path.join(plugin_path, fn))

        # Register CSS files
        for fn in manifest.get('code', {}).get('css', []):
            file_name = fn.replace('/', '.').rsplit('.', 1)[0]
            self.register_css(full_name, file_name,
                              os.path.join(plugin_path, fn))

        # Register web assets
        if plugin_path:
            from mailpile.urlmap import UrlMap
            um = UrlMap(session=self.session, config=self.config)
            for url, info in manifest_iteritems('routes'):
                filename = os.path.join(plugin_path, info['file'])

                # Short-cut for static content
                if url.startswith('/static/'):
                    self.register_web_asset(full_name, url[8:], filename,
                        mimetype=info.get('mimetype', None))
                    continue

                # Finds the right command class and register asset in
                # the right place for that particular command.
                commands = []
                if (not url.startswith('/api/')) and 'api' in info:
                    url = '/api/%d%s' % (info['api'], url)
                    if url[-1] == '/':
                        url += 'as.html'
                for method in ('GET', 'POST', 'PUT', 'UPDATE', 'DELETE'):
                    try:
                        commands = um.map(None, method, url, {}, {})
                        break
                    except UsageError:
                        pass

                output = [o.get_render_mode()
                          for o in commands if hasattr(o, 'get_render_mode')]
                output = output and output[-1] or 'html'
                if commands:
                    command = commands[-1]
                    tpath = command.template_path(output.split('.')[-1],
                                                  template=output)
                    self.register_web_asset(full_name,
                                            'html/' + tpath,
                                            filename)
                else:
                    print('FIXME: Un-routable URL in manifest %s' % url)

        # Register email content/crypto hooks
        s = self
        for which, reg in (
            ('outgoing_content', s.register_outgoing_email_content_transform),
            ('outgoing_crypto', s.register_outgoing_email_crypto_transform),
            ('incoming_crypto', s.register_incoming_email_crypto_transform),
            ('incoming_content', s.register_incoming_email_content_transform)
        ):
            for item in manifest_path('email_transforms', which):
                name = '%3.3d_%s' % (int(item.get('priority', 999)), full_name)
                reg(name, self._get_class(full_name, item['class']))

        # Register search keyword extractors
        s = self
        for which, reg in (
            ('meta', s.register_meta_kw_extractor),
            ('text', s.register_text_kw_extractor),
            ('data', s.register_data_kw_extractor)
        ):
            for item in manifest_path('keyword_extractors', which):
                reg('%s.%s' % (full_name, item),
                    self._get_class(full_name, item))

        # Register contact/vcard hooks
        for which, reg in (
            ('importers', self.register_vcard_importers),
            ('exporters', self.register_contact_exporters),
            ('context', self.register_contact_context_providers)
        ):
            for item in manifest_path('contacts', which):
                reg(self._get_class(full_name, item))

        # Register periodic jobs
        def reg_job(info, spd, register):
            interval, cls = info['interval'], info['class']
            callback = self._get_class(full_name, cls)
            register('%s.%s/%s-%s' % (full_name, cls, spd, interval),
                     interval, callback)
        for info in manifest_path('periodic_jobs', 'fast'):
            reg_job(info, 'fast', self.register_fast_periodic_job)
        for info in manifest_path('periodic_jobs', 'slow'):
            reg_job(info, 'slow', self.register_slow_periodic_job)

        ucfull_name = full_name.capitalize()
        for ui_type, elems in manifest.get('user_interface', {}).iteritems():
            for hook in elems:
                if 'javascript_setup' in hook:
                    js = hook['javascript_setup']
                    if not js.startswith('Mailpile.'):
                       hook['javascript_setup'] = '%s.%s' % (ucfull_name, js)
                if 'javascript_events' in hook:
                    for event, call in hook['javascript_events'].iteritems():
                        if not call.startswith('Mailpile.'):
                            hook['javascript_events'][event] = '%s.%s' \
                                % (ucfull_name, call)
                self.register_ui_element(ui_type, **hook)

    def _process_startup_hooks(self, package,
                               manifest=None, plugin_path=None):
        if not manifest:
            return

        manifest_path = lambda *p: self._mf_path(manifest, *p)

        for method_name in manifest_path('lifecycle', 'startup'):
            method = self._get_method(package, method_name)
            method(self.config)

    def _compat_check(self, strict=True):
        if ((strict and (not self.loading_plugin and not self.builtin)) or
                self.deprecated):
            stack = inspect.stack()
            if str(stack[2][1]) == '<string>':
                raise PluginError('Naughty plugin tried to directly access '
                                  'mailpile.plugins!')

            where = '->'.join(['%s:%s' % ('/'.join(stack[i][1].split('/')[-2:]),
                                          stack[i][2])
                              for i in reversed(range(2, len(stack)-1))])
            print(('FIXME: Deprecated use of %s at %s (issue #547)'
                   ) % (stack[1][3], where))

    def _rhtf(self, kw_hash, term, function):
        if term in kw_hash:
            raise PluginError('Already registered: %s' % term)
        kw_hash[term] = function


    ##[ Pluggable configuration ]#############################################

    def register_config_variables(self, *args):
        self._compat_check()
        args = list(args)
        rules = args.pop(-1)
        dest = mailpile.config.defaults.CONFIG_RULES
        path = '/'.join(args)
        for arg in args:
            dest = dest[arg][-1]
        for rname, rule in rules.iteritems():
            if rname in dest:
                raise PluginError('Variable already exist: %s/%s' % (path, rname))
            else:
                dest[rname] = rule

    def register_config_section(self, *args):
        self._compat_check()
        args = list(args)
        rules = args.pop(-1)
        rname = args.pop(-1)
        dest = mailpile.config.defaults.CONFIG_RULES
        path = '/'.join(args)
        for arg in args:
            dest = dest[arg][-1]
        if rname in dest:
            raise PluginError('Section already exist: %s/%s' % (path, rname))
        else:
            dest[rname] = rules


    ##[ Pluggable message transformations ]###################################

    INCOMING_EMAIL_ENCRYPTION = {}
    INCOMING_EMAIL_CONTENT = {}
    OUTGOING_EMAIL_CONTENT = {}
    OUTGOING_EMAIL_ENCRYPTION = {}

    def _txf_in(self, transforms, config, msg, kwargs):
        matched = 0
        for name in sorted(transforms.keys()):
            txf = transforms[name](config)
            msg, match, cont = txf.TransformIncoming(msg, **kwargs)
            if match:
                matched += 1
            if not cont:
                break
        return msg, matched

    def _txf_out(self, transforms, cfg, s, r, msg, kwa):
        matched = 0
        for name in sorted(transforms.keys()):
            txf = transforms[name](cfg)
            s, r, msg, match, cont = txf.TransformOutgoing(s, r, msg, **kwa)
            if match:
                matched += 1
            if not cont:
                break
        return s, r, msg, matched

    def incoming_email_crypto_transform(self, cfg, msg, **kwa):
        return self._txf_in(self.INCOMING_EMAIL_ENCRYPTION, cfg, msg, kwa)

    def incoming_email_content_transform(self, config, msg, **kwa):
        return self._txf_in(self.INCOMING_EMAIL_CONTENT, config, msg, kwa)

    def outgoing_email_content_transform(self, cfg, s, r, m, **kwa):
        return self._txf_out(self.OUTGOING_EMAIL_CONTENT, cfg, s, r, m, kwa)

    def outgoing_email_crypto_transform(self, cfg, s, r, m, **kwa):
        return self._txf_out(self.OUTGOING_EMAIL_ENCRYPTION, cfg, s, r, m, kwa)

    def register_incoming_email_crypto_transform(self, name, transform):
        return self._rhtf(self.INCOMING_EMAIL_ENCRYPTION, name, transform)

    def register_incoming_email_content_transform(self, name, transform):
        return self._rhtf(self.INCOMING_EMAIL_CONTENT, name, transform)

    def register_outgoing_email_content_transform(self, name, transform):
        return self._rhtf(self.OUTGOING_EMAIL_CONTENT, name, transform)

    def register_outgoing_email_crypto_transform(self, name, transform):
        return self._rhtf(self.OUTGOING_EMAIL_ENCRYPTION, name, transform)


    ##[ Pluggable keyword extractors ]########################################

    DATA_KW_EXTRACTORS = {}
    TEXT_KW_EXTRACTORS = {}
    META_KW_EXTRACTORS = {}

    def register_data_kw_extractor(self, term, function):
        self._compat_check()
        return self._rhtf(self.DATA_KW_EXTRACTORS, term, function)

    def register_text_kw_extractor(self, term, function):
        self._compat_check()
        return self._rhtf(self.TEXT_KW_EXTRACTORS, term, function)

    def register_meta_kw_extractor(self, term, function):
        self._compat_check()
        return self._rhtf(self.META_KW_EXTRACTORS, term, function)

    def get_data_kw_extractors(self):
        self._compat_check(strict=False)
        return self.DATA_KW_EXTRACTORS.values()

    def get_text_kw_extractors(self):
        self._compat_check(strict=False)
        return self.TEXT_KW_EXTRACTORS.values()

    def get_meta_kw_extractors(self):
        self._compat_check(strict=False)
        return self.META_KW_EXTRACTORS.values()


    ##[ Pluggable search terms ]##############################################

    SEARCH_TERMS = {}

    def get_search_term(self, term, default=None):
        self._compat_check(strict=False)
        return self.SEARCH_TERMS.get(term, default)

    def register_search_term(self, term, function):
        self._compat_check()
        if term in self.SEARCH_TERMS:
            raise PluginError('Already registered: %s' % term)
        self.SEARCH_TERMS[term] = function


    ##[ Pluggable keyword filters ]###########################################

    FILTER_HOOKS_PRE = {}
    FILTER_HOOKS_POST = {}

    def get_filter_hooks(self, hooks):
        self._compat_check(strict=False)
        return ([self.FILTER_HOOKS_PRE[k]
                 for k in sorted(self.FILTER_HOOKS_PRE.keys())]
                + hooks +
                [self.FILTER_HOOKS_POST[k]
                 for k in sorted(self.FILTER_HOOKS_POST.keys())])

    def register_filter_hook_pre(self, name, hook):
        self._compat_check()
        self.FILTER_HOOKS_PRE[name] = hook

    def register_filter_hook_post(self, name, hook):
        self._compat_check()
        self.FILTER_HOOKS_POST[name] = hook


    ##[ Pluggable vcard functions ]###########################################

    VCARD_IMPORTERS = {}
    VCARD_EXPORTERS = {}
    VCARD_CONTEXT_PROVIDERS = {}

    def _reg_vcard_plugin(self, what, cfg_sect, plugin_classes, cls, dct):
        for plugin_class in plugin_classes:
            if not plugin_class.SHORT_NAME or not plugin_class.FORMAT_NAME:
                raise PluginError("Please set SHORT_NAME "
                                  "and FORMAT_* attributes!")
            if not issubclass(plugin_class, cls):
                raise PluginError("%s must be a %s" % (what, cls))
            if plugin_class.SHORT_NAME in dct:
                raise PluginError("%s for %s already registered"
                                  % (what, importer.FORMAT_NAME))

            if plugin_class.CONFIG_RULES:
                rules = {
                    'guid': ['VCard source UID', str, ''],
                    'description': ['VCard source description', str, '']
                }
                rules.update(plugin_class.CONFIG_RULES)
                self.register_config_section(
                    'prefs', 'vcard', cfg_sect, plugin_class.SHORT_NAME,
                    [plugin_class.FORMAT_DESCRIPTION, rules, []])

            dct[plugin_class.SHORT_NAME] = plugin_class

    def register_vcard_importers(self, *importers):
        self._compat_check()
        self._reg_vcard_plugin('Importer', 'importers', importers,
                               mailpile.vcard.VCardImporter,
                               self.VCARD_IMPORTERS)

    def register_contact_exporters(self, *exporters):
        self._compat_check()
        self._reg_vcard_plugin('Exporter', 'exporters', exporters,
                               mailpile.vcard.VCardExporter,
                               self.VCARD_EXPORTERS)

    def register_contact_context_providers(self, *providers):
        self._compat_check()
        self._reg_vcard_plugin('Context provider', 'context', providers,
                               mailpile.vcard.VCardContextProvider,
                               self.VCARD_CONTEXT_PROVIDERS)


    ##[ Pluggable cron jobs ]#################################################

    FAST_PERIODIC_JOBS = {}
    SLOW_PERIODIC_JOBS = {}

    def register_fast_periodic_job(self, name, period, callback):
        self._compat_check()
        # FIXME: complain about duplicates?
        self.FAST_PERIODIC_JOBS[name] = (period, callback)

    def register_slow_periodic_job(self, name, period, callback):
        self._compat_check()
        # FIXME: complain about duplicates?
        self.SLOW_PERIODIC_JOBS[name] = (period, callback)


    ##[ Pluggable background worker threads ]################################

    WORKERS = []

    def register_worker(self, thread_obj):
        self._compat_check()
        safe_assert(hasattr(thread_obj, 'start'))
        safe_assert(hasattr(thread_obj, 'quit'))
        # FIXME: complain about duplicates?
        self.WORKERS.append(thread_obj)


    ##[ Pluggable commands ]##################################################

    def register_commands(self, *args):
        self._compat_check()
        COMMANDS = mailpile.commands.COMMANDS
        for cls in args:
            if cls not in COMMANDS:
                COMMANDS.append(cls)


    ##[ Pluggable javascript, CSS template and static content ]###############

    JS_CLASSES = {}
    CSS_FILES = {}
    WEB_ASSETS = {}

    def register_js(self, plugin, classname, filename):
        self.JS_CLASSES['%s.%s' % (plugin, classname)] = filename

    def register_css(self, plugin, classname, filename):
        self.CSS_FILES['%s.%s' % (plugin, classname)] = filename

    def register_web_asset(self, plugin, path, filename, mimetype='text/html'):
        if path in self.WEB_ASSETS:
            raise PluginError(_('Already registered: %s') % path)
        self.WEB_ASSETS[path] = (filename, mimetype, plugin)

    def get_js_classes(self):
        return self.JS_CLASSES

    def get_css_files(self):
        return self.CSS_FILES

    def get_web_asset(self, path, default=None):
        return tuple(self.WEB_ASSETS.get(path, [default, None])[0:2])


    ##[ Pluggable UI elements ]###############################################

    # These are the elements that exist at the moment
    UI_ELEMENTS = {
        'settings': [],
        'activities': [],
        'email_activities': [],  # Activities on e-mails
        'thread_activities': [], # Activities on e-mails in a thread
        'display_modes': [],
        'display_refiners': [],
        'selection_actions': []
    }

    def register_ui_element(self, ui_type,
                            context=None, name=None,
                            text=None, icon=None, description=None,
                            url=None, javascript_setup=None,
                            javascript_events=None, **kwargs):
        name = name.replace('/', '_')
        if name not in [e.get('name') for e in self.UI_ELEMENTS[ui_type]]:
            # FIXME: Is context valid?
            info = {
                "context": context or [],
                "name": name,
                "text": text,
                "icon": icon,
                "description": description,
                "javascript_setup": javascript_setup,
                "javascript_events": javascript_events,
                "url": url
            }
            for k, v in kwargs.iteritems():
                info[k] = v
            self.UI_ELEMENTS[ui_type].append(info)
        else:
            raise ValueError('Duplicate element: %s' % name)

    def get_ui_elements(self, ui_type, context):
        # FIXME: This is a bit inefficient.
        #        The good thing is, it maintains a stable order.
        return [elem for elem in self.UI_ELEMENTS[ui_type]
                if context in elem['context']]


##[ Backwards compatibility ]################################################

_default_pm = PluginManager(builtin=False, deprecated=True)

register_config_variables = _default_pm.register_config_variables
register_config_section = _default_pm.register_config_section
register_data_kw_extractor = _default_pm.register_data_kw_extractor
register_text_kw_extractor = _default_pm.register_text_kw_extractor
register_meta_kw_extractor = _default_pm.register_meta_kw_extractor
get_data_kw_extractors = _default_pm.get_data_kw_extractors
get_text_kw_extractors = _default_pm.get_text_kw_extractors
get_meta_kw_extractors = _default_pm.get_meta_kw_extractors
get_search_term = _default_pm.get_search_term
register_search_term = _default_pm.register_search_term
filter_hooks = _default_pm.get_filter_hooks
register_filter_hook_pre = _default_pm.register_filter_hook_pre
register_filter_hook_post = _default_pm.register_filter_hook_post
register_vcard_importers = _default_pm.register_vcard_importers
register_contact_exporters = _default_pm.register_contact_exporters
register_contact_context_providers = _default_pm.register_contact_context_providers
register_fast_periodic_job = _default_pm.register_fast_periodic_job
register_slow_periodic_job = _default_pm.register_slow_periodic_job
register_worker = _default_pm.register_worker
register_commands = _default_pm.register_commands
