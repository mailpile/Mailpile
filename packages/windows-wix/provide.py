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
    def log_error( func, path, exec_info ):
        logger.error("Unable perform action {}: {} {}".format( msi_path, func, path ),
                      exec_info = exec_info )
    shutil.rmtree( path, ignore_errors = True, onerror = log_error )     

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

@contextlib.contextmanager
def EditableTemporaryFile( **kwargs ):
    '''
    Like named temporary file, but has a context for editing so that other
    apps can use it
    
    https://stackoverflow.com/questions/5344287/create-read-from-tempfile/5344603#5344603
    '''
    kwargs['delete'] = False
    with tempfile.NamedTemporaryFile( **kwargs ) as handle:
            name = handle.name

    @contextlib.contextmanager
    def reopen( mode ):
        with open( name, mode ) as handle:
            yield handle

    reopen.name = name

    try:
        yield reopen
    finally:
        os.unlink( name )
        
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
            with tempfile.TemporaryFile( 'a+' ) as error_file:
                try:
                    return self.method( cmdline, stderr = error_file )
                except subprocess.CalledProcessError as e:
                    error_file.seek( 0 )
                    error_text = error_file.read()
                    print "ERROR" + error_text
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
            return self.cmds[ keyword ]( *args )
            
        def clear( self ):
            logger.info('Removing build context at {}'.format(self.build_dir))
            rmtree_log_error( self.build_dir )

        def config( self, keyword ):
            try:
                result = self.build.config[ keyword ]
            except KeyError:
                result = self.build._defconfig[ keyword ]( keyword )
                logger.info( "Using default {} config '{}'".format( keyword, result ) )
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
    logger.debug( 'Bootstrapping pip from bundled wheels' )
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

@Build.provide( 'gpg' )
def provide_gpg( build, keyword, dep_path ):
    build.depend( 'python27' )
    gpg_installer = build.cache().resource( 'gpg' )

    gpg_ini = [ '''[gpg4win]''',
        '''  inst_gpgol = false''',
        '''  inst_gpgex = false''',
        '''  inst_kleopatra = false''',
        '''  inst_gpa = false''',
        '''  inst_claws_mail = false''',
        '''  inst_compendium = false''',
        '''  inst_start_menu = false''',
        '''  inst_desktop = false''',
        '''  inst_quick_launch_bar = false''' ]

    # Use the built python to elevate if needed
    # https://stackoverflow.com/questions/130763/request-uac-elevation-from-within-a-python-script
    install_template = ('#!/usr/bin/python\n'
                        'import sys\n'
                        'import ctypes\n'
                        'import subprocess\n'
                        'if not ctypes.windll.shell32.IsUserAnAdmin():\n'
                        '    ShellExecuteW = ctypes.windll.shell32.ShellExecuteW\n'
                        '    status = ShellExecuteW(None,\n'
                        '                           "runas",\n'
                        '                           sys.executable,\n'
                        '                           __file__,\n'
                        '                           None,\n'
                        '                           1)\n'
                        '    exit( status )\n'
                        '\n'
                        'install_cmd = ("{installer_path}", "/S",\n'
                        '               "/C={config}",\n'
                        '               "/D={target}")\n'
                        'uninstall_cmd = ("{uninstaller_path}",)\n'
                        'subprocess.check_call( install_cmd )\n'
                        'subprocess.check_call( uninstall_cmd )\n')

    install_template = '''
#!/usr/bin/python
import sys
import ctypes
import subprocess
import time
import os.path
import win32com.shell.shell as shell
import win32com.shell.shellcon as shellcon
import win32event
import win32process
import win32api
import win32con
import socket

address = ("localhost", 54321)
sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )

try:
    if not ctypes.windll.shell32.IsUserAnAdmin():
        sock.settimeout( 720 )
        sock.bind( address )
        parameters = '"{{}}" {{}}'.format( os.path.abspath( __file__ ), address[0] )
        result = shell.ShellExecuteEx(fMask = shellcon.SEE_MASK_NOCLOSEPROCESS,
                                      lpVerb = "runas",
                                      lpFile = sys.executable,
                                      lpParameters = parameters,
                                      nShow = win32con.SW_SHOW )

        handle = result['hProcess']
        print handle
        status = win32event.WaitForSingleObject(handle, -1)
        print status
        win32api.CloseHandle( handle )
        msg = sock.recv( 4096 )
        sock.close()
        sys.stderr.write( msg )
        if len( msg ):
            sys.exit( -1 )
    else:
        try:
            install_cmd = ("{installer_path}", "/S",
                           "/C={config}",
                           "/D={target}")
            uninstall_cmd = ("{uninstaller_path}", "/S")
            portable_cmd = ("{mkportable_path}", "{build}")
            subprocess.check_call( install_cmd )
            subprocess.check_call( portable_cmd )
            subprocess.check_call( uninstall_cmd )
            if len( sys.argv ) > 1:
                sock.sendto( '', address )
        except:
            if len( sys.argv ) > 1:
                import traceback
                sock.sendto( traceback.format_exc(), address )
            raise
finally:
    sock.close()
'''

    def escape( value ):
        return value.replace( '\\', '\\\\' )

    os.mkdir( dep_path )
    
    with EditableTemporaryFile() as ini_file:
        with ini_file( 'w' ) as handle:
            handle.writelines( gpg_ini )
            
        with tempdir() as tmp_path:
            uninstaller = os.path.join(tmp_path, "gpg4win-uninstall.exe")
            mkportable = os.path.join(tmp_path, "bin\\mkportable.exe")
            script_vars = { 'installer_path': escape( gpg_installer ),
                            'uninstaller_path': escape( uninstaller ),
                            'config': escape( ini_file.name ),
                            'target': escape( tmp_path ),
                            'mkportable_path': escape(mkportable),
                            'build': escape( dep_path ) }

            with EditableTemporaryFile() as install_script:
                with install_script( 'w' ) as handle:
                    handle.write( install_template.format( **script_vars ) )
                    #print install_template.format( **script_vars )
                build.invoke( 'python', install_script.name )
                                                    
    return dep_path

@Build.provide( 'git', 'signtool' )
def provide_from_env( build, keyword, dep_path ):
    try:
        exe_path = build.config( keyword )
    except KeyError:
        logger.warning( "No explicit path configured for '{}', assuming on PATH".format( keyword ) )
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
    return { 'commit': 'master',
               'repo': 'https://github.com/AlexanderHaase/gui-o-matic' }
    


@Build.provide( 'mailpile', 'gui-o-matic' )
def provide_checkout( build, keyword, dep_path ):
    build.depend( 'git' )
    config = build.config( keyword )    

    with tempdir() as git_dir:
        build.invoke( 'git', 'clone', config['repo'], dep_path )
        with pushdir( dep_path ):
            build.invoke( 'git', 'checkout', config['commit'] )
            rmtree_log_error( '.git' )
            
    return dep_path

if __name__ == '__main__':
    import cache
    import time
    logging.basicConfig()
    logger.setLevel( logging.DEBUG )
    
    resources = cache.SemanticCache.load( 'resources.json' )
    with Build( resources ) as build:
        build.depend( 'tor' )
        build.depend( 'python27' )
        print build.depend( 'gpg' )
        time.sleep( 30 )
    
