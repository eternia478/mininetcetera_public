"""
This file could work with pox_mininet.py to receive msg sent from that file,, it is just a small test of the JSON and messenger
"""


from pox.core import core
from pox.messenger import *
from pox.lib.revent.revent import autoBindEvents

class CMSBot (ChannelBot):
  def _unhandled (self, event):
    print "4"
    print "CMBot msg: ", event.msg
    if event.msg.get("CHANNEL",'CMS'):
    #TODO: Here we could get the useful information and do what we need do here
      host = event.msg.get("host") 
      print "host", host

def launch (nexus = "MessengerNexus"):
  def start (nexus):
    real_nexus = core.components[nexus]
    CMSBot(real_nexus.get_channel('CMS'))

  core.call_when_ready(start, nexus, args=[nexus])
 
