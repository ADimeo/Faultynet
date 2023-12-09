#!/usr/bin/env python

"""
This example demonstrates tearing down an interface, and logging with a custom command.
It also serves as an example for how to configure logging.
"""
import asyncio
import pathlib
import sys

from mininet import log
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


async def run_ip_without_interface_test(net: Mininet):
    h1 = net.hosts[0]
    #h1.cmd("ip a") 10.0.0.1
    h2 = net.hosts[1]
    #h2.cmd("ip a") 10.0.0.2

    await asyncio.sleep(2)
    log.info("Running ping with working interface...\n")
    log.info(h1.cmd("ping -i 0.2 -w 5 10.0.0.2") + "\n")

    await asyncio.sleep(4)
    log.info("Running ping without working interface...\n")
    log.info(h1.cmd("ping -i 0.2 -w 5 10.0.0.2") + "\n")

    await asyncio.sleep(4)


def fault_example_scenario():
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/interface_down_example.yml"
    topo = SimpleStarTopo()
    Switch = OVSKernelSwitch

    # This is with fault injection
    host = custom(CPULimitedHost, cpu=.1)
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link, host=host,
                   waitConnected=True, faultFilepath=fault_filepath)
    net.start()
    asyncio.run(run_ip_without_interface_test(net))

    while net.isFaultControllerActive():
        continue
    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
