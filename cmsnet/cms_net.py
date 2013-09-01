"""

    Mininet: A simple networking testbed for OpenFlow/SDN!

author: Bob Lantz (rlantz@cs.stanford.edu)
author: Brandon Heller (brandonh@stanford.edu)

Mininet creates scalable OpenFlow test networks by using
process-based virtualization and network namespaces.

Simulated hosts are created as processes in separate network
namespaces. This allows a complete OpenFlow network to be simulated on
top of a single Linux kernel.

Each host has:

A virtual console (pipes to a shell)
A virtual interfaces (half of a veth pair)
A parent shell (and possibly some child processes) in a namespace

Hosts have a network interface which is configured via ifconfig/ip
link/etc.

This version supports both the kernel and user space datapaths
from the OpenFlow reference implementation (openflowswitch.org)
as well as OpenVSwitch (openvswitch.org.)

In kernel datapath mode, the controller and switches are simply
processes in the root namespace.

Kernel OpenFlow datapaths are instantiated using dpctl(8), and are
attached to the one side of a veth pair; the other side resides in the
host namespace. In this mode, switch processes can simply connect to the
controller via the loopback interface.

In user datapath mode, the controller and switches can be full-service
nodes that live in their own network namespaces and have management
interfaces and IP addresses on a control network (e.g. 192.168.123.1,
currently routed although it could be bridged.)

In addition to a management interface, user mode switches also have
several switch interfaces, halves of veth pairs whose other halves
reside in the host nodes that the switches are connected to.

Consistent, straightforward naming is important in order to easily
identify hosts, switches and controllers, both from the CLI and
from program code. Interfaces are named to make it easy to identify
which interfaces belong to which node.

The basic naming scheme is as follows:

    Host nodes are named h1-hN
    Switch nodes are named s1-sN
    Controller nodes are named c0-cN
    Interfaces are named {nodename}-eth0 .. {nodename}-ethN

Note: If the network topology is created using mininet.topo, then
node numbers are unique among hosts and switches (e.g. we have
h1..hN and SN..SN+M) and also correspond to their default IP addresses
of 10.x.y.z/8 where x.y.z is the base-256 representation of N for
hN. This mapping allows easy determination of a node's IP
address from its name, e.g. h1 -> 10.0.0.1, h257 -> 10.0.1.1.

Note also that 10.0.0.1 can often be written as 10.1 for short, e.g.
"ping 10.1" is equivalent to "ping 10.0.0.1".

Currently we wrap the entire network in a 'mininet' object, which
constructs a simulated network based on a network topology created
using a topology object (e.g. LinearTopo) from mininet.topo or
mininet.topolib, and a Controller which the switches will connect
to. Several configuration options are provided for functions such as
automatically setting MAC addresses, populating the ARP table, or
even running a set of terminals to allow direct interaction with nodes.

After the network is created, it can be started using start(), and a
variety of useful tasks maybe performed, including basic connectivity
and bandwidth tests and running the mininet CLI.

Once the network is up and running, test code can easily get access
to host and switch objects which can then be used for arbitrary
experiments, typically involving running a series of commands on the
hosts.

After all desired tests or activities have been completed, the stop()
method may be called to shut down the network.

"""

import os
import re
import select
import signal
from time import sleep
from itertools import chain

from mininet.cli import CLI
from mininet.log import info, warn, error, debug, output
from mininet.node import Host, Switch#, Dummy, POXNormalSwitch  # Uncomment !!
from mininet.link import Link, Intf
from mininet.util import quietRun, fixLimits, numCores, ensureRoot, moveIntf
from mininet.util import macColonHex, ipStr, ipParse, netParse, ipAdd
from mininet.term import cleanUpScreens, makeTerms
#from mininet.net import Mininet    # Uncomment later!!!

from cmsnet.cms_comp import CMSComponent, VirtualMachine, Hypervisor
from cmsnet.cms_log import config_error
import random
import socket
import json
defaultDecoder = json.JSONDecoder()

# For module class searching.
import mininet.net
import cmsnet.cms_comp
import cmsnet.cms_topo

# Patching. REMOVE AFTER CHANGES TO MININET AND UNCOMMENT ABOVE EDIT.
from cmsnet.mininet_node_patch import Dummy, POXNormalSwitch
from cmsnet.mininet_net_patch import MininetPatch as Mininet
import cmsnet.mininet_net_patch


# Mininet version: should be consistent with README and LICENSE
VERSION = "2.0.0.i.x.beta"

class CMSnet( object ):
    "Network emulation with hosts spawned in network namespaces."

    def __init__( self, new_config=False, config_folder=".",
                  vm_dist_mode="random", vm_dist_limit=10, msg_level="all",
                  net_cls=Mininet, vm_cls=VirtualMachine, hv_cls=Hypervisor,
                  controller_ip="127.0.0.1", controller_port=7790, **params):
        """Create Mininet object.
           new_config: True if we are using brand new configurations.
           config_folder: Folder where configuration files are saved/loaded.
           vm_dist_mode: Mode of how VMs are distributed amongst hypervisors
           vm_dist_limit: Limit of number of VMs on hypervisors in packed mode
           msg_level: CMS message handling level at controller
           net_cls: Mininet class.
           vm_cls: VM class.
           hv_cls: Hypervisor class.
           controller_ip = IP to connect to for the controller socket.
           controller_port = Port to connect to for the controller socket.
           params: extra paramters for Mininet"""
        self.new_config = new_config
        self.config_folder = config_folder
        self.vm_dist_mode = vm_dist_mode
        self.vm_dist_limit = vm_dist_limit
        self.msg_level = msg_level
        self.net_cls = net_cls
        self.vm_cls = vm_cls
        self.hv_cls = hv_cls
        self.controller_ip = controller_ip
        self.controller_port = controller_port
        self.params = params

        self.VMs = []
        self.HVs = []
        self.nameToComp = {}   # name to CMSComponent (VM/HV) objects 
        self.controller_socket = None

        self.last_hv = None
        self.hv_cycle = []
        self.cycle_pos = -1

        self.possible_modes = CMSnet.getPossibleVMDistModes()
        self.possible_levels = CMSnet.getPossibleCMSMsgLevels()
        self.possible_scripts = CMSnet.getPossibleVMScripts()

        # Config placeholders. To make the python interp happy.
        self._last_hv_name = None
        self._hv_cycle_names = None
        self._cycle_pos_temp = None

        self._allow_write_net_config = True
        if not self.new_config:
            self.check_net_config()
        self.mn = self.net_cls(**params)
        self.update_net_config()
        self.unlock_net_config()

    # BL: We now have four ways to look up components
    # This may (should?) be cleaned up in the future.
    def getCompByName( self, *args ):
        "Return component(s) with given name(s)"
        if len( args ) == 1:
            return self.nameToComp[ args[ 0 ] ]
        return [ self.nameToComp[ n ] for n in args ]

    def get( self, *args ):
        "Convenience alias for getCompByName"
        return self.getCompByName( *args )

    # Even more convenient syntax for node lookup and iteration
    def __getitem__( self, *args ):
        """net [ name ] operator: Return component(s) with given name(s)"""
        return self.getCompByName( *args )

    def __iter__( self ):
        "return iterator over components"
        #or dow we want to iterate of the keys i.e. comp.name like a dict
        for comp in chain( self.VMs, self.HVs ):
            yield comp.name

    def __len__( self ):
        "returns number of components in net"
        return len( self.VMs ) + len( self.HVs )

    def __contains__( self, item ):
        "returns True if net contains named component"
        return item in self.keys()

    def keys( self ):
        "return a list of all component names or net's keys"
        return list( self.__iter__() )

    def values( self ):
        "return a list of all components or net's values"
        return [ self[name] for name in self.__iter__() ]

    def items( self ):
        "return (key,value) tuple list for every component in net"
        return zip( self.keys(), self.values() )



    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Setup Commands
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def start( self ):
        "Start Mininet, hypervisors, and a connection to the controller."
        self.lock_net_config()
        self.mn.start()
        self.get_hypervisors()
        if not self.new_config:
            err1 = self.get_old_mode_params()
            err2 = self.get_old_VMs()
            if err1 or err2:
                self.stop()
                raise Exception("Stopping CMSnet. Please manually fix config.")
        self.setup_controller_connection()
        self.unlock_net_config()

    def stop( self ):
        "Stop Mininet, VMs, and the connection to the controller."
        self.lock_net_config()
        self.close_controller_connection()
        info( '*** Stopping %i VMs\n' % len( self.VMs ) )
        for vm in self.VMs:
            vm.shutdown()
        self.mn.stop()
        self.unlock_net_config()

    def run( self, test, *args, **kwargs ):
        "Perform a complete start/test/stop cycle."
        self.start()
        info( '*** Running test\n' )
        result = test( *args, **kwargs )
        self.stop()
        return result

    def get_config_file_name( self ):
        "Return the file name of the configuration file."
        return self.config_folder+"/cn.config_cmsnet"

    def lock_net_config( self ):
        "Lock the configuration file to prevent it from being written."
        self._allow_write_net_config = False

    def unlock_net_config( self ):
        "Unlock the configuration file to allow it to be written."
        self._allow_write_net_config = True

    def is_net_config_locked( self ):
        "Return whether the configuration file is locked from writing."
        return not self._allow_write_net_config

    def check_net_config( self ):
        "Check for any previous CMSnet configurations and adjust if necessary."
        self.lock_net_config()

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
            info("No previous config exists for CMSnet.\n")
            self.unlock_net_config()
            return

        # Part 2: Parse and apply from raw string
        config = {}
        try:
            config, l = defaultDecoder.raw_decode(config_raw)
            assert isinstance(config, dict), "Config not a dictionary."
            for attr in config:
                if attr.startswith("topo"):     # Handle separately.
                    pass
                elif attr.endswith("cls_name"):
                    pass
                elif isinstance(config[attr], basestring):
                    setattr(self, attr, str(config[attr]))
                else:
                    setattr(self, attr, config[attr])

            net_cls_name = config.get("net_cls_name")
            vm_cls_name = config.get("vm_cls_name")
            hv_cls_name = config.get("hv_cls_name")
            topo_cls_name = config.get("topo_cls_name")

            if net_cls_name:
                #self.net_cls = getattr(mininet.net, net_cls_name)
                # TODO: Change later when Mininet has correct methods.
                self.net_cls = getattr(cmsnet.mininet_net_patch, net_cls_name)
            if vm_cls_name:
                self.vm_cls = getattr(cmsnet.cms_comp, vm_cls_name)
            if hv_cls_name:
                self.hv_cls = getattr(cmsnet.cms_comp, hv_cls_name)
            if topo_cls_name:
                topo_cls = getattr(cmsnet.cms_topo, topo_cls_name)
                topo_opts = config.get("topo_opts", {})
                topo = topo_cls(**topo_opts)
                self.params.update({'topo': topo})
            else:
                warn("\nNo topology exists for CMSnet.\n")
        except:
            error_msg = "Config for CMSnet cannot be parsed."
            config_error(error_msg, config=config, config_raw=config_raw)
            return

    def update_net_config( self ):
        "Update the CMSnet configurations file."
        if self.is_net_config_locked():
            return

        # Part 1: Get config data and dump to string
        config = {}
        config_raw = None
        try:
            self.set_net_config(config)
            config_raw = json.dumps(config)
        except:
            error_msg = "Config for CMSnet cannot be created."
            config_error(error_msg, config=config)
            return

        # Part 2: Write to file
        try:
            with open(self.get_config_file_name(), "w") as f:
                f.write(config_raw)
                f.flush()
        except IOError:
            error_msg = "Unable to write to config file for CMSnet."
            config_error(error_msg, config_raw=config_raw)
            return

    def set_net_config( self, config ):
        "Set the configurations of CMSnet to be saved."
        config["vm_dist_mode"] = self.vm_dist_mode
        config["vm_dist_limit"] = self.vm_dist_limit
        config["msg_level"] = self.msg_level
        config["net_cls_name"] = self.net_cls.__name__
        config["vm_cls_name"] = self.vm_cls.__name__
        config["hv_cls_name"] = self.hv_cls.__name__
        config["controller_ip"] = self.controller_ip
        config["controller_port"] = self.controller_port
        if self.last_hv:
            config["_last_hv_name"] = self.last_hv.name
        if self.hv_cycle:
            config["_hv_cycle_names"] = [hv.name for hv in self.hv_cycle]
        if self.cycle_pos >= 0:
            config["_cycle_pos_temp"] = self.cycle_pos

        topo = self.mn.topo
        if topo:
            topo_opts = {}
            topo_opts["hv_num"] = topo.hv_num
            topo_opts["fb_num"] = topo.fb_num
            topo_opts["hopts"] = topo.hopts
            topo_opts["sopts"] = topo.sopts
            topo_opts["lopts"] = topo.lopts
            config["topo_cls_name"] = topo.__class__.__name__
            config["topo_opts"] = topo_opts

    def get_hypervisors( self ):
        "Collect all hypervisors."
        # HV don't need loading. Just attach to switch.
        for node_name in self.mn.nameToNode:
            node = self.mn.nameToNode[node_name]
            if node.params.get("cms_type") == "hypervisor":
                hv = self.hv_cls( node, self.config_folder)
                self.HVs.append(hv)
                self.nameToComp[ node_name ] = hv
                # If hv still needs config resuming:
                #    hv.lock_comp_config()
                #    hv.unlock_comp_config()

    def get_old_mode_params( self ):
        "Extract old configuration parameters for VM distribution modes."
        err = False
        if self._last_hv_name is not None:
            self.last_hv = self.nameToComp.get(self._last_hv_name)
            if not self.last_hv:
                error("Last HV %s does not exist.\n" % self._last_hv_name)
                err = True
        if self._hv_cycle_names is not None:
            self.hv_cycle = []
            for hv_name in self._hv_cycle_names:
                hv = self.nameToComp.get(hv_name)
                if not hv:
                    error("Cycle HV %s does not exist.\n" % hv_name)
                    err = True
                else:
                    self.hv_cycle.append(hv)
        if self._cycle_pos_temp is not None:
            self.cycle_pos = self._cycle_pos_temp
            if self.vm_dist_mode == "cycle":
                pos_range = range(0, len(self._hv_cycle_names))
            elif self.vm_dist_mode == "cycleall":
                pos_range = range(0, len(self.cn.HVs))
            else:
                pos_range = range(0, self.cycle_pos+1)
            if pos_range and self.cycle_pos not in pos_range:
                range_str = "range(0, %d)" % len(pos_range)
                error('cycle_pos %s not in %s\n' % (self.cycle_pos, range_str))
                err = True
        if err:
            error("\nError occurred when getting vm_dist_mode parameters!\n")
        return err

    def get_old_VMs( self ):
        "Collect all previously saved VMs."
        # I want to use glob here instead...
        #     http://stackoverflow.com/questions/3207219/
        # Well, this works too.
        #     http://stackoverflow.com/questions/3964681/
        vm_config_suffix = ".config_vm"
        err = False
        orig_last_hv = self.last_hv
        for file_name in os.listdir(self.config_folder):
            if file_name.endswith(vm_config_suffix):
                vm_name = file_name[:-len(vm_config_suffix)]
                vm = self.createVM(vm_name)
                vm.lock_comp_config()
                if vm.config_hv_name:
                    hv = self.nameToComp.get(vm.config_hv_name)
                    if not hv:
                        error_msg = "%s does not exist." % hv
                        error("Cannot run %s: %s\n" % (vm, error_msg))
                    elif not isinstance(hv, Hypervisor):
                        error_msg = "%s is not a hypervisor." % hv
                        error("Cannot run %s: %s\n" % (vm, error_msg))
                    elif not hv.is_enabled():
                        error_msg = "%s is not enabled." % hv
                        error("Cannot run %s: %s\n" % (vm, error_msg))
                    else:
                        self.launchVM(vm, hv)
                    if not vm.is_running():
                        error("VM %s is not launched!\n" % vm)
                        err = True
                    else:
                        if vm.config_is_paused:
                            self.pauseVM(vm)
                            if not vm.is_paused():
                                error("VM %s is not paused!\n" % vm)
                                err = True
                vm.unlock_comp_config()
        if err:
            error("\nError occurred when resuming VMs!\n")
        self.last_hv = orig_last_hv
        return err

    def setup_controller_connection( self ):
        "Start the connection to the controller."
        # Change self.controller_socket from None to the actual socket.
        ip = self.controller_ip
        port = self.controller_port
        try:
            sock = socket.create_connection((ip, port))
            self.controller_socket = sock
        except Exception,e:
            warn("\nCannot connect to controller: %s\n" % str(e))

    def close_controller_connection( self ):
        "Close the connection to the controller."
        if self.controller_socket:
            try:
                self.controller_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass  # If other side already shut down, leave it.
            self.controller_socket.close()
            self.controller_socket = None

    def send_msg_to_controller(self, cmd_type, vm):
        "Send a CMS message to the controller."
        msg = {
          'CHANNEL'   : 'CMS',
          'cmd'       : cmd_type,
          'msg_level' : self.msg_level,
          'host'      : vm.name,
          'new_hv'    : vm.hv_name
        }
        if self.controller_socket:
            try:
                self.controller_socket.send(json.dumps(msg))
            except Exception,e:
                warn("\nCannot send to controller: %s\n" % str(e))

    def makeTerms( self, comp, term='xterm' ):
        "Spawn terminals for the given component."
        new_terms = makeTerms( [ comp.node ], term=term )
        self.mn.terms += new_terms
        if isinstance(comp, VirtualMachine):
            comp.terms += new_terms

    def makeX11( self, comp, cmd ):
        "Create an X11 tunnel for the given component."
        new_terms = runX11( comp.node, cmd )
        self.mn.terms += new_terms
        if isinstance(comp, VirtualMachine):
            comp.terms += new_terms

    @classmethod
    def getPossibleVMDistModes( cls ):
        "Dynamically obtain all possible VM distribution mode names."
        vm_dist_prefix = "_vm_dist_"
        method_list = dir(cls)   #cls.__dict__
        dist_mode_names = []
        for method in method_list:
            if method.startswith(vm_dist_prefix):
                mode_name = method[len(vm_dist_prefix):]
                dist_mode_names.append( mode_name )
        return dist_mode_names

    @classmethod
    def getPossibleCMSMsgLevels( cls ):
        "Dynamically obtain all possible message levels for the controller."
        return ["all", "instantiated", "migrated", "destroyed", "none"]

    @classmethod
    def getPossibleVMScripts( cls ):
        "Dynamically obtain all possible scripts for VMs to run."
        return ["pizza"]   # TODO: Implement me!







    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Testing Stuff
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def addHVSwitch( self, name, cls=None, **params ):
        """Add HV-switch. FOR TESTING PURPOSES ONLY.
           name: name of switch to add
           cls: custom switch class/constructor (optional)
           returns: added switch
           side effect: params has extra parameter cmsnet."""
        if self.built:
            error("Cannot add switch; Mininet already built.")
            return
        params.update({"cms_net": "hypervisor"})
        return self.mn.addSwitch(name, cls=cls, **params)

    def addFabricSwitch( self, name, **params ):
        """Add fabric-switch. FOR TESTING PURPOSES ONLY.
           name: name of switch to add
           cls: custom switch class/constructor (optional)
           returns: added switch
           side effect: params has extra parameter cmsnet."""
        if self.built:
            error("Cannot add switch; Mininet already built.")
            return
        params.update({"cms_net": "fabric", "cls": POXNormalSwitch})
        return self.mn.addSwitch(name, **params)







  
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS VM Distribution Mode Handling
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def _getNextDefaultHV( self, old_hv=None ):
        """
        Using the distribution mode, get the next default HV

        old_hv: The last HV the VM was on. None if VM is not yet running.
        """
        if len(self.HVs) == 0:
            error_msg = "No hypervisor exists"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        if len(self.HVs) == 1 and old_hv and old_hv in self.HVs:
            error_msg = "No other hypervisor exists."
            error("\nCannot get HV: %s\n" % error_msg)
            return

        vm_dist_handler = getattr(self, "_vm_dist_" + self.vm_dist_mode, None)
        if not vm_dist_handler:
            error_msg = "VM distribution mode %s invalid." % self.vm_dist_mode
            error("\nCannot get HV: %s\n" % error_msg)
            return

        hv = vm_dist_handler(old_hv=old_hv)
        return hv

    def isHVFull( self, hv ):
        "Check if hypervisor has reached its VM capacity limit (packed mode)."
        hv_limit = hv.vm_dist_limit
        limit = hv_limit if hv_limit else self.vm_dist_limit
        return hv.get_num_VMs() >= limit

    def _vm_dist_random( self, old_hv=None ):
        "Choose a random HV."
        hv_list = [hv for hv in self.HVs if hv is not old_hv]
        rand_hv = random.choice(hv_list)
        return rand_hv

    def _vm_dist_sparse( self, old_hv=None ):
        "Choose HVs sparsely and evenly."
        hv_list = [hv for hv in self.HVs if hv is not old_hv]
        min_hv = min(hv_list, key=lambda hv: hv.get_num_VMs())
        return min_hv

    def _vm_dist_packed( self, old_hv=None ):
        "Choose HVs so that VMs are packed together."
        hv_list = [hv for hv in self.HVs if hv is not old_hv]
        avail_hvs = [hv for hv in hv_list if not self.isHVFull(hv)]
        if len(avail_hvs) == 0:
            error_msg = "No hypervisor is available."
            error("\nCannot get HV: %s\n" % error_msg)
            return
        max_hv = max(avail_hvs, key=lambda hv: hv.get_num_VMs())
        return max_hv

    def _vm_dist_same( self, old_hv=None ):
        "Choose an HV the same as the last chosen one."
        if not self.last_hv:
            error_msg = "No hypervisor last chosen."
            error("\nCannot get HV: %s\n" % error_msg)
            return
        if self.last_hv is old_hv:
            error_msg = "Last chosen hypervisor same as current one."
            error("\nCannot get HV: %s\n" % error_msg)
            return
        same_hv = self.last_hv
        return same_hv

    def _vm_dist_different( self, old_hv=None ):
        "Choose a random HV different from the last chosen one."
        hv_list = [hv for hv in self.HVs if hv is not old_hv]
        if self.last_hv:
            hv_list = [hv for hv in hv_list if hv is not self.last_hv]
        diff_hv = random.choice(hv_list)
        return diff_hv

    def _vm_dist_cycle( self, old_hv=None ):
        "Choose HVs in a specific cycle."
        if not self.hv_cycle:
            error_msg = "No cycle to choose from."
            error("\nCannot get HV: %s\n" % error_msg)
            return
        cycle_list = [hv for hv in self.hv_cycle if hv is not old_hv]
        if len(cycle_list) == 0:
            error_msg = "No other hypervisor exists in cycle."
            error("\nCannot get HV: %s\n" % error_msg)
            return

        self.cycle_pos %= len(cycle_list)
        cycle_hv = cycle_list[self.cycle_pos]
        self.cycle_pos += 1
        self.cycle_pos %= len(self.hv_cycle)
        return cycle_hv

    def _vm_dist_cycleall( self, old_hv=None ):
        "Choose HVs in a cycle from all HVs."
        hv_list = [hv for hv in self.HVs if hv is not old_hv]

        self.cycle_pos %= len(hv_list)
        full_cycle_hv = hv_list[self.cycle_pos]
        self.cycle_pos += 1
        self.cycle_pos %= len(self.HVs)
        return full_cycle_hv














    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main VM Commands (ZZZ)
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def not_implemented( self ):
        print "NOT IMPLEMENTED YET."

    debug_flag1 = True   # Print statements everywhere.



    def createVM( self, vm_name, vm_script=None, vm_cls=None, **params ):
        "Create a virtual machine image."
        if self.debug_flag1:
            args = (vm_name, vm_script, vm_cls, params)
            print "EXEC: createVM(%s, %s, %s, %s):" % args

        assert vm_name not in self.nameToComp
        assert not vm_cls or issubclass(vm_cls, VirtualMachine)

        # TODO: Handle vm_script (assert and passing in).

        host, host_terms = self.mn.createHostAtDummy(vm_name, **params)
        if not vm_cls:
            vm_cls = self.vm_cls
        vm = vm_cls(host, self.config_folder)
        vm.terms = host_terms
        self.VMs.append(vm)
        self.nameToComp[ vm_name ] = vm

        return vm

    def cloneVM( self, old_vm, new_vm_name=None ):
        "Clone a virtual machine image."
        if self.debug_flag1:
            print "EXEC: cloneVM(%s, %s):" % (old_vm, new_vm_name)

        if new_vm_name is None:          
            new_vm_name = old_vm.name
            while new_vm_name in self.nameToComp:
                new_vm_name += ".cp"

        assert old_vm in self.VMs
        assert new_vm_name not in self.nameToComp
        assert isinstance(old_vm, VirtualMachine)

        vm_cls = old_vm.__class__
        vm_script = None
        params = old_vm.node.params.copy()
        for p in ['ip', 'mac', 'cores']:
            if p in params:
                del params[p]
        params['cls'] = old_vm.node.__class__
        params['inNamespace'] = old_vm.node.inNamespace

        new_vm = self.createVM(new_vm_name, vm_script, vm_cls, **params)
        assert isinstance(new_vm, VirtualMachine)
        old_vm.cloneTo(new_vm)     # Leave complexity in here.

        return new_vm

    def launchVM( self, vm, hv=None ):
        "Initialize the created VM on a hypervisor."
        if self.debug_flag1:
            print "EXEC: launchVM(%s, %s):" % (vm, hv)

        if hv is None:
            hv = self._getNextDefaultHV()
            if hv is None:       # Some error occurred.
                return           # Return and do nothing.

        assert vm in self.VMs
        assert hv in self.HVs
        assert isinstance(vm, VirtualMachine)
        assert isinstance(hv, Hypervisor)
        assert not vm.is_running()
        assert hv.is_enabled()

        self.mn.moveLink(vm.node, hv.node)
        vm.launchOn(hv)
        self.last_hv = hv
        self.send_msg_to_controller("instantiated", vm)

    def migrateVM( self, vm, hv ):
        "Migrate a running image to another hypervisor."
        if self.debug_flag1:
            print "EXEC: migrateVM(%s, %s):" % (vm, hv)

        if hv is None:
            hv = self._getNextDefaultHV(old_hv=vm.hv)
            if hv is None:       # Some error occurred.
                return           # Return and do nothing.

        assert vm in self.VMs
        assert hv in self.HVs
        assert isinstance(vm, VirtualMachine)
        assert isinstance(hv, Hypervisor) 
        assert vm.is_running()
        assert hv.is_enabled()

        if not vm.is_paused():
            self.mn.moveLink(vm.node, hv.node)
        vm.moveTo(hv)
        self.last_hv = hv
        self.send_msg_to_controller("migrated", vm)

    def pauseVM( self, vm ):
        "Pause a currently running VM."
        if self.debug_flag1:
            print "EXEC: pauseVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)
        assert vm.is_running()
        assert not vm.is_paused()

        vm.pause()
        self.mn.removeLink(vm.node)
        self.send_msg_to_controller("paused", vm)

    def resumeVM( self, vm ):
        "Resume a currently paused VM."
        if self.debug_flag1:
            print "EXEC: resumeVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)
        assert vm.is_running()
        assert vm.is_paused()

        self.mn.moveLink(vm.node, vm.hv.node)
        vm.resume()
        self.send_msg_to_controller("resumed", vm)

    def stopVM( self, vm ):
        "Stop a running image."
        if self.debug_flag1:
            print "EXEC: stopVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)
        assert vm.is_running()

        if vm.is_paused():
            self.resumeVM(vm)
        vm.stop()
        self.mn.removeLink(vm.node)
        self.send_msg_to_controller("destroyed", vm)

    def deleteVM( self, vm ):
        "Remove the virtual machine image from the hypervisor."
        if self.debug_flag1:
            print "EXEC: deleteVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)

        if vm.is_running():
            self.stopVM(vm)

        if vm.terms:
            if self.debug_flag1:
                info( '*** Stopping %i terms\n' % len(vm.terms) )
            for term in vm.terms:
                try:
                    os.kill( term.pid, signal.SIGKILL )
                except:
                    pass
                self.mn.terms.remove(term)
            vm.terms = []

        if self.debug_flag1:
            info( '*** Stopping host: %s\n' % vm.name )
        vm.node.terminate()
        self.mn.hosts.remove(vm.node)
        del self.mn.nameToNode[ vm.node.name ]

        info( '*** Removing VM: %s\n' % vm.name )
        self.VMs.remove(vm)
        del self.nameToComp[ vm.name ]
        vm.remove()

















    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main Toggle Commands
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def changeVMDistributionMode( self, vm_dist_mode, vm_dist_args=None ):
        "Change the mode of VM distribution across hypervisors."
        if self.debug_flag1:
            args = (vm_dist_mode, vm_dist_args)
            print "EXEC: changeVMDistributionMode(%s, %s):" % args

        assert vm_dist_mode in self.possible_modes

        self.vm_dist_mode = vm_dist_mode
        if vm_dist_args:
            assert isinstance(vm_dist_args, dict)
            vm_dist_limit = vm_dist_args.get("vm_dist_limit")
            last_hv = vm_dist_args.get("last_hv")
            hv_cycle = vm_dist_args.get("hv_cycle")
            cycle_pos = vm_dist_args.get("cycle_pos")

            if vm_dist_limit is not None:
                assert vm_dist_mode == "packed"
                assert vm_dist_limit > 0
                self.vm_dist_limit = vm_dist_limit
            if last_hv is not None:
                assert vm_dist_mode in ["same", "different"]
                assert isinstance(last_hv, Hypervisor) 
                self.last_hv = last_hv
            if hv_cycle is not None:
                assert vm_dist_mode == "cycle"
                assert isinstance(hv_cycle, list)
                assert len(hv_cycle) > 0
                for hv in hv_cycle:
                    assert isinstance(hv, Hypervisor)
                self.hv_cycle = hv_cycle
            if cycle_pos is not None:
                assert vm_dist_mode in ["cycle", "cycleall"]
                assert cycle_pos >= 0
                if vm_dist_mode == "cycle":
                    assert cycle_pos < len(self.hv_cycle)
                elif vm_dist_mode == "cycleall":
                    assert cycle_pos < len(self.HVs)
                self.cycle_pos = cycle_pos
            else:
                if vm_dist_mode == "cycle":
                    self.cycle_pos %= len(self.hv_cycle)
                elif vm_dist_mode == "cycleall":
                    self.cycle_pos %= len(self.HVs)

        self.update_net_config()

    def changeCMSMsgLevel( self, msg_level ):
        "Change the level of CMS message handling at the controller."
        if self.debug_flag1:
            print "EXEC: changeCMSMsgLevel(%s):" % msg_level
        
        assert msg_level in self.possible_levels
        
        self.msg_level = msg_level
        self.update_net_config()















    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main HV Commands
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def evictVMsFromHV( self, hv ):
        "Evict all VMs running on the hypervisor off to other VMs."
        if self.debug_flag1:
            print "EXEC: evictVMsFromHV(%s):" % hv

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor)
        assert hv.is_enabled()

        if hv.get_num_VMs() == 0:
            warn("VMs already evicted from %s\n" % hv)
            return
        for vm in hv.nameToVMs.values():
            self.migrateVM(vm)

    def invictVMsToHV( self, hv, max_num_vms=1 ):
        "Invict a number of inactive VMs to run on the hypervisor."
        if self.debug_flag1:
            print "EXEC: invictVMsToHV(%s):" % (hv, max_num_vms)

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor)
        assert hv.is_enabled()
        assert max_num_vms > 0

        count = 0
        for vm in self.VMs:
            if not vm.is_running():
                self.launchVM(vm, hv)
                count += 1
            if count == max_num_vms:
                break
        info("Invicted %d VMs into %s\n" % (count, hv))

    def enableHV( self, hv ):
        "Enable a hypervisor."
        if self.debug_flag1:
            print "EXEC: enableHV(%s):" % hv

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor) 
        assert not hv.is_enabled()

        hv.enable()

    def disableHV( self, hv ):
        "Disable a hypervisor."
        if self.debug_flag1:
            print "EXEC: disableHV(%s):" % hv

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor) 
        assert hv.is_enabled()

        self.evictVMsFromHV(hv)
        hv.disable()

    def killHV( self, hv ):
        "Kill a hypervisor."
        if self.debug_flag1:
            print "EXEC: killHV(%s):" % hv

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor) 
        assert hv.is_enabled()

        for vm in hv.nameToVMs.values():
            self.stopVM(vm)
        hv.disable()














