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
  def __init__ (self, added=[], removed=[], reason=None):
    Event.__init__(self)
    self.added = added
    self.removed = removed

    # Reason for modification.
    # Presently, this is only used for removals and is either one of OFPRR_x,
    # or None if it does not correlate to any of the items in the spec.
    self.reason = reason


class CMSEventMixin (EventMixin):
  """
  EventMixin subclass for raising CMS events.
  """
  _eventMixin_events = set([FlowTableModification])


class CMSBot (ChannelBot):
  """
  Channel bot dealing with messages on the CMS channel.

  The "cmd" field of the messages should be of the following:
   - "instantiate"
   - "migrate"
   - "terminate"
   - "synchronize"
  Any other messages are simply discarded.
  """
  def _exec_cmd_instantiate (self, event):
    """
    Handle received messages of cmd type "instantiate."
    """
    pass

  def _exec_cmd_migrate (self, event):
    """
    Handle received messages of cmd type "migrate."
    """

  def _exec_cmd_terminate (self, event):
    """
    Handle received messages of cmd type "terminate."
    """

  def _exec_cmd_synchronize (self, event):
    """
    Handle received messages of cmd type "synchronize."
    """


  def _exec_cmd_migrate (self, event):
    print "migrated"
    print "CMBot msg: %s" % event.msg
    msg = event.msg
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s\n" % msg.get("CHANNEL"))
      return
    assert msg.get("CHANNEL") == 'CMS'
    msg_level = msg.get("msg_level")
    msg_cmd = msg.get("cmd")
    host = msg.get("host")
    new_hv = msg.get("new_hv")
    if msg_cmd == msg_level or msg_level == "all":
      log.info("msg_cmd: %s" % msg_cmd)
      log.info("host: %s" % host)
      log.info("new_hv: %s" % new_hv)

  def _exec_cmd_instantiate (self, event):
    print "instantiated"
    print "CMBot msg: %s" % event.msg
    msg = event.msg
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s\n" % msg.get("CHANNEL"))
      return
    assert msg.get("CHANNEL") == 'CMS'
    msg_level = msg.get("msg_level")
    msg_cmd = msg.get("cmd")
    host = msg.get("host")
    new_hv = msg.get("new_hv")
    if msg_cmd == msg_level or msg_level == "all":
      log.info("msg_cmd: %s" % msg_cmd)
      log.info("host: %s" % host)
      log.info("new_hv: %s" % new_hv)

  def _exec_cmd_terminate (self, event):
    print "destroyed"
    print "CMBot msg: %s" % event.msg
    msg = event.msg
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s\n" % msg.get("CHANNEL"))
      return
    assert msg.get("CHANNEL") == 'CMS'
    msg_level = msg.get("msg_level")
    msg_cmd = msg.get("cmd")
    host = msg.get("host")
    new_hv = msg.get("new_hv")
    if msg_cmd == msg_level or msg_level == "all":
      log.info("msg_cmd: %s" % msg_cmd)
      log.info("host: %s" % host)
      log.info("new_hv: %s" % new_hv)

  def _unhandled (self, event):
    print "unhandled"
    print "CMBot msg: %s" % event.msg
    msg = event.msg
    if msg.get("CHANNEL") != 'CMS':
      log.warn("Not correct channel: %s" % msg.get("CHANNEL"))
      return
    assert msg.get("CHANNEL") == 'CMS'


def launch (nexus = "MessengerNexus"):
  def start (nexus):
    real_nexus = core.components[nexus]
    CMSBot(real_nexus.get_channel('CMS'))

  core.call_when_ready(start, nexus, args=[nexus])
