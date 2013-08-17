"""
Patch file for Mininet.

Put this into node.py. Ignore all imports, of course.

The destination of Dummy should be at the very end of the file.

The destination of POXNormalSwitch should be after all other switches.
"""

import os
import re
import signal
import select
from subprocess import Popen, PIPE, STDOUT
from operator import or_

from mininet.log import info, error, warn, debug
from mininet.util import ( quietRun, errRun, errFail, moveIntf, isShellBuiltin,
                           numCores, retry, mountCgroups )
from mininet.moduledeps import moduleDeps, pathCheck, OVS_KMOD, OF_KMOD, TUN
from mininet.link import Link, Intf, TCIntf
from mininet.node import Node, Host, Switch







#
#   Dummy -----------------------------------------------------------------
#



class Dummy( Node ):
    "A dummy is simply a Node"
    pass





#
#   POXNormalSwitch -------------------------------------------------------
#






def format_pox_extra( extra ):
    remove_slash = extra.replace("\\", "")
    single_quote_slash = remove_slash.replace('\'', '\\\'')
    double_quote_slash = single_quote_slash.replace("\"", "\\\"")
    return double_quote_slash

class POXSwitch( Switch ):
    "Switch to run a POX application."

    def __init__( self, name, control_flag=False, control_type="",
                  address="127.0.0.1", port=6633, ports="", dpid=None,
                  max_retry_delay=16, extra="", listenPort=None, **params):
        """Init.
           name: name for switch
           control_flag: spawn personal controller?
           control_type: personal controller type
           address: IP address to listen to (and personal controller address)
           port: TCP port to listen to (and personal controller port)
           ports: network interfaces to connect
           dpid: dpid for switch (or None to derive from name, e.g. s1 -> 1)
           max_retry_delay: max time between retries to connect to controller
           extra: extra parameters
           listenPort: port to listen on for dpctl connections
           params: Node parameters (see config() for details)"""
        Switch.__init__(self, name, dpid, listenPort=listenPort, **params)

        self.print_personal_debug = False

        ps = "Args: "
        ps += "\n  name           \t"      + str(name)
        ps += "\n  control_flag   \t"      + str(control_flag)
        ps += "\n  control_type   \t"      + str(control_type)
        ps += "\n  address        \t"      + str(address)
        ps += "\n  port           \t"      + str(port)
        ps += "\n  ports          \t"      + str(ports)
        ps += "\n  dpid           \t"      + str(dpid)
        ps += "\n  max_retry_delay\t"      + str(max_retry_delay)
        ps += "\n  extra          \t"      + str(extra)
        ps += "\n  listenPort     \t"      + str(listenPort)
        ps += "\n  params         \t"      + str(params)
        if self.print_personal_debug: print ps

        if 'POX_CORE_DIR' not in os.environ:
            #exit( 'exiting; please set missing POX_CORE_DIR env var' )
            self.poxCoreDir = "~/pox"
        else:
            self.poxCoreDir = os.environ[ 'POX_CORE_DIR' ]

        self.use_remote_controller = (not control_flag)
        self.controller_type = control_type
        self.controller_ip = address if address else "127.0.0.1"
        self.controller_port = int(port) if port else 6633
        self.input_intf_ports = ports.split(";") if ports else []
        self.max_retry_delay = max_retry_delay if max_retry_delay else 16
        self.extra = format_pox_extra(extra).split(";") if extra else []

        # NOTE: In case these are needed elsewhere...
        self.run_file = ""
        self.ctrl_args = ""
        self.cmd_args = ""
        self.cmd_log = ""
        self.cmd_tail = ""
        self.command = ""
        self.intf_ports = []
        self.pox_pid = None
        self.started_switch = False

        ps = "Input to POXSwitch.__init__(): "
        ps += "\n  poxCoreDir      \t"      + str(self.poxCoreDir)
        ps += "\n  switch_name     \t"      + str(self.name)
        ps += "\n  use_remote_controller\t" + str(self.use_remote_controller)
        ps += "\n  controller_type \t"      + str(self.controller_type)
        ps += "\n  controller_ip   \t"      + str(self.controller_ip)
        ps += "\n  controller_port \t"      + str(self.controller_port)
        ps += "\n  input_intf_ports\t"      + str(self.input_intf_ports)
        ps += "\n  switch_dpid     \t"      + str(self.dpid)
        ps += "\n  max_retry_delay \t"      + str(self.max_retry_delay)
        ps += "\n  extra_parameters\t"      + str(self.extra)
        ps += "\n  listenPort      \t"      + str(self.listenPort)
        if self.print_personal_debug: print ps

    def _build_cmd_args( self ):
        "Build command-line argument of POX."
        self.run_file = ""
        self.ctrl_args = ""
        self.cmd_args = ""
        self.cmd_log = ""
        self.cmd_tail = ""

        self.run_file = self.poxCoreDir + "/pox.py"
        pathCheck( self.run_file )

        if self.use_remote_controller:
            self.ctrl_args = "--no-openflow"
        elif self.controller_type:
            self.ctrl_args = self.controller_type + " openflow.of_01"
            self.ctrl_args += " --address="    + str(self.controller_ip)
            self.ctrl_args += " --port="       + str(self.controller_port)

        self.cmd_args = "datapaths.pcap_switch"
        self.cmd_args += " --address="         + str(self.controller_ip)
        self.cmd_args += " --port="            + str(self.controller_port)
        self.cmd_args += " --max_retry_delay=" + str(self.max_retry_delay)
        self.cmd_args += " --dpid="            + str(self.dpid)
        self.cmd_args += " --ports="           + ",".join(self.intf_ports)
        self.cmd_args += " --extra="           + ",".join(self.extra)

        self.cmd_log = "/tmp/" + self.name + ".log"
        self.cmd( 'echo "" > %s' % self.cmd_log )  # Clear previous
        self.cmd_tail = "1>> " + self.cmd_log + " 2>> " + self.cmd_log + " &"

        if self.print_personal_debug: print "WARN: self.listenPort is UNUSED"
        self.command = self.run_file
        self.command += " " + self.ctrl_args
        self.command += " " + self.cmd_args
        self.command += " " + self.cmd_tail
        if self.print_personal_debug: print "EVAL: " + self.command

    def _run_pox_switch( self ):
        "Run the POX switch"
        if self.pox_pid is not None:
            warn( "Killing old pox switch to restart new one." )
            self._kill_pox_switch()
        self._build_cmd_args()
        self.cmd( self.command, printPid=True )
        self.pox_pid = self.lastPid
        self.started_switch = True

    def _kill_pox_switch( self ):
        "Kill the POX switch"
        if self.pox_pid is None:
            error( "No pox switch process to kill" )
            return
        if self.print_personal_debug: print "KILL: process %d" % self.pox_pid
        self.cmd( 'kill %d' % self.pox_pid )
        self.pox_pid = None
        self.started_switch = False

    def attach( self, intf ):
        "Connect a data port"
        self.cmd( 'ifconfig', intf, 'up' )
        intf_name = str(intf)

        if self.input_intf_ports:     # Only add specified ports.
            if intf_name in self.input_intf_ports:
                self.intf_ports.append(intf_name)
        else:                         # Add all ()-eth# ports.
            if self.name in intf_name:
                self.intf_ports.append(intf_name)
        if self.print_personal_debug:
            print "intf_ports currently: "+str(self.intf_ports)

        # If already started, we need to restart the switch.
        if self.started_switch:
            self._run_pox_switch()

    def detach( self, intf ):
        "Disconnect a data port"
        self.cmd( 'ifconfig', intf, 'down' )
        intf_name = str(intf)
        if intf_name in self.intf_ports:
            self.intf_ports.remove(intf_name)
        if self.print_personal_debug:
            print "intf_ports currently: "+str(self.intf_ports)

        # If already started, we need to restart the switch.
        if self.started_switch:
            self._run_pox_switch()

    def start( self, controllers ):
        "Start up a new POX OpenFlow switch"

        if self.poxCoreDir is not None:
            self.cmd( 'cd ' + self.poxCoreDir )

        # We should probably call config instead, but this
        # requires some rethinking...
        self.cmd( 'ifconfig lo up' )
        # Annoyingly, --if-exists option seems not to work
        for intf in self.intfList(): #nameToIntf #self.intfNames
            if not intf.IP():
                self.attach( intf )

        # Add controllers.
        # NOTE: This case is currently impossible and inaccessible.
        if not self.controller_ip or not self.controller_port:
            warn( 'warning: bad input controller ip and port' )
            if len(controllers) == 1:
                c = controllers[0]
                self.controller_ip = c.IP()
                self.controller_port = c.port
            else:
                raise Exception('Cannot find unique controller to connect to')

        self._run_pox_switch()

    def stop( self ):
        "Stop controller."
        self._kill_pox_switch()
        self.terminate()

    def execute():
        # CHECK: Do we need this?
        self.start([])


class POXNormalSwitch( POXSwitch ):
    "Normal l2_pair Switch to run a POX application."

    def __init__( self, name, **params):
        params.update({"inNamespace":True})
        POXSwitch.__init__(self, name, control_flag=True,
                           control_type="forwarding.l2_pairs", **params)


