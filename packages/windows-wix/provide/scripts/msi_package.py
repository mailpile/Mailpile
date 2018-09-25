import sys
import os.path

# Hack to import somewhat relatively
#
lib_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, lib_dir)
import package
sys.path.pop(0)

import json
import copy

try:
    check = unicode
except NameError:
    unicode = str


def format_pod(template, **kwargs):
    '''
    apply str.format to all str elements of a simple object tree template
    '''
    if isinstance(template, dict):
        template = {format_pod(key, **kwargs): format_pod(value, **kwargs)
                    for (key, value) in template.items()}
    elif isinstance(template, str) or isinstance(template, unicode):
        template = template.format(**kwargs)
    elif isinstance(template, list):
        template = [format_pod(value, **kwargs) for value in template]
    elif callable(template):
        template = format_pod(template(), **kwargs)
    else:
        # Maybe raise an error instead?
        #
        template = copy.copy(template)

    return template


def bind(build):

    @build.default_config('package_template')
    def config_package_jsons(keyword):
        '''
        json configuration files for packaging
        '''
        return os.path.join(lib_dir, keyword + '.json')

    @build.default_config('package_cultures')
    def config_package_lang(keyword):
        '''
        Wix 'cultures' for which to produce packages.
        '''
        return ['en-us']

    @build.provide('package')
    def provide_msi(build, keyword):
        '''
        Build an MSI with all the mailpile dependencies
        '''

        build.depend('root')
        dep_path = build.invoke('path', keyword)

        if not os.path.exists(dep_path):
            os.mkdir(dep_path)

        content_keys = ('tor',
                        'mailpile',
                        'python27',
                        'openssl',
                        'gpg',
                        'version')

        content_paths = {key: build.depend(key) for key in content_keys}

        # pre-cache mailpile
        build.invoke('python',
                     os.path.join(content_paths['mailpile'],
                                  'packages\\windows-wix\\bin\\with-mailpile-env.py'),
                     os.path.join(content_paths['mailpile'],
                                  'shared-data\\mailpile-gui\\mailpile-gui.py'),
                     '--compile')

        tool_keys = ('wix',
                     'sign_tree')

        tool_paths = {key: build.depend(key) for key in tool_keys}

        # sign binary content
        #
        for path in content_paths.values():
            if os.path.exists(path):
                build.invoke('sign_tree', path)

        # create the template for building the wix config
        #
        with open(build.config('package_template'), 'r') as handle:
            package_template = json.load(handle)
            package_config = format_pod(package_template, **content_paths)

        with open(os.path.join(dep_path, 'mailpile.package.json'), 'w') as handle:
            json.dump(package_config, handle, indent=2)

        wix = package.WixConfig(package_config)

        # TODO: Split uuid and wix config saving
        wix_config_path = os.path.join(dep_path, 'mailpile')
        wix.save(wix_config_path + '.wxs')

        # Package everything using WIX
        #
        build.invoke('candle', wix_config_path + '.wxs',
                     '-out', os.path.join(dep_path, 'mailpile.wixobj'))

        for lang in build.config('package_cultures'):
            msi_name = 'mailpile-{}-{}.msi'.format(content_paths['version'],
                                                   lang)
            build.log().info("Building msi for culture: " + lang)
            build.invoke('light',
                         '-ext', 'WixUIExtension',
                         '-ext', 'WixUtilExtension',
                         '-cultures:' + lang,
                         wix_config_path + '.wixobj',
                         '-out', os.path.join(dep_path, msi_name))

        # Sign the generated files
        #
        build.invoke('sign_tree', dep_path)
        
        return dep_path
