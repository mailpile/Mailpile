
def bind( build ):
    
    @build.provide( 'git', 'signtool' )
    def provide_from_env( build, keyword ):
        try:
            exe_path = build.config( keyword )
        except KeyError:
            build.log().warning( "No explicit path configured for '{}', assuming on PATH".format( keyword ) )
            exe_path = keyword

        build.publish( keyword, exe_path )
        return None
