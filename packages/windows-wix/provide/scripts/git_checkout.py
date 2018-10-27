import os.path
import shutil

def bind(build):

    def repo_root():
        '''
        Find the root of the current checkout
        '''
        repo_path = os.path.abspath(os.path.dirname(__file__))
        while not os.path.exists(os.path.join(repo_path,'.git')):
            parts = os.path.split(repo_path)
            if parts[0] == repo_path:
                raise ValueError("Cannot find root of git checkout!")
            else:
                repo_path = parts[0]
        return repo_path

    @build.default_config('mailpile')
    def config_repo(keyword):
        '''
        Configure git checkout url and commit/branch. Either a json like
        {"commit": "<hash or branch>", "repo": "<url>" } or path to local
        checkout to copy.
        '''
        return repo_root() #{'commit': 'master',
                #'repo': 'https://github.com/mailpile/{}'.format(keyword)}

    def copy_local_repo(build, src, dst):
        '''
        Copy the repo from on disk
        '''
        build.depend('git')
        util = build.depend('util')

        build.log().info("copying local repo: '{}'".format(src))
        shutil.copytree(src, dst)
        with util.pushdir(dst):
            build.invoke('git', 'clean', '-xdf')

    def clone_remote_repo(build, config, dst):
        '''
        clone the repo from a dict of 'repo' url and 'commit'
        '''
        build.depend('git')
        util = build.depend('util')
        
        build.log().info("cloning remote repo: '{}'".format(config))        
        build.invoke('git', 'clone', config['repo'], dst, '--recursive')
        with util.pushdir(dst):
            build.invoke('git', 'checkout', config['commit'])

    @build.provide('mailpile')
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
        
        if isinstance( config, str ):
            checkout_method = copy_local_repo
        else:
            checkout_method = clone_remote_repo

        checkout_method(build, config, dep_path)
        with util.pushdir(dep_path):
            util.rmtree('.git')
        return dep_path

