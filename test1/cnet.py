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
from mininet.util import quietRun, fixLimits, numCores, ensureRoot
from mininet.util import macColonHex, ipStr, ipParse, netParse, ipAdd
from mininet.term import cleanUpScreens, makeTerms
from mininet.net import Mininet
from comp import CMSNode, VirtualMachine, Hypervisor
import socket
import json
import sys

defaultDecoder = json.JSONDecoder()

class CMSnet( object ):
    "Network emulation with hosts spawned in network namespaces."

    def __init__( self, vm_dist_mode="random",
                  new_config=False, config_folder=".",
                  net_cls=Mininet, vm_cls=VirtualMachine, hv_cls=Hypervisor,
                  controller_ip="127.0.0.1", controller_port=7790, **params):
        self.net_cls = net_cls
        self.vm_cls = vm_cls
        self.hv_cls = hv_cls
        self.controller_ip = controller_ip
        self.controller_port = controller_port
        self.params = params
        self.VMs = []
        self.HVs = []
        self.nameToComp = {}   # name to CMSNode (VM/HV) objects
        self.controller_socket = None
        self.mn = self.net_cls(**params)
        

    def start( self ):
        "Start Mininet, hypervisors, and a connection to the controller."
        # self.mn.start()
        self.mn.build()
        self.setup_controller_connection()

    def stop( self ):
        "Stop Mininet, VMs, and the connection to the controller."
        
        info( '*** Stopping %i VMs\n' % len( self.VMs ) )
        for vm in self.VMs:
            self.stopVM( vm.node.name )
        self.mn.stop()
        self.close_controller_connection()

    def setup_controller_connection( self ):
        "Start the connection to the controller."
        # Change self.controller_socket from None to the actual socket.
        try:
            ip = self.controller_ip
            port = self.controller_port
            sock = socket.create_connection((ip, port))
            self.controller_socket = sock
            print >>sys.stderr, "== Connected =="
            msg = {
                'CHANNEL' : '',
                'cmd' : 'join_channel',
                'channel' : 'CMS',
                'json' : True,
            }
            sock.send(json.dumps(msg))
        except Exception,e:
            warn("\nCannot connect to controller: %s\n" % str(e))

    def close_controller_connection( self ):
        "Close the connection to the controller."
        if self.controller_socket:
            print >>sys.stderr, "== Disconnected =="
            self.controller_socket.close()
            self.controller_socket = None


    def addHVSwitch( self, name, cls=None, **params ):
        # @gly
        if self.mn.built:
            error("Cannot add switch; Mininet already built.")
            return
        params.update({"cms_net": "hypervisor"})
        
        sw = self.mn.addSwitch(name, cls=cls, **params)
        
        # print "type of sw is: ", type(sw)
        hv = self.hv_cls(sw)
        self.HVs.append(hv)
        self.nameToComp[ name ] = hv
        
        
        return sw

    def addFabricSwitch( self, name, **params ):
        if self.mn.built:
            error("Cannot add switch; Mininet already built.")
            return
        params.update({"cms_net": "fabric"})
        return self.mn.addSwitch(name, **params) 


    def not_implemented( self ):
        print "NOT IMPLEMENTED YET."

    debug_flag1 = True   # Print statements everywhere.
    
    def createVM( self, vm_name , cls = None, **params):
        "Create a virtual machine image."
        if self.debug_flag1:
            print "EXEC: createVM(%s):" % vm_name

        assert vm_name not in self.nameToComp
        self.not_implemented()
        # Please see the codes below about createHostAtDummt(in Mininet.net.py)
        host = self.mn.createHostAtDummy(vm_name, cls = cls, **params )
        print type(host)
        
        vm = self.vm_cls(host)
        self.VMs.append(vm)
        self.nameToComp[ vm_name ] = vm
        
        return host
    
    def launchVM( self, vm_name, hv_name ):
        "Initialize the created VM on a hypervisor."
        "we just know the name of a node..."       
        if self.debug_flag1:
            print "EXEC: launchVM(%s, %s):" % (vm_name, hv_name)
        assert vm_name in self.nameToComp
        assert hv_name in self.nameToComp
        vm = self.nameToComp.get(vm_name)
        hv = self.nameToComp.get(hv_name)
        assert isinstance(vm, VirtualMachine)
        assert isinstance(hv, Hypervisor)
        assert not vm.is_running
        dummy = self.mn.nameToNode.get("dummy", None)
        
        for intf in vm.node.intfs.values():
          if intf.link.intf1.node == dummy: 
            vm_intf = intf
            vm_intf_name =  intf.name
            old_intf = intf.link.intf1
            print "Old node is: ", old_intf.node
                      
          if intf.link.intf2.node == dummy:
            vm_intf = intf
            vm_intf_name =  intf.name
            old_intf = intf.link.intf2
            print "Old node is: ", old_intf.node
        old_intf_name = old_intf.name
        old_intf_port = old_intf.node.ports[ old_intf ]
        del dummy.intfs[ old_intf_port ]
        del dummy.ports[ old_intf ]
        del dummy.nameToIntf[ old_intf_name ]
        # Please see the codes below about moveIntfFrom(in Mininet.node.py)
        hv.node.moveIntfFrom( old_intf, dummy )
        old_intf.node = hv.node
        
        print "New node is: ", old_intf.node
        vm.launch(hv)  
        print vm,"'s hv is: ",vm.hv
        msg = {
          'CHANNEL' : 'CMS',
          'host' : vm_name,
          'old_hv': old_intf.node.name,
          'new_hv': hv_name
        }      
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
        assert vm.is_running 
          
        for intf in vm.node.intfs.values():
          if intf.link.intf1 == intf:
            vm_intf = intf
            old_intf = intf.link.intf2
            print "Old node is: ", old_intf.node
          if intf.link.intf2 == intf:
            vm_intf = intf
            old_intf = intf.link.intf1
            print "Old node is: ", old_intf.node
        old_node = old_intf.node
        old_intf_name = old_intf.name
        old_intf_port = old_intf.node.ports[ old_intf ]
        del old_node.intfs[ old_intf_port ]
        del old_node.ports[ old_intf ]
        del old_node.nameToIntf[ old_intf_name ]
        hv.node.moveIntfFrom( old_intf, old_node )
        old_intf.node = hv.node
        
        print "New node is: ", old_intf.node
        vm.moveTo(hv)
        # send out msg to the controller
        msg = {
          'CHANNEL' : 'CMS',
          'host' : vm_name,
          'old_hv': old_node.name,
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
        if not vm.is_running:
          print vm.node.name, "is not running now"
          return
        self.not_implemented()
        dummy = self.mn.nameToNode.get("dummy", None)
        for intf in vm.node.intfs.values():
          if intf.link.intf1 == intf:
            vm_intf = intf
            old_intf = intf.link.intf2
            print "Old node is: ", old_intf.node
          if intf.link.intf2 == intf:
            vm_intf = intf
            old_intf = intf.link.intf1
            print "Old node is: ", old_intf.node
        old_node = old_intf.node
        old_intf_name = old_intf.name
        old_intf_port = old_intf.node.ports[ old_intf ]
        del old_node.intfs[ old_intf_port ]
        del old_node.ports[ old_intf ]
        del old_node.nameToIntf[ old_intf_name ]
        dummy.moveIntfFrom( old_intf, old_node )
        old_intf.node = dummy
        vm.stop() 
        # sending msg to the controller
        msg = {
          'CHANNEL' : 'CMS',
          'host' : vm_name,
          'old_hv': old_node.name,
          'new_hv': dummy.name,
        }
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

        self.not_implemented()
        self.stopVM(vm_name)
        vm = self.nameToComp[vm_name]
        self.VMs.remove(vm)
        del self.nameToComp[ vm_name ]
        info( '*** Stopping host: %s\n' % vm_name ) 
        vm.node.terminate()
   
   #--------------------------------------------------
   #         codes added in other files
   #--------------------------------------------------
   
   
   
   """
   def createHostAtDummy(self, name, cls = None, **params):
        assert name not in self.nameToNode
        # assert self.built()
        vm = self.addHost (name, cls = cls, **params)
        dummy = self.nameToNode.get("dummy", None)
        if dummy is None:
            error('dummy node does not exist\n')
            dummy = self.addDummy()
        assert isinstance(dummy, Dummy)
        self.addLink( vm, dummy)  
        return vm    
   """
   
   """
    def moveIntfFrom( self, intf, intf_node, port=None ):
        if port is None:
            port = self.newPort()
        self.intfs[ port ] = intf
        self.ports[ intf ] = port
        self.nameToIntf[ intf.name ] = intf
        debug( '\nmoving intf %s:%d to node %s\n' % ( intf, port, self.name ))
        debug( 'moving', intf, 'into namespace for', self.name, '\n' )
        moveIntf( intf.name, self, intf_node )

   """
        









    






