# This code searches a computer for Mailpile pile directories
# and prints a summary of their locations and associated ports.
# 
# Copyright (C) 2018 Jack Dodds
# This code is part of Mailpile and is hereby released under the
# Gnu Affero Public Licence v.3 - see ../../COPYING and ../../AGPLv3.txt.
#

import os
import sys
import getpass
import ConfigParser
import fasteners

import random
from mailpile.commands import *
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.config.base import CommentedEscapedConfigParser

_plugins = PluginManager(builtin=__file__)


def discover_piles(option_list, this_user, this_workdir,
                                only_users = None, only_piles = None):

    # Extracts specified public options from accessible Mailpile configurations.
    # Search restricted to specified user and pile if those arguments present. 

    # Find Mailpile data directory for this user.
    this_workdir_parent = os.path.abspath(this_workdir + '/..')
    mp_data = [this_user, this_workdir_parent]
    parent_list = [mp_data]
    
    # Use full path of this Mailpile's workdir as template
    # to make parent_list - Mailpile data directories of 
    # all users where permissions allow access to the workdirs.
    #   Gnu-Linux permissions for other users to allow access:
    #   mailpile.rc must have r, 
    #   the workdir and all higher level directories must have x, but the
    #   Mailpile data directory - parent of the workdirs - must have rx.
    try:
        index = this_workdir_parent.index(this_user)
        workdir_head = this_workdir_parent[ 0:index ]
        workdir_tail = this_workdir_parent[ index + len(this_user): ]
        for user in os.listdir(workdir_head):
            if user != this_user:
                parent = workdir_head + user + workdir_tail
                if os.path.isdir(parent):
                    parent_list += [[user, parent]]
    except OSError:
        pass
    
    # Loop through accessible Mailpile data directories for all users.
    pile_specs = []
    for parent in parent_list:
        if only_users and not parent[0] in only_users:
            continue
        try:
            workdir_list = os.listdir(parent[1])
        except OSError:
            continue
            
        # Loop through all accessible Mailpile workdirs for one user.
        for pile in workdir_list:
            if only_piles and not pile in only_piles:
                continue
            workdir = os.path.join(parent[1], pile)
            if os.path.isdir(workdir):
                public = CommentedEscapedConfigParser()
                public_file = os.path.join(workdir, 'mailpile.rc')
                
                # If permissions allow, prevent mailpile.rc from being
                # written by its owner while this process reads it.
                lock_pub = fasteners.InterProcessLock(
                                    os.path.join(workdir, 'public-lock'))
                try:
                    lock_pub.have = lock_pub.acquire(blocking=True, 
                                                                timeout=5)
                except IOError:
                    lock_pub.have = False
                
                # Try to read mailpile.rc even if it could not be locked.
                try:
                    public.read(public_file)
                except ConfigParser.Error:
                    pass
                    
                if lock_pub.have:
                   lock_pub.release()
                
                if not public.sections():
                    continue               
                
                # Find all the option values for one pile.
                specs = ()
                for field in option_list:
                    if not field[0]:
                        if field[1] == 'user':
                            specs += (parent[0],)
                        elif field[1] == 'pile':
                            specs += (pile,)
                        else:
                            specs += (' ',)
                        continue
                    for section in public.sections():
                        # Find section name in commented section name.
                        if section.startswith(field[0]):
                            try:
                                value = public.get(section,field[1])
                                if isinstance(field[2],int):
                                    value = int(value)
                                specs += (value,)
                            except (ConfigParser.NoOptionError, ValueError):
                                specs += (field[2],)
                            continue
                pile_specs += [specs]
                
    return pile_specs
    


class Discover(Command):
    """Discover Mailpile piles accessible on this machine"""
    SYNOPSIS = (None, 'discover', None,
                    '[--user=<user1[,user2 ...]] [--pile=<pile1[,pile2 ...]]')
    ORDER = ('Internals', 9)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_BROWSE_FILESYSTEM
    
    # List of option values that are extracted for each pile.
    # These are prefixed by the OS's user name and the pile name
    # which are handled as special cases in the code.
    # If no value in config, the config.rules default is used,
    # failing that the value listed below.
    #    
    #                         Section              Option       Default
    option_list_spec = [    ( '',                  'user',      ' '         ),
                            ( '',                  'pile',      ' '         ),
                            ( 'config/sys:',       'http_host', 'localhost' ),
                            ( 'config/sys:',       'http_port', 33411       ),
                            ( 'config/sys/proxy:', 'protocol',  'unknown'   ),
                            ( 'config/sys/proxy:', 'port',      8080        ) ]
                    
    class CommandResult(Command.CommandResult):
        def as_text(self):
            lines = []
            if self.result:
                lines.append(('%-15s %-15s %-15s %-5s   %-15s %-5s') % ('User',
                        'Pile', 'Host', 'Port', 'Proxy-protocol', '-port'))
                lines.append('')              
                for i in self.result:
                    lines.append(('%-15s %-15s %-15s %-5d   %-15s %-5d') % i)
        
            return '\n'.join(lines)

    def command(self, args=None):
    
        config = self.session.config
       
        this_workdir = config.workdir
        this_user = getpass.getuser()
        
        arg_users = None
        arg_piles = None
        for arg in self.args:
            if arg.startswith('--user='):
                arg_users = arg[len('--user='):].split(',')
            elif arg.startswith('--pile='):
                arg_piles = arg[len('--pile='):].split(',')
            else:
                return self._error(_('Unknown parameter %s' ) % arg)
                
        # Extract default values from config.rules
        option_list = []
        for option in self.option_list_spec:
            if not option[0]:
                option_list += [option]
                continue
            # Split up section name, omit '/', omit ':', append option name.
            subsec = option[0][:-1].split('/')[1:] + [option[1]]
            value = config.rules
            try:
                while subsec:
                    value =  value[subsec[0]][2]
                    subsec = subsec[1:]
                option = option[0:2] + (value,)
            except (IndexError, KeyError):
                pass
            option_list += [option]
            
        pile_specs = discover_piles(option_list, this_user, this_workdir,
                            only_users = arg_users, only_piles = arg_piles )

        return self._success(_('Listed %d piles') % len(pile_specs),
                                                            result=pile_specs)

_plugins.register_commands(Discover)
