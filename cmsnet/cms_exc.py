"""
Container for exceptions used for the (debatably) hacky API, taking advantage
of the fact that the code module that starts an internal Python interpreter can
handle throwing basic exceptions.
"""
from mininet.node import Node
from cmsnet.cms_comp import CMSComponent, VirtualMachine, Hypervisor



#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
# CMS Exceptions
#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~



class CMSBaseException (Exception):
  """
  Base Exception class for CMS API.

  An exception thrown is cleaner to write.
  """

  def __init__ (self, message):
    """
    Initialization

    message: Message of exception.
    """
    super(CMSBaseException, self).__init__(message)
    self.message = message







#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
# CMS Input Errors
#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~





class CMSCompNameError (CMSBaseException):
  """
  Component name not found in CMSnet.
  """
  def __init__ (self, name, message=None):
    """
    Initialization

    name: Name of relavant CMS component.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(name)
    super(CMSCompNameError, self).__init__(message)

  def get_message (self, name):
    """
    Generate error message.

    name: Name of relavant CMS component.
    """
    return 'No such CMS component %s.' % name


class CMSVMNameError (CMSCompNameError):
  """
  VM name not found in CMSnet.
  """
  def get_message (self, name):
    return 'No such VM image %s.' % name


class CMSHypervisorNameError (CMSCompNameError):
  """
  Hypervisor name not found in CMSnet.
  """
  def get_message (self, name):
    return 'No such hypervisor %s.' % name


class CMSTypeError (CMSBaseException):
  """
  Inappropriate CMS method argument type.
  """
  pass


class CMSCompTypeError (CMSTypeError):
  """
  Inappropriate CMS component type.
  """
  def __init__ (self, comp, message=None):
    """
    Initialization

    comp: Relavant CMS component.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(comp)
    super(CMSCompTypeError, self).__init__(message)

  def get_message (self, comp):
    """
    Generate error message.

    comp: Relavant CMS component.
    """
    if isinstance(comp, VirtualMachine):
      return '%s is a VM image.' % comp.name
    elif isinstance(comp, Hypervisor):
      return '%s is a hypervisor.' % comp.name
    elif isinstance(comp, CMSComponent):
      return '%s is another type of component.' % comp.name
    elif isinstance(comp, Node):
      return '%s is another node in underlying network.' % comp.name
    else:
      return '%s is a %s.' % (str(comp), comp.__class__.__name__)


class CMSNonpositiveValueError (CMSBaseException):
  """
  CMS argument is not a positive integer.
  """
  def __init__ (self, arg_name, arg_val, message=None):
    """
    Initialization

    arg_name: Relavant argument variable name.
    arg_val: Relavant argument input value.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(arg_name, arg_val)
    super(CMSNonpositiveValueError, self).__init__(message)

  def get_message (self, arg_name, arg_val):
    """
    Generate error message.

    arg_name: Relavant argument variable name.
    arg_val: Relavant argument input value.
    """
    return '%s=%d is not positive.' % (arg_name, arg_val)


class CMSInvalidChoiceValueError (CMSBaseException):
  """
  CMS argument is not a valid choice.
  """
  def __init__ (self, arg_name, arg_val, message=None):
    """
    Initialization

    arg_name: Relavant argument variable name.
    arg_val: Relavant argument input value.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(arg_name, arg_val)
    super(CMSInvalidChoiceValueError, self).__init__(message)

  def get_message (self, arg_name, arg_val):
    """
    Generate error message.

    arg_name: Relavant argument variable name.
    arg_val: Relavant argument input value.
    """
    return '%s=%d is not a valid choice.' % (arg_name, arg_val)






### Testing right now. For vm_dist_mode.





class CMSInvalidParameterValueError (CMSBaseException):
  """
  CMS argument should not contain certain parameter.
  """
  def __init__ (self, arg_name, arg_val, param_name, message=None):
    """
    Initialization

    arg_name: Relavant argument variable name.
    arg_val: Relavant argument input value.
    param_name: Relavant argument parameter name.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(arg_name, arg_val, param_name)
    super(CMSInvalidParameterValueError, self).__init__(message)

  def get_message (self, arg_name, arg_val, param_name):
    """
    Generate error message.

    arg_name: Relavant argument variable name.
    arg_val: Relavant argument input value.
    param_name: Relavant argument parameter name.
    """
    return '%s=%d should not have param %s.' % (arg_name, arg_val, param_name)


class CMSHVCycleIndexError (CMSBaseException):
  """
  Position index out of range of cycle.
  """
  def __init__ (self, cycle_pos, hv_cycle, message=None):
    """
    Initialization

    cycle_pos: Relavant cycle position.
    hv_cycle: Relavant hypervisor cycle.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(cycle_pos, hv_cycle)
    super(CMSHVCycleIndexError, self).__init__(message)

  def get_message (self, cycle_pos, hv_cycle):
    """
    Generate error message.

    cycle_pos: Relavant cycle position.
    hv_cycle: Relavant hypervisor cycle.
    """
    return 'Position %d not in range 0~%d of cycle.' % (cycle_pos, hv_cycle)







#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
# CMS Availability Errors
#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~


class CMSVMNameOccupiedError (CMSBaseException):
  """
  VM name already occupied by other CMS component.
  """
  def __init__ (self, comp, message=None):
    """
    Initialization

    comp: Relavant CMS component.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(comp)
    super(CMSVMNameOccupiedError, self).__init__(message)

  def get_message (self, comp):
    """
    Generate error message.

    comp: Relavant CMS component.
    """
    if isinstance(comp, VirtualMachine):
      return 'VM of the same name %s already exists.' % comp.name
    elif isinstance(comp, Hypervisor):
      return '%s is a hypervisor.' % comp.name
    elif isinstance(comp, CMSComponent):
      return '%s is another type of component.' % comp.name
    elif isinstance(comp, Node):
      return '%s is another node in underlying network.' % comp.name
    else:
      return '%s is a %s.' % (str(comp), comp.__class__.__name__)


class CMSNameReservedError (CMSBaseException):
  """
  Name is reserved.
  """
  def __init__ (self, name, message=None):
    """
    Initialization

    name: Reserved name in question.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(name)
    super(CMSNameReservedError, self).__init__(message)

  def get_message (self, name):
    """
    Generate error message.

    name: Reserved name in question.
    """
    return '%s is a reserved name.' % name


class CMSNameReservedForOtherTypeError (CMSNameReservedError):
  """
  Name is reserved for other components/nodes.
  """
  def get_message (self, name):
    return '%s is a reserved name for another type.' % name


class CMSNameReservedForSpecialVarError (CMSNameReservedError):
  """
  Name is reserved for special local variables in API.
  """
  def get_message (self, name):
    return '%s is a reserved name for special variables.' % name


class CMSNameReservedForMethodError (CMSNameReservedError):
  """
  Name is reserved for CMS methods.
  """
  def get_message (self, name):
    return '%s is a reserved name for methods.' % name











#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
# CMS State Errors
#~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

class CMSCompStateError (CMSBaseException):
  """
  Wrong CMS component state.
  """
  def __init__ (self, comp, message=None):
    """
    Initialization

    comp: Relavant CMS component.
    message: Message of exception. None if default.
    """
    if message is None:
      message = self.get_message(comp)
    super(CMSCompStateError, self).__init__(message)

  def get_message (self, comp):
    """
    Generate error message.

    comp: Relavant CMS component.
    """
    return 'CMS component %s is currently in the wrong state.' % comp.name


class CMSVMRunningStateError (CMSCompStateError):
  """
  Wrong VM running state.
  """
  def get_message (self, vm):
    if vm.is_running():
      return 'VM %s is currently running.' % vm.name
    else:
      return 'VM %s is currently inactive.' % vm.name

class CMSVMPausedStateError (CMSCompStateError):
  """
  Wrong VM paused state.
  """
  def get_message (self, vm):
    if vm.is_paused():
      return 'VM %s is currently paused.' % vm.name
    elif vm.is_running():
      return 'VM %s is currently running.' % vm.name
    else:
      return 'VM %s is currently inactive.' % vm.name

class CMSHypervisorEnabledStateError (CMSCompStateError):
  """
  Wrong Hypervisor enabled state.
  """
  def get_message (self, hv):
    if hv.is_enabled():
      return 'Hypervisor %s is currently enabled.' % hv.name
    else:
      return 'Hypervisor %s is currently disabled.' % hv.name



