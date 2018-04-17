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

locate = ( ("Mailpile","mailpile"),
           ("Mailpile","bin","gpg.exe"),
           ("gui-o-matic","gui_o_matic"))

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

if __name__ == '__main__':
    path_additions = list( map( locate_parent, locate ) )
    python_dir = os.path.abspath( os.path.split( sys.executable )[0] )
    path_additions.append( python_dir )
    path_additions = ';'.join( path_additions )
    for key in ("PATH", "PYTHONPATH" ):
        try:
            os.environ[ key ] = path_additions + ';'  + os.environ[ key ]
        except KeyError:
            os.environ[ key ] = path_additions

    if sys.argv[1].endswith( '.py' ):
        args = [ sys.executable ]
        args.extend( sys.argv[1:] )
    else:
        args = sys.argv[1:]
    subprocess.check_call( args, shell = True )
