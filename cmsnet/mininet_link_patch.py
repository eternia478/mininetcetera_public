from mininet.link import Link as MininetLink
from mininet.link import TCLink as MininetTCLink

class Link( MininetLink ):
    """A basic link is just a veth pair.
       Other types of links could be tunnels, link emulators, etc.."""
    @classmethod
    def intfName( cls, node, n ):
        "Construct a canonical interface name node-N for interface n."
        return node.name + '-' + repr( n )

class TCLink( MininetTCLink ):
    "Link with symmetric TC interfaces configured via opts"
    @classmethod
    def intfName( cls, node, n ):
        "Construct a canonical interface name node-N for interface n."
        return node.name + '-' + repr( n )
