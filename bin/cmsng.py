#!/usr/bin/python

from cmsnet.cms_api import CMSAPI
from mininet.util import custom, customConstructor
from mininet.node import RemoteController, OVSKernelSwitch
from cmsnet.mininet_node_patch import POXSwitch, POXNormalSwitch, POXNGSwitch

class CLITest (CMSAPI):
  """
  This is a test.
  """

  verbosity = "info"

  def set_net_params (self):
    """
    Sets the parameters for CMSnet. Override to change parameters.

    self.net_params is guaranteed to exist when this method is called.
    """
    SWS = {
      'ovsk': OVSKernelSwitch,
      'pox': POXSwitch,
      'ng' : POXNGSwitch,
      'normal': POXNormalSwitch,
    }
    CTR = { 
      'remote': RemoteController,
      'none': lambda name: None,
    }
    self.net_params["vm_dist_mode"] = "sparse"
    self.net_params["vm_dist_limit"] = 13
    self.net_params["switch"] = customConstructor(SWS, "ng")
    self.net_params["controller"] = customConstructor(CTR, "remote, port=6644")

  def set_net_topo (self):
    """
    Sets the topology for CMSnet. Override to change topology.

    self.net is guaranteed to exist when this method is called.
    """
    fabric = self.net.addFabricSwitch('f0')
    for num in [1,2,3]:  # range(1,4):
      s = self.net.addHVSwitch('s%d' % num)
      self.net.mn.addLink(s, fabric)
    s = self.net.addHVSwitch('s4', cls=OVSKernelSwitch)
    self.net.mn.addLink(s, fabric)



if __name__ == '__main__':
    CLITest()
