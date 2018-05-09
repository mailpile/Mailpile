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
import os
import subprocess
import contextlib

logger = logging.getLogger( __name__ )

def rmtree_log_error( path ):
    '''
    Remove an entire directory tree rm -rf style, logging any errors
    '''
    def log_error( func, path, exc_info ):
        logger.error("Unable perform action {}: {} {}".format( msi_path, func, path ),
                      exec_info = exc_info )
    if os.path.isdir( path ):
        shutil.rmtree( path, ignore_errors = True, onerror = log_error )
    else:
        try:
            os.unlink( path )
        except:
            log_error( 'os.unlink', path, sys.exc_info() )

@contextlib.contextmanager
def tempdir( *args, **kwargs ):
    '''
    Temporary directory context: tempdir is deleted at exit.
    returns temp dir absolute path
    '''
    path = tempfile.mkdtemp( *args, **kwargs )
    try:
        yield path
    finally:
        rmtree_log_error( path )

@contextlib.contextmanager
def pushdir( path ):
    '''
    Pushdir as a context manager. Restores previous working directory on exit.
    '''
    cwd = os.path.abspath( os.getcwd() )
    os.chdir( path )
    try:
        yield
    finally:
        os.chdir( cwd )

class TemporaryScope( object ):
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

    def __init__( self, deleter = rmtree_log_error ):
        self.deleter = deleter

    def __enter__( self ):
        self.paths = []
        return self

    def __exit__( self, *ignored ):
        for path in self.paths:
            self.deleter( path )

        del self.paths

    def named_file( self, *args, **kwargs ):
        kwargs['delete'] = False
        result = tempfile.NamedTemporaryFile( *args, **kwargs )
        self.paths.append( result.name )
        return result

    def named_dir( self, *args, **kwargs ):
        result = tempfile.mkdtemp( *args, **kwargs )
        self.paths.append( result )
        return result
            
        
class Build( object ):
    '''
    Construct a build environment where providers can be invoked to
    compose build artifacts.
    '''

    class Invoker( object ):

        def __init__( self, exe, method = subprocess.check_output ):
            self.exe = exe
            self.method = method

        def __call__( self, *args ):
            cmdline = (self.exe,) + tuple(args)
            logger.debug( "Running command line: {}".format( cmdline ) )
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            with tempfile.TemporaryFile( 'a+' ) as error_file:
                try:
                    return self.method( cmdline,
                                        stderr = error_file,
                                        startupinfo = si )
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

        def __init__( self, build ):
            self.build = build
            self.build_dir = tempfile.mkdtemp()
            self.built = {}
            self.cmds = {}
            self.log = logger #TODO: Proxy things for clarity
            self.log.info('Constructing build context at {}'.format(self.build_dir))

        def cache( self ):
            return self.build.cache

        def root( self ):
            return self.build_dir
        
        def depend( self, keyword ):
            try:
                return self.built[ keyword ]
            except KeyError:
                self.log.info( "Inflating dependency {}".format( keyword ) )
                dep_path = os.path.join( self.build_dir, keyword )
                provider = self.build._providers[ keyword ]
                result = provider( self, keyword, dep_path )
                self.built[ keyword ] = result
                return result

        def publish( self, keyword, invoker ):
            if not callable( invoker ):
                invoker = self.build.Invoker( invoker )
            self.log.debug( 'registering invokable {}'.format( keyword ) )
            self.cmds[ keyword ] = invoker

        def invoke( self, keyword, *args ):
            return self.cmds[ keyword ]( *args )
            
        def clear( self ):
            self.log.info('Removing build context at {}'.format(self.build_dir))
            rmtree_log_error( self.build_dir )

        def config( self, keyword ):
            try:
                result = self.build.config[ keyword ]
            except KeyError:
                result = self.build._defconfig[ keyword ]( keyword )
                self.log.info( "Using default {} config '{}'".format( keyword, result ) )
            return result

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

    _defconfig = {}

    @classmethod
    def default_config( cls, *keywords ):
        '''
        decorator that registers a provider for a default configuration
        '''
        def decorator( callback ):
            for keyword in keywords:
                cls._defconfig[ keyword ] = callback
            return callback
        return decorator

    def __init__( self, cache, config = {} ):
        self.cache = cache
        self.config = config
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

    # TODO: Prune unwanted files--either via features or manual delete.

    # Manually bootstrap pip.
    # https://stackoverflow.com/questions/36132350/install-python-wheel-file-without-using-pip
    #
    build.log.debug( 'Bootstrapping pip from bundled wheels' )
    bundle_dir = os.path.join( dep_path, 'Lib\\ensurepip\\_bundled' )
    pip_wheel = next( glob.iglob( os.path.join( bundle_dir, 'pip*.whl' ) ) )
    setup_wheel = next( glob.iglob( os.path.join( bundle_dir, 'setup*.whl' ) ) )

    tmp_pip = os.path.join( pip_wheel, 'pip' )
    build.invoke( 'python', tmp_pip, 'install', setup_wheel )
    build.invoke( 'python', tmp_pip, 'install', pip_wheel )

    # Use pip to install dependencies
    # TODO: Cache/statically version packages.
    #
    mailpile_dir = build.depend( 'mailpile' )
    pip_deps = os.path.join( mailpile_dir, 'requirements.txt' )
    build.invoke( 'python', '-m', 'pip', 'install', '-r', pip_deps )

    # TODO: import requirements from gui-o-matic
    #
    build.invoke( 'python', '-m', 'pip', 'install', 'pywin32' )
    
    # TODO: Rebrand with resource hacker
    #

    return dep_path

import textwrap

@Build.provide( 'gpg' )
def provide_gpg( build, keyword, dep_path ):
    '''
    install GPG in a temporary location and use mkportable to create a
    portable GPG for the build. Requires ADMIN and that gpg4win *is not*
    installed.
    '''
    build.depend( 'python27' )
    gpg_installer = build.cache().resource( 'gpg' )

    gpg_ini = textwrap.dedent( '''
        [gpg4win]
            inst_gpgol = false
            inst_gpgex = false
            inst_kleopatra = false
            inst_gpa = false
            inst_claws_mail = false
            inst_compendium = false
            inst_start_menu = false
            inst_desktop = false
            inst_quick_launch_bar = false
        ''')

    # Use the built python to elevate if needed
    # https://stackoverflow.com/questions/130763/request-uac-elevation-from-within-a-python-script
    build_template = textwrap.dedent( '''
        #!/usr/bin/python
        import sys
        import ctypes
        import subprocess
        import os.path
        import win32com.shell.shell as shell
        import win32com.shell.shellcon as shellcon
        import win32event
        import win32process
        import win32api
        import win32con
        import socket
        import random
        import traceback

        def make_portable_gpg():
            install_cmd = ("{installer_path}", "/S",
                           "/C={config}",
                           "/D={target}")
            uninstall_cmd = ("{uninstaller_path}", "/S")
            portable_cmd = ("{mkportable_path}", "{build}")
            
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.check_call( install_cmd, startupinfo = si )
            subprocess.check_call( portable_cmd, startupinfo = si )
            subprocess.check_call( uninstall_cmd, startupinfo = si )

        def ellevate_and_wait( sock, timeout ):
            sock.settimeout( timeout )
            while True:
                try:
                    port = random.randint(1000, 2**16-1)
                    sock.bind( ("localhost", port) )
                    break
                except socket.error:
                    continue

            parameters = '"{{}}" {{}}'.format( os.path.abspath( __file__ ), port )
            result = shell.ShellExecuteEx(fMask = shellcon.SEE_MASK_NOCLOSEPROCESS,
                                          lpVerb = "runas",
                                          lpFile = sys.executable,
                                          lpParameters = parameters,
                                          nShow = win32con.SW_HIDE )

            handle = result['hProcess']
            status = win32event.WaitForSingleObject(handle, -1)
            win32api.CloseHandle( handle )
            return sock.recv( 4096*1024 )

        def signal_result_and_exit( sock, error_message = '' ):
            if len( sys.argv ) > 1:
                port = int( sys.argv[1] )
                sock.sendto(error_message, ("localhost", port))
            else:
                sys.stderr.write(error_message)
            sys.exit( len( error_message ) )

        try:
            sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )    
            if ctypes.windll.shell32.IsUserAnAdmin():
                try:
                    make_portable_gpg()
                    result = ''
                except:
                    result = traceback.format_exc()
            else:
                result = ellevate_and_wait( sock, 14 )

            signal_result_and_exit( sock, result )

        finally:
            sock.close()
        ''')

    def escape( value ):
        return value.replace( '\\', '\\\\' )

    os.mkdir( dep_path )

    with TemporaryScope() as scope:
        tmp_path = scope.named_dir()
        uninstaller = os.path.join(tmp_path, "gpg4win-uninstall.exe")
        mkportable = os.path.join(tmp_path, "bin\\mkportable.exe")
        
        script_vars = { 'installer_path': escape( gpg_installer ),
                        'uninstaller_path': escape( uninstaller ),
                        'mkportable_path': escape( mkportable ),
                        'build': escape( dep_path ),
                        'target': escape( tmp_path ) }
        
        with scope.named_file() as ini_file:
            ini_file.writelines( gpg_ini )
            script_vars[ 'config' ] = escape( ini_file.name )

        with scope.named_file() as build_script:
            build_script.write( build_template.format( **script_vars ) )
            #print build_template.format( **script_vars )
            script_path = build_script.name

        build.invoke( 'python', script_path )
                                                    
    return dep_path

@Build.provide( 'git', 'signtool' )
def provide_from_env( build, keyword, dep_path ):
    try:
        exe_path = build.config( keyword )
    except KeyError:
        build.log.warning( "No explicit path configured for '{}', assuming on PATH".format( keyword ) )
        exe_path = keyword

    build.publish( keyword, exe_path )
    return None

@Build.default_config( 'mailpile' )
def config_mailpile( keyword ):
    build.depend( 'git' )
    
    scriptdir = os.path.dirname( __file__ )
    with pushdir( os.path.dirname( __file__ ) ):
        commit = build.invoke('git','rev-parse','HEAD').strip()

    search_path = os.path.dirname( os.path.abspath( __file__ ) )

    while True:
        if '.git' in os.listdir( search_path ):
            repo = 'file:///' + search_path
            break

        parts = os.path.split( search_path )
        if search_path == parts[0]:
            repo = 'https://github.com/AlexanderHaase/Mailpile'
            break

        search_path = parts[ 0 ]

    return { 'commit': commit, 'repo': repo }

@Build.default_config( 'gui-o-matic' )
def config_gui_o_matic( keyword ):
    return { 'commit': 'winapi',
               'repo': 'https://github.com/AlexanderHaase/gui-o-matic' }
    

@Build.provide( 'mailpile', 'gui-o-matic' )
def provide_checkout( build, keyword, dep_path ):
    build.depend( 'git' )
    config = build.config( keyword )    

    with tempdir() as git_dir:
        build.invoke( 'git', 'clone', config['repo'], dep_path )
        with pushdir( dep_path ):
            build.invoke( 'git', 'checkout', config['commit'] )
            build.invoke( 'git', 'submodule', 'update', '--init', '--recursive' )
            rmtree_log_error( '.git' )
            
    return dep_path

@Build.provide( 'sign-tree' )
def provide_sign_tree( build, keyword, dep_path ):
    try:
        key = build.config( 'sign-key' )

        #TODO: publish a recursive scanner.

    except KeyError:
        build.log.warning( 'No signing key configured--outputs will not be signed' )

        def sign_tree( path ):
            build.log.info( "ignoring request to sign tree '{}'".format( path ) )

    build.publish( keyword, sign_tree )

    return None

import package
import json
import copy

def format_pod( template, **kwargs ):
    '''
    apply str.format to all str elements of a simple object tree template
    '''
    if isinstance( template, dict ):
        template = { format_pod( key, **kwargs ): format_pod( value, **kwargs ) for (key,value) in template.items() }
    elif isinstance( template, str ) or isinstance( template, unicode ):
        template = template.format( **kwargs )
    elif isinstance( template, list ):
        template = [ format_pod( value, **kwargs ) for value in template ]
    elif callable( template ):
        template = format_pod( template(), **kwargs )
    else:
        # Maybe raise an error instead?
        #
        template = copy.copy( template )
        
    return template

@Build.default_config( 'package_template', 'package_uuid_db' )
def config_package_jsons( keyword ):
    base = os.path.abspath( os.path.dirname( __file__ ) )
    return os.path.join( base , keyword + '.json' )

@Build.provide( 'package' )
def provide_msi( build, keyword, dep_path ):
    content_keys = ('tor',
                    'mailpile',
                    'gui-o-matic',
                    'python27',
                    'gpg')

    if not os.path.exists( dep_path ):
        os.mkdir( dep_path )

    content_paths = { key: build.depend( key ) for key in content_keys }

    tool_keys = ('wix',
                 'sign-tree')

    tool_paths = { key: build.depend( key ) for key in tool_keys }

    for path in content_paths:
        build.invoke( 'sign-tree', path )

    with open( build.config( 'package_template' ), 'r' ) as handle:
        package_template = json.load( handle )
        package_config = format_pod( package_template, **content_paths )

    with open( os.path.join( dep_path, 'mailpile.package.json' ), 'w' ) as handle:
        json.dump( package_config, handle, indent = 2 )

    uuid_db_path = build.config( 'package_uuid_db' )

    if not os.path.exists( uuid_db_path ):
        build.log.warning( "Creating new uuid database '{}'".format( uuid_db_path ))
        with open( uuid_db_path, 'w' ) as handle:
            json.dump( {}, handle )

    wix = package.WixConfig( package_config, uuid_db_path )

    # TODO: Split uuid and wix config saving
    wix_config_path = os.path.join( dep_path, 'mailpile' )
    wix.save( wix_config_path )

    build.invoke( 'candle', wix_config_path + '.wxs',
                  '-out', os.path.join( dep_path, 'mailpile.wixobj' ))
    build.invoke( 'light',
                  '-ext', 'WixUIExtension',
                  '-ext', 'WixUtilExtension',
                  wix_config_path + '.wixobj',
                  '-out', os.path.join( dep_path, 'mailpile.msi' ))
    return dep_path

if __name__ == '__main__':
    import cache
    import time
    logging.basicConfig()
    logger.setLevel( logging.DEBUG )
    
    resources = cache.SemanticCache.load( 'resources.json' )
    with Build( resources ) as build:
        build.depend( 'package' )
        shutil.copytree( build.root(), 'package' )
