#!/usr/bin/env python
'''@package topo

Network topology creation.

@author Brandon Heller (brandonh@stanford.edu)

This package includes code to represent network topologies.

A Topo object can be a topology database for NOX, can represent a physical
setup for testing, and can even be emulated with the Mininet package.
'''

from mininet.util import irange, natural, naturalSeq
from mininet.topo import Topo
#from mininet.node import POXNormalSwitch
from cmsnet.mininet_node_patch import POXNormalSwitch

class CMSTopo(Topo):
    "Network representation solely for CMS networks."

    def __init__(self, hv_num=2, fb_num=1, **opts):
        """Init.
           hv_num: number of HV-switches
           fb_num: number of fabric-switches"""
        super(CMSTopo, self).__init__(**opts)

        self.hv_num = hv_num
        self.fb_num = fb_num

    def addHVSwitch(self, name, **opts):
        """Convenience method: Add hypervisor-representing to graph.
           name: HV-switch name
           opts: HV-switch options
           returns: HV-switch name"""
        opts.update({"cms_type": "hypervisor"})
        result = self.addSwitch(name, **opts)
        return result

    def addFabricSwitch(self, name, **opts):
        """Convenience method: Add fabric-representing switch to graph.
           name: fabric-switch name
           opts: fabric-switch options
           returns: fabric-switch name"""
        opts.update({"cms_type": "fabric", "cls": POXNormalSwitch})
        result = self.addSwitch(name, **opts)
        return result

    def isHVSwitch(self, n):
        '''Returns true if node is switch and represents a hypervisor.'''
        info = self.node_info[n]
        return self.isSwitch(n) and info.get('cms_type') == "hypervisor"

    def isFabricSwitch(self, n):
        '''Returns true if node is switch and represents (part of) a fabric.'''
        info = self.node_info[n]
        return self.isSwitch(n) and info.get('cms_type') == "fabric"

    def hvSwitches(self, sort=True):
        '''Return HV-switches.
        sort: sort HV-switches alphabetically
        @return dpids list of dpids
        '''
        return [n for n in self.nodes(sort) if self.isHVSwitch(n)]

    def fabricSwitches(self, sort=True):
        '''Return fabric-switches.
        sort: sort fabric-switches alphabetically
        @return dpids list of dpids
        '''
        return [n for n in self.nodes(sort) if self.isFabricSwitch(n)]


class CMSLinearTopo(CMSTopo):
    "Linear topology of hv_num HV-switches."

    def __init__(self, *args, **opts):
        """Init.
           opts: Options"""

        super(CMSLinearTopo, self).__init__(*args, **opts)

        lastSwitch = None
        for i in irange(1, self.hv_num):
            # Add switch
            switch = self.addHVSwitch('s%s' % i)
            # Connect switch to previous
            if lastSwitch:
                self.addLink(switch, lastSwitch)
            lastSwitch = switch


class CMSHubAndSpokeTopo(CMSTopo):
    "Hub-and-spoke topology of hv_num HV-switches around 1 fabric switch."

    def __init__(self, *args, **opts):
        """Init.
           opts: Options"""

        super(CMSHubAndSpokeTopo, self).__init__(*args, **opts)

        fabric = self.addFabricSwitch( 'fabric'+str(self.hv_num+1) )

        for i in irange(1, self.hv_num):
            # Add switch
            switch = self.addHVSwitch('s%s' % i)
            # Connect switch to fabric-switch
            self.addLink(switch, fabric)
