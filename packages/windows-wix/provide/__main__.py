import os
import os.path
import time
import argparse
import datetime
import json
import logging
import logging.handlers

logger = logging.getLogger( __name__ )
logging.basicConfig()

if 'DEBUG' in os.environ:
    logging.getLogger().setLevel( logging.DEBUG )
    
import cache
import default

package_dir = os.path.dirname( __file__ )
default_resources = os.path.join( package_dir, '..\\resources.json' )    
resources = cache.SemanticCache.load( default_resources )

config = {'export': {'package': '..\\package'} }

parser = argparse.ArgumentParser()
default_log = datetime.datetime.utcnow().strftime( 'provide-%Y%m%d-%H%M%S.log' )
parser.add_argument( '-l', '--log_file', default = default_log, help="Log file, default build-<isotime>.log")
parser.add_argument( '-v', '--log_level', default = 'DEBUG', help="Log level" )
parser.add_argument( '-i', '--input', help='input config file')

default.build.parser( parser )
args = parser.parse_args()
config = default.build.parse_config( args )

if args.input:
    with open( args.input, 'r' ) as handle:
        config.update( json.load( handle ) )

if args.log_file:
    handler = logging.FileHandler( args.log_file )
    logging.getLogger().addHandler(handler)

if args.log_level:
    logging.getLogger().setLevel(getattr(logging, args.log_level))

logger.debug( "Using configuration: {}".format( config )) 
with default.build.context( resources, config ) as build:
    build.depend( 'export' )
