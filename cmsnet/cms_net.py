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
from mininet.node import Host, Switch#, POXNormalSwitch
from mininet.link import Link, Intf
from mininet.util import quietRun, fixLimits, numCores, ensureRoot, moveIntf
from mininet.util import macColonHex, ipStr, ipParse, netParse, ipAdd
from mininet.term import cleanUpScreens, makeTerms
from mininet.net import Mininet

from cmsnet.cms_comp import CMSComponent, VirtualMachine, Hypervisor
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

        self.last_HV = None
        self.controller_socket = None
        self.possible_modes = CMSnet.getPossibleVMDistModes()
        self.possible_levels = CMSnet.getPossibleCMSMsgLevels()
        self.possible_scripts = CMSnet.getPossibleVMScripts()

        if not self.new_config:
            self.check_net_config()
        self.mn = self.net_cls(**params)
        self.update_net_config()

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
        self._tempStartDummy()
        self.mn.start()
        self.get_hypervisors()
        self.get_old_VMs()
        self.setup_controller_connection()

    def stop( self ):
        "Stop Mininet, VMs, and the connection to the controller."
        self.close_controller_connection()
        info( '*** Stopping %i VMs\n' % len( self.VMs ) )
        for vm in self.VMs:
            vm.shutdown()
        self.mn.stop()
        self._tempStopDummy()

    def run( self, test, *args, **kwargs ):
        "Perform a complete start/test/stop cycle."
        self.start()
        info( '*** Running test\n' )
        result = test( *args, **kwargs )
        self.stop()
        return result

    def check_net_config( self ):
        "Check for any previous CMSnet configurations and adjust if necessary."
        try:
            with open(self.config_folder+"/cn.config_cmsnet", "r") as f:
                config_raw = f.read()
                config = {}
                if config_raw:
                    config, l = defaultDecoder.raw_decode(config_raw)
                for attr in config:
                    if attr.startswith("topo"):       # Handle separately.
                        pass
                    elif attr == "net_cls":
                        cls = getattr(mininet.net, config[attr])
                        setattr(self, attr, cls)
                    elif attr.endswith("cls"):
                        cls = getattr(cmsnet.cms_comp, config[attr])
                        setattr(self, attr, cls)
                    elif isinstance(config[attr], basestring):
                        setattr(self, attr, str(config[attr]))
                    else:
                        setattr(self, attr, config[attr])
                topo_cls_name = config.get("topo_cls")
                if topo_cls_name:
                    topo_cls = getattr(cmsnet.cms_topo, topo_cls_name)
                    topo_opts = config.get("topo_opts", {})
                    topo = topo_cls(**topo_opts)
                    self.params.update({'topo': topo})
                else:
                    warn("\nNo topology exists for CMSnet\n")
                f.close()                
        except IOError as e:
            info("\nNo config exists for CMSnet\n")

    def update_net_config( self ):
        "Update the CMSnet configurations file."
        f = open(self.config_folder+"/cn.config_cmsnet", "w")
        config = {}
        config["vm_dist_mode"] = self.vm_dist_mode
        config["vm_dist_limit"] = self.vm_dist_limit
        config["msg_level"] = self.msg_level
        config["net_cls"] = self.net_cls.__name__
        config["vm_cls"] = self.vm_cls.__name__
        config["hv_cls"] = self.hv_cls.__name__
        config["controller_ip"] = self.controller_ip
        config["controller_port"] = self.controller_port

        topo = self.mn.topo
        if topo:
            topo_opts = {}
            topo_opts["hv_num"] = topo.hv_num
            topo_opts["fb_num"] = topo.fb_num
            topo_opts["hopts"] = topo.hopts
            topo_opts["sopts"] = topo.sopts
            topo_opts["lopts"] = topo.lopts
            config["topo_cls"] = topo.__class__.__name__
            config["topo_opts"] = topo_opts

        f.write(json.dumps(config))
        f.flush()
        f.close()

    def get_hypervisors( self ):
        "Collect all hypervisors."
        # HV don't need loading. Just attach to switch.
        for node_name in self.mn.nameToNode:
            node = self.mn.nameToNode[node_name]
            if node.params.get("cms_type") == "hypervisor":
                hv = self.hv_cls( node, self.config_folder)
                self.HVs.append(hv)
                self.nameToComp[ node_name ] = hv

    def get_old_VMs( self ):
        "Collect all previously saved VMs."
        # I want to use glob here instead...
        #     http://stackoverflow.com/questions/3207219/
        # Well, this works too.
        #     http://stackoverflow.com/questions/3964681/
        vm_config_suffix = ".config_vm"
        err = False
        for file_name in os.listdir(self.config_folder):
            if file_name.endswith(vm_config_suffix):
                vm_name = file_name[:-len(vm_config_suffix)]
                vm = self.createVM(vm_name)
                if vm.config_hv_name:
                    hv = self.nameToComp.get(vm.config_hv_name)
                    if hv:
                        self.launchVM( vm, hv )
                    if not vm.is_running():
                        err = True
        if err:
            error("\nError occurred when resuming VMs!\n")

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
        pass











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

    def _getNextDefaultHV( self ):
        "Using the distribution mode, get the next default HV"
        if len(self.HVs) == 0:
            error_msg = "No hypervisor exists"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        vm_dist_handler = getattr(self, "_vm_dist_" + self.vm_dist_mode, None)
        if not vm_dist_handler:
            error_msg = "VM distribution mode %s invalid" % self.vm_dist_mode
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        hv = vm_dist_handler()
        return hv

    def isHVFull( self, hv ):
        "Check if hypervisor has reached its VM capacity limit (packed mode)."
        hv_limit = hv.vm_dist_limit
        limit = hv_limit if hv_limit else self.vm_dist_limit
        return len(hv.nameToVMs) >= limit

    def _efficientPackedDistMode( self ):
        "UNUSED. An efficient version of the packed mode (loops only once)."
        temp_num = 0
        hv_name = None
        for hv in self.HVs:   # Somehow, while loops suck (not in C?)
            vm_num = len(hv.nameToVMs)
            if vm_num >= temp_num:
                if not self.isHVFull(hv):
                    temp_num = vm_num
                    hv_name = hv.name
        if hv_name is None:
            error_msg = "No hypervisor is available"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        return hv_name

    def _vm_dist_random( self ):
        "Choose a random HV."
        rand_hv = random.choice(self.HVs)
        return rand_hv

    def _vm_dist_sparse( self ):
        "Choose HVs sparsely and evenly."
        min_hv = min(self.HVs, key=lambda hv: len(hv.nameToVMs))
        return min_hv

    def _vm_dist_packed( self ):
        "Choose HVs so that VMs are packed together."
        # return self._efficientPackedDistMode()
        avail_hvs = [hv for hv in self.HVs if not self.isHVFull(hv)]
        if len(avail_hvs) == 0:
            error_msg = "No hypervisor is available"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        max_hv = max(avail_hvs, key=lambda hv: len(hv.nameToVMs))
        return max_hv

    def _vm_dist_same( self ):
        "Choose an HV the same as the last chosen one."
        if not self.last_HV:
            error_msg = "No hypervisor last chosen"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        same_hv = self.last_HV
        return same_hv

    def _vm_dist_different( self ):
        "Choose a random HV different from the last chosen one."
        if not self.last_HV:
            error_msg = "No hypervisor last chosen"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        diff_hv = random.choice([hv for hv in self.HVs if hv != self.last_HV])
        return diff_hv

    def _vm_dist_next( self ):
        "Choose HVs in a cycle."
        if not self.last_HV:
            error_msg = "No hypervisor last chosen"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        last_hv_index = self.HVs.index(self.last_HV)
        next_hv_index = (last_hv_index + 1) % len(self.HVs)
        next_hv = self.HVs[next_hv_index]
        return next_hv

    def _vm_dist_previous( self ):
        "Choose HVs in a cycle, rotating in reverse."
        if not self.last_HV:
            error_msg = "No hypervisor last chosen"
            error("\nCannot get HV: %s.\n" % error_msg)
            return
        last_hv_index = self.HVs.index(self.last_HV)
        prev_hv_index = (last_hv_index - 1) % len(self.HVs)
        prev_hv = self.HVs[prev_hv_index]
        return prev_hv












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

        host = self._createHostAtDummy(vm_name, **params)
        if not vm_cls:
            vm_cls = self.vm_cls
        vm = vm_cls(host, self.config_folder)
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

        self._moveLink(vm.node, hv.node)
        vm.launch(hv)
        self.last_HV = hv
        self.send_msg_to_controller("instantiated", vm)

    def migrateVM( self, vm, hv ):
        "Migrate a running image to another hypervisor."
        if self.debug_flag1:
            print "EXEC: migrateVM(%s, %s):" % (vm, hv)

        assert vm in self.VMs
        assert hv in self.HVs
        assert isinstance(vm, VirtualMachine)
        assert isinstance(hv, Hypervisor) 
        assert vm.is_running()
        assert hv.is_enabled()

        self._moveLink(vm.node, hv.node)
        vm.moveTo(hv)
        self.send_msg_to_controller("migrated", vm)

    def stopVM( self, vm ):
        "Stop a running image."
        if self.debug_flag1:
            print "EXEC: stopVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)
        assert vm.is_running()

        vm.stop()
        self._removeLink(vm.node)
        self.send_msg_to_controller("destroyed", vm)

    def deleteVM( self, vm ):
        "Remove the virtual machine image from the hypervisor."
        if self.debug_flag1:
            print "EXEC: deleteVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)
        if vm.is_running():
            self.stopVM(vm)

        # self.not_implemented()
        
        self.stopVM(vm)
        self.VMs.remove(vm)
        del self.nameToComp[ vm.name ]
        info( '*** Stopping host: %s\n' % vm.name ) 
        vm.node.terminate()
        # Remove the file
        os.remove(vm.get_config_file_name()) 

        """
        # NOTE: many details on this one is hard to do, so
        #  we'll leave it for now. We need to remove intfs, processes,
        #  xterms, and do a bunch of stuff. 

        self.stopVM(vm_name)
        vm = self.nameToComp[vm_name]
        self.VMs.remove(vm)
        del self.nameToComp[ vm_name ]

        info( '*** Stopping host: %s\n' % vm_name ) )
        # FIXME: Get this node's xterm.
        vm.node.terminate()

        # TODO: Remove file!
        """

    def pauseVM( self, vm ):
        "Pause a currently running VM."
        if self.debug_flag1:
            print "EXEC: pauseVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)
        assert vm.is_running()
        #assert not vm.is_paused()

        self.not_implemented()

    def resumeVM( self, vm ):
        "Resume a currently paused VM."
        if self.debug_flag1:
            print "EXEC: resumeVM(%s):" % vm

        assert vm in self.VMs
        assert isinstance(vm, VirtualMachine)
        assert vm.is_running()
        #assert vm.is_paused()

        self.not_implemented()
















    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main Toggle Commands
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def changeVMDistributionMode( self, vm_dist_mode, vm_dist_limit=None ):
        "Change the mode of VM distribution across hypervisors."
        if self.debug_flag1:
            args = (vm_dist_mode, vm_dist_limit)
            print "EXEC: changeVMDistributionMode(%s, %s):" % args

        assert vm_dist_mode in self.possible_modes

        self.vm_dist_mode = vm_dist_mode
        if vm_dist_mode == "packed" and vm_dist_limit:
            assert vm_dist_limit > 0
            self.vm_dist_limit = vm_dist_limit
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

        self.not_implemented()

    def invictVMsToHV( self, hv, num_vms=1 ):
        "Invict a number of inactive VMs to run on the hypervisor."
        if self.debug_flag1:
            print "EXEC: invictVMsToHV(%s):" % (hv, num_vms)

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor)
        assert hv.is_enabled()
        assert num_vms > 0

        self.not_implemented()

    def enableHV( self, hv ):
        "Enable a hypervisor."
        if self.debug_flag1:
            print "EXEC: enableHV(%s):" % hv

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor) 
        assert not hv.is_enabled()

        hv.enable()
        self.not_implemented()

    def disableHV( self, hv ):
        "Disable a hypervisor."
        if self.debug_flag1:
            print "EXEC: disableHV(%s):" % hv

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor) 
        assert hv.is_enabled()

        hv.disable()
        self.not_implemented()

    def killHV( self, hv ):
        "Kill a hypervisor."
        if self.debug_flag1:
            print "EXEC: killHV(%s):" % hv

        assert hv in self.HVs
        assert isinstance(hv, Hypervisor) 
        assert hv.is_enabled()

        self.not_implemented()



























    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Helper Commands to be pushed into Mininet (YYY)
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    """
    NOTE: Please move the other patch code into Mininet. The code directly
          below is modified to be compatible here.
          Also, make the following changes in mininet.net.Mininet:
           - Import Switch and Dummy from mininet.node module
           - Add a self.dummies = [] attribute in __init__()
           - Add the following to the top of build():
                 info( '\n*** Adding dummy:\n' )
                 self.addDummy()
           - Add the following to the bottom of startTerms():
                 self.terms += makeTerms( self.dummies, 'dummy' )
           - Add the following into the bottom of stop() before "Done":
                 info( '\n' )
                 info( '*** Stopping %i dummies\n' % len(self.dummies) )
                 for dummy in self.dummies:
                     info( dummy.name + ' ' )
                     dummy.terminate()
          And make the following changes in this class:
           - Remove above patch importing and import the real POXNormalSwitch
           - Remove the call to self._tempStartDummy() in start():
           - Remove the call to self._tempStopDummy() in stop():
           - Edit all self._moveLink and whatnot to self.mn.moveLink()
           - Remove the below code after making sure everything runs correctly.
    """









    def _tempStartDummy(self):
        info( '*** Adding dummy\n' )
        dummy = self._addDummy()
        if self.mn.xterms:
            self.mn.terms += makeTerms( [dummy], 'dummy' )

    def _tempStopDummy(self):
        info( '\n' )
        info( '*** Stopping %i dummies\n' % 1 )
        dummy = self.mn.nameToNode.get("dummy")
        info( dummy.name + ' ' )
        dummy.terminate()
        info( '\n*** Done\n' )






    def _addDummy( self, name='dummy', cls=Dummy, **params ):
        """Add dummy.
           dummy: Dummy class"""
        if not cls:
            cls = Dummy                  # Any other possible classes?
        dummy_new = cls( name, **params )
        ##self.dummies.append( dummy_new ) # Dunno if we need more dummies.
        self.mn.nameToNode[ name ] = dummy_new
        return dummy_new

    def _createHostAtDummy( self, hostName, **params ):
        """
        Add a host node to Mininet and link it to the dummy.

        hostName: name of the host
        params: parameters for host
        """
        if self.debug_flag1:
            print "EXEC: createHostAtDummy(%s):" % hostName

        # Part 0: Main assertions.
        assert hostName not in self.mn.nameToNode
        assert self.mn.built

        # Part 1: Getting dummy.
        dummy = self.mn.nameToNode.get("dummy", None)
        if dummy is None:
            error('dummy node does not exist\n')
            return
        assert isinstance(dummy, Dummy)

        # The following corresponds to code in self.build()

        # if self.topo:
        #     self.buildFromTopo( self.topo )
        info( '*** Adding host: %s\n' % hostName )
        host = self.mn.addHost( hostName, **params )
        info( '*** Adding link: (%s, %s)\n' % ( host.name, dummy.name ) )
        hostPort = host.newPort()
        dummyPort = dummy.newPort()
        self.mn.addLink( host, dummy, hostPort, dummyPort )

        # if ( self.inNamespace ):
        #     self.configureControlNetwork()        
        if ( self.mn.inNamespace ):
            self.mn.configureControlNetwork()

        # info( '*** Configuring hosts\n' )
        # self.configHosts()
        info( '*** Configuring host: %s\n' % host.name )
        intf = host.defaultIntf()
        if intf:
            host.configDefault()
        else:       # Don't configure nonexistent intf
            host.configDefault( ip=None, mac=None ) 
        host.cmd( 'ifconfig lo up' )

        # if self.xterms:
        #     self.startTerms()
        if self.mn.xterms:
            if 'DISPLAY' not in os.environ:
                error( "Error starting terms: Cannot connect to display\n" )
                return
            info( "*** Running term on %s\n" % os.environ[ 'DISPLAY' ] )
            self.mn.terms += makeTerms( [host], 'host' )

        # if self.autoStaticArp:
        #     self.staticArp()
        if self.mn.autoStaticArp:
            for dst in self.mn.hosts:
                if host != dst:
                    host.setARP( ip=dst.IP(), mac=dst.MAC() )
                    dst.setARP( ip=host.IP(), mac=host.MAC() )

        # self.built = True
        self.mn.built = True
        
        return host

    def _moveLink( self, node1, node2, intf1_name=None, intf2_name=None ):
        """
        Move a host node to destination node in Mininet.

        node1: Moving node instance.
        node2: Destination node instance.
        intf1_name: Moving node interface name. Default if None.
        intf2_name: Destination node interface name. Default if None.
        """
        if self.debug_flag1:
            args = (node1, node2, intf1_name, intf2_name)
            print "EXEC: moveLink(%s, %s, %s, %s):" % args

        # Part 0: Main assertions.
        assert isinstance(node1, Host)
        assert isinstance(node2, Switch) or isinstance(node2, Dummy)
        assert not intf1_name or intf1_name in node1.nameToIntf
        assert not intf2_name or intf2_name not in node2.nameToIntf

        # Part 1: Extracting intf1 information.
        intf1 = node1.intf(intf=intf1_name)  # <- Uses defaultIntf if None.
        assert intf1 is not None
        intf1_name = intf1_name if intf1_name else intf1.name
        assert intf1.link != None
        assert intf1.link.intf1 == intf1 or intf1.link.intf2 == intf1
        assert intf1.node == node1
        intf1_other = None
        if intf1.link.intf1 == intf1:
            intf1_other = intf1.link.intf2
        elif intf1.link.intf2 == intf1:
            intf1_other = intf1.link.intf1
        node1_other = intf1_other.node
        intf1_name_other = intf1_other.name
        intf1_port_other = node1_other.ports[intf1_other]

        # Special case: Node already connected to other node.
        if node1_other == node2:
            if not intf2_name or intf2_name == intf1_name_other:
                warn('connection already established\n')
                return

        # Part 1.5: Call detach() on switch.
        if hasattr(node1_other, 'detach'):
            if self.debug_flag1: 
                print "Detach %s from %s" % (intf1_other, node1_other)
            node1_other.detach(intf1_other)

        # Part 2: Exchange information between node1_other and node2.
        del node1_other.intfs[ intf1_port_other ]
        del node1_other.ports[ intf1_other ]
        del node1_other.nameToIntf[ intf1_name_other ]
        intf2_port = node2.newPort()          # For now, just assign new port.
        intf2 = intf1_other
        if not intf2_name:
            intf2_name = "%s-eth%d" % (node2.name, intf2_port)
        intf2.rename(intf2_name)
        intf2.node = node2
        node2.intfs[ intf2_port ] = intf2
        node2.ports[ intf2 ] = intf2_port
        node2.nameToIntf[ intf2_name ] = intf2

        # Part 3: Moving intf1_other to intf2 by namespace.
        debug( '\nmoving', intf2, 'into namespace for', node2, '\n' )
        moveIntf( intf2_name, node2, srcNode=node1_other )

        # Part 3.5: Call detach() on switch.
        if hasattr(node2, 'attach'):
            if self.debug_flag1:
                print "Attach %s to %s" % (intf2, node2)
            node2.attach(intf2)

    def _removeLink( self, node, intf_name=None, remove_only_once=True ):
        """
        Remove host node from topology in Mininet (link to dummy).

        node: Removed node instance.
        intf_name: Removed node interface name. Default if None.
        remove_only_once: Invoke special case (not removing nodes on dummy).
        """
        if self.debug_flag1:
            args = (node, intf_name)
            print "EXEC: removeLink(%s, %s):" % args

        # Part 0: Main assertions.
        assert isinstance(node, Host)
        assert not intf_name or intf_name in node.nameToIntf

        # Part 1: Getting dummy.
        dummy = self.mn.nameToNode.get("dummy")
        if dummy is None:
            error('dummy node does not exist\n')
            return
        assert isinstance(dummy, Dummy)

        # Part 1.5: Checking intf information.
        intf = node.intf(intf=intf_name)  # <- Uses defaultIntf if None.
        assert intf is not None
        intf_name = intf_name if intf_name else intf.name

        # Special case: Node already connected to dummy.
        if remove_only_once:
            assert intf.link != None
            assert intf.link.intf1 == intf or intf.link.intf2 == intf
            assert intf.node != dummy
            if intf.link.intf1.node == dummy or intf.link.intf2.node == dummy:
                warn('intf %s already removed\n' % intf_name)
                return

        # Part 2: Extracting dummy information and calling moveLink().
        dummy_intf_port = dummy.newPort()
        dummy_intf_name = 'dummy-eth' + str(dummy_intf_port)
        self._moveLink(node, dummy, intf_name, dummy_intf_name)

    def _swapLink( self, node1, node2, intf1_name=None, intf2_name=None ):
        """
        Swap position of two host nodes in Mininet.

        node1: First swapping node instance.
        node2: Second swapping node instance.
        intf1_name: First swapping node interface name. Default if None.
        intf2_name: Second swapping node interface name. Default if None.
        """
        if self.debug_flag1:
            args = (node1, node2, intf1_name, intf2_name)
            print "EXEC: swapLink(%s, %s, %s, %s):" % args

        # Part 0: Main assertions.
        assert isinstance(node1, Host)
        assert isinstance(node2, Host)
        assert not intf1_name or intf1_name in node1.nameToIntf
        assert not intf2_name or intf2_name in node2.nameToIntf

        # Part 1: Extracting intf1 information.
        intf1 = node1.intf(intf=intf1_name)  # <- Uses defaultIntf if None.
        assert intf1 is not None
        intf1_name = intf1_name if intf1_name else intf1.name
        assert intf1.link != None
        assert intf1.link.intf1 == intf1 or intf1.link.intf2 == intf1
        assert intf1.node == node1
        intf1_other = None
        if intf1.link.intf1 == intf1:
            intf1_other = intf1.link.intf2
        elif intf1.link.intf2 == intf1:
            intf1_other = intf1.link.intf1
        node1_other = intf1_other.node
        intf1_name_other = intf1_other.name

        # Part 2: Extracting intf2 information.
        intf2 = node2.intf(intf=intf2_name)  # <- Uses defaultIntf if None.
        assert intf2 is not None
        intf2_name = intf2_name if intf2_name else intf2.name
        assert intf2.link != None
        assert intf2.link.intf1 == intf2 or intf2.link.intf2 == intf2
        assert intf2.node == node2
        intf2_other = None
        if intf2.link.intf1 == intf2:
            intf2_other = intf2.link.intf2
        elif intf2.link.intf2 == intf2:
            intf2_other = intf2.link.intf1
        node2_other = intf2_other.node
        intf2_name_other = intf2_other.name

        # Part 3: Calling removeLink() and moveLink().
        self._removeLink(node1, intf1_name, remove_only_once=False)
        self._moveLink(node2, node1_other, intf2_name, intf1_name_other)
        self._moveLink(node1, node2_other, intf1_name, intf2_name_other)











