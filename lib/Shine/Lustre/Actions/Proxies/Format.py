# Format.py -- Lustre proxy action class : format
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

from Shine.Configuration.Globals import Globals
from Shine.Configuration.Configuration import Configuration

from ProxyAction import *

from ClusterShell.NodeSet import NodeSet


class Format(ProxyAction):
    """
    File system format action class.
    """

    def __init__(self, fs, nodes, targets_type=None, targets_indexes=None):
        ProxyAction.__init__(self)
        self.fs = fs
        assert isinstance(nodes, NodeSet)
        self.nodes = nodes
        self.targets_type = targets_type
        self.targets_indexes = targets_indexes

    def launch(self):
        """
        Launch proxy format command.
        """
        # Prepare proxy format command
        command = ["%s" % self.progpath]
        command.append("format")
        command.append("-f %s" % self.fs.fs_name)
        command.append("-R")

        if self.targets_type:
            command.append("-t %s" % self.targets_type)
            if self.targets_indexes:
                command.append("-i %s" % self.targets_indexes)

        # Schedule cluster command.
        self.task.shell(' '.join(command), nodes=self.nodes, handler=self)

    def ev_read(self, worker):
        node, buf = worker.last_read()
        try:
            event, params = self._shine_msg_unpack(buf)
            self.fs._handle_shine_event(event, node, **params)
        except ProxyActionUnpackError, e:
            print "%s: %s" % (node, buf)

    def ev_close(self, worker):
        for rc, nodelist in worker.iter_retcodes():
            if rc != 0:    
                raise ProxyActionError(rc, "Formatting failed on %s" % \
                       NodeSet.fromlist(nodelist))
