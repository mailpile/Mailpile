import os.path
import json
import sys
import logging
'''
Bootstrap execution in an entirely clean checkout to ensure we use build scripts
matched to the specified build target.
'''

def bind(framework):
    '''
    Attach build config+scripts to the build framework
    '''

    @framework.default_config('bootstrap')
    def config_bootstrap(keyword):
        '''
        Inner configuration JSON for a fully bootstrapped build. All options
        passed here are forwarded to the checked out build. The bootstrap env
        will inherit this build's cache directory and log level. A second log
        file will be created for this build.
        '''
        
        return None

    @framework.provide('bootstrap')
    def provide_bootstrap(build, keyword):
        '''
        bootstrap execution of a native build.
        '''
        if not build.config('bootstrap'):
            return
        
        build.depend('python27')
        mailpile_dir = build.depend('mailpile')

        log_level = logging.getLogger().getEffectiveLevel()
        for attr in dir(logging):
            if getattr(logging,attr) == log_level:
                log_config = attr
                break

        util = build.depend('util')
        with util.temporary_scope() as scope:
            with scope.named_file() as handle:
                json.dump(build.config('bootstrap'), handle)
                config_file = handle.name
                
            devtool_path = os.path.join(mailpile_dir, 'packages\\windows-wix')
            build.log().info("Entering bootstrap build(this could take a while)")
            build.invoke('python', 'provide',
                         '--log_level={}'.format(log_config),
                         '--input={}'.format(config_file),
                         '--cache={}'.format(build.cache().cache.cache_dir))
            build.log().info("Exiting bootstrap build")
