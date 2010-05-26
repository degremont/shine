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

from Shine.Configuration.Configuration import Configuration
from Shine.Configuration.Globals import Globals 
from Shine.Configuration.Exceptions import *

from Status import Status
from Exceptions import *

from Base.FSLiveCommand import FSLiveCriticalCommand
from Base.FSEventHandler import FSGlobalEventHandler
from Base.CommandRCDefs import *
# -R handler
from Base.RemoteCallEventHandler import RemoteCallEventHandler


from Shine.FSUtils import open_lustrefs

# timer events
import ClusterShell.Event

# lustre events
import Shine.Lustre.EventHandler

# Shine Proxy Protocol
from Shine.Lustre.Actions.Proxies.ProxyAction import *
from Shine.Lustre.FileSystem import *

from ClusterShell.NodeSet import *
from ClusterShell.Task import task_self

import datetime
import socket
import sys


class GlobalFormatEventHandler(FSGlobalEventHandler):

    def __init__(self, verbose=1):
        FSGlobalEventHandler.__init__(self, verbose)

    def handle_pre(self, fs):
        # attach fs to this handler
        if self.verbose > 0:
            count = len(list(fs.managed_components(supports='format')))
            servers = fs.managed_component_servers(supports='format')
            print "Starting format of %d targets on %s" % (count, servers)

    def handle_post(self, fs):
        if self.verbose > 0:
            Status.status_view_fs(fs, show_clients=False)

    def ev_formatjournal_start(self, node, comp):
        if self.verbose > 1:
            print "%s: Starting format of %s journal (%s)" % (node, \
                    comp.get_id(), comp.jdev)

    def ev_formatjournal_done(self, node, comp):
        if self.verbose > 1:
            print "%s: Format of %s journal (%s) succeeded" % \
                    (node, comp.get_id(), comp.jdev)

    def ev_formatjournal_failed(self, node, comp, rc, message):
        print "%s: Format of %s journal (%s) failed with error %d" % \
                (node, comp.get_id(), comp.jdev, rc)
        print message

    def ev_formattarget_start(self, node, comp, **kwargs):
        self.update_config_status(comp, "formatting")

        if self.verbose > 1:
            print "%s: Starting format of %s (%s)" % (node, comp.get_id(), \
                                                      comp.dev)

        self.update()

    def ev_formattarget_done(self, node, comp):
        self.update_config_status(comp, "succeeded")

        if self.verbose > 1:
            print "%s: Format of %s (%s) succeeded" % \
                    (node, comp.get_id(), comp.dev)

        self.update()

    def ev_formattarget_failed(self, node, comp, rc, message):
        self.update_config_status(comp, "failed")

        print "%s: Format of %s (%s) failed with error %d" % \
                (node, comp.get_id(), comp.dev, rc)
        print message

        self.update()

    def set_fs_config(self, fs_conf):
        self.fs_conf = fs_conf

    def update_config_status(self, target, status):
        # Retrieve the right target from the configuration
        target_list = [self.fs_conf.get_target_from_tag_and_type(target.tag,
            target.TYPE.upper())]

        # Change the status of targets to avoid their use
        # in an other file system
        if status == "succeeded":
            self.fs_conf.set_status_targets_formated(target_list, None)
        elif status == "failed":
            self.fs_conf.set_status_targets_format_failed(target_list, None)
        else:
            self.fs_conf.set_status_targets_formating(target_list, None)


class LocalFormatEventHandler(Shine.Lustre.EventHandler.EventHandler):

    def __init__(self, verbose=1):
        self.verbose = verbose
        self.failures = 0
        self.success = 0

    def ev_formatjournal_start(self, node, comp):
        print "Starting format of %s journal (%s)" % \
               (comp.get_id(), comp.jdev)

    def ev_formatjournal_done(self, node, comp):
        print "Format of %s journal (%s) succeeded" % \
               (comp.get_id(), comp.jdev)

    def ev_formatjournal_failed(self, node, comp, rc, message):
        self.failures += 1
        print "Format of %s journal (%s) failed with error %d" % \
               (comp.get_id(), comp.jdev, rc)
        print message

    def ev_formattarget_start(self, node, comp):
        print "Starting format of %s (%s)" % \
               (comp.get_id(), comp.dev)
        sys.stdout.flush()

    def ev_formattarget_done(self, node, comp):
        self.success += 1
        print "Format of %s (%s) succeeded" % \
               (comp.get_id(), comp.dev)

    def ev_formattarget_failed(self, node, comp, rc, message):
        self.failures += 1
        print "Format of %s (%s) failed with error %d" % \
               (comp.get_id(), comp.dev, rc)
        print message


class Format(FSLiveCriticalCommand):
    """
    shine format -f <fsname> [-t <target>] [-i <index(es)>] [-n <nodes>]
    """
    
    def __init__(self):
        FSLiveCriticalCommand.__init__(self)

    def get_name(self):
        return "format"

    def get_desc(self):
        return "Format file system targets."

    target_status_rc_map = { \
            MOUNTED : RC_FAILURE,
            EXTERNAL : RC_ST_EXTERNAL,
            RECOVERING : RC_FAILURE,
            OFFLINE : RC_OK,
            TARGET_ERROR : RC_TARGET_ERROR,
            CLIENT_ERROR : RC_CLIENT_ERROR,
            RUNTIME_ERROR : RC_RUNTIME_ERROR }

    def fs_status_to_rc(self, status):
        return self.target_status_rc_map[status]

    def execute(self):
        result = 0

        # Do not allow implicit filesystems format.
        if not self.opt_f:
            raise CommandHelpException("A filesystem is required (use -f).", self)

        # Initialize remote command specifics.
        self.init_execute()

        # Setup verbose level.
        vlevel = self.verbose_support.get_verbose_level()

        target = self.target_support.get_target()
        for fsname in self.fs_support.iter_fsname():

            # Install appropriate event handler.
            eh = self.install_eventhandler(LocalFormatEventHandler(vlevel),
                    GlobalFormatEventHandler(vlevel))

            # Open configuration and instantiate a Lustre FS.
            fs_conf, fs = open_lustrefs(fsname, target,
                    nodes=self.nodes_support.get_nodeset(),
                    excluded=self.nodes_support.get_excludes(),
                    failover=self.target_support.get_failover(),
                    indexes=self.indexes_support.get_rangeset(),
                    labels=self.target_support.get_labels(),
                    event_handler=eh)

            # Warn if trying to act on wrong nodes
            if not self.nodes_support.check_valid_list(fsname, \
                    fs.managed_component_servers(supports='format'), "format"):
                result = RC_FAILURE
                continue

            if not self.has_local_flag():
                # Allow global handler to access fs_conf.
                eh.set_fs_config(fs_conf)

            # Prepare options...
            fs.set_debug(self.debug_support.has_debug())

            # Ignore all clients for this command
            fs.disable_clients()

            if not self.ask_confirm("Format %s on %s: are you sure?" % (fsname,
                    fs.managed_component_servers(supports='format'))):
                result = RC_FAILURE
                continue

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
            if rc > result:
                result = rc

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

        return result

