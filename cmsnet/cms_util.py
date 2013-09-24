"Utility functions/classes for CMSnet."

from mininet.log import info, error, warn, debug
from mininet.util import macColonHex, ipStr, ipNum#, ipAdd#, ipParse, netParse
import json
import os
import shutil
import socket
import cmsnet.cms_comp
import subprocess
import sys
import signal
import atexit



# Message and configuration encoding/decoding.

defaultDecoder = json.JSONDecoder()

def jsondumps( v, **kwargs ):
    """Messy dump the JSON encoding of the input object.
       v: Serializable object to encode.
       returns: String encoded from v."""
    return json.dumps(v, **kwargs) + '\n'

def jsonprint( v ):
    """Pretty print the JSON encoding of the input object.
       v: Serializable object to encode.
       returns: String encoded from v."""
    return jsondumps(v, sort_keys=True, indent=2, separators=(', ',' : '))



# File and folder handling

def makeDirNoErrors( file_path ):
    """Create folder at file_path without OSErrors raised.
       file_path: Path of folder to create.
       Returns: True if folder now exists, else False."""
    if not isinstance(file_path, basestring):
        raise TypeError("File path must be a string.")
    try:
        os.makedirs(file_path)
    except:   # http://stackoverflow.com/questions/273192/#14364249
        if not os.path.isdir(file_path):
            error("Cannot create folder %s.\n" % file_path)
            return False
    return True
        
def removeNoErrors( file_path ):
    """Remove item at file_path without OSErrors raised.
       file_path: Path of file or folder to remove.
       Returns: True if file or folder now does not exist, else False."""
    if not isinstance(file_path, basestring):
        raise TypeError("File path must be a string.")
    try:
        os.remove(file_path)
    except:   # http://stackoverflow.com/questions/17560253
        shutil.rmtree(file_path, ignore_errors=True)
        if os.path.exists(file_path):
            error("File/folder %s not removed.\n" % file_path)
            return False
    return True

def resolvePath( *rawargs ):
    """Resolve the absolute path given the arguments"""
    is_abspath = True
    args = []
    for p in rawargs:
        p = p.strip()
        if is_abspath:
            if p != "":
                is_abspath = False
                args.append(p)
        else:
            if p is not None:
                p = p.strip("/")
                args.append(p)
    return os.path.abspath(os.path.expanduser(os.path.join("", *args)))



# Cgroup exiting and cleanup

grpname = "mininet" + str(os.getpid())
grpbase = "/sys/fs/cgroup/mininet"
grpdir = os.path.join(grpbase, grpname)
tasksfile = os.path.join(grpdir, "tasks")
  
def set_cgroup():
  """Set up Mininet cgroup."""
  if not os.path.isdir(grpbase):
    os.mkdir(grpbase)
  if not os.listdir(grpbase):
    cgroup_mount_cmd = "mount -t cgroup -o cpuacct mininet " + grpbase
    subprocess.call(cgroup_mount_cmd, shell=True)
    with open(os.path.join(grpbase, 'release_agent'), "w") as f:
      agent = os.path.abspath(os.path.dirname(sys.argv[0]))
      agent = os.path.join(agent, "cgroup_release_agent")
      f.write(os.path.join(sys.path[0], agent))
    with open(os.path.join(grpbase, 'notify_on_release'), "w") as f:
      f.write('1')

  assert os.listdir(grpbase)

  os.mkdir(grpdir)

  with open(tasksfile, 'w') as f:
    f.write(str(os.getpid()))
    
  atexit.register(kill_cgroup)

def kill_cgroup():
  """Kill off processes forked from Mininet."""
  pids = open(tasksfile, 'r').read().strip().split("\n")
  pids = [int(p) for p in pids]
  pids = [p for p in pids if p != os.getpid()]
  #print pids

  for pid in pids:
    os.kill(pid, signal.SIGKILL)






# IP and Mac address formatting and parsing

def bitSum( num ):
    """Get the sum of bits of the number's binary form.
       Is also technically the number of 1's in the binary form.
       num: Input integer
       returns: Sum of binary bits."""
    return bin(num).count('1')

def macParse( mac ):
    """Parse a MAC address and return an unsigned int.
       mac: MAC colon-hex string
       returns: MAC address as unsigned int"""
    return int(mac.replace(":",""), 16)

def isValidMAC( mac ):
    """Check if mac is a valid MAC address.
       mac: MAC colon-hex string
       returns: True if mac is valid, else False"""
    try:
        return mac == macColonHex(macParse(mac))
    except:
        return False

def _normalizeMACHex( macarg ):
    """Split and pad hex so long or short MAC colon-hex args are readjusted.
       macarg: one of the MAC colon-hex string
       returns: Split or padded equivalent of macarg"""
    int(macarg, 16) # Make sure this is hex (no empty strings, no spaces, etc.)
    args = [ "%02x" % int(macarg[i:i+2],16) for i in range(0, len(macarg), 2) ]
    return ":".join(args)

def getExpandedMAC( mac ):
    """Expand mac as a MAC address.
       mac: MAC colon-hex string
       returns: Full MAC colon-hex notation if valid, else None"""
    try:
        if mac[-1] == ":": mac = mac[:-1]
        args = [ _normalizeMACHex(arg) for arg in mac.split(":") ]
        args = ":".join(args).split(":")
        macval = int("".join(args[:6] + ['00']*(6-len(args))), 16)
        return macColonHex(macval)
    except:
        return None

def ipParse( ip ):
    """Parse an IP address and return an unsigned int.
       This method overrides the one in mininet.util"""
    args = [ ord(c) for c in socket.inet_aton(ip) ]
    return ipNum( *args )

def isValidIP( ip ):
    """Check if ip is a valid IPv4 address (without prefix size).
       ip: IP address string
       returns: True if IP is valid, else False"""
    try:                        # LOL, and I actually tried to implement this!
        socket.inet_aton(ip)    # http://stackoverflow.com/questions/319279
        return True
    except:
        return False

def getExpandedIP( ip ):
    """Expand ip as an IPv4 address (without prefix size).
       ip: IP address string
       returns: Full IP in quad-dotted notation if valid, else None"""
    try:
        return socket.inet_ntoa(socket.inet_aton(ip))
    except:
        return None

def isValidNetmask( netmask ):
    """Check if netmask is a valid subnet mask.
       netmask: Subnet mask string in quad-dotted notation
       returns: True if netmask is valid, else False"""
    assert isValidIP(netmask)
    prefixLen = getPrefixLenFromNetmask(netmask)
    return getExpandedIP(netmask) == getNetmaskFromPrefixLen(prefixLen)

def isInSameSubnet( ip1, ip2, netmask ):
    """Check if two IP address are in the same subnet, given the subnet mask.
       ip1: First IP address string
       ip2: Second IP address string
       netmask: Subnet mask string in quad-dotted notation
       returns: True if IP's are in same subnet, else False"""
    assert isValidIP(ip1) and isValidIP(ip2) and isValidIP(netmask)
    mask = ipParse(netmask)
    return (mask & ipParse(ip1)) == (mask & ipParse(ip2))

def getNetmaskFromPrefixLen( prefixLen ):
    """Transform a prefix bit-length into a subnet mask.
       prefixLen: Bit-length of IP address prefix
       returns: Subnet mask string in quad-dotted notation"""
    #mask_binrepr = "1"*(prefixLen) + "0"*(32 - prefixLen)
    #return ipStr(int(mask_binrepr, 2))
    assert prefixLen >= 0 and prefixLen <= 32
    return ipStr(((2 << prefixLen) - 1) << (32 - prefixLen))

def getPrefixLenFromNetmask( netmask ):
    """Transform a subnet mask into a prefix bit-length.
       netmask: Subnet mask string in quad-dotted notation
       returns: Bit-length of IP address prefix"""
    assert isValidIP(netmask)
    return bitSum(ipParse(netmask))



# Dictionary subclass for updating.

class UpdatingDict(dict):
    """Dictionary with a callback function when updating."""

    def __init__( self, callback_func, *args, **kwargs ):
        """
        Intialization

        callback_func: Function called when this dictionary is updated.
        """
        if not callable(callback_func):
            raise TypeError("Callback %s is not callable." % (callback_func,))
        self.callback_func = lambda: None
        self.update(*args, **kwargs)
        self.callback_func = callback_func

    def __setitem__( self, key, value ):
        super(UpdatingDict, self).__setitem__(key, value)
        self.callback_func()

    def update( self, *args, **kwargs ):
        if args:
            if len(args) > 1:
                raise TypeError("update expected at most 1 arguments, "
                                "got %d" % len(args))
            other = dict(args[0])
            for key in other:
                self[key] = other[key]
        for key in kwargs:
            self[key] = kwargs[key]

    def setdefault(self, key, value=None):
        if key not in self:
            self[key] = value
        return self[key]


class ConfigUpdatingDict( UpdatingDict ):
    """Dictionary that updates CMS component configurations when updating."""

    def __init__( self, comp, *args, **kwargs ):
        if not isinstance(comp, cmsnet.cms_comp.CMSComponent):
            raise TypeError("%s is not a CMSComponent." % (comp,))
        self.comp = comp
        func = comp.update_comp_config
        super(ConfigUpdatingDict, self).__init__(func, *args, **kwargs)
