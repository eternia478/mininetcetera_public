"""
This file could work with pox_mininet.py to receive msg sent from that file,, it is just a small test of the JSON and messenger
"""


from pox.core import core
from pox.messenger import *
from pox.lib.revent.revent import autoBindEvents
from pox.core import core as core

log = core.getLogger()

class CMSBot (ChannelBot):
  def _exec_cmd_migrated (self, event):
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

  def _exec_cmd_instantiated (self, event):
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

  def _exec_cmd_destroyed (self, event):
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
