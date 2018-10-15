"""
Packaging script for capturing a portable mailpile into an msi.

Assumes use of the wix install system--generates XML to configure the process.

Components:
    - Python
        - (potentially separate downloaded pages at a later date)
    - Mailpile
    - gui-o-matic (likely bunded as site package)
    - gpg + deps
    - openssl + deps

Each component needs a consistant UUID for update purposes
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import os.path
import shutil
import collections
import itertools
import sys
import json
import re
import uuid
import hashlib
import functools

import logging
import logging.handlers

import argparse
import subprocess

logger = logging.getLogger( __name__ )

def consume(iterator, n=None):
    "Advance the iterator n-steps ahead. If n is None, consume entirely."
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(islice(iterator, n, n), None)


def xml_attrs( xml_element, **attrs ):
    consume( itertools.starmap( xml_element.set, attrs.items() ) )

def xml_append( xml_parent, xml_element_type, **attrs ):
    result = ET.SubElement( xml_parent, xml_element_type )
    xml_attrs( result, **attrs )
    return result

class WixConfig( object ):
    '''
    A mailpile-specific wix file generator.

    Takes config that one might expect to modify centrally or express as
    arguments to the packaging process, and uses them to expand a template
    structure.

    Note: UUIDs ***MUST*** remain consistent across versions. While rarely they
    might change, assume anywhere a UUID is required, it must be archived.
    '''

    def __init__( self, config ):
        self.config = config
        self.dirs = {}
        self.logical = {}
                
        self.root = ET.Element( 'Wix' )
        self.root.set( 'xmlns', 'http://schemas.microsoft.com/wix/2006/wi' )
        
        self.product = ET.SubElement( self.root, 'Product' )
        xml_attrs( self.product,
                   Name = 'Mailpile Email Client {version}'.format( **self.config ),
                   Language = config['languages'],
                   Codepage = config['codepage'],
                   Version = config['version'],
                   Manufacturer = config['manufacturer'],
                   Id = config['product_id'],
                   UpgradeCode = config['product_code'] )

        xml_append(self.product, 'Package',
                   Id = '*',
                   Keywords = 'Installer',
                   Description = 'Mailpile {version} Installer'.format(**self.config),
                   Comments = 'Mailpile is under the AGPL license',
                   Manufacturer = config['manufacturer'],
                   InstallerVersion = config['installer_version'],
                   Languages = config['languages'],
                   Compressed = 'yes',
                   SummaryCodepage = config['codepage'] )

        xml_append(self.product, 'Media',
                   Id = '1',
                   Cabinet = 'mailpile.cab',
                   EmbedCab = 'yes',
                   DiskPrompt='CD-ROM #1')

        xml_append(self.product, 'Property',
                   Id = 'DiskPrompt',
                   Value = 'Mailpile {version} Media [1]'.format( **self.config ))

        xml_append(self.product, 'MajorUpgrade',
                   AllowDowngrades = 'no',
                   DowngradeErrorMessage = "Downgrades not supported!",
                   AllowSameVersionUpgrades = 'no')
                   
        self.logical_root( Id = 'TARGETDIR',
                           Name = 'SourceDir' )
        
        self.feature = ET.SubElement( self.product, 'Feature' )
        xml_attrs( self.feature,
                   Id = 'Complete',
                   Title = 'Mailpile {version}'.format( **self.config ),
                   Description = 'Complete Mailpile Install' )

        # Setup: <location>/<manufacturer>/<product>
        #
        self.logical_node( 'TARGETDIR',
                           Id = 'ProgramFilesFolder', # windows token
                           Name = 'ProgramFiles' )

        self.logical_node( 'ProgramFilesFolder',
                           Id = 'APPLICATIONFOLDER',
                           Name = 'Mailpile ehf' )

        self.logical_node( 'APPLICATIONFOLDER',
                           Id = 'MailpileClient',
                           Name = 'Mailpile Client {version}'.format( **self.config ) )

        # Setup: Menu item directory
        #
        self.logical_node( 'TARGETDIR',
                           Id = 'ProgramMenuFolder' )

        self.logical_node( 'ProgramMenuFolder',
                           Id = 'ProgramMenuDir',
                           Name = 'Mailpile {version}'.format( **self.config ) )

        self.menu_component = xml_append( self.logical['ProgramMenuDir'],
                                          'Component',
                                     Id = 'ProgramMenuDir',
                                     Guid = self.uuid( '\\windows\\ProgramMenuDir' ))

        menu_reg_key = xml_append( self.menu_component, 'RegistryValue',
                                   Root = 'HKCU',
                                   Key = 'Software\\[Manufacturer]\\[ProductName]\\StartMenuShortcut',
                                   Type = 'string',
                                   Value = '1',
                                   KeyPath = 'yes' )

        menu_cleanup = xml_append( self.menu_component, 'RemoveFolder',
                                   Id = 'ProgramMenuDir',
                                   On = 'uninstall' )


        xml_append( self.feature, 'ComponentRef',
                    Id = 'ProgramMenuDir' )

        # Setup: Desktop shortcut directory
        #
        self.logical_node( 'TARGETDIR',
                           Id = 'DesktopFolder' )

        self.desktop_component = xml_append( self.logical['DesktopFolder' ],
                                             'Component',
                                             Id = 'DesktopFolderDir',
                                             Guid = self.uuid( '\\windows\\DesktopFolder' ))

        desktop_reg_key = xml_append( self.desktop_component, 'RegistryValue',
                                   Root = 'HKCU',
                                   Key = 'Software\\[Manufacturer]\\[ProductName]\\DesktopShortcut',
                                   Type = 'string',
                                   Value = '1',
                                   KeyPath = 'yes' )

        desktop_cleanup = xml_append( self.desktop_component, 'RemoveFolder',
                                   Id = 'DesktopFolderDir',
                                   On = 'uninstall' )

        xml_append( self.feature, 'ComponentRef',
                    Id = 'DesktopFolderDir' )

        # Setup: unpack groups
        #
        for key, group in self.config['groups'].items():
            self.scan_group( key, **group )

        try:
            self.config_ui( **self.config['ui'] )
        except KeyError:
            logger.warn( "No UI specified, configuring MSI without dialogs." )

        for icon in self.config.get( 'icons', [] ):
            xml_append( self.product, "Icon",
                        Id = os.path.basename( icon ),
                        SourceFile = icon )

        try:
            xml_append( self.product, 'Property',
                        Id = 'ARPPRODUCTICON',
                        Value = self.config['product_icon'] )
        except KeyError:
            raise

    def post_install( self ):
        '''
        post_install actions
        '''
        

    # These properties align folder relocation behavior with implicit structure
    #
    flavor_properties = {
        'WixUI_InstallDir': {
            'WIXUI_INSTALLDIR': 'APPLICATIONFOLDER'
        },
        'WixUI_Advanced': {
            'ApplicationFolderName': 'Mailpile ehf',
            'WixAppFolder': 'WixPerMachineFolder'
        }
    }

    def config_ui( self, flavor = 'WixUI_Advanced', variables = {} ):
        '''
        configure wix UI
        '''
        logger.info( "Configuring UI flavor '{}'".format( flavor ) )
        ui = xml_append( self.product, 'UI' )
        xml_append( ui, 'UIRef', Id = flavor )
        xml_append( ui, 'UIRef', Id = 'WixUI_ErrorProgressText' )

        if flavor not in self.flavor_properties:
            logger.warn( "Unrecognized wix UI type: {}".format( flavor ) )

        for key, value in self.flavor_properties.get( flavor, {} ).items():
            xml_append( self.product, 'Property',
                        Id = key,
                        Value = value )

        for key, value in variables.items():
            xml_append( self.product, 'WixVariable',
                        Id = key,
                        Value = value )
        
        node = xml_append( ui, 'Publish',
                           Dialog = 'WelcomeDlg',
                           Control = 'Next',
                           Event = 'NewDialog',
                           Value = 'InstallDirDlg',
                           Order = '2' )
        node.text = "1"
        node = xml_append( ui, 'Publish',
                           Dialog = 'InstallDirDlg',
                           Control = 'Back',
                           Event = 'NewDialog',
                           Value = 'WelcomeDlg',
                           Order = '2' )
        node.text = "1"

        # Launch mailpile on exit.
        #
        xml_append( self.product, 'Property',
                    Id = 'WixShellExecTarget',
                    Value = '[#{}]'.format( self.file_id( 'bin\\launch-mailpile.bat' ) ) )

        xml_append( self.product, 'CustomAction',
                    Id = 'LaunchApplication',
                    BinaryKey = 'WixCA',
                    DllEntry = 'WixShellExec',
                    Impersonate = 'yes' )

        node = xml_append( ui, 'Publish',
                           Dialog = 'ExitDialog',
                           Control = 'Finish',
                           Event = 'DoAction',
                           Value = 'LaunchApplication' )

        node.text = 'NOT Installed'

        # Kill GPG Agent if this MSI is installed.
        #
        xml_append( self.product, 'SetProperty',
                    Id = 'WixQuietExecCmdLine',
                    Sequence = 'execute',
                    Before = 'GPGAgent.TaskKill',
                    Value = '"[WindowsFolder]\\System32\\taskkill.exe" /F /IM gpg-agent.exe' )

        '''
        xml_append( self.product, 'Property',
                    Id = 'WixQuietExecCmdLine',
                    Value = '"[WindowsFolder]\\System32\\taskkill.exe" /F /IM gpg-agent.exe' )
        '''
        
        xml_append( self.product, 'CustomAction',
                    Id = 'GPGAgent.TaskKill',
                    BinaryKey = 'WixCA',
                    DllEntry = 'WixQuietExec',
                    Execute = 'immediate',
                    Return = 'ignore',
                    Impersonate = 'yes' )

        installSeq = xml_append( self.product, 'InstallExecuteSequence' )
        node = xml_append( installSeq, 'Custom',
                           Action = 'GPGAgent.TaskKill',
                           Before = 'InstallValidate' )

        node.text = 'Installed'

    def logical_node( self, parent_id, **attrs ):
        '''
        Append a logical directory to the specified parent
        '''
        self.logical[ attrs['Id'] ] = xml_append( self.logical[ parent_id ],
                                                  'Directory',
                                                  **attrs )

    def logical_root( self, **attrs ):
        '''
        Create a new top level logical object
        '''
        self.logical[ attrs['Id'] ] = xml_append( self.product,
                                                  'Directory',
                                                  **attrs )

    def uuid( self, path, local_path = None ):
        '''
        get or create an appropriate uuid for the specified path.

        Use UUIDv5 to create namespace/sha1 based uuids(see uuid RFC for
        background about UUID v5). Namespaces are organized as follows:

            product_id -> path -> binary contents of file

        The first is easy:

            root_namespace = self.config['product_id']
            path_namespace = uuid.uuid5(root_namespace, path)

        Sadly, uuid.uuid5() doesn't support generators, so we cannot write:

            with open(localpath, 'rb') as handle:
                guid = uuid.uuid5(path_namespace, handle)

        Instead, we do the work ourselves:
        
            with open(localpath, 'rb') as handle:
                digest = hashlib.sha1()
                digest.update(path_namespace.bytes)
                generator = functools.partial(handle.read, 4096)
                        
                for chunk in iter(generator, b''):
                    digest.update(chunk)

                guid = uuid.UUID(bytes = digest.digest()[:16], version = 5)

        Where the last line overwrites the appropriate uuid version bits.

        :path: path for uuid lookup
        :local path: file to digest.
        '''

        root_namespace = uuid.UUID(self.config['product_id'])
        path_namespace = uuid.uuid5(root_namespace, path.encode())

        if local_path:
            with open(local_path, 'rb') as handle:
                digest = hashlib.sha1()
                digest.update(path_namespace.bytes)
                generator = functools.partial(handle.read, 4096)

                for chunk in iter(generator, b''):
                    digest.update(chunk)

                guid = uuid.UUID(bytes = digest.digest()[:16], version = 5)
        else:
            guid = path_namespace


        logger.debug("Using guid {} for path '{}'".format(guid, path))
        return str(guid)

    def directory( self, path ):
        '''
        Get the xml element for the specified directory
        
        :path: directory path to lookup
        '''
        stack = []
        while True:
            try:
                parent = self.dirs[ path ]
                break
            except KeyError:
                parts = os.path.split( path )
                if parts[0] == path:
                    parent = self.logical['MailpileClient']
                    break
                else:
                    path = parts[ 0 ]
                    stack.append( parts[ 1 ] )

        for part in reversed( stack ):
            path = os.path.join( path, part )
            parent = xml_append( parent, 'Directory',
                                Id = self.directory_id( path ),
                                Name = part )
            self.dirs[ path ] = parent

        return parent

    def id_str( self, use, name ):
        '''
        Generate a unique ID string less than 72 characters long.
        IDs must start with [a-zA-z_], and may contain dot '.'.

        :use: context that allows names to be used for multiple elements.
        :name: element identifier to mangle.
        '''
        #attempt = use + '_' + re.sub( '([-\W])', '_', name )
        #size = len( attempt )
        #if size > 72:
        #    attempt = use + '_' + hashlib.sha1( name ).hexdigest()
        return use + '_' + hashlib.sha1( name.encode() ).hexdigest()

    def directory_id( self, path ):
        return self.id_str( 'Directory', path )

    def component_id( self, name ):
        return self.id_str( 'Component', name )
    
    def file_id( self, name ):
        return self.id_str( 'File', name )

    def mask_path( self, mask, path ):
        '''
        Mask off the local part of a path
        '''
        return path[ len(mask) + 1: ]

    def scan_group( self, name, uuid, root, ignore = [], shortcuts = {} ):
        '''
        Scan an install root, adding files and generating uuids.

        The specified root directory and it's contents are moved into the
        install program files directory:

        %ProgramFiles%/<Manufacturer>/<Product>/<root>

        :name: name of this group
        :uuid: uuid for this group
        :root: local filesystem root directory
        :ignore: sequence of regular expressions to suppress files.
        '''
        logger.info( "Scanning install root '{}' uuid '{}'".format( name, uuid ) )
        mask = os.path.split( root )[0]
        
        def ignore_path( path ):
            for expr in ignore:
                if re.match( expr, path ):
                    return True
            return False

        for parent, dirs, files in os.walk( root ):
            for filename in files:
                local_path = os.path.join( parent, filename )
                path = self.mask_path( mask, local_path )
                
                if ignore_path( path ):
                    logger.debug( 'Ignoring "{}"'.format( path ) )
                    continue
                else:
                    logger.debug( 'Processing file "{}"'.format( path ) )


                parent_dir = self.directory( self.mask_path( mask, parent ) )                
                component_id = self.component_id( path )
                component = xml_append( parent_dir, 'Component',
                                Id = component_id,
                                Guid = self.uuid( path, local_path ) )
                
                file = xml_append( component, 'File',
                                   Id = self.file_id( path ),
                                   Name = filename,
                                   DiskId = '1',
                                   Source = local_path,
                                   KeyPath = 'yes' )

                try:
                    shortcut = dict( shortcuts[path] )
                    name = shortcut.pop( 'Id' )
                    xml_append( self.menu_component, 'Shortcut',
                                Target = '[#{}]'.format( self.file_id( path ) ),
                                Id = name + 'MenuItem',
                                **shortcut )

                    xml_append( self.desktop_component, 'Shortcut',
                                Target = '[#{}]'.format( self.file_id( path ) ),
                                Id = name + 'DesktopShortcut',
                                **shortcut )
                                
                    logger.info( "Created shortcut for '{}'".format( path ) )
                except KeyError:
                    pass

                xml_append( self.feature, 'ComponentRef', Id = component_id )
        

    def save( self, path, indent = 2 ):
        dense = ET.tostring( self.root, encoding='utf-8' )
        reparsed = minidom.parseString( dense )
        pretty = reparsed.toprettyxml( indent = ' ' * indent, encoding = 'utf-8' ) 
        with open( path, 'wb' ) as handle:
            handle.write( pretty )


if __name__ == '__main__':
    logging.basicConfig()

    import argparse
    import sys
    basedir = os.path.dirname( sys.argv[ 0 ] )

    parser = argparse.ArgumentParser( "Generates the wix configuration from a"
                                      " high level configuration file. Also"
                                      " provides machinery for consistent uuids" )

    parser.add_argument( '--candle',
                         default = os.path.join( basedir, "tools\\wix311-binaries\\candle.exe {}" ),
                         help = "template for invoking candle, using brace {} notation" )


    parser.add_argument( '--light',
                         default = os.path.join( basedir, "tools\\wix311-binaries\\light.exe -ext WixUIExtension -ext WixUtilExtension {} -cc cache -reusecab" ),
                         help = "template for invoking light, using brace {} notation" )

    parser.add_argument( 'config',
                         help = 'config file to inflate' )


    parser.add_argument( '-l', '--log-level', help = "Logging verbosity" )

    args = parser.parse_args()

    if args.log_level:
        logger.setLevel( getattr( logging, args.log_level ) )
    
    with open( args.config, 'r' ) as handle:
        config = json.load( handle )

    wix = WixConfig( config, 'mailpile.uuid.json' )
    wix.save( 'mailpile' )

    import subprocess
    import shlex
    cmd = shlex.split( args.candle.format( "mailpile.wxs" ).replace( '\\', '\\\\' ) )
    logger.info( "build step '{}'".format( cmd ) )
    subprocess.check_call( cmd )
    cmd = shlex.split( args.light.format( "mailpile.wixobj" ).replace( '\\', '\\\\' ) )
    logger.info( "build step '{}'".format( cmd ) )
    subprocess.check_call( cmd )
    '''candle mailpile.wxs'''
    '''light -ext WixUIExtension mailpile.wixobj'''
