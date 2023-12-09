#!/usr/bin/env python

"""
This example demonstrates how to inject faults into a single protocol. Specifically, redirects ICMP traffic,
but not IPv6-ICMP traffic
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

async def redirect_single_protocol_test(net: Mininet):
    # run with single_protocol_redirection_example.yml"
    # Should redirect ping traffic (ICMP), but not ping6 traffic (IPv6-ICMP)
    lg.setLogLevel('debug')
    h1 = net.hosts[0]
    # h1.cmd("ip a") #10.0.0.1
    h2 = net.hosts[1]
    # h2.cmd("ip a") #10.0.0.2
    h3 = net.hosts[2]
    # h3.cmd("ip a") #10.0.0.3
    s1 = net.switches[0]

    # add IPv6 addresses
    h1.cmd("ifconfig h1-eth0 inet6 add fc00::1/64")
    h2.cmd("ifconfig h2-eth0 inet6 add fc00::2/64")
    h3.cmd("ifconfig h3-eth0 inet6 add fc00::3/64")

    log.info(s1.cmd("sudo /usr/sbin/tc qdisc show dev s1-eth1 > qdis1.txt 2>&1") + "\n")

    # Wait for faults to activate
    await asyncio.sleep(4)
    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > config_icmp_redirect_only.txt 2>&1") + "\n")
    log.info(s1.cmd("sudo /usr/sbin/tc qdisc show dev s1-eth1 > qdisc_icmp_redirect_only.txt 2>&1") + "\n")

    log.info(h1.cmd("timeout 16 tcpdump -i h1-eth0 -w pcap_h1-s1-post.pcap&") + "\n")
    log.info(s1.cmd("timeout 16 tcpdump -i s1-eth3 -w pcap_s1-h3-post.pcap&") + "\n")
    await asyncio.sleep(1)
    log.info("Running ping IPv4 (expecting redirect)\n")
    h1.cmd("timeout 5 ping -6 -i 0.2 fc00::2")  # between h1 and h2
    log.info("Running ping IPv4 (expecting no redirect)\n")
    h1.cmd("timeout 5 ping -i 0.2 10.0.0.2")  # between h1 and h2


    await asyncio.sleep(4)
    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > post_redirect_removal.txt 2>&1") + "\n")


def fault_example_scenario():

    fault_filepath = os.path.abspath(__file__).parent.absolute() + "single_protocol_redirection_example.yml"
    topo = SimpleStarTopo()
    Switch = OVSKernelSwitch

    # This is with fault injection
    host = custom(CPULimitedHost, cpu=.1)
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link, host=host,
                   waitConnected=True, faultFilepath=fault_filepath)

    net.start()

    asyncio.run(redirect_single_protocol_test(net))
    # the fault controller is actually active
    while net.isFaultControllerActive():
        continue

    net.stop()


if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
