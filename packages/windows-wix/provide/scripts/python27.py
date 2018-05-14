import os.path
import glob

def bind( build ):

    @build.provide( 'python27' )
    def provide_python27( build, keyword ):
        '''
        provide python27 prepared for mailpile
        '''

        build.depend('root')
        dep_path = build.invoke('path', keyword)
        
        extractor = build.depend( 'extract_msi' )
        extractor( build.cache().resource( keyword ), dep_path )

        util = build.depend( 'util' )
        util.publish_exes( build, dep_path )

        # TODO: Prune unwanted files--either via features or manual delete.

        # Manually bootstrap pip.
        # https://stackoverflow.com/questions/36132350/install-python-wheel-file-without-using-pip
        #
        build.log().debug( 'Bootstrapping pip from bundled wheels' )
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
