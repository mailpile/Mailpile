# Plugins!
import imp
import inspect
import json
import os
import sys
from gettext import gettext as _

from mailpile.util import *
import mailpile.commands
import mailpile.defaults
import mailpile.vcard


##[ Plugin discovery ]########################################################


# These are the plugins we ship/import by default
__all__ = [
    'eventlog', 'search', 'tags', 'contacts', 'compose', 'groups',
    'dates', 'sizes', 'autotag', 'cryptostate', 'crypto_utils',
    'setup_magic', 'exporters',
    'vcard_carddav', 'vcard_gnupg', 'vcard_gravatar', 'vcard_mork',
    'hacks', 'html_magic', 'smtp_server'
]


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
        'eventlog', 'search', 'tags', 'contacts', 'compose', 'groups',
        'dates', 'sizes', 'cryptostate', 'setup_magic', 'html_magic'
    ]
    DISCOVERED = {}

    def __init__(self, plugin_name=None, builtin=False, deprecated=False,
                 config=None, session=None):
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
                    print 'Cannot overwrite built-in plugin: %s' % pname
                    continue
                if pname in self.DISCOVERED and not update:
                    # FIXME: this is lame
                    print 'Ignoring duplicate plugin: %s' % pname
                    continue
                try:
                    plug_path = os.path.join(pdir, subdir)
                    with open(os.path.join(plug_path, 'manifest.json')) as mfd:
                        manifest = json.loads(self._uncomment(mfd.read()))
                        assert(manifest.get('name') == subdir)
                        # FIXME: Need more sanity checks
                        self.DISCOVERED[pname] = (plug_path, manifest)
                except (OSError, IOError):
                    pass

        return self

    def available(self):
        return self.BUILTIN[:] + self.DISCOVERED.keys()

    def _import(self, full_name, full_path):
        parent = full_name.rsplit('.', 1)[0]
        if parent not in sys.modules:
            sys.modules[parent] = imp.new_module(parent)
        sys.modules[full_name] = imp.new_module(full_name)
        sys.modules[full_name].__file__ = full_path
        with open(full_path, 'r') as mfd:
            exec mfd.read() in sys.modules[full_name].__dict__

    def _load(self, plugin_name, process_manifest=False):
        full_name = 'mailpile.plugins.%s' % plugin_name
        if full_name in sys.modules:
            return

        self.loading_plugin = full_name
        if plugin_name in self.BUILTIN:
            # The builtins are just normal Python code. If they have a
            # manifest, they'll invoke process_manifest themselves.
            self.loading_builtin = True
            module = __import__(full_name)

        else:
            dirname, manifest = self.DISCOVERED.get(plugin_name)
            self.loading_builtin = False

            # Load the Python requested by the manifest.json
            files = manifest.get('files', {}).get('python', [])
            files.sort(key=lambda f: len(f))
            try:
                for filename in files:
                    path = os.path.join(dirname, filename)
                    if filename == '.':
                        self._import(full_name, dirname)
                    elif filename.endswith('.py'):
                        subname = filename[:-3].replace('/', '.')
                    elif os.path.isdir(path):
                        subname = filename.replace('/', '.')
                    else:
                        continue
                    self._import('.'.join([full_name, subname]), path)
            except KeyboardInterrupt:
                raise
            except:
                print 'FIXME: Loading %s failed, tell user!' % full_name
                return

            spec = (full_name, manifest, dirname)
            self.manifests.append(spec)
            if process_manifest:
                self._process_manifest_pass_one(*spec)
                self._process_manifest_pass_two(*spec)

        return self

    def load(self, *args, **kwargs):
        try:
            return self._load(*args, **kwargs)
        finally:
            self.loading_plugin = None
            self.loading_builtin = False

    def process_manifests(self):
        for spec in self.manifests:
            self._process_manifest_pass_one(*spec)
        for spec in self.manifests:
            self._process_manifest_pass_two(*spec)
        return self

    def _mf_path(self, mf, *path):
        for p in path:
            mf = mf.get(p, {})
        return mf

    def _mf_iteritems(self, mf, *path):
        return self._mf_path(mf, *path).iteritems()

    def _get_class(self, full_name, class_name):
        full_class_name = '.'.join([full_name, class_name])
        mod_name, class_name = full_class_name.rsplit('.', 1)
        module = __import__(mod_name, globals(), locals(), class_name)
        return getattr(module, class_name)

    def _process_manifest_pass_one(self, full_name,
                                   manifest=None, plugin_path=None):
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
            # FIXME: This is a bit hacky, we probably just want to kill
            #        the SYNOPSIS attribute entirely.
            cls.SYNOPSIS = tuple([cls.SYNOPSIS[0],
                                  command.get('name', cls.SYNOPSIS[1]),
                                  command.get('url', cls.SYNOPSIS[2]),
                                  cls.SYNOPSIS_ARGS or cls.SYNOPSIS[3]])
            self.register_commands(cls)

    def _process_manifest_pass_two(self, full_name,
                                   manifest=None, plugin_path=None):
        if not manifest:
            return

        manifest_path = lambda *p: self._mf_path(manifest, *p)
        manifest_iteritems = lambda *p: self._mf_iteritems(manifest, *p)

        # Register contact/vcard hooks
        for importer in manifest_path('contacts', 'importers'):
            self.register_vcard_importers(self._get_class(full_name, importer))
        for exporter in manifest_path('contacts', 'exporters'):
            self.register_contact_exporters(self._get_class(full_name,
                                                            exporter))
        for context in manifest_path('contacts', 'context'):
            self.register_contact_context_providers(self._get_class(full_name,
                                                                    context))

        # Register web assets
        if plugin_path:
          try:
            from mailpile.urlmap import UrlMap
            um = UrlMap(session=self.session, config=self.config)
            for url, info in manifest_iteritems('files', 'routes'):
                filename = os.path.join(plugin_path, info['file'])

                # Short-cut for static content
                if url.startswith('/static/'):
                    self.register_web_asset(full_name, url[8:], filename,
                        mimetype=info.get('mimetype',
                                          'application/octet-stream'))
                    continue

                # Finds the right command class and register asset in
                # the right place for that particular command.
                commands = []
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
                    print 'FIXME: Un-routable URL in manifest %s' % url
          except:
            import traceback
            traceback.print_exc()

    def _compat_check(self, strict=True):
        if ((strict and (not self.loading_plugin and not self.builtin)) or
                self.deprecated):
            stack = inspect.stack()
            if str(stack[2][1]) == '<string>':
                raise PluginError('Naughty plugin tried to directly access '
                                  'mailpile.plugins!')
            print ('FIXME: Deprecated use of %s at %s:%s (issue #547)'
                   ) % (stack[1][3], stack[2][1], stack[2][2])


    ##[ Pluggable configuration ]#############################################

    def register_config_variables(self, *args):
        self._compat_check()
        args = list(args)
        rules = args.pop(-1)
        dest = mailpile.defaults.CONFIG_RULES
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
        dest = mailpile.defaults.CONFIG_RULES
        path = '/'.join(args)
        for arg in args:
            dest = dest[arg][-1]
        if rname in dest:
            raise PluginError('Section already exist: %s/%s' % (path, rname))
        else:
            dest[rname] = rules


    ##[ Pluggable keyword extractors ]########################################

    DATA_KW_EXTRACTORS = {}
    TEXT_KW_EXTRACTORS = {}
    META_KW_EXTRACTORS = {}

    def _rkwe(self, kw_hash, term, function):
        if term in kw_hash:
            raise PluginError('Already registered: %s' % term)
        kw_hash[term] = function

    def register_data_kw_extractor(self, term, function):
        self._compat_check()
        return self._rkwe(self.DATA_KW_EXTRACTORS, term, function)

    def register_text_kw_extractor(self, term, function):
        self._compat_check()
        return self._rkwe(self.TEXT_KW_EXTRACTORS, term, function)

    def register_meta_kw_extractor(self, term, function):
        self._compat_check()
        return self._rkwe(self.META_KW_EXTRACTORS, term, function)

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
        self._compat_check()
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
                register_config_section(
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
        assert(hasattr(thread_obj, 'start'))
        assert(hasattr(thread_obj, 'quit'))
        # FIXME: complain about duplicates?
        self.WORKERS.append(thread_obj)


    ##[ Pluggable commands ]##################################################

    def register_commands(self, *args):
        self._compat_check()
        COMMANDS = mailpile.commands.COMMANDS
        for cls in args:
            if cls not in COMMANDS:
                COMMANDS.append(cls)


    ##[ Pluggable templates and static content ]##############################

    WEB_ASSETS = {}

    def register_web_asset(self, plugin, path, filename, mimetype='text/html'):
        if path in self.WEB_ASSETS:
            raise PluginError(_('Already registered: %s') % path)
        self.WEB_ASSETS[path] = (filename, mimetype, plugin)

    def get_web_asset(self, path, default=None):
        return tuple(self.WEB_ASSETS.get(path, [default, None])[0:2])


    ##[ Pluggable UI elements ]###############################################

    DEFAULT_UICLASSES = ["base", "search", "thread", "contact", "tag"]
    UICLASSES = []
    DISPLAY_MODES = {}
    DISPLAY_ACTIONS = {}
    SELECTION_ACTIONS = {}
    ASSETS = {"javascript": [], "stylesheet": [], "content-view_block": []}
    BODY_BLOCKS = {}
    ACTIVITIES = []

    def _register_builtin_uiclasses(self):
        self._compat_check()
        for cl in self.DEFAULT_UICLASSES:
            self.register_uiclass(cl)

    def register_uiclass(self, uiclass):
        self._compat_check()
        if uiclass not in self.UICLASSES:
            self.UICLASSES.append(uiclass)
            self.DISPLAY_ACTIONS[uiclass] = []
            self.DISPLAY_MODES[uiclass] = []
            self.SELECTION_ACTIONS[uiclass] = []
            self.BODY_BLOCKS[uiclass] = []

    def register_display_mode(self, uiclass, name, jsaction, text,
                              url="#", icon=None):
        self._compat_check()
        assert(uiclass in self.DISPLAY_MODES)
        if name not in [x["name"] for x in self.DISPLAY_MODES[uiclass]]:
            self.DISPLAY_MODES[uiclass].append({
                "name": name,
                "jsaction": jsaction,
                "url": url,
                "text": text,
                "icon": icon
            })

    def register_display_action(self, uiclass, name, jsaction, text,
                                url="#", icon=None):
        self._compat_check()
        assert(uiclass in self.DISPLAY_ACTIONS)
        if name not in [x["name"] for x in self.DISPLAY_ACTIONS[uiclass]]:
            self.DISPLAY_ACTIONS[uiclass].append({
                "name": name,
                "jsaction": jsaction,
                "url": url,
                "text": text,
                "icon": icon
            })

    def register_selection_action(self, uiclass, name, jsaction, text,
                                  url="#", icon=None):
        self._compat_check()
        assert(uiclass in self.SELECTION_ACTIONS)
        if name not in [x["name"] for x in self.SELECTION_ACTIONS[uiclass]]:
            self.SELECTION_ACTIONS[uiclass].append({
                "name": name,
                "jsaction": jsaction,
                "url": url,
                "text": text,
                "icon": icon
            })

    def register_activity(self, name, jsaction, icon, url="#"):
        self._compat_check()
        if name not in [x["name"] for x in self.ACTIVITIES]:
            self.ACTIVITIES.append({
                "name": name,
                "jsaction": jsaction,
                "url": url,
                "icon": icon,
                "text": text
            })

    def register_asset(self, assettype, name):
        self._compat_check()
        assert(assettype in self.ASSETS)
        if name not in self.ASSETS[assettype]:
            self.ASSETS[assettype].append(name)

    def get_assets(self, assettype):
        self._compat_check(strict=False)
        assert(assettype in self.ASSETS)
        return self.ASSETS[assettype]

    def register_body_block(self, uiclass, name):
        self._compat_check()
        assert(uiclass in self.UICLASSES)
        if name not in self.BODY_BLOCKS[uiclass]:
            self.BODY_BLOCKS[uiclass].append(name)

    def get_body_blocks(self, uiclass):
        self._compat_check(strict=False)
        assert(uiclass in self.UICLASSES)
        return self.BODY_BLOCKS[uiclass]

    def get_activities(self):
        self._compat_check(strict=False)
        return self.ACTIVITIES

    def get_selection_actions(self, uiclass):
        self._compat_check(strict=False)
        return self.SELECTION_ACTIONS[uiclass]

    def get_display_actions(self, uiclass):
        self._compat_check(strict=False)
        return self.DISPLAY_ACTIONS[uiclass]

    def get_display_modes(self, uiclass):
        self._compat_check(strict=False)
        return self.DISPLAY_MODES[uiclass]


# Initial global setup
PluginManager(builtin=True)._register_builtin_uiclasses()

# Backwards compatibility
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
register_display_mode = _default_pm.register_display_mode
register_display_action = _default_pm.register_display_action
register_selection_action = _default_pm.register_selection_action
register_activity = _default_pm.register_activity
register_asset = _default_pm.register_asset
get_assets = _default_pm.get_assets
register_body_block = _default_pm.register_body_block
get_body_blocks = _default_pm.get_body_blocks
get_activities = _default_pm.get_activities
get_selection_actions = _default_pm.get_selection_actions
get_display_actions = _default_pm.get_display_actions
get_display_modes = _default_pm.get_display_modes
