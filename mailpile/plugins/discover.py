# This code searches a computer for Mailpile pile directories
# and prints a summary of their location and associated ports.
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
import mailpile.config.defaults as mpdefaults


import datetime
import json
import random
import re
import socket
import subprocess
import traceback
import threading
import time
import webbrowser

import mailpile.util
import mailpile.postinglist
import mailpile.security as security
from mailpile.commands import *
from mailpile.config.validators import WebRootCheck
from mailpile.crypto.gpgi import GnuPG
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailboxes import IsMailbox
from mailpile.mailutils import ClearParseCache, Email
from mailpile.postinglist import GlobalPostingList
from mailpile.plugins import PluginManager
from mailpile.safe_popen import MakePopenUnsafe, MakePopenSafe
from mailpile.search import MailIndex
from mailpile.util import *
from mailpile.vcard import AddressInfo
from mailpile.vfs import vfs, FilePath

_plugins = PluginManager(builtin=__file__)


class Discover(Command):
    """Discover Mailpile piles present on this machine"""
    SYNOPSIS = (None, 'discover', 'discover', "[-a] [-d] [</path/*.foo> ...]")
    ORDER = ('Internals', 5)
    CONFIG_REQUIRED = True
    IS_USER_ACTIVITY = True
    COMMAND_SECURITY = security.CC_BROWSE_FILESYSTEM
    
    # List of option values that are extracted for each pile.
    # These are prefixed by the OS's user name and the pile name.
    # If no value in config, the CONFIG_RULES default is used,
    # failing that the value listed below.
    #    
    #               Section                Option       Default
    option_list_spec = [    ( 'config/sys:',       'http_host', 'localhost' ),
                            ( 'config/sys:',       'http_port', 33411       ),
                            ( 'config/sys/proxy:', 'protocol',  'unknown'   ),
                            ( 'config/sys/proxy:', 'port',      8080        ) ]
                    
    # Extract default values from mailpile.config.defaults.CONFIG_RULES
    option_list = []
    for option in option_list_spec:
        # Split up section name, omit '/', omit ':', append option name.
        subsec = option[0][:-1].split('/')[1:] + [option[1]]
        value = mpdefaults.CONFIG_RULES
        try:
            while subsec:
                value =  value[subsec[0]][2]
                subsec = subsec[1:]
            option = option[0:2] + (value,)
        except (IndexError, KeyError):
            pass
        option_list += [option]
        
    def discover_piles(self, this_user, this_workdir):
    
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
            try:
                workdir_list = os.listdir(parent[1])
            except OSError:
                continue
                
            # Loop through all accessible Mailpile workdirs for one user.
            for pile in workdir_list:
                workdir = os.path.join(parent[1], pile)
                if os.path.isdir(workdir):
                    public = ConfigParser.ConfigParser()
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
                    specs = (parent[0], pile)
                    for field in self.option_list:
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

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                lines = []
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
        
        pile_specs = self.discover_piles(this_user, this_workdir)

        return self._success(_('Listed %d piles') % len(pile_specs),
                                                            result=pile_specs)

_plugins.register_commands(Discover)
