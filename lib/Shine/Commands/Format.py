# Format.py -- Format file system targets
# Copyright (C) 2007, 2008, 2009 CEA
#
# This file is part of shine
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# $Id$

from Shine.Commands.Status import Status

# Command base class
from Shine.Commands.Base.FSLiveCommand import FSTargetLiveCriticalCommand
from Shine.Commands.Base.CommandRCDefs import RC_OK, RC_ST_EXTERNAL, \
                                              RC_FAILURE, RC_TARGET_ERROR, \
                                              RC_CLIENT_ERROR, RC_RUNTIME_ERROR
# Lustre events
from Shine.Commands.Base.FSEventHandler import FSGlobalEventHandler, \
                                               FSLocalEventHandler

from Shine.Lustre.FileSystem import MOUNTED, RECOVERING, EXTERNAL, OFFLINE, \
                                    TARGET_ERROR, CLIENT_ERROR, RUNTIME_ERROR


class GlobalFormatEventHandler(FSGlobalEventHandler):

    ACTION = 'format'
    ACTIONING = 'formating'

    def handle_post(self, fs):
        if self.verbose > 0:
            Status.status_view_fs(fs, show_clients=False)

class LocalFormatEventHandler(FSLocalEventHandler):

    ACTION = 'format'
    ACTIONING = 'formating'


class Format(FSTargetLiveCriticalCommand):
    """
    shine format -f <fsname> [-t <target>] [-i <index(es)>] [-n <nodes>]
    """
    
    NAME = "format"
    DESCRIPTION = "Format file system targets."

    GLOBAL_EH = GlobalFormatEventHandler
    LOCAL_EH = LocalFormatEventHandler

    TARGET_STATUS_RC_MAP = { \
            MOUNTED : RC_FAILURE,
            EXTERNAL : RC_ST_EXTERNAL,
            RECOVERING : RC_FAILURE,
            OFFLINE : RC_OK,
            TARGET_ERROR : RC_TARGET_ERROR,
            CLIENT_ERROR : RC_CLIENT_ERROR,
            RUNTIME_ERROR : RC_RUNTIME_ERROR }

    def execute_fs(self, fs, fs_conf, eh, vlevel):

        # Warn if trying to act on wrong nodes
        servers = fs.components.managed(supports='format').servers()
        if not self.nodes_support.check_valid_list(fs.fs_name, servers,
                                                   'format'):
            return RC_FAILURE

        # Ignore all clients for this command
        fs.disable_clients()

        if not self.ask_confirm("Format %s on %s: are you sure?" % (fs.fs_name,
                                                                    servers)):
            return RC_FAILURE

        mkfs_options = {}
        format_params = {}
        for target_type in [ 'mgt', 'mdt', 'ost' ]:
            format_params[target_type] = \
                    fs_conf.get_target_format_params(target_type)
            mkfs_options[target_type] = \
                    fs_conf.get_target_mkfs_options(target_type) 

        # Call a pre_format method if defined by the event handler.
        if hasattr(eh, 'pre'):
            eh.pre(fs)
        
        # Notify backend of file system status mofication
        fs_conf.set_status_fs_formating()

        # Format really.
        status = fs.format(stripecount=fs_conf.get_stripecount(),
                    stripesize=fs_conf.get_stripesize(),
                    format_params=format_params,
                    mkfs_options=mkfs_options,
                    quota=fs_conf.has_quota(),
                    quota_type=fs_conf.get_quota_type(),
                    addopts = self.addopts.get_options(),
                    failover=self.target_support.get_failover())

        rc = self.fs_status_to_rc(status)

        if rc == RC_OK:
            # Notify backend of file system status mofication
            fs_conf.set_status_fs_formated()

            if vlevel > 0:
                print "Format successful."
        else:
            # Notify backend of file system status mofication
            fs_conf.set_status_fs_format_failed()

            if rc == RC_RUNTIME_ERROR:
                for nodes, msg in fs.proxy_errors:
                    print "%s: %s" % (nodes, msg)
            if vlevel > 0:
                print "Format failed"

        # Call a post_format method if defined by the event handler.
        if hasattr(eh, 'post'):
            eh.post(fs)

        return rc
