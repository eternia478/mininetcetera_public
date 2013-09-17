# Copyright 2013 Jamie Tsao
# Copyright 2012 James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A super simple "knowing switch"

Run like:
./pox.py messenger messenger.tcp_transport \
         pox_cmsmsg.knowing_switch pox_cmsmsg.cmsnet_service
"""

# These next two imports are common POX convention.
from pox.core import core
import pox.openflow.libopenflow_01 as of

# Even a simple usage of the logger is much nicer than print!
log = core.getLogger()


def openflow_dpid_to_cms (dpid):
  """
  Convert OpenFlow DPID to CMS DPID
  """
  return "%016x" % (dpid,)


def cms_dpid_to_of (dpid):
  """
  Convert CMS DPID to OpenFlow DPID
  """
  return int(dpid, 16)


class KnowingSwitch (object):
  """
  "Knowing switch" controller

  Uses knowledge of host placement/address from the CMS in order to proactively
  set up forwarding entries.
  """
  def __init__ (self, quiet = False):
    # Don't log as much if quiet
    self.quiet = quiet

    # This table maps hypervisor edge switch dpid to information about
    # the switch (name, connection, fabric port, VM name->port).
    self.hvs = {}

    # This table maps VM host node name to information about the node
    # running the VM (MAC address, IP address, HV dpid).
    self.vms = {}

    # DPIDs with bad synchronizations
    self.bad_sync = set()

    core.listen_to_dependencies(self)

  def _all_dependencies_met (self):
    log.info("Running")

  def _get_hv_port_no (self, hv_intf_name, hv_connection):
    """
    Workaround for a bug in POX
    """
    #TODO: Explain to Murphy how to reproduce the bug

    #return hv_connection.ports[hv_intf_name].port_no
    is_same_port = lambda p: p.name == hv_intf_name
    all_possible_ports = filter(is_same_port, hv_connection.ports._ports)

    all_possible_ports = [p for p in hv_connection.ports._ports
                          if p.name == hv_intf_name]

    if len(all_possible_ports) > 0:
      return max([p.port_no for p in all_possible_ports])

    try:
      return hv_connection.ports[hv_intf_name].port_no
    except:
      return None

  def _handle_cmsbot_CMSInitialize (self, event):
    """
    Handle the CMSInitialize event.

    Save the new VMInfo instance. Then, add a new flow table entry for the VM
    on the VM's hypervisor edge switch.
    """
    log.info("%s initialized on %s", event.new_vm_info.name,
             event.new_vm_info.hv_dpid)
    self.vms[event.new_vm_info.name] = event.new_vm_info
    self._sync(event.new_vm_info.hv_dpid)

  def _handle_cmsbot_CMSMigrate (self, event):
    """
    Handle the CMSMigrate event.

    Replace with the new VMInfo instance. Then, delete the old flow table entry
    on the original hypervisor edge switch before adding a new one on the edge
    switch for the new hypervisor.
    """
    log.info("%s migrating to %s", event.new_vm_info.name,
             event.new_vm_info.hv_dpid)
    self.vms[event.new_vm_info.name] = event.new_vm_info
    if event.old_vm_info.hv_dpid == event.new_vm_info.hv_dpid:
      log.warn("%s migrated to the same node", event.new_vm_info.name)
    else:
      self._sync(event.old_vm_info.hv_dpid)
    self._sync(event.new_vm_info.hv_dpid)

  def _handle_cmsbot_CMSTerminate (self, event):
    """
    Handle the CMSTerminate event.

    Remove the VMInfo instance. Then, delete the flow table entry for the VM on
    the original hypervisor edge switch.
    """
    log.info("%s terminated on %s", event.old_vm_info.name,
             event.old_vm_info.hv_dpid)
    self.vms.pop(event.old_vm_info.name, None)
    self._sync(event.old_vm_info.hv_dpid)

  def _handle_cmsbot_CMSSynchronize (self, event):
    """
    Handle the CMSSynchronize event.

    Add in all Info instances. Then for each hypervisor edge switch, clear the
    flow table and add default entries for hypervisors to send to fabrics. Then
    add entries for the VMs on the hypervisor.
    """
    # Clear any old info
    self.hvs.clear()
    self.vms.clear()

    # Update information from CMS message
    for hv_info in event.hv_info_list:
      self.hvs[hv_info.dpid] = hv_info
    for vm_info in event.vm_info_list:
      self.vms[vm_info.name] = vm_info

    for hv in self.hvs.itervalues():
      self._sync(hv.dpid)

  def _sync (self, dpid):
    """
    Synchronize dpid with our model

    Expects DPID to be in "native" form, not OpenFlow.  Thus, it's a string.
    """
    hv_info = self.hvs.get(dpid)
    if hv_info is None:
      log.warn("Can't sync unknown switch %s", dpid)
      self.bad_sync.add(dpid)
      return

    con = core.openflow.connections.get(cms_dpid_to_of(hv_info.dpid))
    # Are they really hex?
    if con is None:
      log.warn("Can't sync disconnected switch %s", hv_info.dpid)
      self.bad_sync.add(dpid)
      return

    # Delete previous entries
    msg = of.ofp_flow_mod()
    msg.command = of.OFPFC_DELETE
    con.send(msg)

    bad_sync = False

    if not hv_info.fabric_ports:
      log.warn("Switch %s has no fabric ports", hv_info.dpid)
      bad_sync = True
    else:
      fabric_port_name = hv_info.fabric_ports[0]

      fabric_port = self._get_hv_port_no(fabric_port_name, con)
      #fabric_port = hv_connection.ports[fabric_port_name].port_no
      msg = of.ofp_flow_mod()
      msg.command = of.OFPFC_ADD
      msg.priority = 0
      msg.actions.append(of.ofp_action_output(port=fabric_port))
      con.send(msg)

      # Add exception for flooding
      msg = of.ofp_flow_mod()
      msg.command = of.OFPFC_ADD
      msg.priority = 1
      msg.match.dl_dst = of.EthAddr("ff:ff:ff:ff:ff:ff")
      msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
      con.send(msg)

    # Add entries for sending to VMs
    for vm in self.vms.itervalues():
      if vm.hv_dpid == dpid:
        # VM is on this switch
        hv_port_to_vm = self._get_hv_port_no(vm.hv_port_to_vm, con)
        #hv_port_to_vm = con.ports[vm.hv_port_to_vm].port_no
        if not hv_port_to_vm:
          log.info("Ignoring VM %s on unknown port %s.%s.", vm.name, dpid,
                   vm.hv_port_to_vm)
          bad_sync = True
          continue

        msg = of.ofp_flow_mod()
        msg.command = of.OFPFC_ADD
        msg.match.dl_dst = vm.mac_addr
        msg.actions.append(of.ofp_action_output(port=hv_port_to_vm))
        con.send(msg)
      else:
        # VM is on another switch
        pass

    if bad_sync:
      self.bad_sync.add(dpid)
      log.debug("Synchronized %s with issues", dpid)
    else:
      self.bad_sync.discard(dpid)
      log.debug("Synchronized %s okay", dpid)

  def _handle_openflow_PacketIn (self, event):
    # We don't expect many of these...
    error_str = "PacketIn:"
    error_str += "\n\tpacket = %s" % (event.parsed,)
    error_str += "\n\tswitch_con = %s" % (event.connection,)
    error_str += "\n\tin_port = %s" % (event.port,)
    error_str += "\n\tin_mac = %s" % (event.parsed.src,)
    error_str += "\n\tout_mac = %s" % (event.parsed.dst,)
    if not self.quiet:
      log.debug(error_str)

  def _handle_openflow_ConnectionUp (self, event):
    dpid = openflow_dpid_to_cms(event.dpid)
    self._sync(dpid)

  def _handle_openflow_PortStatus (self, event):
    dpid = openflow_dpid_to_cms(event.dpid)
    if dpid in self.bad_sync:
      log.debug("Ports may have changed -- resyncing")
      self._sync(dpid)

def launch (quiet = False):
  core.registerNew(KnowingSwitch, quiet)
