import tempfile
import os.path
import glob
import contextlib
import shutil
import stat
import logging
import sys

logger = logging.getLogger(__name__)

class TemporaryScope(object):
    '''
    Context for tracking multiple temporary files.

    Principly combats nested contexts:

        with tempfile() as x:
            with tempfile() as y:
                with tempdir() as z:
                    with tempsomething as q:
                        ...
    translates to:

        with TemporaryScope() as context:

            with context.named_file(...) as x:
                ...

            with context.named_file(...) as Y:
                ...

            z = context.named_dir(...):
                ...

    so that named resouces may be sequentially constructed and automatically
    cleaned up.
    '''

    def __init__(self, deleter):
        self.deleter = deleter

    def __enter__(self):
        self.paths = []
        return self

    def __exit__(self, *ignored):
        for path in self.paths:
            self.deleter(path)

        del self.paths

    def named_file(self, *args, **kwargs):
        kwargs['delete'] = False
        result = tempfile.NamedTemporaryFile(*args, **kwargs)
        self.paths.append(result.name)
        return result

    def named_dir(self, *args, **kwargs):
        result = tempfile.mkdtemp(*args, **kwargs)
        self.paths.append(result)
        return result


class Util(object):
    '''
    Utility functions for builds
    '''

    @staticmethod
    def rmtree(path):
        '''
        Remove an entire directory tree rm -rf style, logging any errors
        '''

        def retry_log(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
                func(path)
            except:
                logger.error("Unable perform action {}: {} {}".format(path, func, path),
                         exc_info=exc_info)
                
        if os.path.isdir(path):
            shutil.rmtree(path, onerror=retry_log)
        else:
            try:
                os.unlink(path)
            except:
                log_error('os.unlink', path, sys.exc_info())

    @classmethod
    def temporary_scope(cls):
        '''
        Create a temporary scope that uses rmtree as deleter
        '''

        return TemporaryScope(cls.rmtree)

    @staticmethod
    def publish_exes(build, path):
        '''
        Publish all exes found on the path
        '''

        for exe in glob.glob(os.path.join(path, '*.exe')):
            cmd = os.path.basename(exe).split('.')[0]
            build.publish(cmd, exe)

    @staticmethod
    @contextlib.contextmanager
    def tempdir(*args, **kwargs):
        '''
        Temporary directory context: tempdir is deleted at exit.
        returns temp dir absolute path
        '''

        path = tempfile.mkdtemp(*args, **kwargs)
        try:
            yield path
        finally:
            rmtree_log_error(path)

    @staticmethod
    @contextlib.contextmanager
    def pushdir(path):
        '''
        Pushdir as a context manager. Restores previous working directory on exit.
        '''
        cwd = os.path.abspath(os.getcwd())
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(cwd)


def bind(build):

    @build.provide('util')
    def provide_util(build, keyword):
        return Util
