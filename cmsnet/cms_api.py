"""
API for a (debatably) hacky approach, using the Python interpreter as the CLI
instead of the Mininet one (which uses Python's cmd module).

This is only a base class. All attempts to run CMSnet should be done by
subclasses to use its functionality via extension of methods.
"""
import os
import sys
if 'PYTHONPATH' in os.environ:
    sys.path = os.environ[ 'PYTHONPATH' ].split( ':' ) + sys.path
print "PYTHONPATH   = %s" % os.environ.get( 'PYTHONPATH' )
print "POX_CORE_DIR = %s" % os.environ.get( 'POX_CORE_DIR' )

#from mininet.net import Mininet, MininetWithControlNet, VERSION
from mininet.cli import CLI as MininetCLI
from mininet.node import ( Node, Host, CPULimitedHost,
                           Controller, OVSController, NOX, RemoteController,
                           UserSwitch, OVSLegacyKernelSwitch, OVSKernelSwitch,
                           IVSSwitch )
#from mininet.link import Link, TCLink, Intf
from mininet.link import Intf
from mininet.log import info, output, error
from mininet.term import makeTerms, runX11
from cmsnet.cms_net import CMSnet
from cmsnet.cms_comp import CMSComponent, VirtualMachine, Hypervisor
import cmsnet.cms_comp
from cmsnet.cms_exc import ( CMSCompNameError, CMSVMNameError,
                               CMSHypervisorNameError,
                               CMSTypeError, CMSCompTypeError,
                               CMSNonpositiveValueError,
                               CMSInvalidChoiceValueError,
                               CMSInvalidParameterValueError,
                               CMSHVCycleIndexError,

                               CMSVMNameOccupiedError,
                               CMSNameReservedError,
                               CMSNameReservedForOtherTypeError,
                               CMSNameReservedForSpecialVarError,
                               CMSNameReservedForMethodError,

                               CMSCompStateError,
                               CMSVMRunningStateError,
                               CMSVMPausedStateError,
                               CMSHypervisorEnabledStateError )

from cmsnet.mininet_node_patch import Dummy, POXSwitch, POXNormalSwitch
from cmsnet.mininet_net_patch import MininetPatch as Mininet
from cmsnet.mininet_link_patch import Link, TCLink

from mininet.log import setLogLevel
import code
import atexit
import re

class CMSAPI (object):
  """
  API for simple command-line interface to talk to VMs and hypervisors.
  """

  verbosity = 'info'

  def __init__ (self):
    """
    Initialization. This does not yet run the CLI.
    """
    self.net_params = {}
    self.net = None
    self.local_vars = locals().copy()

    setLogLevel(self.verbosity)
    atexit.register(self.stop)

    self.set_default_net_params()
    self.set_net_params()
    self.net = CMSnet(**self.net_params)
    self.net.mn.addController('c1')
    self.net.mn.addDummy('dummy')
    self.set_net_topo()
    self.net.start()
    self.set_cms_commands()
    
    try:
      code.interact(local=self.local_vars)
    finally:
      self.net.stop()
      self.net = None

  def run (self):
    """
    Runs the CLI. CURRENTLY UNUSED.
    """
    return
    self.set_net_topo()
    self.net.start()
    self.set_cms_commands()
    code.interact(local=self.local_vars)

  def stop (self):
    """
    Quit from the CLI. At the same time, stop CMSnet
    """
    if self.net:
      self.net.stop()

  def set_default_net_params (self):
    """
    Sets the default parameters for CMSnet. Do not override.

    self.net_params is guaranteed to exist when this method is called.
    """
    self.net_params["new_config"] = False
    self.net_params["config_folder"] = "."
    self.net_params["vm_dist_mode"] = "random"
    self.net_params["vm_dist_limit"] = 10
    self.net_params["msg_level"] = "all"
    self.net_params["net_cls"] = Mininet
    self.net_params["vm_cls"] = VirtualMachine
    self.net_params["hv_cls"] = Hypervisor
    self.net_params["controller_ip"] = "127.0.0.1"
    self.net_params["controller_port"] = 7790

    self.net_params["topo"] = None
    self.net_params["switch"] = OVSKernelSwitch
    self.net_params["host"] = Host
    self.net_params["controller"] = RemoteController
    self.net_params["link"] = Link
    self.net_params["intf"] = Intf
    self.net_params["build"] = False
    self.net_params["xterms"] = False
    self.net_params["cleanup"] = False
    self.net_params["ipBase"] = '10.0.0.0/8'
    self.net_params["inNamespace"] = False
    self.net_params["autoSetMacs"] = False
    self.net_params["autoStaticArp"] = False
    self.net_params["autoPinCpus"] = False
    self.net_params["listenPort"] = 6634

  def set_net_params (self):
    """
    Sets the parameters for CMSnet. Override to change parameters.

    self.net_params is guaranteed to exist when this method is called.
    """
    pass

  def set_net_topo (self):
    """
    Sets the topology for CMSnet. Override to change topology.

    self.net is guaranteed to exist when this method is called.
    """
    pass

  def set_cms_commands (self):
    """
    Sets the usable commands for the CLI. Do not override.

    self.local_vars is guaranteed to exist when this method is called.
    """
    self.local_vars.update(self.net.nameToComp)
    self.local_vars.update(self.get_special_vars())
    self.local_vars.update(self.get_method_names())
    self.local_vars.update(self.get_method_aliases())

  def get_special_vars (self):
    """
    Get the dictionary mapping from special variable names to their values.
    """
    special_vars = {
      'net': self.net,
      'VMs': self.net.VMs,
      'HVs': self.net.HVs,
    }
    return special_vars

  def get_method_names (self):
    """
    Get the dictionary mapping from method names to methods.
    """
    method_names = {
      'createVM':  self.createVM,
      'cloneVM':   self.cloneVM,
      'launchVM':  self.launchVM,
      'migrateVM': self.migrateVM,
      'pauseVM':   self.pauseVM,
      'resumeVM':  self.resumeVM,
      'stopVM':    self.stopVM,
      'deleteVM':  self.deleteVM,

      'printVMDistributionMode':  self.printVMDistributionMode,
      'changeVMDistributionMode': self.changeVMDistributionMode,
      'changeCMSMsgLevel':        self.changeCMSMsgLevel,
      'runMininet':               self.runMininet,

      'evictVMsFromHV': self.evictVMsFromHV,
      'invictVMsToHV':  self.invictVMsToHV,
      'enableHV':       self.enableHV,
      'disableHV':      self.disableHV,
      'killHV':         self.killHV,

      'xterm':    self.xterm,
      'gterm':    self.gterm,
      'x11':      self.x11,
      'isHVFull': self.isHVFull,
    }
    return method_names

  def get_method_aliases (self):
    """
    Get the dictionary mapping from method aliases to methods.
    """
    method_aliases = {
      'create':  self.createVM,
      'addVM':   self.createVM,
      'add':     self.createVM,
      'clone':    self.cloneVM,
      'copyVM':   self.cloneVM,
      'copy':     self.cloneVM,
      'cp':       self.cloneVM,
      'launch':  self.launchVM,
      'startVM': self.launchVM,
      'start':   self.launchVM,
      'migrate':  self.migrateVM,
      'moveVM':   self.migrateVM,
      'move':     self.migrateVM,
      'mv':       self.migrateVM,
      'pause':   self.pauseVM,
      'resume':    self.resumeVM,
      'unpauseVM': self.resumeVM,
      'unpause':   self.resumeVM,
      'stop':    self.stopVM,
      'delete':   self.deleteVM,
      'removeVM': self.deleteVM,
      'remove':   self.deleteVM,
      'rm':       self.deleteVM,

      'mode_info': self.printVMDistributionMode,
      'mode':      self.changeVMDistributionMode,
      'level':     self.changeCMSMsgLevel,

      'evict':   self.evictVMsFromHV,
      'invict':  self.invictVMsToHV,
      'enable':  self.enableHV,
      'disable': self.disableHV,
      'kill':    self.killHV,
      'crashHV': self.killHV,
      'crash':   self.killHV,
    }
    return method_aliases
























  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
  # CMS Command Argument Checks
  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

  non_vm_cmsnet_name = r'^([scdf]|hv|switch|controller|dummy|fabric)(\d+)?$'
  rsvd_name_pattern = re.compile(non_vm_cmsnet_name)

  def _check_vm_name_available (self, vm_name):
    """
    Check availability of name for a new VM.

    vm_name: Name of VM image.
    Returns True if error occured, False otherwise.
    """
    if vm_name in self.net.mn:
      if vm_name in self.net:
        raise CMSVMNameOccupiedError(self.net[vm_name])
      else:
        raise CMSVMNameOccupiedError(self.net.mn[vm_name])

    if self.rsvd_name_pattern.search(vm_name):
      raise CMSNameReservedForOtherTypeError(vm_name)
    elif vm_name in self.get_special_vars():
      raise CMSNameReservedForSpecialVarError(vm_name)
    elif vm_name in self.get_method_names():
      raise CMSNameReservedForMethodError(vm_name)
    elif vm_name in self.get_method_aliases():
      raise CMSNameReservedForMethodError(vm_name)

  def _get_vm_cls (self, vm_cls_input):
    """
    Get the intended VM class.

    vm_cls_input: Input information to obtain VM class (name or class itself).
    Returns VM class represented by input.
    """
    vm_cls = vm_cls_input
    if isinstance(vm_cls_input, basestring):
      vm_cls = getattr(cmsnet.cms_comp, vm_cls_input, None)
      if not vm_cls:
        raise CMSCompClassNameError(vm_cls_input)
    return vm_cls

  def _check_vm (self, vm, exp_running=None, exp_paused=None):
    """
    Check conditions for an existing VM.

    vm: VM image instance.
    exp_running: Expected result of running or not. None if not matter.
    exp_paused: Expected result of paused or not. None if not matter.
    Returns True if error occured, False otherwise.
    """
    if not isinstance(vm, VirtualMachine):
      raise CMSCompTypeError(vm)

    if exp_running is not None:
      if exp_running != vm.is_running():
        raise CMSVMRunningStateError(vm)

    if exp_paused is not None:
      if exp_paused != vm.is_paused():
        raise CMSVMPausedStateError(vm)

  def _check_hv (self, hv, exp_enabled=None):
    """
    Check conditions for a hypervisor.

    hv: VM image instance.
    exp_enabled: Expected result of HV enabled or not. None if not matter.
    Returns True if error occured, False otherwise.
    """
    if not isinstance(hv, Hypervisor):
      raise CMSCompTypeError(hv)

    if exp_enabled is not None:
      if exp_enabled != hv.is_enabled():
        raise CMSHypervisorEnabledStateError(hv)

  def _get_comp (self, comp_input):
    """
    Get the CMS component representation.

    comp_input: Input info on CMS component (its name or component itself).
    Returns CMS component represented by input.
    """
    comp = comp_input
    if isinstance(comp_input, basestring):
      if comp_input not in self.net:
        raise CMSCompNameError(comp_input)
      comp = self.net[comp_input]

    if isinstance(comp, CMSComponent):
      return comp
    else:
      raise CMSCompTypeError(comp)

  def _get_vm (self, vm_input):
    """
    Get the VM representation.

    vm_input: Input information to obtain VM. May be its name or VM itself.
    Returns VM represented by input.
    """
    vm = vm_input
    if isinstance(vm_input, basestring):
      if vm_input not in self.net:
        raise CMSVMNameError(vm_input)
      vm = self.net[vm_input]

    if isinstance(vm, VirtualMachine):
      return vm
    else:
      raise CMSCompTypeError(vm)

  def _get_hv (self, hv_input):
    """
    Get the hypervisor representation.

    vm_input: Input information to obtain HV. May be its name or HV itself.
    Returns HV represented by input.
    """
    hv = hv_input
    if isinstance(hv_input, basestring):
      if hv_input not in self.net:
        raise CMSHypervisorNameError(hv_input)
      hv = self.net[hv_input]

    if isinstance(hv, Hypervisor):
      return hv
    else:
      raise CMSCompTypeError(hv)









  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
  # CMS Main VM Commands (ZZZ)
  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~


  def createVM (self, vm_name, vm_script=None, vm_cls=None, **params):
    """
    Create a virtual machine image.

    vm_name: Name of new VM to be created.
    vm_script: Script name for VM to run. None if default.
    vm_cls: Class type of the VM component. None if default.
    params: Parameters for the underlying node.
    Returns a newly created VM instance. None if errored.
    """
    vm_cls = self._get_vm_cls(vm_cls)

    if not isinstance(vm_name, basestring):
      raise CMSTypeError('vm_name must be a string')
    if vm_script is not None and not isinstance(vm_script, basestring):
      raise CMSTypeError('vm_script must be None or a string')
    if vm_cls is not None and not issubclass(vm_cls, VirtualMachine):
      raise CMSTypeError('vm_cls must be None or a subclass of VirtualMachine')

    self._check_vm_name_available(vm_name)
    if vm_script and vm_script not in self.net.possible_scripts:
      raise CMSInvalidChoiceValueError('vm_script', vm_script)

    vm = self.net.createVM(vm_name, vm_script, vm_cls, **params)
    if vm is None:
      return None
    self.local_vars[vm_name] = vm
    return vm

  def cloneVM (self, old_vm, new_vm_name=None):
    """
    Clone a virtual machine image.

    old_vm: VM instance/name to be copied from.
    new_vm_name: Name of new VM to be cloned to. None if default.
    Returns a newly copied VM instance, None if errored.
    """
    old_vm = self._get_vm(old_vm)
    # self._check_vm(old_vm)

    if new_vm_name is not None:
      if not isinstance(new_vm_name, basestring):
        raise CMSTypeError('new_vm_name must be None or a string')
      self._check_vm_name_available(new_vm_name)

    vm = self.net.cloneVM(old_vm, new_vm_name)
    if vm is None:
      return None
    self.local_vars[vm_name] = vm
    return vm

  def launchVM (self, vm, hv=None):
    """
    Initialize the created VM on a hypervisor.

    vm: VM instance/name to launch.
    hv: Hypervisor instance/name to launch on. None if default.
    """
    vm = self._get_vm(vm)
    self._check_vm(vm, exp_running=False)

    if hv is not None:
      hv = self._get_hv(hv)
      self._check_hv(hv, exp_enabled=True)

    self.net.launchVM(vm, hv)

  def migrateVM (self, vm, hv=None):
    """
    Migrate a running image to another hypervisor.

    vm: VM instance/name to move.
    hv: Hypervisor instance/name to migrate onto. None if default.
    """
    vm = self._get_vm(vm)
    self._check_vm(vm, exp_running=True)

    if hv is not None:
      hv = self._get_hv(hv)
      self._check_hv(hv, exp_enabled=True)

    self.net.migrateVM(vm, hv)

  def pauseVM (self, vm):
    """
    Pause a currently running VM.

    vm: VM instance/name to pause.
    """
    vm = self._get_vm(vm)
    self._check_vm(vm, exp_paused=False)

    self.net.pauseVM(vm)

  def resumeVM (self, vm):
    """
    Resume a currently paused VM.

    vm: VM instance/name to resume.
    """
    vm = self._get_vm(vm)
    self._check_vm(vm, exp_paused=True)

    self.net.resumeVM(vm)

  def stopVM (self, vm):
    """
    Stop a running image.

    vm: VM instance/name to stop running.
    """
    vm = self._get_vm(vm)
    self._check_vm(vm, exp_running=True)

    self.net.stopVM(vm)

  def deleteVM (self, vm):
    """
    Remove the virtual machine image from the hypervisor.

    vm: VM instance/name to remove
    """
    vm = self._get_vm(vm)
    # self._check_vm(vm)

    vm_name = vm.name
    self.net.deleteVM(vm)
    del self.local_vars[vm_name]











  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
  # CMS Main Toggle Commands
  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~


  def printVMDistributionMode (self):
    """
    Print information about the mode of VM distribution across hypervisors.
    """
    out_str = []
    out_str.append("vm_dist_mode: %s" % self.net.vm_dist_mode)
    if self.net.vm_dist_mode == "packed":
      out_str.append("vm_dist_limit: %s" % self.net.vm_dist_limit)
    elif self.net.vm_dist_mode in ["same", "different"]:
      out_str.append("last_hv: %s" % self.net.last_hv)
    elif self.net.vm_dist_mode in ["cycle", "cycleall"]:
      out_str.append("cycle_pos: %s" % self.net.cycle_pos)
      if self.net.vm_dist_mode == "cycle":
        hv_cycle_names = [hv.name for hv in self.net.hv_cycle]
        out_str.append("hv_cycle: %s" % hv_cycle_names)

    output("\n\t".join(out_str)+"\n")

  def changeVMDistributionMode (self, vm_dist_mode, vm_dist_limit=None):
    """
    Change the mode of VM distribution across hypervisors.

    vm_dist_mode: Mode to change to.
      - random    = Choose a random HV.
      - sparse    = Choose HVs sparsely and evenly.
      - packed    = Choose HVs so that VMs are packed together.
    vm_dist_limit: Limit of number of VMs hypervisors can hold.
                   For "packed" mode only.
    """
    if not isinstance(vm_dist_mode, basestring):
      raise CMSTypeError('vm_dist_mode must be a string')
    if vm_dist_mode not in self.net.possible_modes:
      raise CMSInvalidChoiceValueError('vm_dist_mode', vm_dist_mode)
    vm_dist_args = {}

    if vm_dist_limit is not None:
      if not isinstance(vm_dist_limit, int):
        raise CMSTypeError('vm_dist_limit must be an integer')
      if vm_dist_limit <= 0:
        raise CMSNonpositiveValueError('vm_dist_limit', vm_dist_limit)
      if vm_dist_mode != "packed":
        raise CMSInvalidParameterValueError('vm_dist_mode', vm_dist_mode,
                                            'vm_dist_limit')
      vm_dist_args["vm_dist_limit"] = vm_dist_limit

    self.net.changeVMDistributionMode(vm_dist_mode, vm_dist_args)

  def changeCMSMsgLevel (self, msg_level):
    """
    Change the level of CMS message handling at the controller.

    msg_level: level of CMS message handling at controller.
    """
    if not isinstance(msg_level, basestring):
      raise CMSTypeError('msg_level must be a string')
    if msg_level not in self.net.possible_levels:
      raise CMSInvalidChoiceValueError('msg_level', msg_level)

    self.net.changeCMSMsgLevel(msg_level)

  def runMininet (self):
    """
    Run the Mininet CLI.
    """
    MininetCLI(self.net.mn)







  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
  # CMS Main HV Commands
  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

  def evictVMsFromHV (self, hv):
    """
    Evict all VMs running on the hypervisor off to other VMs.

    hv: Hypervisor instance/name to evict all VMs off of.
    """
    hv = self._get_hv(hv)
    self._check_hv(hv, exp_enabled=True)

    self.net.evictVMsFromHV(hv)

  def invictVMsToHV (self, hv, max_num_vms=1):
    """
    Invict a number of inactive VMs to run on the hypervisor.

    hv: Hypervisor instance/name to invict VMs onto.
    """
    hv = self._get_hv(hv)
    self._check_hv(hv, exp_enabled=True)

    if not isinstance(max_num_vms, int):
      raise CMSTypeError('max_num_vms must be an integer')
    if max_num_vms <= 0:
      raise CMSNonpositiveValueError('max_num_vms', max_num_vms)

    self.net.invictVMsToHV(hv, max_num_vms)

  def enableHV (self, hv):
    """
    Enable a hypervisor.

    hv: Hypervisor instance/name to enable.
    """
    hv = self._get_hv(hv)
    self._check_hv(hv, exp_enabled=False)

    self.net.enableHV(hv)

  def disableHV (self, hv):
    """
    Disable a hypervisor. This simulates shutting down for maintainence.

    hv: Hypervisor instance/name to disable.
    """
    hv = self._get_hv(hv)
    self._check_hv(hv, exp_enabled=True)

    self.net.disableHV(hv)

  def killHV (self, hv):
    """
    Kill a hypervisor. This simulates a hypervisor failing.

    hv: Hypervisor instance/name to kill off.
    """
    hv = self._get_hv(hv)
    self._check_hv(hv, exp_enabled=True)

    self.net.killHV(hv)







  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
  # CMS Other Extra Commands
  #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

  def xterm (self, *comps, **kwargs):
    """
    Spawn xterm(s) for the given component(s).

    comp: Components to run xterm for.
    """
    temp_comps = []
    for comp in comps:
      comp = self._get_comp(comp)
      temp_comps.append(comp)
    comps = temp_comps

    for comp in comps:
      self.net.makeTerm(comp, term='xterm', **kwargs)

  def gterm (self, *comps, **kwargs):
    """
    Spawn gnome-terminal(s) for the given component(s).

    comp: Components to run gterm for.
    """
    temp_comps = []
    for comp in comps:
      comp = self._get_comp(comp)
      temp_comps.append(comp)
    comps = temp_comps

    for comp in comps:
      self.net.makeTerm(comp, term='gterm', **kwargs)

  def x11 (self, comp, cmd_list=[]):
    """
    Spawn xterm(s) for the given component(s).

    comp: Components to run xterm for.
    """
    comp = self._get_comp(comp)
    if not isinstance(cmd_list, list):
      raise CMSTypeError('cmd_list must be an list of strings')
    for cmd in cmd_list:
      if not isinstance(cmd, basestring):
        raise CMSTypeError('cmd_list must be an list of strings')

    self.net.makeX11(comp, cmd_list)

  def isHVFull (self, hv):
    """
    Check if hypervisor has reached its VM capacity limit (packed mode).

    hv: Hypervisor instance/name to check.
    """
    hv = self._get_hv(hv)
    #self._check_hv(hv)
    if self.net.vm_dist_mode != "packed": return False
    return self.net.isHVFull(hv)





















































  # Beta stuff. Don't bother with this.


  def changeVMDistributionModeBETA (self, vm_dist_mode, vm_dist_limit=None,
                                last_hv=None, cycle_pos=None, hv_cycle=None):
    """
    HIGHLY INCOMPLETE!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    Please wait until later to use this method.


    Change the mode of VM distribution across hypervisors.

    vm_dist_mode: Mode to change to.
      - random    = Choose a random HV.
      - sparse    = Choose HVs sparsely and evenly.
      - packed    = Choose HVs so that VMs are packed together.
      - same      = Choose an HV the same as the last chosen one.
      - different = Choose a random HV different from the last chosen one.
      - cycle     = Choose HVs in a specific cycle.
      - cycleall  = Choose HVs in a cycle from all HVs.
    vm_dist_limit: Limit of number of VMs hypervisors can hold.
                   For "packed" mode only.
    last_hv: Last used hypervisor (name) as default.
             For "same" or "different" mode only.
    cycle_pos: Position of pointer in hypervisor cycle.
               For "cycle" or "cycleall" mode only.
    hv_cycle: Hypervisor cycle.
              For "cycle" mode only.
    """
    return

    if not isinstance(vm_dist_mode, basestring):
      raise CMSTypeError('vm_dist_mode must be a string')
    if vm_dist_mode not in self.net.possible_modes:
      raise CMSInvalidChoiceValueError('vm_dist_mode', vm_dist_mode)
    vm_dist_args = {}

    if vm_dist_limit is not None:
      if not isinstance(vm_dist_limit, int):
        raise CMSTypeError('vm_dist_limit must be an integer')
      if vm_dist_limit <= 0:
        raise CMSNonpositiveValueError('vm_dist_limit', vm_dist_limit)
      if vm_dist_mode != "packed":
        raise CMSInvalidParameterValueError('vm_dist_mode', vm_dist_mode,
                                            'vm_dist_limit')
      vm_dist_args["vm_dist_limit"] = vm_dist_limit

    if last_hv is not None:
      last_hv = self._get_hv(last_hv)
      #self._check_hv(last_hv)
      if vm_dist_mode != "packed":
        raise CMSInvalidParameterValueError('vm_dist_mode', vm_dist_mode,
                                            'last_hv')
      vm_dist_args["last_hv"] = last_hv

    """
    if cycle_pos is not None:
      if not isinstance(cycle_pos, int):
        raise CMSTypeError('cycle_pos must be an integer')
      if cycle_pos <= 0:
        raise CMSNonpositiveValueError('cycle_pos', vm_dist_limit)
      if hv_cycle is not None:
        # CMSHVCycleIndexError
      vm_dist_args["cycle_pos"] = cycle_pos


    if hv_cycle is not None:
      if not isinstance(hv_cycle, list):
        raise CMSTypeError('hv_cycle must be an list')
      temp_cycle = []
      for hv in hv_cycle:
        hv = self._get_hv(hv)
        #self._check_hv(hv)
        temp_cycle.append(hv)
      hv_cycle = temp_cycle


      if cycle_pos <= 0:
        raise CMSNonpositiveValueError('cycle_pos', vm_dist_limit)
      vm_dist_args["hv_cycle"] = hv_cycle
    """

    #CMSHVCycleIndexError
    #CMSNonpositiveValueError
    #CMSInvalidParameterValueError
    #CMSInvalidChoiceValueError

    self.net.changeVMDistributionMode(vm_dist_mode, vm_dist_args)
