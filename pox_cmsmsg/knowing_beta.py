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

  def _get_hv_port_no (self, hv_intf_name, hv_connection):
    """
    Temporary measure as a workaround a bug in POX to get correct port number.
    """
    #return hv_connection.ports[hv_intf_name].port_no
    is_same_port = lambda p: p.name == hv_intf_name
    all_possible_ports = filter(is_same_port, hv_connection.ports._ports)
    if len(all_possible_ports) > 0:
       hv_port = max([p.port_no for p in all_possible_ports])
    else:
       hv_port = hv_connection.ports[hv_intf_name].port_no
    return hv_port

  def _add_new_flow_mod (self, vm_info):
    """
    Send a flow mod message to add a new entry for the VM.
    """
    hv_connection = core.openflow.connections[int(vm_info.hv_dpid, 16)]
    hv_port_to_vm = self._get_hv_port_no(vm_info.hv_port_to_vm, hv_connection)
    #hv_port_to_vm = hv_connection.ports[vm_info.hv_port_to_vm].port_no

    add_msg = of.ofp_flow_mod()
    add_msg.command = of.OFPFC_ADD
    add_msg.match.dl_dst = vm_info.mac_addr
    add_msg.actions.append(of.ofp_action_output(port=hv_port_to_vm))
    hv_connection.send(add_msg)

  def _remove_old_flow_mod (self, vm_info):
    """
    Send a flow mod message to remove the old entry for the VM.
    """
    hv_connection = core.openflow.connections[int(vm_info.hv_dpid, 16)]

    del_msg = of.ofp_flow_mod()
    del_msg.command = of.OFPFC_DELETE
    del_msg.match.dl_dst = vm_info.mac_addr
    hv_connection.send(del_msg)

  def _handle_CMSInitialize (self, event):
    """
    Handle the CMSInitialize event.

    Save the new VMInfo instance. Then, add a new flow table entry for the VM
    on the VM's hypervisor edge switch.
    """
    self.vm_info_table[event.new_vm_info.name] = event.new_vm_info
    self._add_new_flow_mod(event.new_vm_info)

  def _handle_CMSMigrate (self, event):
    """
    Handle the CMSMigrate event.

    Replace with the new VMInfo instance. Then, delete the old flow table entry
    on the original hypervisor edge switch before adding a new one on the edge
    switch for the new hypervisor.
    """
    self.vm_info_table[event.new_vm_info.name] = event.new_vm_info
    self._remove_old_flow_mod(event.old_vm_info)
    self._add_new_flow_mod(event.new_vm_info)

  def _handle_CMSTerminate (self, event):
    """
    Handle the CMSTerminate event.

    Remove the VMInfo instance. Then, delete the flow table entry for the VM on
    the original hypervisor edge switch.
    """
    del self.vm_info_table[event.old_vm_info.name]
    self._remove_old_flow_mod(event.old_vm_info)

  def _handle_CMSSynchronize (self, event):
    """
    Handle the CMSSynchronize event.

    Add in all Info instances. Then for each hypervisor edge switch, clear the
    flow table and add default entries for hypervisors to send to fabrics. Then
    add entries for the VMs on the hypervisor.
    """
    # Clear any old info
    self.hv_info_table = {}
    self.vm_info_table = {}

    # Update information from CMS message
    for hv_info in event.hv_info_list:
      self.hv_info_table[hv_info.dpid] = hv_info
    for vm_info in event.vm_info_list:
      self.vm_info_table[vm_info.name] = vm_info

    for hv_info in event.hv_info_list:
      hv_connection = core.openflow.connections[int(hv_info.dpid, 16)]

      # Delete previous entries
      del_all_msg = of.ofp_flow_mod()
      del_all_msg.command = of.OFPFC_DELETE
      hv_connection.send(del_all_msg)

      # Add default entries for sending to fabric
      for fabric_intf_name in hv_info.fabric_ports:
        fabric_port = self._get_hv_port_no(fabric_intf_name, hv_connection)
        #fabric_port = hv_connection.ports[fabric_intf_name].port_no
        add_fabric_msg = of.ofp_flow_mod()
        add_fabric_msg.command = of.OFPFC_ADD
        add_fabric_msg.priority = 0
        add_fabric_msg.actions.append(of.ofp_action_output(port=fabric_port))
        hv_connection.send(add_fabric_msg)
        
        # Add exception for flooding
        add_flood_msg = of.ofp_flow_mod()
        add_flood_msg.command = of.OFPFC_ADD
        add_flood_msg.priority = 1
        add_flood_msg.match.dl_dst = of.EthAddr("ff:ff:ff:ff:ff:ff")
        add_flood_msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
        hv_connection.send(add_flood_msg)

    # Add entries for sending to VM's
    for vm_info in event.vm_info_list:
      self._add_new_flow_mod(vm_info)



def launch (disable_flood = False):
  if not cmsnet_service.cmsbot:
    log.warn("Didn't start CMSnet messenging service.")
    cmsnet_service.launch()

  ctl = KnowingSwitchBeta()
  cmsnet_service.cmsbot.addListeners(ctl)

  # Handle messages the switch has sent us because it has no matching rule.
  def _handle_PacketIn (event):
    error_str = "This shouldn't be the case: "
    error_str += "\n\tpacket = %s" % (event.parsed,)
    error_str += "\n\tswitch_con = %s" % (event.connection,)
    error_str += "\n\tin_port = %s" % (event.port,)
    error_str += "\n\tin_mac = %s" % (event.parsed.src,)
    error_str += "\n\tout_mac = %s" % (event.parsed.dst,)
    #log.error(error_str)
  core.openflow.addListenerByName("PacketIn", _handle_PacketIn)

  log.info("Knowing switch (beta) running.")
