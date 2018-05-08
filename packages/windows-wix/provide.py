#!/usr/bin/python

'''
This is a framework to facilitate dynamically constructing the build environment
based on demands, including custom logic. At a high level, we'd like to be able
to script generating a release as composing a set of artifacts which we then
prepare and pacakge. I.e:

 items = ['python27',
          'gpg',
          'tor',
          'openssl',
          'mailpile',
          'gui-o-matic']
 paths = provide( items, build_dir )
 prepare( paths, signing_key )
 msi_path, checksum = package( paths, build_version, languages )

In reality, we're targeting building on an arbitrary modern-ish windows as much
as possible, so we'll have to 1) play nice and 2) provide a bunch of add-hock
build tools:

  - lessmsi: unpack msis that may already be installed
  - resource-hacker: customize python branding
  - wix-tools: package output into msi
  - git: cleanly checkout repos for builds
  - signtool(windowsdk) NOTE: doesn't play nice
  - gpg4win: mkportable.exe for portable gpg NOTE: doesn't play nice.

General things that need to happen:
  - artifacts:
    - python:
       - unpack
       - install deps(TODO pip cache)
         - depends on mailpile commit--assume current commit
         - depends on gui-o-matic commit
       - rebrand
    - gpg:
       - install locally
       - make portable install into build dir
       - uninstall
    - tor:
       - extract zip in build directory
    - openssl:
       - TODO!
    - mailpile:
       - git clone, submodule update, and checkout to target commit
       - prune cloned tree(git files, others?)
    - gui-o-matic:
       - git clone, submodule update, and checkout to target commit
       - prune cloned tree(git files, others?)
  - tools:
    - git: probably already installed?!?
      - register in build env
    - lessmsi:
      - extract zip
      - register in build env
    - wix-tools:
      - extract zip
      - register in build env
    - resource-hacker:
      - extract zip
      - register in build env
    - signtool: TODO!

  - packaging:
    - sign all the binaries
    - extract build version
      - if on a release tag, use that
      - else TODO
    - Build component database for WIX
      - uuids should match output paths to unique file versions
      - TODO: Use hash to detect/disambiguate source changes across versions
    - Build msi for languages:
      - TODO: script this!
    - sign msi: TODO!

Returning to the topic of build systems, we're really aiming for something thats
easy to customize and produces the right behavior as an emergent property--
i.e. internally handles sequencing etc. so long as no dependency cycles exist.

To do so, we construct a class-level provider registry that we populate with
recipies. Recipies are invoked relative to a build, and can depend on the output
of other recipies.
'''

import tempfile
import logging
import shutil
import os.path
import subprocess

logger = logging.getLogger( __name__ )

class Build( object ):
    '''
    Construct a build environment where providers can be invoked to
    compose build artifacts.
    '''

    class Invoker( object ):

        def __init__( self, exe ):
            self.exe = exe

        def __call__( self, args ):
            cmdline = (exe,) + args
            subprocess.check_call( cmdline ) 

    class Context( object ):
        '''
        Build context that's disposed of after a build
        '''

        def __init__( self, build ):
            self.build = build
            self.build_dir = tempfile.mkdtemp()
            self.built = {}
            self.cmds = {}
            logger.info('Constructing build context at {}'.format(self.build_dir))

        def cache( self ):
            return self.build.cache
        
        def depend( self, keyword ):
            try:
                return self.built[ keyword ]
            except KeyError:
                logger.info( "Inflating dependency {}".format( keyword ) )
                dep_path = os.path.join( self.build_dir, keyword )
                provider = self.build._providers[ keyword ]
                result = provider( self, keyword, dep_path )
                self.built[ keyword ] = result
                return result

        def publish( self, keyword, invoker ):
            if not callable( invoker ):
                invoker = self.build.Invoker( invoker )
            logger.debug( 'registering invokable {}'.format( keyword ) )
            self.cmds[ keyword ] = invoker

        def invoke( self, keyword, *args ):
            self.cmds[ keyword ]( args )
            
        def clear( self ):
            logger.info('Removing build context at {}'.format(self.build_dir))
            def log_error( func, path, exec_info ):
                logger.error("Error cleaning up {}: {} {}".format( msi_path, func, path ),
                             exec_info = exec_info )
            shutil.rmtree( self.build_dir, ignore_errors = True, onerror = log_error )        

    _providers = {}

    @classmethod
    def provide( cls, *keywords ):
        '''
        decorator that registers a provider for a keyword
        '''
        def decorator( provider ):
            for keyword in keywords:
                cls._providers[ keyword ] = provider
            return provider
        return decorator

    def __init__( self, cache ):
        self.cache = cache
        self.context = None
        
    def __enter__( self ):
        assert( self.context is None )
        self.context = self.Context( self )
        return self.context

    def __exit__( self, type, value, traceback ):

        if traceback:
            logger.exception( "Build failed!" )
        self.context.clear()
        self.context = None

import zipfile
import glob

def publish_exes( build, path ):
    for exe in glob.glob( os.path.join( path, '*.exe' ) ):
        cmd = os.path.basename( exe ).split('.')[0]
        build.publish( cmd, exe )

@Build.provide( 'wix', 'tor', 'lessmsi' )
def provide_zip( build, keyword, dep_path ):
    zip_path = build.cache().resource( keyword )
    archive = zipfile.ZipFile( zip_path )
    archive.extractall( dep_path )
    publish_exes( build, dep_path )
    return dep_path

import msi_extract

@Build.provide( 'python27' )
def provide_python( build, keyword, dep_path ):
    lessmsi = os.path.join( build.depend( 'lessmsi' ), 'lessmsi.exe' )
    extractor = msi_extract.LessMSI( lessmsi )
    extractor( build.cache().resource( keyword ), dep_path )
    publish_exes( build, dep_path )

    # TODO: PIP things
    # TOTO: Resource hacker

    return dep_path

if __name__ == '__main__':
    import cache
    import time
    logging.basicConfig()
    logger.setLevel( logging.DEBUG )
    
    resources = cache.SemanticCache.load( 'resources.json' )
    with Build( resources ) as build:
        build.depend( 'wix' )
        build.depend( 'python27' )
    
