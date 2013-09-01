

# REMEMBER TO ALSO IMPORT THIS IN MININET LATER SINCE MOVELINK USES THIS:
from mininet.util import moveIntf




class MininetPatch(object):
    """
    NOTE: Please move the below code into Mininet. The code directly
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



    def addDummy( self, name='dummy', cls=Dummy, **params ):
        """
        Add dummy.
        
        dummy: Dummy class
        """
        if not cls:
            cls = Dummy                  # Any other possible classes?
        dummy_new = cls( name, **params )
        self.dummies.append( dummy_new ) # Dunno if we need more dummies.
        self.nameToNode[ name ] = dummy_new
        return dummy_new







    debug_flag1 = True   # Print statements everywhere.

    def createHostAtDummy( self, hostName, **params ):
        """
        Add a host node to Mininet and link it to the dummy.

        hostName: name of the host
        params: parameters for host
        """
        if self.debug_flag1:
            print "EXEC: createHostAtDummy(%s):" % hostName

        # Part 0: Main assertions.
        assert hostName not in self.nameToNode
        assert self.built
        host_terms = []

        # Part 1: Getting dummy.
        dummy = self.nameToNode.get("dummy", None)
        if dummy is None:
            error('dummy node does not exist\n')
            return
        assert isinstance(dummy, Dummy)

        # The following corresponds to code in self.build()

        # if self.topo:
        #     self.buildFromTopo( self.topo )
        info( '*** Adding host: %s\n' % hostName )
        host = self.addHost( hostName, **params )
        info( '*** Adding link: (%s, %s)\n' % ( host.name, dummy.name ) )
        hostPort = host.newPort()
        dummyPort = dummy.newPort()
        self.addLink( host, dummy, hostPort, dummyPort )

        # if ( self.inNamespace ):
        #     self.configureControlNetwork()        
        if ( self.inNamespace ):
            self.configureControlNetwork()

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
        if self.xterms:
            if 'DISPLAY' not in os.environ:
                error( "Error starting terms: Cannot connect to display\n" )
                return
            info( "*** Running term on %s\n" % os.environ[ 'DISPLAY' ] )
            host_terms = makeTerms( [ host ], 'host' )
            self.terms += host_terms

        # if self.autoStaticArp:
        #     self.staticArp()
        if self.autoStaticArp:
            for dst in self.hosts:
                if host != dst:
                    host.setARP( ip=dst.IP(), mac=dst.MAC() )
                    dst.setARP( ip=host.IP(), mac=host.MAC() )

        # self.built = True
        self.built = True
        
        return host, host_terms

    def moveLink( self, node1, node2, intf1_name=None, intf2_name=None ):
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

    def removeLink( self, node, intf_name=None, remove_only_once=True ):
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
        dummy = self.nameToNode.get("dummy")
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
        self.moveLink(node, dummy, intf_name, dummy_intf_name)

    def swapLink( self, node1, node2, intf1_name=None, intf2_name=None ):
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
        self.removeLink(node1, intf1_name, remove_only_once=False)
        self.moveLink(node2, node1_other, intf2_name, intf1_name_other)
        self.moveLink(node1, node2_other, intf1_name, intf2_name_other)


