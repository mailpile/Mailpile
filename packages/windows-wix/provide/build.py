import subprocess
import os.path
import tempfile
import argparse
import datetime
import logging

logger = logging.getLogger( __name__ )
        
class Build( object ):
    '''
    Construct a build environment where providers can be invoked to
    compose build artifacts.
    '''

    class Invoker( object ):
        '''
        Utility class for invoking external binaries. Captures stderr on error,
        otherwise returns stdout. The intention is for the invocation to be
        mostly a pythonic function call.
        '''

        def __init__( self, exe, method = subprocess.check_output ):
            '''
            Configure the execution target and invocation method.
            '''
            
            self.exe = exe
            self.method = method

        def __call__( self, *args ):
            '''
            Invoke the command, proxying arguments. Also surpress displaying
            windows when possible.
            '''
            
            cmdline = (self.exe,) + tuple(args)
            logger.debug( "Running command line: {}".format( cmdline ) )
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            with tempfile.TemporaryFile( 'ab+' ) as error_file:
                try:
                    return self.method( cmdline,
                                        stderr = error_file,
                                        startupinfo = si,
                                        universal_newlines = True)
                except subprocess.CalledProcessError as e:
                    error_file.seek( 0 )
                    error_text = error_file.read()
                    logger.critical( "stderr from exception:\n" + error_text )
                    e.stderr = error_text
                    raise

    class Context( object ):
        '''
        Build context that's disposed of after a build
        '''

        def __init__( self, build, cache, config ):
            '''
            Attach the context to the parent build, and configure initial
            properties.
            '''
            
            self._build = build
            self._built = {}
            self._cmds = {}
            self._log = logger #TODO: Proxy things for clarity
            self._config = config
            self._cache = cache
            self._cleanup = []

        def cache( self ):
            '''
            API for accessing the SemanticCache for this build.
            '''
            
            return self._cache

        def log( self ):
            '''
            API for accessing the logger for this build.
            '''

            return self._log
        
        def depend( self, keyword ):
            '''
            Return the path to the specified build dependency, building it if
            needed.
            '''
            
            try:
                return self._built[ keyword ]
            except KeyError:
                self.log().info( "Inflating dependency {}".format( keyword ) )
                provider = self._build._providers[ keyword ]
                result = provider( self, keyword )
                self._built[ keyword ] = result
                return result

        def cleanup( self, action ):
            '''
            Add a cleanup action to the build context.
            '''

            self._cleanup.append( action )

        def publish( self, keyword, invoker ):
            '''
            Provide an invokable for other build scripts to use. Can either be
            a callable, or an absolute path to an executable. See Build.Invoker.
            '''
            
            if not callable( invoker ):
                invoker = self._build.Invoker( invoker )
            self.log().debug( 'registering invokable {}'.format( keyword ) )
            self._cmds[ keyword ] = invoker

        def invoke( self, keyword, *args, **kwargs ):
            '''
            Call a published interface with the specified arguments and kwargs
            '''
            
            return self._cmds[ keyword ]( *args, **kwargs )
            
        def clear( self ):
            '''
            Delete everything in the build context.
            '''
            
            for action in self._cleanup:
                try:
                    action()
                except:
                    self.log().exception("Error during cleanup!")

        def config( self, keyword ):
            '''
            Query a key-value config item.
            '''
            
            try:
                result = self._config[ keyword ]
            except KeyError:
                result = self._build._defaults[ keyword ]( keyword )
                self.log().info( "Using default '{}' config '{}'".format( keyword, result ) )
            return result

        def __enter__( self ):
            self._begin = datetime.datetime.utcnow()
            self.log().info('Entering build context at {}'.format(self._begin.isoformat()))
            return self

        def __exit__( self, type, value, traceback ):
            end = datetime.datetime.utcnow()
            self.log().info('Exiting build context at {}'.format(end.isoformat()))
          
            if traceback:
                self.log().exception( "Build failed!" )
            self.clear()
            self.log().info('Elapsed build time: {}'.format(end-self._begin))

    def __init__( self ):
        '''
        Create a new build framework
        '''
        
        self._providers = {}
        self._defaults ={}
        self._options = {}

    def provide( self, *keywords ):
        '''
        decorator that registers a provider for a keyword
        '''
        
        def decorator( provider ):
            for keyword in keywords:
                self._providers[ keyword ] = provider
            return provider
        return decorator

    def default_config( self, *keywords ):
        '''
        decorator that registers a provider for a default configuration
        '''
        
        def decorator( callback ):
            for keyword in keywords:
                self._defaults[ keyword ] = callback
            return callback
        return decorator

    def context( self, cache, config = {} ):
        '''
        Create a new build context
        '''
        return self.Context( self, cache, config )

    def parser( self ):
        '''
        Create an argument parser for this build
        '''
        parser = argparse.ArgumentParser()
        for keyword, doc in self._options():
            parser.add_argument('--' + keyword, help=doc)
        return parser
    
    def parse( self, *args, **kwargs ):
        '''
        create a context from argv
        '''
        args = self.parser().parse_args( *args, **kwargs )
        def resolve( value ):
            try:
                return json.loads( value )
            except:
                return value

        config = {key: resolve(getattr(key, args)) for key in dir(args)}
        resources = cache.SemanticCache.load( 'resources.json' )
        return self.context( resources, config )
            
