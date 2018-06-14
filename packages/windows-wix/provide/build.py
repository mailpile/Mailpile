import subprocess
import os.path
import tempfile
import argparse
import datetime
import logging
import json
import itertools

logger = logging.getLogger(__name__)


class Build(object):
    '''
    Construct a build environment where providers can be invoked to
    compose build artifacts.
    '''

    class Invoker(object):
        '''
        Utility class for invoking external binaries. Captures stderr on error,
        otherwise returns stdout. The intention is for the invocation to be
        mostly a pythonic function call.
        '''

        def __init__(self, build, exe, method=subprocess.check_output):
            '''
            Configure the execution target and invocation method.
            '''
            self.build = build
            self.exe = exe
            self.method = method

        def __call__(self, *args):
            '''
            Invoke the command, proxying arguments. Also surpress displaying
            windows when possible.
            '''

            cmdline = (self.exe,) + tuple(args)
            self.build.log().debug("Running command line: {}".format(cmdline))
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            with tempfile.TemporaryFile('ab+') as error_file:
                try:
                    return self.method(cmdline,
                                       stderr=error_file,
                                       startupinfo=si,
                                       universal_newlines=True)
                except subprocess.CalledProcessError as e:
                    error_file.seek(0)
                    error_text = error_file.read()
                    self.build.log().critical("stderr from exception:\n" + error_text.decode())
                    self.build.log().critical("stdout from exception:\n" + e.output)
                    e.stderr = error_text
                    raise

    class Context(object):
        '''
        Build context that's disposed of after a build
        '''

        def __init__(self, build, cache, config):
            '''
            Attach the context to the parent build, and configure initial
            properties.
            '''

            self._build = build
            self._built = {}
            self._cmds = {}
            self._config = config
            self._cache = cache
            self._cleanup = []
            self._log = [logger]  # TODO: Proxy things for clarity

        def cache(self):
            '''
            API for accessing the SemanticCache for this build.
            '''

            return self._cache

        def log(self):
            '''
            API for accessing the logger for this build.
            '''

            return self._log[-1]

        def depend(self, keyword):
            '''
            Return the path to the specified build dependency, building it if
            needed.
            '''

            try:
                return self._built[keyword]
            except KeyError:
                self.log().info("Inflating dependency {}".format(keyword))
                log_name = '{}.{}@{}'.format(__name__, keyword, len(self._log))
                self._log.append(logging.getLogger(log_name))
                provider = self._build._providers[keyword]
                result = provider(self, keyword)
                self._built[keyword] = result
                self._log.pop()
                return result

        def cleanup(self, action):
            '''
            Add a cleanup action to the build context.
            '''

            self._cleanup.append(action)

        def publish(self, keyword, invoker):
            '''
            Provide an invokable for other build scripts to use. Can either be
            a callable, or an absolute path to an executable. See Build.Invoker.
            '''

            if not callable(invoker):
                invoker = self._build.Invoker(self, invoker)
            self.log().debug('registering invokable {}'.format(keyword))
            self._cmds[keyword] = invoker

        def invoke(self, keyword, *args, **kwargs):
            '''
            Call a published interface with the specified arguments and kwargs
            '''

            return self._cmds[keyword](*args, **kwargs)

        def clear(self):
            '''
            Delete everything in the build context.
            '''

            for action in self._cleanup:
                try:
                    action()
                except:
                    self.log().exception("Error during cleanup!")

        def config(self, keyword):
            '''
            Query a key-value config item.
            '''

            try:
                result = self._config[keyword]
            except KeyError:
                result = self._build._defaults[keyword](keyword)
                self.log().info("Using default '{}' config '{}'".format(keyword, result))
            return result

        def __enter__(self):
            self._begin = datetime.datetime.utcnow()
            self.log().info('Entering build context at {}'.format(self._begin.isoformat()))
            return self

        def __exit__(self, type, value, traceback):
            end = datetime.datetime.utcnow()
            self.log().info('Exiting build context at {}'.format(end.isoformat()))

            if traceback:
                self.log().exception("Build failed!")
            self.clear()
            self.log().info('Elapsed build time: {}'.format(end-self._begin))

    def __init__(self):
        '''
        Create a new build framework
        '''

        self._providers = {}
        self._defaults = {}
        self._options = {}

    def provide(self, *keywords, **extra):
        '''
        decorator that registers a provider for a keyword
        '''

        def decorator(provider):
            for keyword in keywords:
                self._providers[keyword] = provider
            return provider
        return decorator

    def default_config(self, *keywords, **extra):
        '''
        decorator that registers a provider for a default configuration
        '''

        def decorator(callback):
            for keyword in keywords:
                self._defaults[keyword] = callback
            return callback
        return decorator

    def define_config(self, keyword, doc):
        '''
        Configuration value without default.
        '''
        self._options[keyword] = doc

    def context(self, cache, config={}):
        '''
        Create a new build context
        '''
        return self.Context(self, cache, config)

    def parser(self, parser=None):
        '''
        Create an argument parser for this build
        '''
        parser = parser or argparse.ArgumentParser()
        for keyword, func in self._defaults.items():
            help_str = repr(func(keyword))
            if func.__doc__:
                desc = func.__doc__.strip()
                if not desc.endswith('.'):
                    desc += '.'
                help_str = '{} Default: {}'.format(desc, help_str)
                
            parser.add_argument('--config_' + keyword.replace('-', '_'),
                                help=help_str)

        for keyword, desc in self._options.items():                   
            parser.add_argument('--config_' + keyword.replace('-', '_'),
                                help=desc)
        return parser

    def parse_config(self, args):
        '''
        create a context from argv
        '''
        config = {}
        for key in itertools.chain(self._defaults.keys(), self._options.keys()):
            test = 'config_' + key.replace('-', '_')
            value = getattr(args, test)
            if value is not None:
                try:
                    value = json.loads(value)
                except:
                    pass

                config[key] = value

        return config
