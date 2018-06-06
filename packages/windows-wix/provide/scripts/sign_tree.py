import os
import os.path

def is_signable(path):
    '''
    Check if a file is in the PE format by looking for the 'MZ' magic.
    '''
    try:
        # FIXME--not the correct check...
        with open(path, 'rb') as handle:
            magic = handle.read(2)
            if magic == "\x7F\x45":
                return True
    except IOError:
        pass

    recognized_formats = ('.msi', '.exe', '.dll', '.pyd')
    return any( map( path.endswith, recognized_formats) )

def bind(build):
    @build.default_config('timestamp_server')
    def config_signing_timestamp_server(keyword):
        '''
        Time server for signing execubles
        '''
        return 'http://timestamp.digicert.com'

    build.define_config('signing_key',
                        'Key for signing PE files (pkcs12 format).')
    build.define_config('signing_passwd',
                        'Password for signing key.')
    
    @build.provide('sign_tree')
    def provide_sign_tree(build, keyword):
        '''
        Provide tool to sign all executables in the specified build path
        '''
        build.depend('signtool')
        try:
            key = os.path.abspath(build.config('signing_key'))
            build.log().debug('Using signing key {}'.format(key))
            password = build.config('signing_passwd')

            def sign_file(path):
                '''
                Sign a single file, if it's in PE format
                '''
                if is_signable(path):
                    build.log().info("Signing '{}'".format(path))
                    build.invoke('signtool', 'sign',
                                 '/f', key,
                                 '/p', password,
                                 '/tr', build.config('timestamp_server'),
                                 '/td', 'sha512',
                                 '/fd', 'sha512',
                                 path)

            # TODO: publish a recursive scanner.
            def sign_tree(path):
                '''
                Sign all detected PE files in the specified path
                '''
                build.log().debug("Scanning '{}' for signable files...".format(path))
                assert(os.path.exists(path))
                for root, dirs, files in os.walk(path):
                    for name in files:
                        path = os.path.join(root,name)
                        sign_file(path)
                        
        except KeyError:
            build.log().warning('No signing key configured--outputs will not be signed')

            def sign_tree(path):
                '''
                Stub to support debug/test unsigned builds.
                '''
                build.log().warn("Ignoring request to sign tree '{}'".format(path))

        build.publish(keyword, sign_tree)

        return None
