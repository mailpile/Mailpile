"""
This script sets up a mailpile-compatible environment, then executes the
specified command. It localizes the majority of bootstrapping into python,
so that top-level entry points (like start menu items) only need to know
about python and this script.

Example: path\\to\\python with-mailpile-env.py mailpile-gui.py
"""

import os
import sys
import subprocess
import argparse
from functools import reduce

locate = (("Mailpile", "mailpile"),
          ("gpg", "bin", "gpg.exe"),
          ("gpg", "bin", "gpg-agent.exe"),
          ("Mailpile", "submodules", "gui-o-matic", "gui_o_matic"),
          ("tor", "Tor", "tor.exe"),
          ("openssl", "openssl.exe"))

def locate_parent( path_parts ):

    if len( path_parts ) > 1:
        path = reduce( os.path.join, path_parts )
    else:
        path = path_parts[ 0 ]
    directory = os.path.abspath( __file__ )
    while True:
        test_path = os.path.join( directory, path )
        if os.path.exists( test_path ):
            return os.path.split( test_path )[ 0 ]
        
        parent = os.path.split( directory )[0]
        if parent == directory:
            raise ValueError( "Cannot locate '{}'".format( path ) )
        else:
            directory = parent

def split_args( args = sys.argv[1:] ):
    '''
    Split arguments into options and remainder at first non-option argument
    '''
    opts = []
    
    for arg in args:
        if arg.startswith('-'):
            opts.append( arg )
        else:
            break
        
    invoke = args[ len(opts): ]
    return (opts, invoke)

if __name__ == '__main__':
    path_additions = set( map( locate_parent, locate ) )
    python_dir = os.path.abspath( os.path.split( sys.executable )[0] )
    path_additions.add( python_dir )
    for key in ("PATH", "PYTHONPATH" ):
        try:
            paths = list( path_additions )
            paths.extend( filter( lambda path: path not in path_additions,
                                  os.environ[ key ].split( ';' ) ) )
            os.environ[ key ] = ';'.join( paths )
        except KeyError:
            os.environ[ key ] = ';'.join( path_additions )

    parser = argparse.ArgumentParser(description="Invokes a command with environment variables setup for mailpile")
    parser.add_argument( '--stdin', type = str,
                         help= "Redirect stdin from file" )
    parser.add_argument( '--stdout', type = str,
                         help = "Redirect stdout to file" )
    parser.add_argument( '--stderr', type = str,
                         help = "Redirect stderr to file" )

    parser.add_argument( '-q', '--quiet',
                         action = 'store_true',
                         help = "Redirect stdin, stdout, stderr to devnull unless otherwise specified" )

    if len(sys.argv) <= 1:
        parser.print_usage()
        exit( -1 )
        
    opts, invoke = split_args()
    args = parser.parse_args(opts)

    redirects = {}

    for (key, mode) in (('stdin','r'), ('stdout','w'), ('stderr','w')):
        path = getattr( args, key )
        if path:
            redirects[ key ] = open( path, mode )
        elif args.quiet:
            redirects[ key ] = open( os.devnull, mode )

    if invoke[0].endswith( '.py' ):
        invoke = [ sys.executable ] + invoke
        
    try:
        subprocess.check_call( invoke, shell = True, **redirects )
    finally:
        for handle in redirects.values():
            handle.close()
