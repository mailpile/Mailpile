import sys
import os.path

# Hack to import somewhat relatively
#
lib_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert( 0, lib_dir )
import package
sys.path.pop( 0 )

import json
import copy

try:
    check = unicode
except NameError:
    unicode = str

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

def bind( build ):
    
    @build.default_config( 'package_template', 'package_uuid_db' )
    def config_package_jsons( keyword ):
        return os.path.join( lib_dir, keyword + '.json' )

    @build.provide( 'package' )
    def provide_msi( build, keyword ):

        build.depend( 'root' )
        dep_path = build.invoke( 'path', keyword )

        if not os.path.exists( dep_path ):
            os.mkdir( dep_path )
            
        content_keys = ('tor',
                        'mailpile',
                        'gui-o-matic',
                        'python27',
                        'gpg')

        content_paths = { key: build.depend( key ) for key in content_keys }

        tool_keys = ('wix',
                     'sign_tree')

        tool_paths = { key: build.depend( key ) for key in tool_keys }

        for path in content_paths:
            build.invoke( 'sign_tree', path )

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
