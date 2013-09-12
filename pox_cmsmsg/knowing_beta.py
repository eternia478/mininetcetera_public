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
  def __init__ (self, name, mac_addr, ip_addr, hv_dpid):
    self.name = name
    self.mac_addr = mac_addr
    self.ip_addr = ip_addr
    self.hv_dpid = hv_dpid


class KnowingSwitchBeta (object):
  """
  Beta version of knowing switch controller.
  """
  def __init__ (self):
    # This table maps hypervisor edge switch dpid to information about
    # the switch (name, connection, fabric port, VM name->port).
    self.hv_info_table = {}
    # This table maps VM host node name to information about the node
    # running the VM (MAC address, IP address, HV dpid).
    self.vm_info_table = {}

  def _handle_CMSInitialize (self, event):
    vm_name = event.vm_info.get("name")
    new_hv_dpid = event.new_hv_info.get("dpid")
    new_hv_vm_port = event.new_hv_info.get("vm_port")
    vm_param = {"hv_dpid": new_hv_dpid}
    vm_param.update(event.vm_info)
    self.vm_info_table[vm_name] = VMInfo(**vm_param)
    new_hv_info = self.hv_info_table[new_hv_dpid]
    new_hv_info.vm_ports[vm_name] = new_hv_vm_port
    add_msg = of.ofp_flow_mod()
    add_msg.command = OFPFC_ADD
    add_msg.match.dl_dst = vm_info.mac_addr
    add_msg.actions.append(of.ofp_action_output(port=new_hv_vm_port))
    new_hv_info.connection.send(add_msg)

  def _handle_CMSMigrate (self, event):
    vm_name = event.vm_info.get("name")
    old_hv_dpid = event.old_hv_info.get("dpid")
    new_hv_dpid = event.new_hv_info.get("dpid")
    new_hv_vm_port = event.new_hv_info.get("vm_port")
    vm_info = self.vm_info_table[vm_name]
    vm_info.hv_dpid = new_hv_dpid
    old_hv_info = self.hv_info_table[old_hv_dpid]
    del old_hv_info.vm_ports[vm_name]
    del_msg = of.ofp_flow_mod()
    del_msg.command = OFPFC_DELETE
    del_msg.match.dl_dst = vm_info.mac_addr
    old_hv_info.connection.send(del_msg)
    new_hv_info = self.hv_info_table[new_hv_dpid]
    new_hv_info.vm_ports[vm_name] = new_hv_vm_port
    add_msg = of.ofp_flow_mod()
    add_msg.command = OFPFC_ADD
    add_msg.match.dl_dst = vm_info.mac_addr
    add_msg.actions.append(of.ofp_action_output(port=new_hv_vm_port))
    new_hv_info.connection.send(add_msg)

  def _handle_CMSTerminate (self, event):
    vm_name = event.vm_info.get("name")
    old_hv_dpid = event.old_hv_info.get("dpid")
    del self.vm_info_table[vm_name]
    old_hv_info = self.hv_info_table[old_hv_dpid]
    del old_hv_info.vm_ports[vm_name]
    del_msg = of.ofp_flow_mod()
    del_msg.command = OFPFC_DELETE
    del_msg.match.dl_dst = vm_info.mac_addr
    old_hv_info.connection.send(del_msg)

  def _handle_CMSSynchronize (self, event):
    pass




def launch (disable_flood = False):
  ctl = KnowingSwitchBeta()

  def switch_up (event):
    log.debug("Controlling %s, dpid=%d" % (event.connection, event.dpid))
    ctl.hv_info_table[event.dpid] = HVInfo(event.dpid, event.connection)

  def switch_down (event):
    log.debug("Disconnecting %s, dpid=%d" % (event.connection, event.dpid))
    for vm_name in ctl.hv_info_table[event.dpid].vm_ports:
      log.debug(" -> Disconnected VM %s" % (vm_name,))
      del ctl.vm_info_table[vm_name]
    del ctl.hv_info_table[event.dpid]

  # Handle messages the switch has sent us because it has no matching rule.
  def _handle_PacketIn (event):
    error_str = "This shouldn't be the case: "
    error_str += "\n\tpacket = %s" % (event.parsed,)
    error_str += "\n\tswitch_con = %s" % (event.connection,)
    error_str += "\n\tin_port = %s" % (event.port,)
    error_str += "\n\tin_mac = %s" % (packet.src,)
    error_str += "\n\tout_mac = %s" % (packet.dst,)
    log.error(error_str)

  core.openflow.addListenerByName("ConnectionUp", switch_up)
  core.openflow.addListenerByName("ConnectionDown", switch_down)
  core.openflow.addListenerByName("PacketIn", _handle_PacketIn)

  if not cmsnet_service.cmsbot:
      log.warn("Didn't start CMSnet messenging service.")
      cmsnet_service.launch()
  cmsnet_service.cmsbot.addListeners(ctl)

  log.info("Knowing switch (beta) running.")
