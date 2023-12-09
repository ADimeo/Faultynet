#!/usr/bin/env python

"""
This example demonstrates how to add load to the cpu of a host, as well as executing logging commands
from the host system instead of from a specific node
"""
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


def fault_example_scenario():
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/cpu_stress_example.yml"

    topo = SimpleStarTopo()
    Switch = OVSKernelSwitch

    # This is with fault injection
    host = custom(CPULimitedHost, cpu=.3)
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link, host=host,
                   waitConnected=True, faultFilepath=fault_filepath)
    net.start()

    while net.isFaultControllerActive():
        continue
    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
