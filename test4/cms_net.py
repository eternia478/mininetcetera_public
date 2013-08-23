import os
import re
import select
import signal
from time import sleep
from itertools import chain
# @GLY
import random

from mininet.cli import CLI
from mininet.log import info, warn, error, debug, output
from mininet.node import Host, Switch
from mininet.link import Link, Intf
from mininet.util import quietRun, fixLimits, numCores, ensureRoot, moveIntf
from mininet.util import macColonHex, ipStr, ipParse, netParse, ipAdd

from mininet.term import cleanUpScreens, makeTerms
from mininet.net import Mininet
from cmsnet.cms_comp import CMSComponent, VirtualMachine, Hypervisor
import socket
import json
defaultDecoder = json.JSONDecoder()

# For module class searching.
import mininet.net
import cmsnet.cms_comp
import cmsnet.cms_topo

# Patching. REMOVE AFTER CHANGES TO MININET AND UNCOMMENT ABOVE EDIT.
from mininet_node_patch import Dummy, POXNormalSwitch


# Mininet version: should be consistent with README and LICENSE
VERSION = "2.0.0.i.x.beta"

class CMSnet( object ):
    "Network emulation with hosts spawned in network namespaces."
    # @GLY
    def __init__( self, vm_dist_mode="random",vm_dist_limit=10,
                  new_config=False, config_folder=".",
                  net_cls=Mininet, vm_cls=VirtualMachine, hv_cls=Hypervisor,
                  controller_ip="127.0.0.1", controller_port=7790, msglevel =
                  None, **params):
        """Create Mininet object.
           vm_dist_mode: Mode of how VMs are distributed amongst hypervisors
           new_config: True if we are using brand new configurations.
           config_folder: Folder where configuration files are saved/loaded.
           net_cls: Mininet class.
           vm_cls: VM class.
           hv_cls: Hypervisor class.
           controller_ip = IP to connect to for the controller socket.
           controller_port = Port to connect to for the controller socket.
           params: extra paramters for Mininet"""
        self.vm_dist_mode = vm_dist_mode
        self.vm_dist_limit = vm_dist_limit
        self.config_folder = config_folder
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
        self.possible_modes = ["packed", "sparse", "random"]
        
        # @GLY
        self.msglevel = msglevel
        self.possible_level = {"instantiated","migrated","destroyed"}

        
            
        if not new_config:
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
        # @ GLY
        # self.mn.build()
        self.mn.start()
        self.get_hypervisors()
        # we did not delete VM when we just shutdown or something, so we need not to recreate them
        self.get_old_VMs()
        self.setup_controller_connection()

    def stop( self ):
        "Stop Mininet, VMs, and the connection to the controller."
        info( '*** Stopping %i VMs\n' % len( self.VMs ) )
        
        for vm in self.VMs:
            vm.shutdown()
            self.stopVM( vm.node.name )
        self.mn.stop()
        self._tempStopDummy()
        # @GLY
        self.close_controller_connection()
        
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
            with open(self.config_folder+"/cm.config_cmsnet", "r") as f:
                config_raw = f.read()
                # print "raw is: ",config_raw
                
                
                
                config = {}
                if config_raw:
                    config, l = defaultDecoder.raw_decode(config_raw)
                    # print config 
                    # print l
                    
                    
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
                #print config
             
                # @GLY
                topo_cls_name = config.get("topo_cls")
                # print type(topo_cls_name)
                # print topo_cls_name
                
                if topo_cls_name:
                    # print "tag 1"
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
        
        # print "flag 2"
        
        f = open(self.config_folder+"/cm.config_cmsnet", "w")
        config = {}
        config["vm_dist_mode"] = self.vm_dist_mode
        config["net_cls"] = self.net_cls.__name__
        config["vm_cls"] = self.vm_cls.__name__
        config["hv_cls"] = self.hv_cls.__name__
        config["controller_ip"] = self.controller_ip
        config["controller_port"] = self.controller_port
        # @GLY
        config["msglevel"] = self.msglevel

        topo = self.mn.topo
        
        # print "mn.topo is ", topo
        
        topo_opts = {}
        if topo:
            topo_opts["hv_num"] = topo.hv_num
            topo_opts["fb_num"] = topo.fb_num
            topo_opts["hopts"] = topo.hopts
            topo_opts["sopts"] = topo.sopts
            topo_opts["lopts"] = topo.lopts
        # @GLY
        if topo:
            config["topo_cls"] = topo.__class__.__name__
       
        # print "topocls_name : ",topo.__class__.__name__
        
        
        config["topo_opts"] = topo_opts
        # @GLY: why must we use the JSON
        # f.write(config)
        f.write(json.dumps(config))
        f.flush()
        f.close()

    def get_hypervisors( self ):
        "Collect all hypervisors."
        # HV don't need loading. Just attach to switch.
        if not self.vm_dist_mode:
            self.get_hypervisors_beta()
            return
        if self.mn.topo is not None:
            assert hasattr(self.mn.topo, 'hvSwitches')
            for hv_name in self.mn.topo.hvSwitches():
                sw = self.mn.nameToNode[hv_name]
                hv = self.hv_cls(sw, self.config_folder)
                self.HVs.append(hv)
                self.nameToComp[ hv_name ] = hv
        else:
            return
            # print "Sorry, we don't support hacky approaches. Muahaha!"
            # print "Please leave a topo after the beep. BEEEEEEEP!"

 
    def get_old_VMs( self ):
        "Collect all previously saved VMs."
        # I want to use glob here instead...
        #     http://stackoverflow.com/questions/3207219/
        # Well, this works too.
        #     http://stackoverflow.com/questions/3964681/
        err = False
        for file_name in os.listdir(self.config_folder):
            if file_name.endswith(".config_vm"):
                vm_name = file_name[:-10]
                self.createVM(vm_name)
                vm = self.nameToComp[ vm_name ]
                # if vm.config_hv_name:
                # @GLY
                if vm.config_hv_name:
                    self.launchVM( vm_name, vm.config_hv_name )
                    if not vm.is_running():
                        err = True
        if err:
            error("\nError occurred when resuming VMs!\n")


    def setup_controller_connection( self ):
        "Start the connection to the controller."
        # Change self.controller_socket from None to the actual socket.
        try:
            ip = self.controller_ip
            port = self.controller_port
            sock = socket.create_connection((ip, port))
            self.controller_socket = sock
        except Exception,e:
            warn("\nCannot connect to controller: %s\n" % str(e))

    def close_controller_connection( self ):
        "Close the connection to the controller."
        if self.controller_socket:
            self.controller_socket.close()
            self.controller_socket = None








    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Testing Stuff
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def get_hypervisors_beta( self ):
        "Collect all hypervisors."
        # TODO: Untested version. Please test this at some point.
        # HV don't need loading. Just attach to switch.
        # Default? In case added more nodes after topo...
        for node_name in self.mn.nameToNode:
            node = self.mn.nameToNode[hv_name]
            if node.params.get("cms_type") == "hypervisor":
                hv = hv_cls( node, self.config_folder)
                self.HVs.append(hv)
                self.nameToComp[ node_name ] = hv

    def addHVSwitch( self, name, cls=None, **params ):
        """Add HV-switch. FOR TESTING PURPOSES ONLY.
           name: name of switch to add
           cls: custom switch class/constructor (optional)
           returns: added switch
           side effect: params has extra parameter cmsnet."""
        if self.mn.built:
            error("Cannot add switch; Mininet already built.")
            return
        params.update({"cms_net": "hypervisor"})
        # @GLY
        sw = self.mn.addSwitch(name, cls=cls, **params)
        hv = self.hv_cls(sw)
        self.HVs.append(hv)
        self.nameToComp[ name ] = hv
        return sw

    def addFabricSwitch( self, name, **params ):
        """Add fabric-switch. FOR TESTING PURPOSES ONLY.
           name: name of switch to add
           cls: custom switch class/constructor (optional)
           returns: added switch
           side effect: params has extra parameter cmsnet."""
        if self.mn.built:
            error("Cannot add switch; Mininet already built.")
            return
        # @GLY -- Pox normal switch has not been completed
        params.update({"cms_net": "fabric", "cls": POXNormalSwitch})  
        return self.mn.addSwitch(name, **params)


    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # File system
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    


    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main Commands (ZZZ)
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def not_implemented( self ):
        print "NOT IMPLEMENTED YET."

    debug_flag1 = True   # Print statements everywhere.



    def createVM( self, vm_name, cls = None, **params ):
        "Create a virtual machine image."
        if self.debug_flag1:
            print "EXEC: createVM(%s):" % vm_name

        assert vm_name not in self.nameToComp

        # self.not_implemented()
        host = self._createHostAtDummy(vm_name, cls = cls, **params)
        # @GLY
        vm = self.vm_cls(host, self.config_folder)
        self.VMs.append(vm)
        self.nameToComp[ vm_name ] = vm
        return host
    
    # @GLY
    def cloneVM (self, vm_name, new_name = None, cls = None, **params ):
        "Create a virtual machine image."
        if self.debug_flag1:
            print "EXEC: cloneVM(%s):" % vm_name
        assert vm_name in self.nameToComp
        assert new_name not in self.nameToComp
        vm_old = self.nameToComp.get(vm_name)
        assert isinstance(vm_old, VirtualMachine)
        
        # self.not_implemented()
        if new_name == None:          
            new_name = vm_name + '.cp'
            while new_name in self.nameToComp:
                new_name = new_name + '.cp'
              
        else:
            if new_name in self.nameToComp:
                return "ERROR: name has existed already"  
        print new_name           
        host = self.createVM(new_name, cls = cls, **params)
        # @GLY
        vm_new = self.vm_cls(host, self.config_folder)
        vm_old = self.nameToComp.get(vm_name)
        vm_old.cloneto(vm_new)
        return host
    
    
    """    
    def cloneVM( self, vm1_name, vm2_name ):
        "Clone a virtual machine image."
        if self.debug_flag1:
            print "EXEC: cloneVM(%s):" % vm_name

        assert vm1_name in self.nameToComp
        assert vm2_name not in self.nameToComp
        vm1 = self.nameToComp.get(vm1_name)
        assert isinstance(vm1, VirtualMachine)

        self.not_implemented()
    """        
    
    
    def launchVM( self, vm_name, hv_name= None ):
        "Initialize the created VM on a hypervisor."
        if self.debug_flag1:
            print "EXEC: launchVM(%s, %s):" % (vm_name, hv_name)
        
        
        #@GLY       
        if hv_name == None:
          if self.vm_dist_mode == 'random':
            temp_num = ramdom.randint(0,len(self.HVs)-1)
            hv = self.HVs[temp_num]
            hv_name = hv.node.name
          
          if self.vm_dist_mode == 'sparse':
            temp_num = len( self.HVs[0].nameToVMs)
            hv_name = self.HVs[0].node.name
            for hv in self.HVs:
              if len (hv.nameToVMs) <= temp_num:
                 hv_name = hv.node.name                      
          
          if self.vm_dist_mode == 'packed':
            temp_num = len( self.HVs[0].nameToVMs)
            hv_name = None
            for hv in self.HVs:
              if len (hv.nameToVMs) >= temp_num:
                if len (hv.nameToVMs) < self.vm_dist_limit:
                  if hv.vm_limit and len (hv.nameToVMs)< hv.vm_limit:
                    hv_name = hv.node.name 
            if hv_name == None:
              return "ERROR: No hv is avaliable" 
       
       
        assert vm_name in self.nameToComp
        assert hv_name in self.nameToComp
        vm = self.nameToComp.get(vm_name)
        hv = self.nameToComp.get(hv_name)
        assert isinstance(vm, VirtualMachine)
        assert isinstance(hv, Hypervisor)
        assert not vm.is_running()
        assert hv.is_enabled()

        # self.not_implemented()
        
        dummy = self.mn.nameToNode.get("dummy", None)
        
        for intf in vm.node.intfs.values():
          print "old link: ", intf.link
          if intf.link.intf1 == intf: 
            vm_intf = intf
            old_intf = intf.link.intf2
            # print "Old node is: ", old_intf.node
                      
          if intf.link.intf2 == intf:
            vm_intf = intf 
            old_intf = intf.link.intf1
            # print "Old node is: ", old_intf.node             
        vm_intf_name =  intf.name
        self._moveLink(vm.node, hv.node, vm_intf_name)
        print "new link: ", vm_intf.link
        
        # print "New node is: ", old_intf.node
        vm.launch(hv)  
        # @GLY
        "Sending msg to comtroller"
        msg = {
          'CHANNEL' : 'CMS',
          'msglevel': self.msglevel,
          'cmd' : 'instantiated',
          'host' : vm_name,
           #'old_hv': old_intf.node.name,
          'new_hv': hv_name
        }      
        if self.controller_socket:
            self.controller_socket.send(json.dumps(msg))       
        
    def migrateVM( self, vm_name, hv_name ):
        "Migrate a running image to another hypervisor."
        if self.debug_flag1:
            print "EXEC: migrateVM(%s, %s):" % (vm_name, hv_name)

        assert vm_name in self.nameToComp
        assert hv_name in self.nameToComp
        vm = self.nameToComp.get(vm_name)
        hv = self.nameToComp.get(hv_name)
        assert isinstance(vm, VirtualMachine)
        assert isinstance(hv, Hypervisor) 
        assert vm.is_running()
        assert hv.is_enabled()

        # self.not_implemented()
        
          
        for intf in vm.node.intfs.values():
          print "old link: ", intf.link
          if intf.link.intf1 == intf:
            vm_intf = intf
            ## old_intf = intf.link.intf2
            ## print "Old node is: ", old_intf.node
          if intf.link.intf2 == intf:
            vm_intf = intf
            ## old_intf = intf.link.intf1
            ## print "Old node is: ", old_intf.node
        
        vm_intf_name = vm_intf.name
        self._moveLink(vm.node, hv.node, vm_intf_name)
        print "new link: ", vm_intf.link
        # print "New node is: ", old_intf.node
        vm.moveTo(hv)
        
        # @GLY
        "Sending msg to comtroller"
        msg = {
          'CHANNEL' : 'CMS',
          'cmd' : 'migrated',
          'msglevel': self.msglevel,
          'host' : vm_name,
          ## 'old_hv':  old_intf.node.name,
          'new_hv': hv_name
        }
        self.controller_socket.send(json.dumps(msg))       

       

    def stopVM( self, vm_name ):
        "Stop a running image."
        if self.debug_flag1:
            print "EXEC: stopVM(%s):" % vm_name

        assert vm_name in self.nameToComp
        vm = self.nameToComp.get(vm_name)
        assert isinstance(vm, VirtualMachine)
        # @GLY
        if not vm.is_running():
            return
        #assert vm.is_running()

        # self.not_implemented()
        
        dummy = self.mn.nameToNode.get("dummy", None)
        for intf in vm.node.intfs.values():
          print "old link: ", intf.link
          if intf.link.intf1 == intf:
            vm_intf = intf
            ## old_intf = intf.link.intf2
            ## print "Old node is: ", old_intf.node
          if intf.link.intf2 == intf:
            vm_intf = intf
            ## old_intf = intf.link.intf1
            ## print "Old node is: ", old_intf.node
        vm_intf_name = vm_intf.name
        self._removeLink(vm.node, vm_intf_name)
        print "new link: ", vm_intf.link
        vm.stop() 
        
        # @GLY
        "Sending msg to comtroller"
        msg = {
          'CHANNEL' : 'CMS',
          'cmd' : 'destroyed',
          'msglevel': self.msglevel,
          'host' : vm_name,
          ## 'old_hv': old_node.name,
          'new_hv': dummy.name,
        }
        if self.controller_socket:
            self.controller_socket.send(json.dumps(msg))       
        
        
       

    def deleteVM( self, vm_name ):
        "Remove the virtual machine image from the hypervisor."
        if self.debug_flag1:
            print "EXEC: deleteVM(%s):" % vm_name

        assert vm_name in self.nameToComp
        vm = self.nameToComp.get(vm_name)
        assert isinstance(vm, VirtualMachine)
        if vm.is_running():
            self.stopVM(vm_name)

        # self.not_implemented()
        
        self.stopVM(vm_name)
        vm = self.nameToComp[vm_name]
        self.VMs.remove(vm)
        del self.nameToComp[ vm_name ]
        info( '*** Stopping host: %s\n' % vm_name ) 
        vm.node.terminate()
        # Remove the file
        os.remove(vm.get_config_file_name()) 
        
        """
        self.stopVM(vm_name)
        vm = self.nameToComp[vm_name]
        self.VMs.remove(vm)
        del self.nameToComp[ vm_name ]

        info( '*** Stopping host: %s\n' % vm_name ) )
        # FIXME: Get this node's xterm.
        vm.node.terminate()

        # TODO: Remove file!
        """
    """    
    def cloneVM( self, vm1_name, vm2_name ):
        "Clone a virtual machine image."
        if self.debug_flag1:
            print "EXEC: cloneVM(%s):" % vm_name

        assert vm1_name in self.nameToComp
        assert vm2_name not in self.nameToComp
        vm1 = self.nameToComp.get(vm1_name)
        assert isinstance(vm1, VirtualMachine)

        self.not_implemented()
    """    

    def changeVMDistributionMode( self, vm_dist_mode, vm_dist_limit = None ):
        "Change the mode of VM distribution across hypervisors."
        if self.debug_flag1:
            print "EXEC: changeVMDistributionMode(%s):" % vm_dist_mode

        assert vm_dist_mode in self.possible_modes

        self.vm_dist_mode = vm_dist_mode
        self.update_net_config()
        # @GLY
        if (vm_dist_mode =="packed") and  vm_dist_limit:
          self.vm_dist_limit = vm_dist_limit
        
    # @GLY
    def changeLevel( self, msglevel):
        "Change the msglevel."
        if self.debug_flag1:
            print "EXEC: changeLevel(%s):" % msglevel

        assert msglevel in self.possible_level

        self.msglevel = msglevel
        self.update_net_config()
       
          
    def enableHV( self, hv_name ):  ##???
        "Enable a hypervisor."
        if self.debug_flag1:
            print "EXEC: enableHV(%s):" % hv_name

        assert hv_name in self.nameToComp
        hv = self.nameToComp.get(hv_name)
        assert isinstance(hv, Hypervisor) 
        assert not hv.is_enabled()

        hv.enable()

    def disableHV( self, hv_name ):
        "Disable a hypervisor."
        if self.debug_flag1:
            print "EXEC: disableHV(%s):" % hv_name

        assert hv_name in self.nameToComp
        hv = self.nameToComp.get(hv_name)
        assert isinstance(hv, Hypervisor) 
        assert hv.is_enabled()
        hv.disable()



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
        info( '\n*** Adding dummy:\n' )
        dummy = self._addDummy()
        # self.mn.terms += makeTerms( [dummy], 'dummy' )

    def _tempStopDummy(self):
        info( '\n' )
        info( '*** Stopping %i dummies\n' % 1 )
        dummy = self.mn.nameToNode.get("dummy")
        info( dummy.name + ' ' )
        dummy.terminate()






    def _addDummy( self, name='dummy', cls=Dummy, **params ):
        """Add dummy.
           dummy: Dummy class"""
        if not cls:
            cls = Dummy                  # Any other possible classes?
        dummy_new = cls( name, **params )
        ##self.dummies.append( dummy_new ) # Dunno if we need more dummies.
        self.mn.nameToNode[ name ] = dummy_new
        return dummy_new

    def _createHostAtDummy( self, hostName , **params):
        """
        Add a host node to Mininet and link it to the dummy.

        hostName: name of the host
        """
        if self.debug_flag1:
            print "EXEC: createHostAtDummy(%s):" % hostName

        # Part 0: Main assertions.
        assert hostName not in self.mn.nameToNode
        # @GLY
        # assert self.mn.built

        # Part 1: Getting dummy.
        dummy = self.mn.nameToNode.get("dummy", None)
        if dummy is None:
            error('dummy node does not exist\n')
            # return
            # @ GLY
            dummy = self._addDummy()
        assert isinstance(dummy, Dummy)

        # The following corresponds to code in self.build()

        # if self.topo:
        #     self.buildFromTopo( self.topo )
        info( '*** Adding host: %s\n' % hostName )
        host = self.mn.addHost( hostName )
        info( '*** Adding link: (%s, %s) ' % ( host.name, dummy.name ) )
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










