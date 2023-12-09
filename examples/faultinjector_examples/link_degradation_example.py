#!/usr/bin/env python

"""
This example demonstrates how to inject gradually increasing packet loss into a link
"""
import asyncio
import pathlib
import sys

from mininet.log import lg
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, Controller, CPULimitedHost
from mininet.link import Link
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

async def degradation_command_test(net: Mininet):
    # Runs with link_degradation_example.yml
    lg.setLogLevel('debug')
    h1 = net.hosts[0] # h1.cmd("ip a") 10.0.0.1
    await asyncio.sleep(6)
    h1.cmd("ping -i 0.2 -w 10 10.0.0.2") # This should indicate packet loss

def fault_example_scenario():
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/link_degradation_example.yml"
    topo = SimpleStarTopo()
    Switch = OVSKernelSwitch

    host = custom(CPULimitedHost, cpu=.1)
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link, host=host,
                   waitConnected=True, faultFilepath=fault_filepath)
    net.start()
    asyncio.run(degradation_command_test(net))

    # the fault controller is actually active
    while net.isFaultControllerActive():
        continue
    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
