#!/usr/bin/env python

"""
This example demonstrates how to inject gradually increasing packet loss into a link
"""
import asyncio
import pathlib
import sys

from mininet.fault_controllers.MostUsedLinkFaultController import MostUsedLinkFaultControllerStarter
from mininet.log import lg
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, Controller
from mininet.link import Link
from mininet.topo import Topo

flush = sys.stdout.flush
class SimpleExampleTopo(Topo):
    # pylint: disable=arguments-differ
    def build(self, N=0, **params):
        # Create switches and hosts

        switch1 = self.addSwitch('s1')
        switch12 = self.addSwitch('s12')
        switch13 = self.addSwitch('s13')
        switch14 = self.addSwitch('s14')

        h1 = self.addHost('h1')
        self.addLink(h1, switch1)

        self.addLink(switch1, switch12)
        self.addLink(switch1, switch13)
        self.addLink(switch1, switch14)

        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')

        self.addLink(h2, switch12)
        self.addLink(h3, switch13)
        self.addLink(h4, switch14)




async def degradation_command_test(net: Mininet):
    # Runs with link_degradation_example.yml

    h1 = net.hosts[0] # h1.cmd("ip a") 10.0.0.1
    h2 = net.hosts[1] # 10.0.0.2
    h3 = net.hosts[1] # 10.0.0.3
    h4 = net.hosts[1] # 10.0.0.4


    h1.cmd("ping -w 5 -i 0.5 10.0.0.4")
    net.faultControllerStarter.start_next_run()

    h1.cmd("ping -w 5 -i 0.2 10.0.0.3")
    net.faultControllerStarter.start_next_run()

    h1.cmd("ping -w 5 -i 0.1 10.0.0.2")
    net.faultControllerStarter.start_next_run()
    await asyncio.sleep(5)
    net.faultControllerStarter.start_next_run()
    await asyncio.sleep(5)
    net.faultControllerStarter.start_next_run()
    await asyncio.sleep(5)
    # The faultinjector log will show that faults are injected in this order:
    # - On the path to 10.0.0.4
    # - On the path to 10.0.0.3
    # - On the path to 10.0.0.2
    # But none of the links that interact with h1 directly contain faults.

    net.faultControllerStarter.stop()

def fault_example_scenario():
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/most_used_example.yml"
    topo = SimpleExampleTopo()
    Switch = OVSKernelSwitch

    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link,
                   waitConnected=True,
                  faultControllerStarter=MostUsedLinkFaultControllerStarter,
                  faultFilepath=fault_filepath)
    net.start()
    asyncio.run(degradation_command_test(net))

    # the fault controller is actually active
    while net.isFaultControllerActive():
        continue
    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
