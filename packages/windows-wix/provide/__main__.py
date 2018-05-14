import logging

logger = logging.getLogger( __name__ )

logging.basicConfig()
logging.getLogger().setLevel( logging.DEBUG )

import cache
import os.path
import default
import time

package_dir = os.path.dirname( __file__ )
default_resources = os.path.join( package_dir, '..\\resources.json' )    
resources = cache.SemanticCache.load( default_resources )

config = {'export': {'package': '..\\package'} }

with default.build.context( resources, config ) as build:
    build.depend( 'export' )
