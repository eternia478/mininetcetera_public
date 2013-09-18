"Utility functions/classes for CMSnet."

from mininet.util import macColonHex, ipStr, ipNum, ipAdd, ipParse, netParse
import json



# Message and configuration encoding/decoding.

defaultDecoder = json.JSONDecoder()

def jsonprint( v ):
    """Pretty print the JSON encoding of the input object.
       v: Serializable object to encode.
       returns: String encoded from v."""
    return json.dumps(v, sort_keys=True, indent=2, separators=(', ',' : ')) + '\n'

def jsondumps( v ):
    """Messy dump the JSON encoding of the input object.
       v: Serializable object to encode.
       returns: String encoded from v."""
    return json.dumps(v, sort_keys=True) + '\n'



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

def isValidMAC( macstr ):
    """Check if macstr is a valid MAC address.
       macstr: MAC colon-hex string
       returns: True if macstr is valid, else False"""
    try:
        macval = macParse(macstr)
        return macstr == macColonHex(macval)
    except:
        return False

def isValidIP( ipstr ):
    """Check if ipstr is a valid IPv4 address.
       ipstr: IP address string
       returns: True if macstr is valid, else False"""
    try:
        ip = ipstr
        if '/' in ipstr:
            ip, pf = ipstr.split( '/' )
            prefixLen = int( pf )
        args = [ int( arg ) for arg in ip.split( '.' ) ]
        ip_range = range(256)
        return len(args) == 4 and all([ arg in ip_range for arg in args ])
    except:
        return False

def isValidNetmask( netmask ):
    """Check if netmask is a valid subnet mask.
       netmask: Subnet mask string in quad-dotted notation
       returns: True if netmask is valid, else False"""
    assert isValidIP(netmask) and '/' not in netmask
    prefixLen = getPrefixLenFromNetmask(netmask)
    return netmask == getNetmaskFromPrefixLen(prefixLen)

def isInSameSubnet( ip1, ip2, netmask ):
    """Check if two IP address are in the same subnet, given the subnet mask.
       ip1: First IP address string
       ip2: Second IP address string
       netmask: Subnet mask string in quad-dotted notation
       returns: True if IP's are in same subnet, else False"""
    assert isValidIP(ip1) and '/' not in ip1
    assert isValidIP(ip2) and '/' not in ip2
    assert isValidIP(netmask) and '/' not in netmask
    assert isValidNetmask(netmask)
    mask = ipParse(netmask)
    return mask & ipParse(ip1) == mask & ipParse(ip2)

def getNetmaskFromPrefixLen( prefixLen ):
    """Transform a prefix bit-length into a subnet mask.
       prefixLen: Bit-length of IP address prefix
       returns: Subnet mask string in quad-dotted notation"""
    mask_binrepr = "1"*(32 - prefixLen) + "0"*(prefixLen)
    return ipStr(int(mask_binrepr, 2))

def getPrefixLenFromNetmask( netmask ):
    """Transform a subnet mask into a prefix bit-length.
       netmask: Subnet mask string in quad-dotted notation
       returns: Bit-length of IP address prefix"""
    assert isValidIP(netmask) and '/' not in netmask
    return 32 - bitSum(ipParse(netmask))



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
        if not isinstance(comp, CMSComponent):
            raise TypeError("%s is not a CMSComponent." % (comp,))
        self.comp = comp
        func = comp.update_comp_config
        super(ConfigUpdatingDict, self).__init__(func, *args, **kwargs)
