
def bind( build ):

    @build.default_config( 'git', 'signtool' )
    def default_config_env( keyword ):
        return keyword + '.exe'
    
    @build.provide( 'git', 'signtool' )
    def provide_from_env( build, keyword ):
        exe_path = build.config( keyword )
        
        build.publish( keyword, exe_path )
        return None
