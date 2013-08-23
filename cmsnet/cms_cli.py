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
from mininet.util import checkInt

from cmsnet.cms_comp import VirtualMachine, Hypervisor

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
    # CMS Main Commands (ZZZ)
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def _check_vm_name( self, vm_name, exp_exist=True, exp_running=None ):
        """
        Checks the correctness of the VM of the given name.

        vm_name: Name of the VM image. If None, ignore and return.
        exp_exist: Expected result of existing or not.
        exp_running: Expected result of running or not. None if not matter.
        Returns True if error occured, False otherwise.
        """
        if not vm_name:      # Ignore if not set by input.
            return False     # NOTE: Already handled at parsing.

        in_cn = vm_name in self.cn
        comp = self.cn[vm_name] if in_cn else None
        is_VM = isinstance(comp, VirtualMachine)
        is_HV = isinstance(comp, Hypervisor)
        err = False

        if is_HV:
            error('%s is a hypervisor\n' % vm_name)
            err = True
        elif in_cn and not any([is_VM, is_HV]):
            error('%s is another type of component\n' % vm_name)
            err = True
        elif not is_VM and exp_exist:
            error('No such VM image %s\n' % vm_name)
            err = True
        elif is_VM:
            if not exp_exist:
                error('VM of the same name %s already exists\n' % vm_name)
                err = True
            elif exp_running is not None:
                vm_run = comp.is_running()
                if not vm_run and exp_running:
                    error('VM %s is currently inactive\n' % vm_name)
                    err = True
                elif vm_run and not exp_running:
                    error('VM %s is currently running\n' % vm_name)
                    err = True

        return err

    def _check_hv_name( self, hv_name, exp_enabled=True ):
        """
        Checks the correctness of the hypervisor of the given name.

        hv_name: Name of the hypervisor. If None, ignore and return.
        exp_enabled: Expected result of HV enabled or not.
        Returns True if error occured, False otherwise.
        """
        if not hv_name:      # Ignore if not set by input.
            return False     # NOTE: Already handled at parsing.

        in_cn = hv_name in self.cn
        comp = self.cn[hv_name] if in_cn else None
        is_VM = isinstance(comp, VirtualMachine)
        is_HV = isinstance(comp, Hypervisor)
        err = False

        if is_VM:
            error('%s is a VM image\n' % hv_name)
            err = True
        elif in_cn and not any([is_VM, is_HV]):
            error('%s is another type of component\n' % hv_name)
            err = True
        elif not is_HV:
            error('No such hypervisor %s\n' % hv_name)
            err = True
        elif is_HV:
            hv_enb = comp.is_enabled()
            if not hv_enb and exp_enabled:
                error('Hypervisor %s is currently disabled\n' % hv_name)
                err = True
            elif hv_enb and not exp_enabled:
                error('Hypervisor %s is currently enabled\n' % hv_name)
                err = True

        return err

    def do_add( self, line, cmd_name='add' ):
        "Create a virtual machine image."
        args = line.split()
        vm_name = None
        vm_script = None      # TODO: Still working on extra options.
        vm_ip = None          # Current there is no point in these variables.
        vm_extra_params = {}

        if len(args) == 1:
            vm_name = args[0]
        elif len(args) == 2:
            vm_name = args[0]
            vm_script = args[1]
        else:
            usage = '%s vm_name [vm_script]' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err = self._check_vm_name(vm_name, exp_exist=False)
        # TODO: Check vm_script value.
        
        if not err:
            self.cn.createVM(vm_name, vm_script)

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

        err1 = self._check_vm_name(old_vm_name, exp_exist=True)
        err2 = self._check_vm_name(new_vm_name, exp_exist=False)

        if not err1 and not err2:
            self.cn.cloneVM(old_vm_name, new_vm_name)

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

        err1 = self._check_vm_name(vm_name, exp_exist=True, exp_running=False)
        err2 = self._check_hv_name(hv_name, exp_enabled=True)

        if not err1 and not err2:
            self.cn.launchVM(vm_name, hv_name)

    def do_mv( self, line, cmd_name='mv' ):
        "Migrate a running image to another hypervisor."
        args = line.split()
        vm_name = None
        hv_name = None

        if len(args) == 2:
            vm_name = args[0]
            hv_name = args[1]
        else:
            usage = '%s vm_name hv_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err1 = self._check_vm_name(vm_name, exp_exist=True, exp_running=True)
        err2 = self._check_hv_name(hv_name, exp_enabled=True)

        if not err1 and not err2:
            self.cn.migrateVM(vm_name, hv_name)

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

        err = self._check_vm_name(vm_name, exp_exist=True, exp_running=True)
        
        if not err:
            self.cn.stopVM(vm_name)

    def do_rm( self, line, cmd_name='rm' ):
        "Remove the virtual machine image from the hypervisor."
        args = line.split()
        vm_name = None

        if len(args) == 1:
            vm_name = args[0]
        else:
            usage = '%s vm_name' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        err = self._check_vm_name(vm_name, exp_exist=True, exp_running=False)
        
        if not err:
            self.cn.deleteVM(vm_name)

    def do_mode( self, line, cmd_name='mode' ):
        "Change the mode of VM distribution across hypervisors."
        args = line.split()
        vm_dist_mode = None
        vm_dist_limit = None

        if len(args) == 0:
            out_str = "vm_dist_mode: %s" % self.cn.vm_dist_mode
            if self.cn.vm_dist_mode == "packed":
                out_str += "\tvm_dist_limit: %s" % self.cn.vm_dist_limit
            output(out_str+"\n")
            return
        if len(args) == 1:
            vm_dist_mode = args[0]
        elif len(args) == 2:
            vm_dist_mode = args[0]
            if not checkInt(args[1]):
                error('second argument not an integer: %s\n' % args[1])
                return
            vm_dist_limit = int(args[1])
        else:
            usage = '%s [dist_mode [dist_limit]]' % cmd_name
            error('invalid number of args: %s\n' % usage)
            return

        if vm_dist_mode not in self.cn.possible_modes:
            error('No such VM distribution mode: %s\n' % vm_dist_mode)
            return
        if vm_dist_limit is not None:
            if vm_dist_mode != "packed":
                error('Mode %s should not have limit\n' % vm_dist_mode)
                return
            if vm_dist_limit <= 0:
                error('Invalid capacity limit: %s\n' % vm_dist_limit)
                return

        self.cn.changeVMDistributionMode(vm_dist_mode, vm_dist_limit)

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

        err = self._check_hv_name(hv_name, exp_enabled=False)

        if not err:
            self.cn.enableHV(hv_name)

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

        err = self._check_hv_name(hv_name, exp_enabled=True)

        if not err:
            self.cn.disableHV(hv_name)



    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~
    # CMS Main Command Aliases
    #~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~

    def do_create( self, line ):
        self.do_add(line, cmd_name='create')

    def do_clone( self, line ):
        self.do_cp(line, cmd_name='clone')

    def do_start( self, line ):
        self.do_launch(line, cmd_name='start')

    def do_migrate( self, line ):
        self.do_mv(line, cmd_name='migrate')

    def do_move( self, line ):
        self.do_mv(line, cmd_name='move')

    def do_delete( self, line ):
        self.do_rm(line, cmd_name='delete')


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
                    error( "component '%s' not in network\n" % arg )
                else:
                    comp = self.cn[ arg ]
                    self.cn.terms += makeTerms( [ comp.node ], term = term )

    def do_x( self, line ):
        """Create an X11 tunnel to the given component,
           optionally starting a client."""
        args = line.split()
        if not args:
            error( 'usage: x comp [cmd args]...\n' )
        else:
            comp = self.cn[ args[ 0 ] ]
            cmd = args[ 1: ]
            self.cn.terms += runX11( comp.node, cmd )

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
        if not args:
            return
        if args and len(args) > 0 and args[ -1 ] == '\n':
            args = args[ :-1 ]
        rest = args.split( ' ' )

        if first in self.cn:
            comp = self.cn[ first ]
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
            error( '*** Unknown command: %s\n' % first )

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
