#!/usr/bin/env python

import asyncio
import pathlib
import sys
from subprocess import call, Popen

from mininet import log
from mininet.net import Mininet
from mininet.node import  OVSKernelSwitch, OVSController
from mininet.topo import Topo
from mininet.log import lg

flush = sys.stdout.flush


class DemoTopo(Topo):
    """
    H1 - S01 - H2
    |     |    |
    S11 - S12 - S13

    """

    # pylint: disable=arguments-differ
    def build( self,):
        # Create switches and hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        s01 = self.addSwitch('s01')
        s11 = self.addSwitch('s11')
        s12 = self.addSwitch('s12')
        s13 = self.addSwitch('s13')



        self.addLink(h1, s01)
        self.addLink(s01, h2)

        self.addLink(h1, s11)
        self.addLink(s11, s12)
        self.addLink(s12, s13)
        self.addLink(s13, h2)

        self.addLink(s01, s12)



async def create_traffic(net):
    while net.isFaultControllerActive():
        loss_percentage = net.pingAll(0.1)
        log.info(f"LOSS PERCENTAGE IS {loss_percentage}\n")
        await asyncio.sleep(1)

def demoRun():
    """Test is: start up network, constant pingalls, deteriorate network and log pcap, shutdown
    """
    fault_filepath = str(pathlib.Path(__file__).parent.resolve()) + "/demo.yml"
    topo = DemoTopo()
    net = Mininet(topo=topo, switch=OVSKernelSwitch,
                  controller=OVSController,
                  waitConnected=True,
                  faultFilepath=fault_filepath)
    net.start()
    # Commented out due to log output formatting
    # tcpdump_command = ["sudo", "timeout", "15", "tcpdump", "-i", "lo", "-nn", "-w", "openflow_traffic.pcap"]
    # Popen(tcpdump_command)

    asyncio.run(create_traffic(net))

    while net.isFaultControllerActive():
        continue
    net.stop()


if __name__ == '__main__':
    lg.setLogLevel( 'info' )
    demoRun()
