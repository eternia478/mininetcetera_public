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

from cmsnet.cms_log import config_error
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
        self._node = node
        self._config_folder = config_folder
        self._allow_write_comp_config = True

    @property
    def node( self ):
        return self._node

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
        return self._config_folder+"/"+self.name+".config_cmscomp"

    def lock_comp_config( self ):
        "Lock the configuration file to prevent it from being written."
        self._allow_write_comp_config = False

    def unlock_comp_config( self ):
        "Unlock the configuration file to allow it to be written."
        self._allow_write_comp_config = True

    def is_comp_config_locked( self ):
        "Return whether the configuration file is locked from writing."
        return not self._allow_write_comp_config

    def check_comp_config( self ):
        "Check for any previous configurations and adjust if necessary."
        self.lock_comp_config()

        # Part 1: Read from file
        config_raw = None
        try:
            # See http://stackoverflow.com/questions/3642080/
            # Or alternatively see http://blog.bitfoc.us/?p=328
            with open(self.get_config_file_name(), "r") as f:
                config_raw = f.read()
        except IOError:
            pass

        if not config_raw:
            info("No previous config exists for %s.\n" % self.name)
            self.unlock_comp_config()
            return

        # Part 2: Parse and apply from raw string
        config = {}
        try:
            config, l = defaultDecoder.raw_decode(config_raw)
            assert isinstance(config, dict), "Config not a dictionary."
            for attr in config:
                if isinstance(config[attr], basestring):
                    setattr(self, attr, str(config[attr]))
                else:
                    setattr(self, attr, config[attr])
        except:
            error_msg = "Previous config for %s cannot be parsed." % self.name
            config_error(error_msg, config=config, config_raw=config_raw)
            return

    def update_comp_config( self ):
        "Update the configurations for this component."
        if self.is_comp_config_locked():
            return

        # Part 1: Get config data and dump to string
        config = {}
        config_raw = None
        try:
            self.set_comp_config(config)
            config_raw = json.dumps(config)
        except:
            error_msg = "Config for %s cannot be created." % self.name
            config_error(error_msg, config=config)
            return

        # Part 2: Write to file
        try:
            with open(self.get_config_file_name(), "w") as f:
                f.write(config_raw)
                f.flush()
        except IOError:
            error_msg = "Unable to write to config file for %s." % self.name
            config_error(error_msg, config_raw=config_raw)
            return

    def set_comp_config( self, config ):
        "Set the configurations of this component to be saved."
        # NOTE: This should be overridden.
        pass


class VirtualMachine( CMSComponent ):
    """A virtual machine, intended to run on a hypervisor. A wrapper class for
       the Host class."""

    vm_uuid = 0  # UNUSED: For ID purposes? Maybe name is enough.

    def __init__( self, node, config_folder=".", tenant_id=1 ):
        """
        Intialization

        node: Mininet node
        config_folder: Folder containing configuration file
        """
        assert isinstance(node, Host)
        CMSComponent.__init__( self, node, config_folder )

        self._tenant_id = tenant_id
        self._hv = None
        self._is_paused = False
        self.start_script = ""   # CHECK: Should these be modifiable?
        self.pause_script = ""
        self.resume_script = ""
        self.stop_script = ""

        self.config_hv_name = None   # temp holder for HV name in config
        self.config_is_paused = None # temp holder for paused status in config
        self.terms = []              # temp holder for terms to kill on removal

        self.check_comp_config()
        self.update_comp_config()
        self.unlock_comp_config()

    @CMSComponent.name.setter
    def name( self, name ):
        old_name = self.name
        CMSComponent.name.fset(self, name)
        if self._hv:
            del self._hv.nameToVMs[old_name]
            self._hv.nameToVMs[self.name] = self

    @property
    def IP( self ):
        return self.node.IP()

    @IP.setter
    def IP( self, ip ):
        self.node.setIP(ip)
        self.update_comp_config()

    @property
    def MAC( self ):
        return self.node.MAC()

    @MAC.setter
    def MAC( self, mac ):
        self.node.setMAC(mac)
        self.update_comp_config()

    @property
    def hv( self ):
        return self._hv

    @hv.setter
    def hv( self, hv ):
        if self._hv:
            del self._hv.nameToVMs[self.name]
        self._hv = hv
        if self._hv:
            self._hv.nameToVMs[self.name] = self
            assert self.is_running()
        else:
            assert not self.is_running()
        self.update_comp_config()

    @property
    def hv_name( self ):
        if isinstance(self.hv, Hypervisor):
            return self.hv.name
        return None

    @property
    def tenant_id( self ):
        return self._tenant_id

    def __repr__( self ):
        "More informative string representation"
        # TODO: This should be different.
        return repr(self.node)

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        return self._config_folder+"/"+self.name+".config_vm"

    def set_comp_config( self, config ):
        "Set the configurations of this component to be saved."
        config["_tenant_id"] = self._tenant_id
        config["IP"] = self.IP
        config["MAC"] = self.MAC
        config["config_hv_name"] = self.hv_name
        config["config_is_paused"] = self.is_paused()
        config["start_script"] = self.start_script
        config["pause_script"] = self.pause_script
        config["resume_script"] = self.resume_script
        config["stop_script"] = self.stop_script

    def is_running( self ):
        "Test if this VM image is running (or inactive) on any hypervisor."
        return self.hv_name is not None

    def is_paused( self ):
        "Test if this VM image is paused (or running) on any hypervisor."
        return self.is_running() and self._is_paused

    def cloneTo( self, new_vm ):
        "Clone information from this VM to the new VM image."
        assert new_vm is not None
        assert isinstance(new_vm, VirtualMachine)
        assert not new_vm.is_running()
        new_vm.start_script = self.start_script
        new_vm.stop_script = self.stop_script
        new_vm._tenant_id = self.tenant_id
        # FIXME: Copy script image files in file system.

    def launchOn( self, hv ):
        "Initialize the VM on the input hypervisor."
        assert not self.is_running()
        assert hv is not None
        assert hv.is_enabled()
        self.hv = hv
        self.node.cmd(self.start_script)

    def moveTo( self, hv ):
        "Migrate the VM to the new input hypervisor."
        assert self.is_running()
        assert hv is not None
        assert hv.is_enabled()
        self.hv = hv

    def pause( self ):
        "Pause the VM."
        assert self.is_running()
        assert not self.is_paused()
        self._is_paused = True
        self.update_comp_config()
        self.node.cmd(self.pause_script)

    def resume( self ):
        "Resume the VM."
        assert self.is_running()
        assert self.is_paused()
        self._is_paused = False
        self.update_comp_config()
        self.node.cmd(self.resume_script)

    def stop( self ):
        "Stop running the VM."
        assert self.is_running()
        self.hv = None
        self.node.cmd(self.stop_script)

    def remove( self ):
        "Remove traces of the VM from existence."
        try:      # Remove config file.
            os.remove(self.get_config_file_name())
        except:
            pass

    def shutdown( self ):
        "Shutdown VM when CMSnet is shutting down."
        if not self.is_running():
            return
        self.lock_comp_config()    # Prevent adjustments to config file.
        self.stop()


class Hypervisor( CMSComponent ):
    """A hypervisor that virtual machines run on. A wrapper class for the
       Switch class."""

    def __init__( self, node, config_folder=".", vm_dist_limit=None):
        """
        Intialization

        node: Mininet node
        config_folder: Folder containing configuration file
        """
        assert isinstance(node, Switch)
        CMSComponent.__init__( self, node, config_folder )

        self.nameToVMs = {}   # UNUSED: mapping for VMs in this hypervisor
        self._enabled = True
        self._vm_dist_limit = vm_dist_limit

        self.check_comp_config()
        self.update_comp_config()
        self.unlock_comp_config()

    @CMSComponent.name.setter
    def name( self, name ):
        CMSComponent.name.fset(self, name)
        for vm in self.nameToVMs.values():
            vm.update_comp_config()

    @property
    def vm_dist_limit( self ):
        return self._vm_dist_limit

    @vm_dist_limit.setter
    def vm_dist_limit( self, vm_dist_limit ):
        self._vm_dist_limit = vm_dist_limit
        self.update_comp_config()

    def __repr__( self ):
        "More informative string representation"
        # TODO: This should be different.
        return repr(self.node)

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        return self._config_folder+"/"+self.name+".config_hv"

    def set_comp_config( self, config ):
        "Set the configurations of this component to be saved."
        config["vm_dist_limit"] = self.vm_dist_limit
        config["_enabled"] = self._enabled

    def get_num_VMs( self ):
        "Return the number of VMs running on this hypervisor."
        return len(self.nameToVMs)

    def is_enabled( self ):
        "Test if this hypervisor is enabled to run VMs or not."
        return self._enabled

    def enable( self ):
        "Enable the hypervisor to run VMs."
        assert not self.is_enabled()
        self._enabled = True
        self.update_comp_config()

    def disable( self ):
        "Disable the hypervisor from running VMs."
        assert self.is_enabled()
        self._enabled = False
        self.update_comp_config()
