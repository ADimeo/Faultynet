#!/usr/bin/env python

"""
This example demonstrates how to inject gradually increasing packet loss into a link
"""
import asyncio
import pathlib
import sys
import time

from mininet.fault_controllers.RandomLinkFaultController import RandomLinkFaultControllerStarter
from mininet.log import lg
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, Controller, CPULimitedHost
from mininet.link import Link
from mininet.topo import Topo
from mininet.util import custom

flush = sys.stdout.flush
class SimpleExampleTopo(Topo):
    # pylint: disable=arguments-differ
    def build(self, N=0, **params):
        # Create switches and hosts

        switch1 = self.addSwitch('s1')
        switch2 = self.addSwitch('s2')
        switch3 = self.addSwitch('s3')

        self.addLink(switch1, switch2)
        self.addLink(switch2, switch3)


        h1s1 = self.addHost('h1s1')
        h2s1 = self.addHost('h2s1')
        h3s1 = self.addHost('h3s1')

        self.addLink(h1s1, switch1)
        self.addLink(h2s1, switch1)
        self.addLink(h3s1, switch1)

        h1s2 = self.addHost('h1s2')
        self.addLink(h1s2, switch2)

        h1s3 = self.addHost('h1s3')
        h2s3 = self.addHost('h2s3')
        h3s3 = self.addHost('h3s3')

        self.addLink(h1s3, switch3)
        self.addLink(h2s3, switch3)
        self.addLink(h3s3, switch3)


async def degradation_command_test(net: Mininet):
    # Runs with link_degradation_example.yml

    h1 = net.hosts[0] # h1.cmd("ip a") 10.0.0.1
    for i in range (7):
        h1.cmd("ping -w 9 10.0.0.7") # This should indicate packet corruption
        time.sleep(3)
        net.faultControllerStarter.start_next_run()
    # Controller is stopped prematurely
    net.faultControllerStarter.stop()

def fault_example_scenario():
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/random_link_example.yml"
    topo = SimpleExampleTopo()
    Switch = OVSKernelSwitch

    net = Mininet(topo=topo, switch=Switch, faultControllerStarter=RandomLinkFaultControllerStarter,
                   controller=Controller, link=Link,
                   waitConnected=True,  faultFilepath=fault_filepath)
    net.start()
    asyncio.run(degradation_command_test(net))

    # the fault controller is actually active
    while net.isFaultControllerActive():
        continue
    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
