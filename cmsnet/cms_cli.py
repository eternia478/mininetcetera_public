"""
A simple command-line interface for CMSnet.

The CMSnet CLI provides a simple control console which
makes it easy to talk to nodes/components. For example, the command

cmsnet> h27 ifconfig

runs 'ifconfig' on VM h27's host node.

Having a single console rather than, for example, an xterm for each
node is particularly convenient for networks of any reasonable
size.

The CLI automatically substitutes IP addresses for node/component names,
so commands like

cmsnet> h2 ping h3

should work correctly and allow VM host h2 to ping VM host h3

Several useful commands are provided, including the ability to
list all components ('comps'), to print out the cloud hierarchy
('dump') and to handle VMs ('create', 'init', 'mv', and 'rm').
"""

from subprocess import call
from cmd import Cmd
from os import isatty
from select import poll, POLLIN
import sys
import time

from mininet.log import info, output, error
from mininet.term import makeTerms, runX11
from mininet.util import quietRun, isShellBuiltin, dumpNodeConnections
from mininet.util import checkInt, splitArgs

from cmsnet.cms_comp import VirtualMachine, Hypervisor
import re

class CMSCLI( Cmd ):
    "Simple command-line interface to talk to VMs and hypervisors."

    prompt = 'cmsnet> '

    def __init__( self, cmsnet, stdin=sys.stdin, script=None ):
        self.cn = cmsnet
        # Local variable bindings for py command
        self.locals = { 'net': cmsnet }
        # Attempt to handle input
        self.stdin = stdin
        self.inPoller = poll()
        self.inPoller.register( stdin )
        self.inputFile = script
        Cmd.__init__( self )
        info( '*** Starting CLI:\n' )
        if self.inputFile:
            self.do_source( self.inputFile )
            return
        while True:
            try:
                # Make sure no nodes are still waiting
                for node in self.cn.mn.values():
                    while node.waiting:
                        node.sendInt()
                        node.monitor()
                if self.isatty():
                    quietRun( 'stty sane' )
                self.cmdloop()
                break
            except KeyboardInterrupt:
                output( '\nInterrupt\n' )

    def emptyline( self ):
        "Don't repeat last command when you hit return."
        pass

    def getLocals( self ):
        "Local variable bindings for py command"
        self.locals.update( self.cn )
        return self.locals

    # Disable pylint "Unused argument: 'arg's'" messages, as well as
    # "method could be a function" warning, since each CLI function
    # must have the same interface
    # pylint: disable-msg=R0201

    helpStr = (
        'IGNORE WHATEVER IS BELOW. NOT FOR CMSnet!!!\n'
        'You may also send a command to a node using:\n'
        '  <node> command {args}\n'
        'For example:\n'
        '  mininet> h1 ifconfig\n'
        '\n'
        'The interpreter automatically substitutes IP addresses\n'
        'for node names when a node is the first arg, so commands\n'
        'like\n'
        '  mininet> h2 ping h3\n'
        'should work.\n'
        '\n'
        'Some character-oriented interactive commands require\n'
        'noecho:\n'
        '  mininet> noecho h2 vi foo.py\n'
        'However, starting up an xterm/gterm is generally better:\n'
        '  mininet> xterm h2\n\n'
    )

    def not_implemented( self ):
        print "NOT IMPLEMENTED YET."

    def do_help( self, line ):
        "Describe available CLI commands."
        Cmd.do_help( self, line )
        if line is '':
            output( self.helpStr )
        self.not_implemented()

    def do_comps( self, _line ):
        "List all components."
        comps = ' '.join( sorted( self.cn ) )
        output( 'available components are: \n%s\n' % comps )

    def do_dump( self, _line ):
        "Dump component info."
        # NOTE: This may be useful for CMS, but currently not implemented.
        #for node in self.cn.values():
        #    output( '%s\n' % repr( node ) )
        self.not_implemented()
        return

    def do_sh( self, line ):
        "Run an external shell command"
        call( line, shell=True )

    # do_py() and do_px() need to catch any exception during eval()/exec()
    # pylint: disable-msg=W0703

    def do_py( self, line ):
        """Evaluate a Python expression.
           Node names may be used, e.g.: py h1.cmd('ls')"""
        try:
            result = eval( line, globals(), self.getLocals() )
            if not result:
                return
            elif isinstance( result, str ):
                output( result + '\n' )
            else:
                output( repr( result ) + '\n' )
        except Exception, e:
            output( str( e ) + '\n' )

    # We are in fact using the exec() pseudo-function
    # pylint: disable-msg=W0122

    def do_px( self, line ):
        """Execute a Python statement.
            Node names may be used, e.g.: px print h1.cmd('ls')"""
        try:
            exec( line, globals(), self.getLocals() )
        except Exception, e:
            output( str( e ) + '\n' )

    # pylint: enable-msg=W0703,W0122


    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Command Argument Checks
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def _check_vm_name_available( self, vm_name ):
        """
        Check availability of name for a new VM.

        vm_name: Name of VM image. If None, ignore and return.
        Returns True if error occured, False otherwise.
        """
        if not vm_name:              # Ignore NoneType names
            return False

        if vm_name in self.cn.mn:
            if vm_name in self.cn:
                comp = self.cn[vm_name]
                if isinstance(comp, VirtualMachine):
                    error('VM of the same name %s already exists\n' % vm_name)
                elif isinstance(comp, Hypervisor):
                    error('%s is a hypervisor\n' % vm_name)
                else:
                    error('%s is another type of component\n' % vm_name)
            else:
                error('%s is another node in underlying network\n' % vm_name)
            return True
        r = r'^([scdf]|hv|switch|controller|dummy|fabric)(\d+)?$'
        if re.search( r, vm_name ):
            error('%s is a reserved name for another type\n' % vm_name)
            return True

        return False

    def _check_vm( self, vm, exp_running=None, exp_paused=None ):
        """
        Check conditions for an existing VM.

        vm: VM image instance. If None, ignore and return.
        exp_running: Expected result of running or not. None if not matter.
        exp_paused: Expected result of paused or not. None if not matter.
        Returns True if error occured, False otherwise.
        """
        if not vm:                   # Ignore NoneType instances
            return False
        if exp_paused is not None:   # exp_paused implies exp_running is True
            exp_running = True

        if not isinstance(vm, VirtualMachine):
            if isinstance(vm, Hypervisor):
                error('%s is a hypervisor\n' % vm.name)
            else:
                error('%s is another type of component\n' % vm.name)
            return True

        vm_running = vm.is_running()
        if exp_running is not None:
            if not vm_running and exp_running:
                error('VM %s is currently inactive\n' % vm.name)
                return True
            elif vm_running and not exp_running:
                error('VM %s is currently running\n' % vm.name)
                return True

        vm_paused = vm.is_paused()
        if exp_paused is not None and vm_running:
            if not vm_paused and exp_paused:
                error('VM %s is currently running\n' % vm.name)
                return True
            elif vm_paused and not exp_paused:
                error('VM %s is currently paused\n' % vm.name)
                return True

        return False

    def _check_hv( self, hv, exp_enabled=None ):
        """
        Check conditions for a hypervisor.

        hv: VM image instance. If None, ignore and return.
        exp_enabled: Expected result of HV enabled or not. None if not matter.
        Returns True if error occured, False otherwise.
        """
        if not hv:                   # Ignore NoneType instances
            return False

        if not isinstance(hv, Hypervisor):
            if isinstance(hv, VirtualMachine):
                error('%s is a VM image\n' % hv.name)
            else:
                error('%s is another type of component\n' % hv.name)
            return True

        hv_enabled = hv.is_enabled()
        if exp_enabled is not None:
            if not hv_enabled and exp_enabled:
                error('Hypervisor %s is currently disabled\n' % hv.name)
                return True
            elif hv_enabled and not exp_enabled:
                error('Hypervisor %s is currently enabled\n' % hv.name)
                return True

        return False

    def _check_vm_name( self, name, exp_running=None, exp_paused=None ):
        if not name:                 # Ignore if not set by input.
            return False, None       # NOTE: Already handled at parsing.

        if name not in self.cn:
            error('No such VM image %s\n' % name)
            return True, None
        vm = self.cn[name]
        er = self._check_vm(vm, exp_running=exp_running, exp_paused=exp_paused)
        return er, vm


    def _check_hv_name( self, name, exp_enabled=None ):
        if not name:                 # Ignore if not set by input.
            return False, None       # NOTE: Already handled at parsing.

        if name not in self.cn:
            error('No such hypervisor %s\n' % name)
            return True, None
        hv = self.cn[name]
        err = self._check_hv(hv, exp_enabled=exp_enabled)
        return err, hv












    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main VM Commands (ZZZ)
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~


    def do_add( self, line, cmd_name='add' ):
        "Create a virtual machine image."
        args = line.split()
        vm_name = None
        vm_kwargs = {}

        if len(args) == 1:
            vm_name, vm_args, vm_kwargs = splitArgs(args[0])
            if len(vm_args) >= 1:
                if vm_kwargs.get("vm_script"):
                    error("Bad argument: multiple values for vm_script\n")
                    return
                else:
                    vm_kwargs["vm_script"] = vm_args[0]
            if len(vm_args) >= 2:
                if vm_kwargs.get("vm_cls"):
                    error("Bad argument: multiple values for vm_cls\n")
                    return
                else:
                    vm_kwargs["vm_cls"] = vm_args[1]
            if len(vm_args) >= 3:
                error("Bad argument: have more than 3 non-keyword arguments\n")
                return
        else:
            item = 'vm_name[,vm_script][,vm_cls][,vm_kwarg=kwarg]'
            usage = '%s %s' % (cmd_name, item)
            error('invalid number of args: %s\n' % usage)
            return

        err1 = self._check_vm_name_available(vm_name)
        err2 = False      # TODO: Check vm_script value and others.

        if not err1 and not err2:
            self.cn.createVM(vm_name, **vm_kwargs)

    def do_cp( self, line, cmd_name='cp' ):
        "Clone a virtual machine image."
        args = line.split()
        old_vm_name = None
        new_vm_name = None

        if len(args) == 1:
            old_vm_name = args[0]
        elif len(args) == 2:
            old_vm_name = args[0]
            new_vm_name = args[1]
        else:
            usage = '%s old_vm_name [new_vm_name]' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err1, old_vm = self._check_vm_name(old_vm_name)
        err2 = self._check_vm_name_available(vm_name)

        if not err1 and not err2:
            self.cn.cloneVM(old_vm, new_vm_name)

    def do_launch( self, line, cmd_name='launch' ):
        "Initialize the created VM on a hypervisor."
        args = line.split()
        vm_name = None
        hv_name = None

        if len(args) == 1:
            vm_name = args[0]
        elif len(args) == 2:
            vm_name = args[0]
            hv_name = args[1]
        else:
            usage = '%s vm_name [hv_name]' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err1, vm = self._check_vm_name(vm_name, exp_running=False)
        err2, hv = self._check_hv_name(hv_name, exp_enabled=True)

        if not err1 and not err2:
            self.cn.launchVM(vm, hv)

    def do_mv( self, line, cmd_name='mv' ):
        "Migrate a running image to another hypervisor."
        args = line.split()
        vm_name = None
        hv_name = None

        if len(args) == 1:
            vm_name = args[0]
        elif len(args) == 2:
            vm_name = args[0]
            hv_name = args[1]
        else:
            usage = '%s vm_name [hv_name]' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err1, vm = self._check_vm_name(vm_name, exp_running=True)
        err2, hv = self._check_hv_name(hv_name, exp_enabled=True)

        if not err1 and not err2:
            self.cn.migrateVM(vm, hv)

    def do_pause( self, line, cmd_name='pause' ):
        "Pause a currently running VM."
        args = line.split()
        vm_name = None

        if len(args) == 1:
            vm_name = args[0]
        else:
            usage = '%s vm_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, vm = self._check_vm_name(vm_name, exp_paused=False)

        if not err:
            self.cn.pauseVM(vm)

    def do_resume( self, line, cmd_name='resume' ):
        "Resume a currently paused VM."
        args = line.split()
        vm_name = None

        if len(args) == 1:
            vm_name = args[0]
        else:
            usage = '%s vm_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, vm = self._check_vm_name(vm_name, exp_paused=True)

        if not err:
            self.cn.resumeVM(vm)

    def do_stop( self, line, cmd_name='stop' ):
        "Stop a running image."
        args = line.split()
        vm_name = None

        if len(args) == 1:
            vm_name = args[0]
        else:
            usage = '%s vm_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, vm = self._check_vm_name(vm_name, exp_running=True)

        if not err:
            self.cn.stopVM(vm)

    def do_rm( self, line, cmd_name='rm' ):
        "Remove the virtual machine image from CMSnet."
        args = line.split()
        vm_name = None

        if len(args) == 1:
            vm_name = args[0]
        else:
            usage = '%s vm_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, vm = self._check_vm_name(vm_name)

        if not err:
            self.cn.deleteVM(vm)



















    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main Toggle Commands
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~


    def do_modeinfo( self, line, cmd_name='modeinfo' ):
        "Output the current VM distribution mode information."
        args = line.split()

        if len(args) != 0:
            usage = '%s [nothing]' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        out_str = "vm_dist_mode: %s" % self.cn.vm_dist_mode
        if self.cn.vm_dist_mode == "packed":
            out_str += "\tvm_dist_limit: %s" % self.cn.vm_dist_limit
        elif self.cn.vm_dist_mode in ["same", "different"]:
            out_str += "\tlast_hv: %s" % self.cn.last_hv
        elif self.cn.vm_dist_mode in ["cycle", "cycleall"]:
            out_str += "\tcycle_pos: %s" % self.cn.cycle_pos
            if self.cn.vm_dist_mode == "cycle":
                hv_cycle_names = [hv.name for hv in self.cn.hv_cycle]
                out_str += "\thv_cycle: %s" % hv_cycle_names

        output(out_str+"\n")

    def do_mode( self, line, cmd_name='mode' ):
        "Change the mode of VM distribution across hypervisors."
        args = line.split()
        vm_dist_mode = None
        vm_dist_args = None

        if len(args) == 0:
            usage1 = '\t%s random|sparse' % cmd_name
            usage2 = '\t%s packed [vm_dist_limit]' % cmd_name
            usage3 = '\t%s same|different [last_vm]' % cmd_name
            usage4 = '\t%s cycle [cycle_pos [hv_name1 hv_name2...]]' % cmd_name
            usage5 = '\t%s cycleall [cycle_pos]' % cmd_name
            output("usage:\n")
            output("\n".join([usage1, usage2, usage3, usage4, usage5]))
            output("\n")
            self.do_modeinfo(line, cmd_name='mode')
            return

        vm_dist_mode = args[0]
        if vm_dist_mode not in self.cn.possible_modes:
            error('No such VM distribution mode: %s\n' % vm_dist_mode)
            return

        if len(args) >= 2:
            vm_dist_args = {}
            if vm_dist_mode == "packed":
                if len(args) > 2:
                    usage = '%s %s [vm_dist_limit]' % (cmd_name, vm_dist_mode)
                    error('invalid number of args: %s\n' % usage)
                    return
                if not checkInt(args[1]):
                    error('second argument not an integer: %s\n' % args[1])
                    return
                vm_dist_limit = int(args[1])
                if vm_dist_limit <= 0:
                    error('Invalid capacity limit: %s\n' % vm_dist_limit)
                    return
                vm_dist_args["vm_dist_limit"] = vm_dist_limit
            elif vm_dist_mode in ["same", "different"]:
                if len(args) > 2:
                    usage = '%s %s [last_hv]' % (cmd_name, vm_dist_mode)
                    error('invalid number of args: %s\n' % usage)
                    return
                last_hv_name = args[1]
                err, last_hv = self._check_hv_name(last_hv_name)
                if err: return
                vm_dist_args["last_hv"] = last_hv
            elif vm_dist_mode in ["cycle", "cycleall"]:
                if not checkInt(args[1]):
                    error('second argument not an integer: %s\n' % args[1])
                    return
                hv_cycle = None
                cycle_pos = int(args[1])

                if len(args) > 2:
                    if vm_dist_mode == "cycleall":
                        usage = '%s %s [cycle_pos]' % (cmd_name, vm_dist_mode)
                        error('invalid number of args: %s\n' % usage)
                        return
                    any_err = False
                    hv_cycle = []
                    for hv_name in args[2:]:
                        err, hv = self._check_hv_name(hv_name)
                        hv_cycle.append(hv)
                        any_err = any_err or err
                    if any_err: return

                if hv_cycle:
                    pos_range = range(0, len(hv_cycle))
                elif vm_dist_mode == "cycle":
                    pos_range = range(0, len(self.cn.hv_cycle))
                else:
                    pos_range = range(0, len(self.cn.HVs))
                if cycle_pos not in pos_range:
                    range_str = "range(0, %d)" % len(pos_range)
                    error('cycle_pos %s not in %s\n' % (cycle_pos, range_str))
                    return

                vm_dist_args["hv_cycle"] = hv_cycle
                vm_dist_args["cycle_pos"] = cycle_pos
            else:
                usage = '%s %s' % (cmd_name, vm_dist_mode)
                error('invalid number of args: %s\n' % usage)
                return

        self.cn.changeVMDistributionMode(vm_dist_mode, vm_dist_args)

    def do_level( self, line, cmd_name='level' ):
        "Change the level of CMS message handling at the controller."
        args = line.split()
        msg_level = None

        if len(args) == 0:
            out_str = "msg_level: %s" % self.cn.msg_level
            output(out_str+"\n")
            return
        elif len(args) == 1:
            msg_level = args[0]
        else:
            usage = '%s msg_level' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        if msg_level not in self.cn.possible_levels:
            error('No such CMS message level: %s\n' % msg_level)
            return

        self.cn.changeCMSMsgLevel(msg_level)
















    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main HV Commands
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def do_evict( self, line, cmd_name='evict' ):
        "Evict all VMs running on the hypervisor off to other VMs."
        args = line.split()
        hv_name = None

        if len(args) == 1:
            hv_name = args[0]
        else:
            usage = '%s hv_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, hv = self._check_hv_name(hv_name, exp_enabled=True)

        if not err:
            self.cn.evictVMsFromHV(hv)

    def do_invict( self, line, cmd_name='invict' ):
        "Invict a number of inactive VMs to run on the hypervisor."
        args = line.split()
        hv_name = None
        max_num_vms = 1

        if len(args) == 1:
            hv_name = args[0]
        elif len(args) == 2:
            hv_name = args[0]
            if not checkInt(args[1]):
                error('second argument not an integer: %s\n' % args[1])
                return
            max_num_vms = int(args[1])
            if max_num_vms <= 0:
                error('max_num_vms not positive: %s\n' % max_num_vms)
                return
        else:
            usage = '%s hv_name [max_num_vms]' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, hv = self._check_hv_name(hv_name, exp_enabled=True)

        if not err:
            self.cn.invictVMsToHV(hv, max_num_vms)

    def do_enable( self, line, cmd_name='enable' ):
        "Enable a hypervisor."
        args = line.split()
        hv_name = None

        if len(args) == 1:
            hv_name = args[0]
        else:
            usage = '%s hv_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, hv = self._check_hv_name(hv_name, exp_enabled=False)

        if not err:
            self.cn.enableHV(hv)

    def do_disable( self, line, cmd_name='disable' ):
        "Disable a hypervisor."
        args = line.split()
        hv_name = None

        if len(args) == 1:
            hv_name = args[0]
        else:
            usage = '%s hv_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, hv = self._check_hv_name(hv_name, exp_enabled=True)

        if not err:
            self.cn.disableHV(hv)

    def do_kill( self, line, cmd_name='kill' ):
        "Kill a hypervisor."
        args = line.split()
        hv_name = None

        if len(args) == 1:
            hv_name = args[0]
        else:
            usage = '%s hv_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err, hv = self._check_hv_name(hv_name, exp_enabled=True)

        if not err:
            self.cn.killHV(hv)



















    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Beta Commands
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~




    def do_qstart( self, line ):
        "Combination of add and launch."
        args = line.split()
        vm_name = None
        hv_name = None

        if len(args) == 1:
            vm_name = args[0]
        elif len(args) == 2:
            vm_name = args[0]
            hv_name = args[1]
        else:
            usage = '%s vm_name [hv_name]' % "qstart"
            error('invalid number of args: %s\n' % usage)
            return

        err1 = self._check_vm_name_available(vm_name)
        err2, hv = self._check_hv_name(hv_name, exp_enabled=True)

        if not err1 and not err2:
            self.do_add(vm_name)
            self.do_launch(line)

    def do_madd( self, line, cmd_name='madd' ):
        "Create multiple virtual machine images."
        args = line.split()

        if not args:
            item1 = 'vm_name1[,vm_script][,vm_cls][,vm_kwarg=kwarg]'
            item2 = 'vm_name2'
            defitem = '[vm_kwarg=default_kwarg]'
            usage = '%s %s %s... %s' % (cmd_name, item1, item2, defitem)
            error('invalid number of args: %s\n' % usage)
            return

        default_kwargs = {}
        last_arg = args[-1]
        if "=" in last_arg.split(",",1)[0]:
            default_arg = "filler," + last_arg
            filler, filler_args, default_kwargs = splitArgs(default_arg)
            args = args[:-1]

        vm_info = {}
        for arg in args:
            vm_name, vm_args, vm_kwargs_temp = splitArgs(arg)
            vm_kwargs = default_kwargs.copy()
            vm_kwargs.update(vm_kwargs_temp)
            if len(vm_args) >= 1:
                if vm_kwargs.get("vm_script"):
                    error("Bad argument: multiple values for vm_script\n")
                    return
                else:
                    vm_kwargs["vm_script"] = vm_args[0]
            if len(vm_args) >= 2:
                if vm_kwargs.get("vm_cls"):
                    error("Bad argument: multiple values for vm_cls\n")
                    return
                else:
                    vm_kwargs["vm_cls"] = vm_args[1]
            if len(vm_args) >= 3:
                error("Bad argument: have more than 3 non-keyword arguments\n")
                return
            vm_info[vm_name] = vm_kwargs

        for vm_name in vm_info:
            vm_kwargs = vm_info[vm_name]
            err1 = self._check_vm_name_available(vm_name)
            err2 = False      # TODO: Check vm_script value and others.
            if not err1 and not err2:
                self.cn.createVM(vm_name, **vm_kwargs)

    def do_mlaunch( self, line, cmd_name='mlaunch' ):
        "Initialize multiple created VMs on hypervisors."
        args = line.split()

        if not args:
            usage = '%s vm_name1 vm_name2...' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        for arg in args:
            vm_name = arg
            err, vm = self._check_vm_name(vm_name, exp_running=False)
            if not err:
                self.cn.launchVM(vm)

    def do_mstop( self, line, cmd_name='mstop' ):
        "Stop multiple running images."
        args = line.split()

        if not args:
            usage = '%s vm_name1 vm_name2...' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        for arg in args:
            vm_name = arg
            err, vm = self._check_vm_name(vm_name, exp_running=True)
            if not err:
                self.cn.stopVM(vm)

    def do_mrm( self, line, cmd_name='mrm' ):
        "Remove multiple virtual machine images from CMSnet."
        args = line.split()

        if not args:
            usage = '%s vm_name1 vm_name2...' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        for arg in args:
            vm_name = arg
            err, vm = self._check_vm_name(vm_name)
            if not err:
                self.cn.deleteVM(vm)












    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main Command Aliases
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def do_create( self, line ):
        self.do_add(line, cmd_name='create')

    def do_clone( self, line ):
        self.do_cp(line, cmd_name='clone')

    def do_start( self, line ):
        self.do_launch(line, cmd_name='start')

    def do_instantiate( self, line ):
        self.do_launch(line, cmd_name='instantiate')

    def do_migrate( self, line ):
        self.do_mv(line, cmd_name='migrate')

    def do_move( self, line ):
        self.do_mv(line, cmd_name='move')

    #def do_destroy( self, line ):
    #    self.do_stop(line, cmd_name='destroy')

    def do_remove( self, line ):
        self.do_rm(line, cmd_name='remove')

    def do_delete( self, line ):
        self.do_rm(line, cmd_name='delete')

    def do_crash( self, line ):
        self.do_kill(line, cmd_name='crash')

    def do_unpause( self, line ):
        self.do_resume(line, cmd_name='unpause')




    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    #
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~


    def do_xterm( self, line, term='xterm' ):
        "Spawn xterm(s) for the given component(s)."
        args = line.split()
        if not args:
            error( 'usage: %s comp1 comp2 ...\n' % term )
        else:
            for arg in args:
                if arg not in self.cn:
                    error( "Component '%s' not found.\n" % arg )
                else:
                    comp = self.cn[ arg ]
                    self.cn.makeTerms(comp, term=term)

    def do_x( self, line ):
        """Create an X11 tunnel to the given component,
           optionally starting a client."""
        args = line.split()
        if not args:
            error( 'usage: x comp [cmd args]\n' )
        else:
            if args[0] not in self.cn:
                error( "Component '%s' not found.\n" % args[0] )
            else:
                comp = self.cn[ args[ 0 ] ]
                cmd = args[ 1: ]
                self.cn.makeX11(comp, cmd)

    def do_gterm( self, line ):
        "Spawn gnome-terminal(s) for the given component(s)."
        self.do_xterm( line, term='gterm' )

    def do_exit( self, _line ):
        "Exit"
        return 'exited by user command'

    def do_quit( self, line ):
        "Exit"
        return self.do_exit( line )

    def do_EOF( self, line ):
        "Exit"
        output( '\n' )
        return self.do_exit( line )

    def isatty( self ):
        "Is our standard input a tty?"
        return isatty( self.stdin.fileno() )

    def do_noecho( self, line ):
        "Run an interactive command with echoing turned off."
        if self.isatty():
            quietRun( 'stty -echo' )
        self.default( line )
        if self.isatty():
            quietRun( 'stty echo' )

    def do_source( self, line ):
        "Read commands from an input file."
        args = line.split()
        if len(args) != 1:
            error( 'usage: source <file>\n' )
            return
        try:
            self.inputFile = open( args[ 0 ] )
            while True:
                line = self.inputFile.readline()
                if len( line ) > 0:
                    self.onecmd( line )
                else:
                    break
        except IOError:
            error( 'error reading file %s\n' % args[ 0 ] )
        self.inputFile = None

    def do_time( self, line ):
        "Measure time taken for any command in Mininet."
        start = time.time()
        self.onecmd(line)
        elapsed = time.time() - start
        self.stdout.write("*** Elapsed time: %0.6f secs\n" % elapsed)

    def default( self, line ):
        """Called on an input line when the command prefix is not recognized.
        Overridden to run shell commands when a component is the first CLI
        argument. Past the first CLI argument, component names are then
        automatically replaced with corresponding node IP addrs."""

        first, args, line = self.parseline( line )

        if first in self.cn:
            if not args:
                print "*** Enter a command for component: %s <cmd>" % first
                return
            comp = self.cn[ first ]
            rest = args.split( ' ' )
            # Substitute IP addresses for node names in command
            rest = [ self.cn[ arg ].node.defaultIntf().updateIP()
                     if arg in self.cn else arg
                     for arg in rest ]
            rest = ' '.join( rest )
            # Run cmd on node:
            builtin = isShellBuiltin( first )
            comp.node.sendCmd( rest, printPid=( not builtin ) )
            self.waitForNode( comp.node )
        else:
            error( '*** Unknown command: %s\n' % line )

    # pylint: enable-msg=R0201

    def waitForNode( self, node ):
        "Wait for a node to finish, and  print its output."
        # Pollers
        nodePoller = poll()
        nodePoller.register( node.stdout )
        bothPoller = poll()
        bothPoller.register( self.stdin, POLLIN )
        bothPoller.register( node.stdout, POLLIN )
        if self.isatty():
            # Buffer by character, so that interactive
            # commands sort of work
            quietRun( 'stty -icanon min 1' )
        while True:
            try:
                bothPoller.poll()
                # XXX BL: this doesn't quite do what we want.
                if False and self.inputFile:
                    key = self.inputFile.read( 1 )
                    if key is not '':
                        node.write(key)
                    else:
                        self.inputFile = None
                if isReadable( self.inPoller ):
                    key = self.stdin.read( 1 )
                    node.write( key )
                if isReadable( nodePoller ):
                    data = node.monitor()
                    output( data )
                if not node.waiting:
                    break
            except KeyboardInterrupt:
                node.sendInt()

# Helper functions

def isReadable( poller ):
    "Check whether a Poll object has a readable fd."
    for fdmask in poller.poll( 0 ):
        mask = fdmask[ 1 ]
        if mask & POLLIN:
            return True
