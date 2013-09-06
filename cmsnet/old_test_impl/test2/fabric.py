#!/usr/bin/python

from cms_net import CMSnet
from cms_comp import *
from mininet.node import Node
from mininet.log import setLogLevel,info, error, debug, output

def makeNet ():
    net = CMSnet()
    # add 2 HV
    HVswitches = []
    for i in range(0, 2):
      i += 1
      s = net.addHVSwitch('s%s'%i,  ip='0.0.0.0', inNamespace=False) #cls=Node,
      HVswitches.append(s)
    # add 1 fabric
    fabric = net.addFabricSwitch('s3',ip='0.0.0.0', inNamespace=False) # cls=Node,

    # add 1 vm to the 2 HVs
    host_num = 1
    hosts = []
    for i in range(0, 2):
      s = HVswitches[i]
      s.linkTo(fabric)
      i += 1
      h = net.createVM('h%s'%host_num, ip='10.0.0.%s'%host_num)
      hosts.append(h)
      host_num += 1
      # s.linkTo(h)
    print "Hosts: ", " ".join(s.name for s in hosts)
    print "HVswitches: ", " ".join(s.name for s in HVswitches)
    print "Fabric: ", fabric.name

    for i,(s,num_hosts) in enumerate(zip(HVswitches, [1])):
      ifaces = []
      for j in range(1+int(num_hosts)):
        iface = "%s-eth%s" % (s.name, j)
        ifaces.append(iface)
        s.cmd("ifconfig %s 0.0.0.0 up" % iface)
      s.cmd('~/mnpy ~/pox/pox.py datapaths.pcap_switch '
              '--ports=%s --address=127.0.0.1 --port=%s '
              'openflow.of_01 --port=%s '
              'forwarding.l2_pairs &'
              % (",".join(ifaces), 6641+i, 6641+i))

    # Configure the fabric
    ifaces = []
    for i in range(0,1):
      iface = "%s-eth%s" % (fabric.name, i)
      ifaces.append(iface)
      s.cmd("ifconfig %s 0.0.0.0 up" % iface)

    # Run L2 switch in the fabric node
    fabric.cmd('~/mnpy ~/pox/pox.py datapaths.pcap_switch '
            '--ports=%s --address=127.0.0.1 --port=%s '
            'openflow.of_01 --port=%s '
            'forwarding.l2_pairs &'
            % (",".join(ifaces), 6640, 6640))

    net.start()
    # we should receive msg in the controller
    # print  hosts[0].name, HVswitches[1].name
    net.launchVM ( hosts[0].name, HVswitches[1].name)
    net.launchVM ( hosts[1].name, HVswitches[0].name)
    hosts[0].cmd("ping 10.0.0.2 -c 3")
    net.migrateVM ( hosts[0].name, HVswitches[0].name)
    net.migrateVM ( hosts[1].name, HVswitches[1].name)
    net.stop()

if __name__ == '__main__':
    # setLogLevel('info')
    makeNet()
