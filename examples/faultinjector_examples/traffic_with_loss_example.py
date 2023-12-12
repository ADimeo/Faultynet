#!/usr/bin/env python

"""
This example demonstrates a simple increasing degradation in packet loss, as well as
a basic logging setup
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



async def run_test_traffic(net: Mininet):
    h1 = net.hosts[0]
    h2 = net.hosts[1]
    listener_ip = h2.IP()

    log.setLogLevel('debug')
    log.info("Starting iperf3 listener\n")
    h2.popen('iperf3 -s')
    log.info("Done\n")
    iperf_command = f"iperf3 -c {listener_ip} -t 10"
    # iperf_command = f"ping -c 10 {listener_ip} "

    log.debug("Debug output activated\n")

    log.info("starting before iperf\n")
    h1.cmd(iperf_command + " &> before_run")
    log.info("Done\n")
    # await asyncio.sleep(10)

    for i in range(15):
        await asyncio.sleep(1)
    log.info("starting during iperf\n")
    h1.cmd(iperf_command + " &> during_run")
    log.info("Done\n")
    # await asyncio.sleep(10)

    await asyncio.sleep(5)
    log.info("starting after iperf\n")
    h1.cmd(iperf_command + " &> after_run")
    # await asyncio.sleep(10)
    log.info("Done\n")
    await asyncio.sleep(10)
    log.info("Waiting for fault engine to shut down\n")


def fault_example_scenario():
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/traffic_with_loss_example.yml"
    topo = SimpleStarTopo()
    Switch = OVSKernelSwitch

    # This is with fault injection
    host = custom(CPULimitedHost, cpu=.1)
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link, host=host,
                   waitConnected=True, faultFilepath=fault_filepath)
    net.start()

    asyncio.run(run_test_traffic(net))
    # the fault controller is actually active
    while net.isFaultControllerActive():
        continue

    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
