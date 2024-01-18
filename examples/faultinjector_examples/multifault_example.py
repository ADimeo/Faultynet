#!/usr/bin/env python

"""
This example demonstrates how to inject multiple faults into a single link
"""
import asyncio
import pathlib
import sys

from mininet import log
from mininet.log import lg
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, Controller
from mininet.link import Link
from mininet.topo import Topo

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

async def multifault_test(net: Mininet):
    lg.setLogLevel('debug')
    h1 = net.hosts[0]
    # h1.cmd("ip a") #10.0.0.1
    h2 = net.hosts[1]
    # h2.cmd("ip a") #10.0.0.2
    h3 = net.hosts[2]
    # h3.cmd("ip a") #10.0.0.3
    s1 = net.switches[0]


    await asyncio.sleep(4)
    log.info(s1.cmd("sudo /usr/sbin/tc qdisc show dev s1-eth1 > s1-state_during.txt 2>&1") + "\n")
    # Wait for faults to activate
    await asyncio.sleep(4)

    log.info(s1.cmd("sudo /usr/sbin/tc qdisc show dev s1-eth1 > s1-state_post.txt 2>&1") + "\n")

def fault_example_scenario():

    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/multifault_example.yml"
    topo = SimpleStarTopo()
    Switch = OVSKernelSwitch

    # This is with fault injection
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link,
                   waitConnected=True, faultFilepath=fault_filepath)

    net.start()

    asyncio.run(multifault_test(net))
    # the fault controller is actually active
    while net.isFaultControllerActive():
        continue

    net.stop()


if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
