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


class CMSEvent (Event):
  def __init__ (self, cms_msg):
    super(CMSEvent, self).__init__()
    assert isinstance(cms_msg, dict)
    self.cms_msg = cms_msg


class CMSVMEvent (CMSEvent):
  def __init__ (self, cms_msg, vm_info, old_hv_info={}, new_hv_info={}):
    super(CMSVMEvent, self).__init__(cms_msg)
    assert isinstance(vm_info, dict)
    assert isinstance(old_hv_info, dict)
    assert isinstance(new_hv_info, dict)
    self.vm_info = vm_info
    self.old_hv_info = old_hv_info
    self.new_hv_info = new_hv_info


class CMSInitialize (CMSVMEvent):
  pass


class CMSMigrate (CMSVMEvent):
  pass


class CMSTerminate (CMSVMEvent):
  pass


class CMSSynchronize (CMSEvent):
  def __init__ (self, cms_msg, cms_data):
    super(CMSSynchronize, self).__init__(cms_msg)
    assert isinstance(cms_data, dict)
    self.cms_data = cms_data


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

  def _exec_cmd_instantiate (self, event):
    """
    Handle received messages of cmd type "instantiate."
    """
    msg = event.msg
    log.debug("Received instantiate CMS message: %s" % (msg,))
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s" % msg.get("CHANNEL"))
      return
    assert msg.get("cmd") == "instantiate"
    vm_info = msg.get("vm_info")
    new_hv_info = msg.get("new_hv_info")
    self.raiseEvent(CMSInitialize(msg, vm_info, new_hv_info=new_hv_info))

  def _exec_cmd_migrate (self, event):
    """
    Handle received messages of cmd type "migrate."
    """
    msg = event.msg
    log.debug("Received migrate CMS message: %s" % (msg,))
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s" % msg.get("CHANNEL"))
      return
    assert msg.get("cmd") == "migrate"
    vm_info = msg.get("vm_info")
    old_hv_info = msg.get("old_hv_info")
    new_hv_info = msg.get("new_hv_info")
    self.raiseEvent(CMSMigrate(msg, vm_info, old_hv_info, new_hv_info))

  def _exec_cmd_terminate (self, event):
    """
    Handle received messages of cmd type "terminate."
    """
    msg = event.msg
    log.debug("Received terminate CMS message: %s" % (msg,))
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s" % msg.get("CHANNEL"))
      return
    assert msg.get("cmd") == "terminate"
    vm_info = msg.get("vm_info")
    old_hv_info = msg.get("old_hv_info")
    self.raiseEvent(CMSTerminate(msg, vm_info, old_hv_info=old_hv_info))

  def _exec_cmd_synchronize (self, event):
    """
    Handle received messages of cmd type "synchronize."
    """
    msg = event.msg
    log.debug("Received synchronize CMS message: %s" % (msg,))
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s" % msg.get("CHANNEL"))
      return
    assert msg.get("cmd") == "synchronize"
    cms_data = msg.get("cms_data")
    self.raiseEvent(CMSSynchronize(msg, cms_data))

  def _unhandled (self, event):
    """
    Unhandled cmd type.
    """
    msg = event.msg
    log.debug("Received unhandled CMS message: %s" % (msg,))
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s" % msg.get("CHANNEL"))
      return
    cmd = msg.get("cmd")
    log.warn("Invalid cmd type %s for CMS message!" % (cmd,))


cmsbot = None


def launch (nexus = "MessengerNexus"):
  def start (nexus):
    global cmsbot
    real_nexus = core.components[nexus]
    cmsbot = CMSBot(real_nexus.get_channel('CMS'))

  core.call_when_ready(start, nexus, args=[nexus])
