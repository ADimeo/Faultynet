#!/usr/bin/env python

"""
This example illustrates how to inject a redirection for all traffic on an interface
"""
import asyncio
import os
import sys

from mininet import log
from mininet.link import Link
from mininet.log import lg
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, Controller, CPULimitedHost
from mininet.topo import Topo
from mininet.util import custom

flush = sys.stdout.flush
class SimpleStarTopo(Topo):
    """Three hosts connected to a switch"""
    # pylint: disable=arguments-differ
    def build(self, N=0, **params):
        # Create switches and hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')

        switch = self.addSwitch('s1')

        self.addLink(h1, switch)
        self.addLink(h2, switch)
        self.addLink(h3, switch)


async def redirect_command_test(net: Mininet):
    # run with redirection_example.yml"
    lg.setLogLevel('debug')
    h1 = net.hosts[0]
    #h1.cmd("ip a") 10.0.0.1
    h2 = net.hosts[1]
    #h2.cmd("ip a") 10.0.0.2
    h3 = net.hosts[2]
    #h3.cmd("ip a") 10.0.0.3
    s1 = net.switches[0]

    # Activate faults, redirect traffic from s1:h1 to s1:h3
    log.info(s1.cmd("timeout 5 tcpdump -i s1-eth3 -w pcap_s1-h3-pre.pcap&") + "\n")
    await asyncio.sleep(2)
    log.info("Running ping without injection...\n")
    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > no_redirect_injected.txt 2>&1") + "\n")
    h1.cmd("timeout 3 ping -i 0.2 10.0.0.2") # between h1 and h2

    await asyncio.sleep(4)
    log.info("Running ping with injection now...\n")
    log.info(h1.cmd("timeout 5 tcpdump -i h1-eth0 -w pcap_h1-s1-post.pcap&") + "\n")
    # log.info(s1.cmd("timeout 5 tcpdump -i s1-eth1 -w pcap_s1-h1-post.pcap&") + "\n") # Calling this line would delete the redirection, since tcpdump overwrites forwarding rules.
    log.info(s1.cmd("timeout 5 tcpdump -i s1-eth3 -w pcap_s1-h3-post.pcap&") + "\n")

    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > yes_redirect_injected.txt 2>&1") + "\n")
    h1.cmd("timeout 4 ping -i 0.2 10.0.0.2") # between h1 and h2
    await asyncio.sleep(4)
    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > post_redirect_removal.txt 2>&1") + "\n")



def fault_example_scenario():
    fault_filepath = os.path.abspath(__file__).parent.absolute() + "redirection_example.yml"
    topo = SimpleStarTopo()
    Switch = OVSKernelSwitch

    # This is with fault injection
    host = custom(CPULimitedHost, cpu=.1)
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link, host=host,
                   waitConnected=True, faultFilepath=fault_filepath)
    net.start()

    asyncio.run(redirect_command_test(net))
    while net.isFaultControllerActive():
        continue

    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
