import os.path

def bind( build ):    

    @build.default_config( 'mailpile', 'gui-o-matic' )
    def config_gui_o_matic( keyword ):
        return { 'commit': {'gui-o-matic':'winapi', 'mailpile':'windows-packaging'}[keyword],
                   'repo': 'https://github.com/AlexanderHaase/{}'.format(keyword) }

    @build.provide( 'mailpile', 'gui-o-matic' )
    def provide_checkout( build, keyword ):
        build.depend( 'git' )
        build.depend( 'root' )
        dep_path = build.invoke( 'path', keyword )
        util = build.depend( 'util' )
        config = build.config( keyword )

        build.invoke( 'git', 'clone', config['repo'], dep_path, '--recursive' )
        with util.pushdir( dep_path ):
            build.invoke( 'git', 'checkout', config['commit'] )
            #build.invoke( 'git', 'submodule', 'update', '--init', '--recursive' )
            util.rmtree( '.git' )
                
        return dep_path
