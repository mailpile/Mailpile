import os.path
import shutil

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
            util.rmtree('.git')

        return dep_path

    def provide_copy(build, keyword):
        '''
        Copy the repo from on disk
        '''
        build.depend('git')
        build.depend('root')
        dep_path = build.invoke('path', keyword)
        util = build.depend('util')

        # find the root of this repo
        repo_root = os.path.abspath(os.dirname(__file__))
        while ! os.path.exists(os.path.join(repo_root,'.git')):
            parts = os.path.split(repo_root)
            if parts[0] == repo_path:
                raise ValueError("Cannot find root of git checkout!")
            else:
                repo_path = parts[0]
        shutil.copytree(repo_path, dep_path)
        with util.pushdir(dep_path):
            subprocess.check_call( ['git', 'clean', '-xdf'] )

        return dep_path
