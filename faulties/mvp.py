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
from mininet.node import UserSwitch, OVSKernelSwitch, Controller, CPULimitedHost
from mininet.topo import Topo
from mininet.log import lg, info
from mininet import log
from mininet.util import irange, quietRun, custom
from mininet.link import Link

flush = sys.stdout.flush

class CgroupTestTopo(Topo):
    "used to test cpu utilisation."

    # pylint: disable=arguments-differ
    def build(self, N, **params):
        # Create switches and hosts
        h1 = self.addHost('h1')

        h2 = self.addHost('h2')
        switch = self.addSwitch('s1')

        self.addLink(h1, switch)
        self.addLink(h2, switch)
        # Wire up switches


class LinearTestTopo(Topo):
    "Topology for a string of N hosts and N-1 switches."
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


async def cgroup_test_commands(net: Mininet):
    command = "systemd - cgtop - bn1 | grep mininetcgroup.slice | awk '{print $1, $3}'" # output i s "cgroup name" "cpu usage"

    cpu_limited_h1 = net.hosts[0]
    if not isinstance(cpu_limited_h1, CPULimitedHost):
        # cpu_limited_h1 is the switch, the other host must be cpu limited
        cpu_limited_h1 = net.hosts[1]
    # This tests starts us off at  no cpu usage, and slowly ramps up cpu usage
    # with stress-ng s -l option

    lg.setLogLevel('debug')
    lg.debug("STARTING DEBUG INFO")
    cpu_limited_h1.setCPUFrac(.3, "cfs")
    lg.debug("ENDING DEBUG INFO")

    # CPU usage goes 20,40,60,80, each for 10 seconds
    stress_command = "stress-ng -l {} -t 15 --cpu 1 --cpu-method decimal64" # decimal64 gives usages which are relatively close to the requested usage, unlike euler
    log.info("Starting CPU Stressor: 10%\n")
    cpu_limited_h1.cmd(stress_command.format(str(10)))
    time.sleep(5)
    log.info("Starting CPU Stressor: 20%\n")
    cpu_limited_h1.cmd(stress_command.format(str(20)))
    time.sleep(5)
    log.info("Starting CPU Stressor: 50%\n")
    cpu_limited_h1.cmd(stress_command.format(str(50)))
    time.sleep(5)
    log.info("Starting CPU Stressor: 90%\n")
    cpu_limited_h1.cmd(stress_command.format(str(90)))
    time.sleep(5)
    log.info("Done")



async def degradation_command_test(net: Mininet):
    # Runs with degradation_test.yml
    lg.setLogLevel('debug')
    h1 = net.hosts[0]
    # h1.cmd("ip a") 10.0.0.1
    h2 = net.hosts[1]
    # h2.cmd("ip a") 10.0.0.2
    s1 = net.switches[0]
    await asyncio.sleep(6)
    s1.cmd("sudo tc qdisc show dev s1-eth1 root > degradation_interface_status 2>&1")
    h1.cmd("ping -i 0.2 -w 10 10.0.0.2 > degradation_test_file.txt 2>&1") # expect that that indicates packet loss

async def redirect_command_test(net: Mininet):
    # run with redirect_test.yml"
    lg.setLogLevel('debug')
    h1 = net.hosts[0]
    #h1.cmd("ip a") 10.0.0.1
    h2 = net.hosts[1]
    #h2.cmd("ip a") 10.0.0.2
    h3 = net.hosts[2]
    #h3.cmd("ip a") 10.0.0.3
    s1 = net.switches[0]

    # Activate faults, redirect traffic from s1:h1 to s1:h3
    log.info(s1.cmd("timeout 5 tcpdump -i s1-eth3 -w pcap_s1-h3-pre.pcap&") + "\n")
    await asyncio.sleep(2)
    log.info("Running ping without injection...\n")
    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > no_redirect_injected.txt 2>&1") + "\n")
    h1.cmd("timeout 3 ping -i 0.2 10.0.0.2") # between h1 and h2

    await asyncio.sleep(4)
    log.info("Running ping with injection now...\n")
    log.info(h1.cmd("timeout 5 tcpdump -i h1-eth0 -w pcap_h1-s1-post.pcap&") + "\n")
    # log.info(s1.cmd("timeout 5 tcpdump -i s1-eth1 -w pcap_s1-h1-post.pcap&") + "\n") # It's this motherfucking line
    log.info(s1.cmd("timeout 5 tcpdump -i s1-eth3 -w pcap_s1-h3-post.pcap&") + "\n")

    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > yes_redirect_injected.txt 2>&1") + "\n")
    h1.cmd("timeout 4 ping -i 0.2 10.0.0.2") # between h1 and h2
    await asyncio.sleep(4)
    log.info(s1.cmd("sudo /usr/sbin/tc filter show dev s1-eth1 root > post_redirect_removal.txt 2>&1") + "\n")


async def redirect_single_protocol_test(net: Mininet):
    # run with protocol_redirect_test.yml"
    # Should redirect ping traffic (ICMP), but not ping6 traffic (UPv6-ICMP)
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


def linearBandwidthTest(lengths):
    "Check bandwidth at various lengths along a switch chain."
    results = {}
    # fault_filepath = "/home/containernet/containernet/faulties/degradation_test.yml"
    fault_filepath = "/home/containernet/containernet/faulties/redirect_test.yml"
    fault_filepath = "/home/containernet/containernet/faulties/protocol_redirect_test.yml"
    fault_filepath = "/home/containernet/containernet/faulties/mvp.yml"
    topo = LinearTestTopo()
    Switch = OVSKernelSwitch




    # This is with fault injection
    host = custom(CPULimitedHost, cpu=.1)
    net = Mininet(topo=topo, switch=Switch,
                   controller=Controller, link=Link, host=host,
                   waitConnected=True, faultFilepath=fault_filepath)

    lg.setLogLevel('debug')
    net.start()

    # asyncio.run(degradation_command_test(net))
    # asyncio.run(redirect_single_protocol_test(net))
    # the fault controller is actually active
    while net.faultController.is_active():
        continue

    log.info("Fault controller is not active")
    net.stop()

    # asyncio.run(inject(net))

    # link = partial(TCLink, delay='30ms', bw=100) # TODO this requires custom re-building + injection logic


if __name__ == '__main__':
    sizes = [1, ]
    lg.setLogLevel('info')
    info("*** Running Faultynet MVP", sizes, '\n')
    linearBandwidthTest(sizes)
