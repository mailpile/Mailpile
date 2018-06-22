import os.path


def bind(build):

    @build.default_config('mailpile', 'gui-o-matic')
    def config_gui_o_matic(keyword):
        '''
        Configure git checkout url and commit/branch.
        '''
        return {'commit': 'master',
                'repo': 'https://github.com/mailpile/{}'.format(keyword)}

    @build.provide('mailpile', 'gui-o-matic')
    def provide_checkout(build, keyword):
        '''
        Checkout the specified git repository to the specified commit/branch and
        delete git files.
        '''
        build.depend('git')
        build.depend('root')
        dep_path = build.invoke('path', keyword)
        util = build.depend('util')
        config = build.config(keyword)

        build.invoke('git', 'clone', config['repo'], dep_path, '--recursive')
        with util.pushdir(dep_path):
            build.invoke('git', 'checkout', config['commit'])
            #build.invoke( 'git', 'submodule', 'update', '--init', '--recursive' )
            util.rmtree('.git')

        return dep_path
