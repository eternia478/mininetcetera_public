"""
Component objects for CMSnet.

Components provide a simple abstraction for interacting with virtual machines
and hypervisors.

CMSComponent: superclass for all components in the cloud.

VM: a virtual machine.

Hypervisor: a hypervisor.

(There may be more components to add later.)
"""

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

class CMSComponent( object ):
    """A component of the cloud network. This is simply a wrapper for Node
       objects in Mininet."""

    def __init__( self, node, config_folder="." ):
        """
        Intialization

        node: Mininet node
        config_folder: Folder containing configuration file
        """
        assert isinstance(node, Node)
        assert isinstance(config_folder, basestring)
        self.node = node
        self.config_folder = config_folder
        self.have_comp_config = False

    @property
    def name( self ):
        return self.node.name

    @name.setter
    def name( self, name ):
        try:      # Remove old config file.
            os.remove(self.get_config_file_name())
        except:
            pass
        self.node.name = name
        if self.have_comp_config:
            self.update_comp_config()

    def __repr__( self ):
        "More informative string representation"
        # NOTE: This should be overridden.
        return repr(self.node)

    def __str__( self ):
        "Abbreviated string representation"
        return self.name

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        # NOTE: This should be overridden.
        return self.config_folder+"/"+self.name+".config_cmscomp"

    def check_comp_config( self ):
        "Check for any previous configurations and adjust if necessary."
        # NOTE: This should be overridden.
        pass

    def update_comp_config( self ):
        "Update the configurations for this component."
        # NOTE: This should be overridden.
        pass


class VirtualMachine( CMSComponent ):
    """A virtual machine, intended to run on a hypervisor. A wrapper class for
       the Host class."""

    vm_uuid = 0  # UNUSED: For ID purposes? Maybe name is enough.

    def __init__( self, node, config_folder="." ):
        """
        Intialization

        node: Mininet node
        config_folder: Folder containing configuration file
        """
        assert isinstance(node, Host)
        CMSComponent.__init__( self, node, config_folder )

        self.hv = None
        self.start_script = ""
        self.stop_script = ""

        self.config_hv_name = None   # temp holder for HV name in config
        self.check_comp_config()
        self.update_comp_config()
        self.have_comp_config = True

    @property
    def IP( self ):
        return self.node.IP()

    @IP.setter
    def IP( self, ip ):
        self.node.setIP(ip)
        if self.have_comp_config:
            self.update_comp_config()

    @property
    def MAC( self ):
        return self.node.MAC()

    @MAC.setter
    def MAC( self, mac ):
        self.node.setMAC(mac)
        if self.have_comp_config:
            self.update_comp_config()

    @property
    def hv_name( self ):
        if isinstance(self.hv, Hypervisor):
            return self.hv.name
        return None

    def __repr__( self ):
        "More informative string representation"
        # TODO: This should be different.
        return repr(self.node)

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        return self.config_folder+"/"+self.name+".config_vm"

    def check_comp_config( self ):
        "Check for any previous configurations and adjust if necessary."
        # See http://stackoverflow.com/questions/14574518/
        try:
            with open(self.get_config_file_name(), "r") as f:
                config_raw = f.read()
                config = {}
                if config_raw:
                    config, l = defaultDecoder.raw_decode(config_raw)
                for attr in config:
                    if isinstance(config[attr], basestring):
                        setattr(self, attr, str(config[attr]))
                    else:
                        setattr(self, attr, config[attr])
                f.close()                
        except IOError as e:
            info("No config exists for VM %s" % self.name)

    def update_comp_config( self ):
        "Update the configurations for this component."
        f = open(self.get_config_file_name(), "w")
        config = {}
        config["IP"] = self.IP
        config["MAC"] = self.MAC
        config["start_script"] = self.start_script
        config["stop_script"] = self.stop_script
        config["config_hv_name"] = self.hv_name
        f.write(json.dumps(config))
        f.flush()
        f.close()

    def is_running( self ):
        "Test if this VM image is running (or inactive) on any hypervisor."
        return self.hv_name is not None

    def launch( self, hv ):
        "Initialize the VM on the input hypervisor."
        assert not self.is_running()
        assert hv.is_enabled()

        self.hv = hv
        self.hv.nameToVMs[self.name] = self

        if self.have_comp_config:
            self.update_comp_config()
        self.node.cmd(self.start_script)

    def moveTo( self, hv ):
        "Migrate the VM to the new input hypervisor."
        assert self.is_running()
        assert hv.is_enabled()

        del self.hv.nameToVMs[self.name]
        self.hv = hv
        self.hv.nameToVMs[self.name] = self

        if self.have_comp_config:
            self.update_comp_config()

    def stop( self ):
        "Stop running the VM."
        assert self.is_running()

        del self.hv.nameToVMs[self.name]
        self.hv = None

        if self.have_comp_config:
            self.update_comp_config()
        self.node.cmd(self.stop_script)

    def shutdown( self ):
        "Shutdown VM when CMSnet is shutting down."
        if not self.is_running():
            return
        self.have_comp_config = False  # Prevent adjustments to config file.
        self.stop()


class Hypervisor( CMSComponent ):
    """A hypervisor that virtual machines run on. A wrapper class for the
       Switch class."""

    def __init__( self, node, config_folder="." ):
        """
        Intialization

        node: Mininet node
        config_folder: Folder containing configuration file
        """
        assert isinstance(node, Switch)
        CMSComponent.__init__( self, node, config_folder )

        self.nameToVMs = {}   # UNUSED: mapping for VMs in this hypervisor
        self._enabled = True

    def __repr__( self ):
        "More informative string representation"
        # TODO: This should be different.
        return repr(self.node)

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        return self.config_folder+"/"+self.name+".config_hv"

    def is_enabled( self ):
        "Test if this hypervisor is enabled to run VMs or not."
        return self._enabled

    def enable( self ):
        "Enable the hypervisor to run VMs."
        assert not self.is_enabled()
        self._enabled = True

    def disable( self ):
        "Disable the hypervisor from running VMs."
        assert self.is_enabled()
        self._enabled = False



