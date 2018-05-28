import os
import os.path
import itertools

def bind(build):

    @build.default_config('git', 'signtool')
    def default_config_env(keyword):
        '''
        Commands expected to exist on PATH.
        '''
        return keyword + '.exe'

    @build.default_config('signtool')
    def default_config_sdk(keyword):
        '''
        Try to discover tools from the windows sdk, otherwise expect on PATH.
        '''
        win_sdk_root = 'C:\\Program Files (x86)\\Windows Kits\\10\\bin'
        versions = os.listdir(win_sdk_root)
        versions.sort(reverse=True)
        template = win_sdk_root + '\\{}\\{}\\{}.exe'
        for version, platform in itertools.product(versions,('x86','x64')):
            path = template.format(version, platform, keyword)
            if os.path.exists(path):
                return path

        return keyword + '.exe'

    @build.provide('git', 'signtool')
    def provide_from_config(build, keyword):
        '''
        Trivial wrapper to inject invokables from config
        '''
        exe_path = build.config(keyword)

        build.publish(keyword, exe_path)
        return None
