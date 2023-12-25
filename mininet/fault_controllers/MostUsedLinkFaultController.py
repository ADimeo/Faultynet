"""MostUsedLinkFaultController implements a fault injector that injects faults on the link that had the most traffic during the last run
 For details, see FaultControllersREADME.md"""
import asyncio
import re
import sys

from subprocess import run


from mininet import log
from mininet.fault_controllers.BaseFaultController import BaseFaultControllerStarter, BaseFaultController, MESSAGE_SETUP_DONE, MESSAGE_INJECTION_DONE
from mininet.fault_controllers.AgnosticLink import AgnosticLink
from mininet.fault_injectors import LinkInjector


class MostUsedLinkFaultController(BaseFaultController):

    async def _wait_for_next_run(self):
        if self.mode == "automatic":
            return True
        elif self.mode == "manual" or self.mode == "repeating":
            log.debug("Starting wait for run...\n")
            while self.do_next_run is False and self.is_active is True:
                await asyncio.sleep(0)
                continue
            self.do_next_run = False
            log.debug("Done waiting for run...\n") # either because it's starting, or because we're stopping
            return True
        else:
            log.error(f"FaultController running in unknown mode: {self.mode}\n")


    async def go(self):
        await super().go()

        end_number_of_links = min(self.end_number_of_links, len(self.target_links_list))
        while True:
            for _ in range(1,end_number_of_links+1):
                await self._wait_for_next_run()
                if not self.is_active:
                    break
                await self._do_next_iteration()
            if self.mode != "repeating" or not self.is_active:
                # Only run this once if our mode isn't repeating,
                # otherwise run until we're deactivated
                break

        # All faults have finished injecting, so send the "done" message
        await self.deactivate_and_send_done_message()

    async def _do_next_iteration(self):
        faults_for_run = []
        fault_coroutines = []

        uninjected_links =  list(set(self.target_links_list) - set(self.links_to_inject))
        most_trafficked_link = None
        max_traffic_on_link = -1

        for i, link_information in enumerate(uninjected_links):
            traffic_on_link = self._get_traffic_on_link(link_information)
            old_traffic = link_information.traffic
            traffic_since_last_run = traffic_on_link - old_traffic
            uninjected_links[i].traffic = traffic_on_link

            if traffic_since_last_run > max_traffic_on_link:
                most_trafficked_link = link_information
                max_traffic_on_link = traffic_since_last_run



        if most_trafficked_link is not None:
            self.links_to_inject.append(most_trafficked_link)
        for link in self.links_to_inject:
            injector0, injector1 = self._get_injectors_for_link(link)
            faults_for_run.append(injector0)
            faults_for_run.append(injector1)

        log.info(f"Injecting faults on {len(self.links_to_inject)} links\n")
        for i in faults_for_run:
            fault_coroutines.append(i.go())

        await asyncio.gather(*fault_coroutines)
        log.debug("Fault iteration is done\n")

    def _get_traffic_on_link(self, link_information:AgnosticLink):
        # We only check one side of the link here. That might cause weird behavior if a link loses a lot of traffic
        # (since both sides of the link won't be balanced.
        # This is not an issue, since for this controller we only check faultless links.
        # For more complex controllers checking both sides of the link will sometimes yield more intuitive results.
        base_command = f"nsenter --target {str(link_information.link1_pid)} --net --pid --net "
        command_to_execute_rx = "ifconfig " + link_information.link1_name + """ | grep  "RX packets" | awk '{print $3}'"""
        command_to_execute_tx = "ifconfig " + link_information.link1_name + """ | grep "TX packets" | awk '{print $3}'"""

        completed_process_rx = run(base_command + command_to_execute_rx, capture_output=True, text=True, shell=True)
        completed_process_tx = run(base_command + command_to_execute_tx, capture_output=True, text=True, shell=True)
        number_of_received_packets = int(completed_process_rx.stdout)
        number_of_transmitted_packets = int(completed_process_tx.stdout)
        log.debug(f"link {link_information.link1_node_name}->{link_information.link2_node_name} has usage of {str(number_of_transmitted_packets + number_of_received_packets)}\n")

        return number_of_transmitted_packets + number_of_received_packets


    def _get_injectors_for_link(self, link_element:AgnosticLink):
        # (pid, interface name, node name), (pid, interface_name, node_name))
        target_pid_0 = link_element.link1_pid
        target_pid_1 = link_element.link2_pid

        target_interface_0 = link_element.link1_name
        target_interface_1 = link_element.link2_name

        target_nodename_0 = link_element.link1_node_name
        target_nodename_1 = link_element.link2_node_name

        tag_0 = f"{target_nodename_0}:{target_interface_0}->{target_nodename_1}:{target_interface_1}"
        tag_1 = f"{target_nodename_1}:{target_interface_1}->{target_nodename_0}:{target_interface_0}"

        injector0 = LinkInjector(target_interface=target_interface_0,
                                 target_namespace_pid=target_pid_0,
                                 tag=tag_0,

                                 fault_target_protocol="any",

                                 fault_type=self.fault_type,
                                 fault_pattern=self.fault_pattern,
                                 fault_args=self.fault_args,
                                 fault_pattern_args=self.fault_pattern_args,

                                 pre_injection_time=0,
                                 injection_time=self.injection_time,
                                 post_injection_time=0)

        injector1 = LinkInjector(target_interface=target_interface_1,
                                 target_namespace_pid=target_pid_1,
                                 tag=tag_1,

                                 fault_target_protocol="any",

                                 fault_type=self.fault_type,
                                 fault_pattern=self.fault_pattern,
                                 fault_args=self.fault_args,
                                 fault_pattern_args=self.fault_pattern_args,

                                 pre_injection_time=0,
                                 injection_time=self.injection_time,
                                 post_injection_time=0)
        return injector0, injector1


    def _configByFile(self, config):
        """Reconfigures this controller according to the given file """

        self.end_number_of_links = int(config.get("end_links",  sys.maxsize)) # defaults to "as many links as we have" in go()
        target_links_list = config.get("links", None)

        self.target_links_list = [] # links we could inject into
        self.links_to_inject = [] # links we do inject in this run
        for link_tuple in target_links_list:
            link_tuple = list(link_tuple)
            corresponding_link_object = AgnosticLink(link1_pid=link_tuple[0][0],
                                        link1_name=link_tuple[0][1],
                                                     link1_node_name=link_tuple[0][2],
                                                     link2_pid=link_tuple[1][0],
                                                     link2_name=link_tuple[1][1],
                                                     link2_node_name=link_tuple[1][2])
            self.target_links_list.append(corresponding_link_object)

        self.mode = config.get("mode", "automatic")
        self.do_next_run = False # Starting immediately after "go" seems unintuitive

        link_fault_regex = "^link_fault:(\w*)$"


        if match := re.match(link_fault_regex, config.get("fault_type")):
            self.fault_type = match.groups()[0]
        else:
            log.error(f"Unknown fault type: {config.get('fault_type')}\n")

        self.fault_args = config.get("type_args")
        self.fault_pattern = config.get("pattern")
        self.fault_pattern_args = config.get("pattern_args")

        self.injection_time = int(config.get("injection_time"))

        self.target_protocol, self.src_port, self.dst_port = self.get_target_arguments_from_fault_dict(config)
        self.src_port = int(config.get("src_port", 0))
        self.dst_port = int(config.get("dst_port", 0))
        if self.src_port == 0:
            self.src_port = None
        if self.dst_port == 0:
            self.dst_port = None


class MostUsedLinkFaultControllerStarter(BaseFaultControllerStarter):

    controller_class = MostUsedLinkFaultController
    def make_controller_config(self, net_reference, starter_config):
        # Copy over values for type, type_args, pattern, pattern_args, injection_time, start_links, end_links
        controller_config = starter_config
        log_dict = self.get_controller_log_dict(net_reference, controller_config)
        if log_dict is not None:
            controller_config['log'] = log_dict

        links_list = []
        blacklisted_nodes = starter_config.get('nodes_blacklist', {})

        for link in net_reference.links:
            if link.intf1.node.name in blacklisted_nodes or link.intf2.node.name in blacklisted_nodes:
                # Links that link to a blacklisted node can never contain faults
                continue

            # list of ((pid, interface name, node name), (pid, interface_name, node_name))
            link_element = {(
                link.intf1.node.pid,
                link.intf1.name,
                link.intf1.node.name),

                (link.intf2.node.pid,
                 link.intf2.name,
                 link.intf2.node.name)
            }
            links_list.append(link_element)

        controller_config['links'] = links_list
        return controller_config
