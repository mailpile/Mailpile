import os.path
import tempfile


def bind(build):

    @build.provide('root')
    def provide_root(build, keyword):
        '''
        Provide build root temporary directory and 'path' invokable.
        '''
        util = build.depend('util')

        root = tempfile.mkdtemp()
        build.log().info("Initialized build root at '{}'".format(root))

        def cleanup_root():
            build.log().info("Removing build root at '{}'".format(root))
            util.rmtree(root)

        build.cleanup(cleanup_root)

        def dependency_path(dependency):
            return os.path.join(root, dependency)

        build.publish('path', dependency_path)

        return root
