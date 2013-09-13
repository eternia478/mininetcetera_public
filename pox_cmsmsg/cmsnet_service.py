"""
This is a messenger service for working with the CMSnet.

It does two things:
  a) Listen on the "CMS" channel. Messages sent to this channel
     should have vital information about the CMS network.
  b) Raise events for controllers to listen to. This is for the
     controller to react to changes in the network.
"""

from pox.core import core
from pox.messenger import *
from pox.lib.revent.revent import autoBindEvents
from pox.core import core as core

log = core.getLogger()


class HVInfo (object):
  """
  Container for information of a hypervisor edge switch.
  """
  def __init__ (self, hv_info_dict):
    assert isinstance(hv_info_dict, dict)
    self.name = hv_info_dict["name"]
    self.dpid = hv_info_dict["dpid"]
    self.fabric_ports = hv_info_dict["fabric_ports"]


class VMInfo (object):
  """
  Container for information of a host node running a VM.
  """
  def __init__ (self, vm_info_dict):
    assert isinstance(vm_info_dict, dict)
    self.name = vm_info_dict["name"]
    self.mac_addr = vm_info_dict["mac_addr"]
    self.ip_addr = vm_info_dict["ip_addr"]
    self.hv_dpid = vm_info_dict["hv_dpid"]
    self.hv_port_to_vm = vm_info_dict["hv_port_to_vm"]


class CMSEvent (Event):
  """
  Event raised from receiving a CMS message.
  """
  def __init__ (self, cms_msg):
    super(CMSEvent, self).__init__()
    assert isinstance(cms_msg, dict)
    self.cms_msg = cms_msg


class CMSInitialize (CMSEvent):
  def __init__ (self, cms_msg):
    super(CMSInitialize, self).__init__(cms_msg)
    new_vm_data = cms_msg["new_vm_info"]
    self.new_vm_info = VMInfo(new_vm_data)


class CMSMigrate (CMSEvent):
  def __init__ (self, cms_msg):
    super(CMSMigrate, self).__init__(cms_msg)
    new_vm_data = cms_msg["new_vm_info"]
    old_vm_data = cms_msg["old_vm_info"]
    self.new_vm_info = VMInfo(new_vm_data)
    self.old_vm_info = VMInfo(old_vm_data)

  @property
  def vm_name (self):
    return self.new_vm_info.name

  @property
  def new_hv_dpid (self):
    return self.new_vm_info.hv_dpid

  @property
  def old_hv_dpid (self):
    return self.old_vm_info.hv_dpid

  @property
  def new_port (self):
    return self.new_vm_info.hv_port_to_vm


class CMSTerminate (CMSEvent):
  def __init__ (self, cms_msg):
    super(CMSTerminate, self).__init__(cms_msg)
    old_vm_data = cms_msg["old_vm_info"]
    self.old_vm_info = VMInfo(old_vm_data)

  @property
  def vm_name (self):
    return self.old_vm_info.name

  @property
  def old_hv_dpid (self):
    return self.old_vm_info.hv_dpid


class CMSSynchronize (CMSEvent):
  def __init__ (self, cms_msg):
    super(CMSSynchronize, self).__init__(cms_msg)
    hv_data_list = cms_msg["hv_info_list"]
    vm_data_list = cms_msg["vm_info_list"]
    self.hv_info_list = [HVInfo(hv_data) for hv_data in hv_data_list]
    self.vm_info_list = [VMInfo(vm_data) for vm_data in vm_data_list]


class CMSBot (ChannelBot, EventMixin):
  """
  Channel bot dealing with messages on the CMS channel.

  The "cmd" field of the messages should be of the following:
   - "instantiate"
   - "migrate"
   - "terminate"
   - "synchronize"
  Any other messages are simply discarded.
  """
  _eventMixin_events = set([CMSInitialize, CMSMigrate, CMSTerminate,
                            CMSSynchronize])

  def _check_msg (self, msg, cmd_type):
    """
    Check the values stored in the message sent on the CMS channel.
    """
    log.debug("Received %s CMS message: %s" % (cmd_type, msg))
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s" % msg.get("CHANNEL"))
      return
    if cmd_type != "unhandled":
      assert cmd_type in ['instantiate', 'migrate', 'terminate']
      assert msg.get("cmd") == cmd_type

  def _exec_cmd_instantiate (self, event):
    """
    Handle received messages of cmd type "instantiate."
    """
    msg = event.msg
    self._check_msg(msg, "instantiate")
    self.raiseEvent(CMSInitialize(msg))

  def _exec_cmd_migrate (self, event):
    """
    Handle received messages of cmd type "migrate."
    """
    msg = event.msg
    self._check_msg(msg, "migrate")
    self.raiseEvent(CMSMigrate(msg))

  def _exec_cmd_terminate (self, event):
    """
    Handle received messages of cmd type "terminate."
    """
    msg = event.msg
    self._check_msg(msg, "terminate")
    self.raiseEvent(CMSTerminate(msg))

  def _exec_cmd_synchronize (self, event):
    """
    Handle received messages of cmd type "synchronize."
    """
    msg = event.msg
    self._check_msg(msg, "synchronize")
    self.raiseEvent(CMSSynchronize(msg))

  def _unhandled (self, event):
    """
    Unhandled cmd type.
    """
    msg = event.msg
    self._check_msg(msg, "unhandled")
    log.warn("Invalid cmd type %s for CMS message!" % (msg.get("cmd"),))


cmsbot = None


def launch (nexus = "MessengerNexus"):
  def start (nexus):
    global cmsbot
    real_nexus = core.components[nexus]
    cmsbot = CMSBot(real_nexus.get_channel('CMS'))

  core.call_when_ready(start, nexus, args=[nexus])
