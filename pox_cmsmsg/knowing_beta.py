"""
A super simple knowing switch. Beta version.
"""

# These next two imports are common POX convention.
from pox.core import core
import pox.openflow.libopenflow_01 as of

# This import is specifically for this controller's functionality.
from pox.messenger import cmsnet_service

# Even a simple usage of the logger is much nicer than print!
log = core.getLogger()

# This table maps hypervisor edge switch dpid to information about
# the switch (name, connection, fabric port, VM name->port).
hv_info_table = {}

# This table maps VM host node name to information about the node
# running the VM (MAC address, IP address, HV).
vm_info_table = {}

# This table maps (switch,MAC-addr) pairs to the port on 'switch' at
# which we last saw a packet *from* 'MAC-addr'.
# (In this case, we use a Connection object for the switch.)
table = {}

# To send out all ports, we can use either of the special ports
# OFPP_FLOOD or OFPP_ALL.  We'd like to just use OFPP_FLOOD,
# but it's not clear if all switches support this, so we make
# it selectable.
all_ports = of.OFPP_FLOOD


class HVInfo (object):
  """
  Container for information of a hypervisor edge switch.
  """
  def __init__ (self, dpid, connection):
    self.name = None
    self.dpid = dpid
    self.connection = connection
    self.fabric_port = None
    self.vm_ports = {}


class VMInfo (object):
  """
  Container for information of a host node running a VM.
  """
  def __init__ (self, name, mac_addr, ip_addr, hv):
    self.name = name
    self.mac_addr = mac_addr
    self.ip_addr = ip_addr
    self.hv = hv





# Handle messages the switch has sent us because it has no
# matching rule.
def _handle_PacketIn (event):
  packet = event.parsed

  # Learn the source
  table[(event.connection,packet.src)] = event.port

  dst_port = table.get((event.connection,packet.dst))

  if dst_port is None:
    # We don't know where the destination is yet.  So, we'll just
    # send the packet out all ports (except the one it came in on!)
    # and hope the destination is out there somewhere. :)
    msg = of.ofp_packet_out(data = event.ofp)
    msg.actions.append(of.ofp_action_output(port = all_ports))
    event.connection.send(msg)
  else:
    # Since we know the switch ports for both the source and dest
    # MACs, we can install rules for both directions.
    msg = of.ofp_flow_mod()
    msg.match.dl_dst = packet.src
    msg.match.dl_src = packet.dst
    msg.actions.append(of.ofp_action_output(port = event.port))
    event.connection.send(msg)
    
    # This is the packet that just came in -- we want to
    # install the rule and also resend the packet.
    msg = of.ofp_flow_mod()
    msg.data = event.ofp # Forward the incoming packet
    msg.match.dl_src = packet.src
    msg.match.dl_dst = packet.dst
    msg.actions.append(of.ofp_action_output(port = dst_port))
    event.connection.send(msg)

    log.debug("Installing %s <-> %s" % (packet.src, packet.dst))


def launch (disable_flood = False):
  def switch_up (event):
    global hv_info_table
    log.debug("Controlling %s, dpid=%d" % (event.connection, event.dpid))
    hv_info_table[event.dpid] = HVInfo(event.connection)

  def switch_down (event):
    global hv_info_table
    log.debug("Disconnecting %s, dpid=%d" % (event.connection, event.dpid))
    del hv_info_table[event.dpid]

  core.openflow.addListenerByName("ConnectionUp", switch_up)
  core.openflow.addListenerByName("ConnectionDown", switch_down)
  if not cmsnet_service.cms_em:
      cmsnet_service.cms_em = CMSEventMixin()
  cmsnet_service.cms_em.addListener(


  global all_ports
  if disable_flood:
    all_ports = of.OFPP_ALL
  core.openflow.addListenerByName("PacketIn", _handle_PacketIn)

  log.info("Pair-Learning switch running.")
