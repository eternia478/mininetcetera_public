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
    if event.msg.get("CHANNEL",'CMS'):
      print "migrated"
      print "CMBot msg: ", event.msg
      msglevel = event.msg.get("msglevel")
      msgcmd = event.msg.get("cmd")
      if msgcmd == msglevel or msglevel == None:
        log.info("migrated")
  
  def _exec_cmd_instantiated (self, event):
    if event.msg.get("CHANNEL",'CMS'):
      print "instantiated"
      print "CMBot msg: ", event.msg
      msglevel = event.msg.get("msglevel")
      msgcmd = event.msg.get("cmd")
      if msgcmd == msglevel or msglevel == None:
        log.info("instantiated")  
  
  def _exec_cmd_destroyed (self, event):
    if event.msg.get("CHANNEL",'CMS'):
      print "destroyed" 
      print "CMBot msg: ", event.msg
      msglevel = event.msg.get("msglevel")
      msgcmd = event.msg.get("cmd")
      if msgcmd == msglevel or msglevel == None:
        log.info("destroyed")  
  
  
  def _unhandled (self, event):
    if event.msg.get("CHANNEL",'CMS'):
      print "CMBot msg: ", event.msg 
        

def launch (nexus = "MessengerNexus"):
  def start (nexus):
    real_nexus = core.components[nexus]
    CMSBot(real_nexus.get_channel('CMS'))

  core.call_when_ready(start, nexus, args=[nexus])
 
