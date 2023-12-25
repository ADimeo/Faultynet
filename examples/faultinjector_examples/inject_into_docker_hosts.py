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
from mininet.net import Mininet, Containernet
from mininet.node import OVSKernelSwitch, Controller, CPULimitedHost
from mininet.link import Link
from mininet.topo import Topo
from mininet.util import custom

flush = sys.stdout.flush



async def run_test_traffic(net: Mininet):
    d1 = net.hosts[0]
    log.info("Starting pings...\n")
    # Ping without loss
    d1.cmdPrint("apt update && apt -y install iputils-ping") # ~15 seconds
    d1.cmdPrint("ping -w 3 -i 0.2 172.17.0.3 2>&1")
    await asyncio.sleep(5)
    # Ping with loss
    d1.cmdPrint("ping -w 3 -i 0.2 172.17.0.3 2>&1")
    await asyncio.sleep(5)


def fault_example_scenario():
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/inject_into_docker_hosts.yml"

    # This is with fault injection
    net = Containernet(waitConnected=True, faultFilepath=fault_filepath)
    net.addController('c0')
    d1 = net.addDocker('d10', ip='10.0.0.251', dimage="ubuntu:jammy")
    d2 = net.addDocker('d20', ip='10.0.0.252', dimage="ubuntu:jammy")
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')
    net.addLink(d1, s1)
    net.addLink(s1, s2)
    net.addLink(s2, d2)
    lg.setLogLevel('debug')
    net.start()

    asyncio.run(run_test_traffic(net))
    # the fault controller is actually active
    while net.isFaultControllerActive():
        continue

    net.stop()

if __name__ == '__main__':
    lg.setLogLevel('info')
    fault_example_scenario()
