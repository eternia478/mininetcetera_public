import os
import re
import signal
import select
from subprocess import Popen, PIPE, STDOUT
from operator import or_
from time import sleep
from mininet.log import info, error, warn, debug
from mininet.util import ( quietRun, errRun, errFail, moveIntf, isShellBuiltin,
                           numCores, retry, mountCgroups )
from mininet.moduledeps import moduleDeps, pathCheck, OVS_KMOD, OF_KMOD, TUN
from mininet.link import Link, Intf, TCIntf
from mininet.node import Node, Host, Switch
import json
defaultDecoder = json.JSONDecoder()

class CMSNode( object ):
    """
    A component of the cloud network.
    This is simply a wrapper for Node objects in Mininet.

    """

    def __init__( self, node, **params ):
        """node: Mininet node"""
        assert isinstance(node, Node)
        # assert isinstance(config_folder, basestring)
        self.node = node

class VirtualMachine( CMSNode ):
    """A virtual machine, intended to run on a hypervisor. A wrapper class for
       the Host class."""

    def __init__( self, node,**params ):
        """node: Mininet node"""
        assert isinstance(node, Host)
        CMSNode.__init__( self, node )
        self.hv = None
        self.is_running = False

    def launch( self, hv ):
        "Initialize the VM on the input hypervisor."
        assert not self.is_running
        self.is_running = True
        self.hv = hv
        self.hv.nameToVMs[self.node.name] = self


    def moveTo( self, hv ):
        "Migrate the VM to the new input hypervisor."
        assert self.is_running

        del self.hv.nameToVMs[self.node.name]
        self.hv = hv
        self.hv.nameToVMs[self.node.name] = self

        "Stop running the VM."
        assert self.is_running
        del self.hv.nameToVMs[self.node.name]
        self.hv = None

    def stop( self ):
        "Stop running the VM."
        assert self.is_running
        if self.hv != None:
          del self.hv.nameToVMs[self.node.name]
          self.hv = None

    """
        def shutdown( self ):
        "Shutdown VM when CMSnet is shutting down."
        if not self.is_running:
            return
        self.stop()
    """


class Hypervisor( CMSNode ):
    """A hypervisor that virtual machines run on. A wrapper class for the
       Switch class."""

    def __init__( self, node, **params):
        """node: Mininet node"""
        assert isinstance(node, Switch)
        CMSNode.__init__( self, node)
        self.nameToVMs = {}
