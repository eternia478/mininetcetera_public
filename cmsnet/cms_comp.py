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

#from mininet.log import info, error, warn, debug, output
from mininet.util import ( quietRun, errRun, errFail, moveIntf, isShellBuiltin,
                           numCores, retry, mountCgroups )
from mininet.moduledeps import moduleDeps, pathCheck, OVS_KMOD, OF_KMOD, TUN
from mininet.link import Link, Intf, TCIntf
from mininet.node import Node, Host, Switch

from cmsnet.cms_log import error, info, output, warn, debug, config_error
import shutil
from cmsnet.cms_util import ( defaultDecoder, jsonprint, jsondumps,
                              makeDirNoErrors, removeNoErrors,
                              isValidMAC, getExpandedIP, isValidIP,
                              isValidNetmask, isInSameSubnet,
                              getNetmaskFromPrefixLen, getPrefixLenFromNetmask,
                              UpdatingDict, ConfigUpdatingDict )

class CMSComponent( object ):
    """A component of the cloud network. This is simply a wrapper for Node
       objects in Mininet."""

    def __init__( self, node, cmsnet_info={} ):
        """
        Intialization

        node: Mininet node
        cmsnet_info: Dictionary of necessary information from CMSnet
        """
        assert isinstance(node, Node)
        assert isinstance(cmsnet_info, dict)
        self._node = node
        self._cmsnet_info = cmsnet_info
        self._allow_write_comp_config = True

    @property
    def node( self ):
        return self._node

    @property
    def name( self ):
        return self.node.name

    @name.setter
    def name( self, name ):        # Remove old config file.
        removeNoErrors(self.get_config_file_name())
        self.node.name = name
        self.update_comp_config()

    @property
    def config_folder( self ):
        return self._cmsnet_info.get("config_folder")

    def __repr__( self ):
        "More informative string representation"
        # NOTE: This should be overridden.
        return repr(self.node)

    def __str__( self ):
        "Abbreviated string representation"
        return self.name

    def get_info( self ):
        "Get information to be sent with a CMS message to the controller."
        info = {
          'name' : self.name,
        }
        return info

    def get_temp_folder_path( self ):
        "Return the path to the component's temporary folder."
        return "/tmp/cmsnet/"+self.name+"/"

    def create_temp_folder( self ):
        "Create the component's temporary folder."
        makeDirNoErrors(self.get_temp_folder_path())

    def remove_temp_folder( self ):
        "Remove the component's temporary folder."
        removeNoErrors(self.get_temp_folder_path())

    def store_temp_folder( self ):
        "UNUSED. Store temporary folder into configuration folder."
        temp_path = self.get_temp_folder_path()
        config_folder = os.path.dirname(self.get_config_file_name())
        config_path = config_folder+"/"+os.path.basename(temp_path)
        try:
            shutil.move(temp_path, new_path)
        except:
            pass

    def reload_temp_folder( self ):
        "UNUSED. Reload the temporary folder from the configuration folder."
        temp_path = self.get_temp_folder_path()
        config_folder = os.path.dirname(self.get_config_file_name())
        config_path = old_folder+"/"+os.path.basename(temp_path)
        try:
            shutil.move(config_path, temp_path)
        except:
            pass

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        # NOTE: This should be overridden.
        if not self.config_folder:
            return "./"+self.name+".config_cmscomp"
        else:
            return self.config_folder+"/"+self.name+".config_cmscomp"

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
            info(self, "No previous config exists.")
            self.unlock_comp_config()
            return

        # Part 2: Parse and apply from raw string
        config = {}
        try:
            config, l = defaultDecoder.raw_decode(config_raw)
            assert isinstance(config, dict), "Config not a dictionary."
            if config.pop('NAME', self.name) != self.name:
                warn("\nVM %s name changed?\n" % (self.name,))
            for attr in config:
                if isinstance(config[attr], basestring):
                    setattr(self, attr, str(config[attr]))
                else:
                    setattr(self, attr, config[attr])
        except:
            error_msg = "Previous config cannot be parsed."
            config_error(self, error_msg, config=config, config_raw=config_raw)
            return

    def update_comp_config( self ):
        "Update the configurations for this component."
        if self.is_comp_config_locked():
            return

        # Part 1: Get config data and dump to string
        config = {}
        config['NAME'] = self.name
        config_raw = None
        try:
            self.set_comp_config(config)
            config_raw = jsonprint(config)
        except:
            error_msg = "Config cannot be created."
            config_error(self, error_msg, config=config)
            return

        # Part 2: Write to file
        try:
            with open(self.get_config_file_name(), "w") as f:
                f.write(config_raw)
                f.flush()
        except IOError:
            error_msg = "Unable to write to config file."
            config_error(self, error_msg, config_raw=config_raw)
            return

    def remove_comp_config( self ):
        "Remove the configurations of this component."
        removeNoErrors(self.get_config_file_name())

    def set_comp_config( self, config ):
        "Set the configurations of this component to be saved."
        # NOTE: This should be overridden.
        pass


class VirtualMachine( CMSComponent ):
    """A virtual machine, intended to run on a hypervisor. A wrapper class for
       the Host class."""

    vm_uuid = 0  # UNUSED: For ID purposes? Maybe name is enough.

    def __init__( self, node, vm_script=None, cmsnet_info={}, tenant_id=1 ):
        """
        Intialization

        node: Mininet node
        cmsnet_info: Dictionary of necessary information from CMSnet
        """
        assert isinstance(node, Host)
        CMSComponent.__init__( self, node, cmsnet_info )

        self._vm_script = vm_script
        self._vm_script_params = ConfigUpdatingDict(self)
        self._tenant_id = tenant_id
        self._hv = None
        self._is_paused = False

        self.config_hv_name = None   # temp holder for HV name in config
        self.config_is_paused = None # temp holder for paused status in config
        self.terms = []              # temp holder for terms to kill on removal

        #self.reload_temp_folder()
        self.create_temp_folder()

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
    def vm_script( self ):
        return self._vm_script

    @vm_script.setter
    def vm_script( self, vm_script ):
        if vm_script:
            if not vm_script in self._cmsnet_info["possible_scripts"]:
                error(self, "No such script '%s'." % (vm_script,))
                return
        self._vm_script = vm_script
        self.update_comp_config()

    @property
    def vm_script_params( self ):
        return self._vm_script_params

    @vm_script_params.setter
    def vm_script_params( self, vm_script_params ):
        self._vm_script_params = ConfigUpdatingDict(self, vm_script_params)
        self.update_comp_config()

    @property
    def tenant_id( self ):
        return self._tenant_id

    @property
    def MAC( self ):
        return self.node.MAC()

    @MAC.setter
    def MAC( self, mac ):
        oldmac = self.MAC
        if not isValidMAC(mac):
            error(self, "'%s' is not a valid MAC address." % (mac,))
            return
        err = self.node.setMAC(mac)
        if err:
            error(self, err)
            self.node.setMAC(oldmac)
        else:
            self.update_comp_config()
        if self.default_gateway:                         # Re-set table.
            self.default_gateway = self.default_gateway

    @property
    def IP( self ):
        return self.node.IP()

    @IP.setter
    def IP( self, ip ):
        oldip = self.IP
        oldpl = self.prefixLen
        prefixLen = self.prefixLen
        ipstr = ip
        if ip and '/' in ip:
            ip, pf = ip.split( '/' )
            prefixLen = int( pf )
        if not isValidIP(ip):
            error(self, "'%s' is not a valid (CIDR) IPv4 address." % (ipstr,))
            return
        err = self.node.setIP(getExpandedIP(ip), prefixLen=prefixLen)
        if err:
            error(self, err)
            self.node.setIP(oldip, prefixLen=oldpl)
        else:
            self.update_comp_config()
        if self.default_gateway:                         # Re-set table.
            self.default_gateway = self.default_gateway


    @property
    def prefixLen( self ):
        return int(self.node.intf().prefixLen)

    @prefixLen.setter
    def prefixLen( self, prefixLen ):
        try:
            prefixLen = int(prefixLen)
        except:
            error(self, "Prefix length '%s' should be integer." % (prefixLen,))
            return
        if prefixLen < 0 or prefixLen > 32:
            error(self, "Prefix length '%s' out of bounds." % (prefixLen,))
            return
        self.IP = "%s/%s" % (self.IP, prefixLen)

    @property
    def netmask( self ):
        return getNetmaskFromPrefixLen(self.prefixLen)

    @netmask.setter
    def netmask( self, netmask ):
        if not isValidIP(netmask):
            error(self, "'%s' is not a valid IPv4 address." % (netmask,))
            return
        elif not isValidNetmask(netmask):
            error(self, "'%s' is not a valid netmask address." % (netmask,))
            return
        self.prefixLen = getPrefixLenFromNetmask(netmask)

    @property
    def default_gateway( self ):
        try:
            default_route = self.node.params['defaultRoute']
            default_route_params = default_route.split()
            gateway = default_route_params[default_route_params.index("via")+1]
            return getExpandedIP(gateway)
        except:
            return None

    @default_gateway.setter
    def default_gateway( self, default_gateway ):
        if default_gateway is None:
            self.node.cmd( 'ip route del default' )
            self.node.params['defaultRoute'] = None
            self.update_comp_config()
            return
        elif not isValidIP(default_gateway):
            error(self, "'%s' is not a valid IPv4 address."%(default_gateway,))
            return
        elif not isInSameSubnet(default_gateway, self.IP, self.netmask):
            msg_args = (default_gateway, "%s/%s" % (self.IP, self.prefixLen))
            warn(self, "Gateway '%s' not in same subnet as %s." % msg_args)
        default_route = "dev %s via %s" % (self.node.intf(), default_gateway)
        err = self.node.setDefaultRoute(intf=default_route)
        if err:
            error(self, err)
            olddr = "dev %s via %s" % (self.node.intf(), self.default_gateway)
            self.node.setDefaultRoute(intf=olddr)
        else:
            self.node.params['defaultRoute'] = default_route
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
    def hv_dpid( self ):
        if isinstance(self.hv, Hypervisor):
            return self.hv.dpid
        return None

    @property
    def hv_port_to_vm( self ):
        if self.is_running() and not self.is_paused():
            intf = self.node.defaultIntf()
            intf_other = None
            assert intf is not None
            assert intf.link != None
            assert intf.link.intf1 == intf or intf.link.intf2 == intf
            assert intf.node == self.node
            if intf.link.intf1 == intf:
                intf_other = intf.link.intf2
            elif intf.link.intf2 == intf:
                intf_other = intf.link.intf1
            assert intf_other.node is self.hv.node
            return intf_other.name
        return None

    def __repr__( self ):
        "More informative string representation"
        # TODO: This should be different.
        return repr(self.node)

    def get_info( self ):
        "Get information to be sent with a CMS message to the controller."
        info = {
          'name'            : self.name,
          'mac_addr'        : self.MAC,
          'ip_addr'         : self.IP,
          'netmask'         : self.netmask,
          'default_gateway' : self.default_gateway,
          'hv_dpid'         : self.hv_dpid,
          'hv_port_to_vm'   : self.hv_port_to_vm,
        }
        return info

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        if not self.config_folder:
            return "./"+self.name+".config_vm"
        else:
            return self.config_folder+"/"+self.name+".config_vm"

    def set_comp_config( self, config ):
        "Set the configurations of this component to be saved."
        config["vm_script"] = self.vm_script
        config["vm_script_params"] = self.vm_script_params
        config["_tenant_id"] = self._tenant_id
        config["MAC"] = self.MAC
        config["IP"] = self.IP
        config["netmask"] = self.netmask
        config["default_gateway"] = self.default_gateway
        config["config_hv_name"] = self.hv_name
        config["config_is_paused"] = self.is_paused()

    def is_running( self ):
        "Test if this VM image is running (or inactive) on any hypervisor."
        return self.hv_name is not None

    def is_paused( self ):
        "Test if this VM image is paused (or running) on any hypervisor."
        return self.is_running() and self._is_paused

    def get_vm_script_cmd( self, script_type="start" ):
        "Get the bash command to call the VM script with."
        if not self.vm_script:
            return "echo \"No %s script.\"" % (script_type,)
        assert script_type in ["start", "pause", "resume", "stop", "check"]
        script_folder = self._cmsnet_info.get("script_folder")
        if not script_folder:
            script_folder = "."
        script_folder += "/vm_scripts"
        return "/".join([script_folder, self.vm_script, script_type])

    def get_autoexec_script_cmd( self, script_type="start" ):
        "Get the bash command to call the autoexec script with."
        autoexec_script = self._cmsnet_info.get("autoexec_script")
        if not autoexec_script:
            return ""
        assert script_type in ["start", "stop"]
        script_folder = self._cmsnet_info.get("script_folder")
        if not script_folder:
            script_folder = "."
        script_folder += "/autoexec_scripts"
        return "/".join([script_folder, autoexec_script, script_type])

    def get_vm_script_params( self ):
        "Get the parameters to run the VM script with."
        default_params = { 
          'HOME'            : self.get_temp_folder_path(),
          'NAME'            : self.name,
          'MAC'             : self.MAC,
          'IP'              : self.IP,
          'NETMASK'         : self.netmask,
          'DEFAULT_GATEWAY' : self.default_gateway, 
        }
        default_params.update(self.vm_script_params)
        return default_params

    def write_rc_file( self ):
        "Write the run control file for the script."
        params = self.get_vm_script_params()
        try:
            with open(self.get_temp_folder_path()+"/.cmsnetrc", "w") as f:
                for arg,val in params.items():
                    f.write("export %s=%s\n" % (arg, val))
                f.flush()
        except IOError:
            error_msg = "Unable to make rc file."
            config_error(self, error_msg)
            return

    def run_vm_script( self, script_type="start" ):
        "Run the VM script with preset parameters."
        if not self.vm_script:
            return
        temp_path = self.get_temp_folder_path()
        check_script_name = self.get_vm_script_cmd(script_type="check")
        script_name = self.get_vm_script_cmd(script_type=script_type)
        self.write_rc_file()

        init_cmd = "cd {0} && source .cmsnetrc && [ -x \"{1}\" ] && {1}"
        cmd = "{1} >> {0}/log.out 2>> {0}/log.err &"
        auto_start_cmd = self.get_autoexec_script_cmd(script_type="start")
        auto_stop_cmd = self.get_autoexec_script_cmd(script_type="stop")
        err = self.node.cmd(init_cmd.format(temp_path, check_script_name))
        if not err:
            if script_type == "start": self.node.cmd(auto_start_cmd)
            self.node.cmd(cmd.format(temp_path, script_name))
            if script_type == "stop": self.node.cmd(auto_stop_cmd)
        else:
            error(self, err)

    def cloneTo( self, new_vm ):
        "Clone information from this VM to the new VM image."
        assert new_vm is not None
        assert isinstance(new_vm, VirtualMachine)
        assert not new_vm.is_running()
        # Copied here to override any config loading
        new_vm.vm_script = self.vm_script
        new_vm.vm_script_params = self.vm_script_params
        new_vm._tenant_id = self._tenant_id

    def launchOn( self, hv ):
        "Initialize the VM on the input hypervisor."
        assert not self.is_running()
        assert hv is not None
        assert hv.is_enabled()
        self.hv = hv
        self.run_vm_script(script_type="start")
        self.vm_script_pid = self.node.lastPid

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
        self.run_vm_script(script_type="pause")

    def resume( self ):
        "Resume the VM."
        assert self.is_running()
        assert self.is_paused()
        self._is_paused = False
        self.update_comp_config()
        self.run_vm_script(script_type="resume")

    def stop( self ):
        "Stop running the VM."
        assert self.is_running()
        self.hv = None
        self.run_vm_script(script_type="stop")
        if self.vm_script_pid:
            self.node.cmd("kill -- -%s" % (self.vm_script_pid,))
            self.vm_script_pid = None

    def remove( self ):
        "Remove traces of the VM from existence."
        self.remove_comp_config()
        self.remove_temp_folder()

    def shutdown( self ):
        "Shutdown VM when CMSnet is shutting down."
        if not self.is_running():
            return
        self.lock_comp_config()    # Prevent adjustments to config file.
        self.stop()
        # self.store_temp_folder()


class Hypervisor( CMSComponent ):
    """A hypervisor that virtual machines run on. A wrapper class for the
       Switch class."""

    def __init__( self, node, cmsnet_info={}, vm_dist_limit=None ):
        """
        Intialization

        node: Mininet node
        cmsnet_info: Dictionary of necessary information from CMSnet
        vm_dist_limit: Hypervisor's personal VM capacity limit
        """
        assert isinstance(node, Switch) or "Switch" in type(node).__name__
        # That's a big old hack, but what really IS a switch?

        CMSComponent.__init__( self, node, cmsnet_info )

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
    def dpid( self ):
        return getattr(self.node, 'real_dpid', self.node.dpid)

    @dpid.setter
    def dpid( self, dpid ):
        self.node.dpid = dpid
        self.update_comp_config()

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

    def get_info( self ):
        "Get information to be sent with a CMS message to the controller."
        info = {
          'name'         : self.name,
          'dpid'         : self.dpid,
          'fabric_ports' : [self.name+"-eth1"],
        }
        return info

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        if not self.config_folder:
            return "./"+self.name+".config_hv"
        else:
            return self.config_folder+"/"+self.name+".config_hv"

    def set_comp_config( self, config ):
        "Set the configurations of this component to be saved."
        config["dpid"] = self.dpid
        config["vm_dist_limit"] = self.vm_dist_limit
        config["_enabled"] = self._enabled

    def get_num_VMs( self ):
        "Return the number of VMs running on this hypervisor."
        return len(self.nameToVMs)

    def is_full( self ):
        "Check if this hypervisor has reached its VM capacity limit."
        if self.vm_dist_limit:
            return self.get_num_VMs() >= self.vm_dist_limit
        else:
            net_vm_dist_limit = self._cmsnet_info.get("vm_dist_limit")
            if net_vm_dist_limit:
                return self.get_num_VMs() >= net_vm_dist_limit
            else:
                return False

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
