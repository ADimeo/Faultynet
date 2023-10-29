#!/usr/bin/env python

"""
h1 <-> s1 <-> s2 .. sN-1
       |       |    |
       h2      h3   hN
"""
import asyncio
import logging
import sys
import time

from functools import partial

from mininet.net import Mininet
from mininet.node import UserSwitch, OVSKernelSwitch, Controller
from mininet.topo import Topo
from mininet.log import lg, info
from mininet import log
from mininet.util import irange, quietRun
from mininet.link import Link
from mininet.faultcontrollerstarter import FaultControllerStarter

flush = sys.stdout.flush


class LinearTestTopo(Topo):
    "Topology for a string of N hosts and N-1 switches."
    # pylint: disable=arguments-differ
    def build(self, N, **params):
        # Create switches and hosts
        h1 = self.addHost('h1')

        h2 = self.addHost('h2')
        switch = self.addSwitch('s1')


        self.addLink(h1, switch)
        self.addLink(h2, switch)
        # Wire up switches

async def run_test_commands(net: Mininet):
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
    # h1.popen(iperf_command + " &> /home/containernet/before_run", shell=True)
    h1.cmd(iperf_command + " &> /home/containernet/before_run")
    log.info("Done\n")
    # await asyncio.sleep(10)

    for i in range(15):
        await asyncio.sleep(1)
    log.info("starting during iperf\n")
    #h1.popen(iperf_command + " &> /home/containernet/during_run", shell=True)
    h1.cmd(iperf_command + " &> /home/containernet/during_run")
    log.info("Done\n")
    # await asyncio.sleep(10)

    await asyncio.sleep(5)
    log.info("starting after iperf\n")
    #h1.popen(iperf_command + " &> /home/containernet/after_run", shell=True)
    h1.cmd(iperf_command + " &> /home/containernet/after_run")
    # await asyncio.sleep(10)
    log.info("Done\n")
    await asyncio.sleep(10)
    log.info("Waiting for fault engine to shut down\n")



async def inject(net: Mininet):
    log.info("The net is a faulty boy\n")
    lg.setLogLevel('debug')

    filepath = ("/home/containernet/containernet/faulties/mvp.yml") # TODO
    faultcontroller = FaultControllerStarter(net, filepath)
    faultcontroller.go()

    await run_test_commands(net)


    log.info("Test done, injections done, preparing for teardown\n")

def linearBandwidthTest(lengths):
    "Check bandwidth at various lengths along a switch chain."
    results = {}
    switchCount = max(lengths)
    hostCount = switchCount + 1


    topo = LinearTestTopo(hostCount)

    Switch = OVSKernelSwitch
    # link = partial(TCLink, delay='30ms', bw=100) # TODO this requires custom re-building + injection logic
   #  net = Mininet(topo=topo, switch=Switch,
   #               controller=Controller, link=Link,
    #              waitConnected=True) # TODO Mininet() should be allowed to create a faultcontroler

    host = custom(CPULimitedHost, cpu=.1)
    net = Mininet(topo=topo, switch=Switch,
                  controller=Controller, link=Link, host=host,
                  waitConnected=True) # TODO Mininet() should be allowed to create a faultcontroler
    net.start()
    asyncio.run(inject(net))
    net.stop()


if __name__ == '__main__':
    sizes = [1, ]
    lg.setLogLevel('info')
    info("*** Running Faultynet MVP", sizes, '\n')
    linearBandwidthTest(sizes)
