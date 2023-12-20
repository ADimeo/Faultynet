"""ConfigFileFaultController implements a fault injector that defines faults from a single ocnfiguration file.
 For details, see FaultControllersREADME.md"""
import asyncio
import random
import re
import atexit
import sys
import uuid

from multiprocessing import Pipe, Process

import yaml

from mininet import log
from mininet.faultlogger import FaultLogger
from mininet.node import Node
from mininet.fault_injectors import LinkInjector

MESSAGE_SETUP_DONE = "m_faultinjector_ready"
MESSAGE_SETUP_ERROR = "m_faultinjector_setuperror"
MESSAGE_START_INJECTING = "m_faultinjector_go"
MESSAGE_INJECTION_DONE = "m_faultinjector_done"
MESSAGE_SHUTDOWN = "m_write_logs"
MESSAGE_START_NEXT_RUN = "m_faultinjector_next"


class RandomLinkFaultControllerStarter():

    def __init__(self, net_reference: 'Mininet', filepath_to_config_file=None):
        self.net_reference = net_reference
        self.faults_are_active = False

        self._prepare_communication_pipes()

        starter_config = self._get_base_config_dict(filepath_to_config_file)

        controller_config = self._make_controller_config(net_reference, starter_config)

        # "Mode" is nothing the starter needs to keep track of - calling start_next_run() will just not do anything
        # if the mode is automatic
        if 'log' in controller_config:
            log.debug("Config has enabled logging\n")
            self.logger_active = True
        else:
            log.debug("Config has disabled logging\n")
            self.logger_active = False

        fault_process = Process(target=entrypoint_for_fault_controller, args=(
            controller_config, self.recv_pipe_mininet_to_faults,
            self.send_pipe_mininet_to_faults, self.recv_pipe_faults_to_mininet,
            self.send_pipe_faults_to_mgininet))

        fault_process.start()



        log.debug("Fault process started\n")
        response = self.recv_pipe_faults_to_mininet.recv_bytes()
        log.debug("Received message from FI\n")
        # We need the second pipe,Otherwise we're getting interference from ourselves

        if response == MESSAGE_SETUP_DONE.encode():
            log.debug("FaultController has signalled that it's ready\n")
            return
        log.debug(f"FaultController has sent weird message: {response.decode()}\n")
        return

    def _prepare_communication_pipes(self):
        recv_pipe_mininet_to_faults, send_pipe_mininet_to_faults = Pipe()
        recv_pipe_faults_to_mininet, send_pipe_faults_to_mininet = Pipe()

        self.send_pipe_mininet_to_faults = send_pipe_mininet_to_faults
        self.recv_pipe_mininet_to_faults = recv_pipe_mininet_to_faults
        self.send_pipe_faults_to_mininet = send_pipe_faults_to_mininet
        self.recv_pipe_faults_to_mininet = recv_pipe_faults_to_mininet

    def _make_controller_config(self, net_reference, starter_config):
        # Copy over values for type, type_args, pattern, pattern_args, injection_time, start_links, end_links
        controller_config = starter_config
        log_dict = self._get_controller_log_dict(net_reference, controller_config)
        if log_dict is not None:
            controller_config['log'] = log_dict

        links_list = []

        for link in net_reference.links:
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

    def go(self):
        log.info("Initiating faults\n")
        self.faults_are_active = True
        self.send_pipe_mininet_to_faults.send_bytes(MESSAGE_START_INJECTING.encode())

        atexit.register(notify_controller_of_shutdown, self.send_pipe_mininet_to_faults)

    # TODO implement a "stop"function
    def start_next_run(self):
        """Tells the FaultController to start the next iteration"""
        self.send_pipe_mininet_to_faults.send_bytes(MESSAGE_START_NEXT_RUN.encode())

    def is_active(self):
        if not self.faults_are_active:
            return False
        # Injector might have sent us "done" message
        if self.recv_pipe_faults_to_mininet.poll() is False:
            return True
        potential_done_message = self.recv_pipe_faults_to_mininet.recv_bytes()
        if potential_done_message == MESSAGE_INJECTION_DONE.encode():
            self.faults_are_active = False
            return False
        # This destroys the message in the pipe, but "I'm done injecting" is the only message we expect

        return True


    def _get_controller_log_dict(self, net: 'Mininet', yml_config: dict) -> dict:
        """Reads the given config, and out of that returns a dict that should be a part of the controller
        modifier, under the 'log' key """
        if 'log' not in yml_config:
            # Caller doesn't want logs
            return None
        log_config = yml_config['log']
        if log_config is None:
            # This means that the log: key exists, but without any values -
            # So yes to logging, but all defaults
            return {}
        commands = log_config.get("commands", None)
        if commands is None:
            return log_config
        for i, debug_command in enumerate(commands):

            tag = debug_command.get('tag', None)
            if tag is None:
                tag = str(uuid.uuid4())
                log_config['commands'][i]['tag'] = str(tag)

            host_string = debug_command.get("host", None)
            node_identifying_tuple = self._get_mininet_agnostic_identifiers_from_identifier_string(net, host_string)
            log_config['commands'][i]['host'] = node_identifying_tuple[0]
        return log_config

    def _get_base_config_dict(self, filepath_to_config_file):
        if filepath_to_config_file is None:
            log.error("Filepath to config file is missing\n")
            return None
        with open(filepath_to_config_file, 'r') as file:
            config = yaml.safe_load(file)
        return config

    @staticmethod
    def _get_mininet_agnostic_identifiers_from_identifier_string(net: 'Mininet', identifier_string: str) -> (
            int, str, str, str):
        """Takes a string in our node presentation, which can either be a node name (h1), arrow notation (h1->s1),
        or arrow notation with interfaces (h1->s1:eth0)"""
        corresponding_interface_name, corresponding_host = RandomLinkFaultControllerStarter._get_node_and_interface_name_from_identifier_string(
            net, identifier_string)
        process_group_id, interface_name = RandomLinkFaultControllerStarter._get_passable_identifiers_from_node_and_interface_name(
            corresponding_interface_name, corresponding_host)
        return process_group_id, interface_name, identifier_string

    @staticmethod
    def _get_node_and_interface_name_from_identifier_string(net: 'Mininet', identifier_string) -> (str, Node):
        # These patterns are expected for link_fault s
        implicit_link_regex = "^(\w*)->(\w*)$"  # matches "host_name->host_name"
        explicit_link_regex = "^(\w*)->(\w*):(\w*)$"  # matches "host_name->host_name:interface_name", useful if more than one link exists
        if identifier_string is None:
            # This can happen for e.g. log commands, that don't need to be executed on a specific host
            return None, None
        if match := re.match(implicit_link_regex, identifier_string):
            nodename_a = match.groups()[0]
            nodename_b = match.groups()[1]
            explicit_name = None
        elif match := re.match(explicit_link_regex, identifier_string):
            nodename_a = match.groups()[0]
            nodename_b = match.groups()[1]
            explicit_name = match.groups()[2]
        else:
            # The identifier is in node pattern, so just the name of the node, no interface required.
            # Used for node injections, where there is no interface/second node
            nodename_a = identifier_string
            nodename_b = None
            explicit_name = None

        # Create a lookup dict and update it when appropriate if this is a performance bottleneck
        corresponding_interface_name = None
        corresponding_host = None

        if nodename_b is None:
            # not looking for an interface name, so we can skip that part
            for node in net.hosts:
                # Running over hosts _should_ be fine, since switches (usually) run in the root namespace
                # (and None defaults to the root namespace in the fault injectors)
                # If that doesn't work add in the switches/etc. into this list.
                if node.name == nodename_a:
                    return None, node

        for link in net.links:
            if link.intf1.node.name == nodename_a and link.intf2.node.name == nodename_b:
                corresponding_interface_name = link.intf1.name
                corresponding_host = link.intf1.node
                # If we're looking for a specific interface stop searching only if interface names match
                if explicit_name:
                    if explicit_name == corresponding_interface_name:
                        break
                    corresponding_interface_name = None
                    corresponding_host = None
            elif link.intf1.node.name == nodename_b and link.intf2.node.name == nodename_a:
                corresponding_interface_name = link.intf2.name
                corresponding_host = link.intf2.node
                # If we're looking for a specific interface stop searching only if interface names match
                if explicit_name:
                    if explicit_name == corresponding_interface_name:
                        break
                    corresponding_interface_name = None
                    corresponding_host = None

        if corresponding_interface_name is None:
            if explicit_name:
                log.warn(
                    f"Couldn't find interface {explicit_name} between hosts {nodename_a} and {nodename_b}. Are all names correct?...\n")
            else:
                log.warn(
                    f"Couldn't find fitting interface between hosts {nodename_a} and {nodename_b}. Are both names correct?...\n")
            return None, None

        return corresponding_interface_name, corresponding_host

    @staticmethod
    def _get_passable_identifiers_from_node_and_interface_name(corresponding_interface_name: str,
                                                               corresponding_node: Node):
        # Returns a tuple of (pgid, interface_name)#
        # process group id
        if corresponding_node is None:
            return None, None
        process_group_id = corresponding_node.pid  # If nodes assume this we can also assume it
        interface_name = corresponding_interface_name
        return process_group_id, interface_name


class RandomLinkFaultController:
    def __init__(self, controller_config, recv_pipe_mininet_to_faults, send_pipe_mininet_to_faults,
                 recv_pipe_faults_to_mininet, send_pipe_faults_to_mininet):
        self.config = controller_config
        self.fault_logger = None  # set in config_logger
        self.do_next_run = None # set in _configByFile

        self.recv_pipe_mininet_to_faults = recv_pipe_mininet_to_faults
        self.send_pipe_mininet_to_faults = send_pipe_mininet_to_faults

        self.recv_pipe_faults_to_mininet = recv_pipe_faults_to_mininet
        self.send_pipe_faults_to_mininet = send_pipe_faults_to_mininet

        self._configByFile(self.config)
        self._config_logger(self.config)

        log.debug("FI: Sending setup finished command\n")
        self.send_pipe_faults_to_mininet.send_bytes(MESSAGE_SETUP_DONE.encode())

    async def _wait_for_next_run(self):
        if self.mode == "automatic":
            return True
        elif self.mode == "manual":
            log.debug("Starting wait for run...\n")
            while self.do_next_run is False:
                await asyncio.sleep(0)
                continue
            self.do_next_run = False
            log.debug("Done waiting for run...\n")
            return True
        else:
            log.error(f"FaultController running in unknown mode: {self.mode}\n")


    def wait_until_go(self):
        log.info("Fault injector is waiting for go command\n")
        potential_go_message = self.recv_pipe_mininet_to_faults.recv_bytes()
        if potential_go_message == MESSAGE_START_INJECTING.encode():
            asyncio.run(self.go())

    # TODO also build a eternal fault injector that listens to a stop signal
    # and sets local "stopped" variable

    # TODO allow interrupt/stop: Listen on each run whether it was stopped?
    async def go(self):
        log.debug("Initiating faults\n")

        if self.fault_logger is not None:
            log_task = asyncio.create_task(self.fault_logger.go())
        pipe_listener_task = asyncio.create_task(self.listen_for_pipe_messages())



        end_number_of_links = min(self.end_number_of_links, len(self.target_links_list))
        for number_of_links_to_inject in range(self.start_number_of_links, end_number_of_links + 1):
            faults_for_run = []
            fault_coroutines = []

            await self._wait_for_next_run()

            links_to_inject = random.sample(self.target_links_list, number_of_links_to_inject)
            # TODO also check for stopped

            for link_information_tuple in links_to_inject:
                injector0, injector1 = self._get_injectors_for_link(link_information_tuple)
                faults_for_run.append(injector0)
                faults_for_run.append(injector1)

            log.info(f"Injecting faults on {number_of_links_to_inject} links\n")
            for i in faults_for_run:
                fault_coroutines.append(i.go())

            await asyncio.gather(*fault_coroutines)
            log.debug("Fault iteration is done\n")


        self.send_pipe_faults_to_mininet.send_bytes(MESSAGE_INJECTION_DONE.encode())
        if self.fault_logger is not None:
            self.fault_logger.stop()
            await log_task
        await  asyncio.gather(pipe_listener_task)
        # All faults have finished injecting, so send the "done" message

    def _get_injectors_for_link(self, link_information_tuple):
        # (pid, interface name, node name), (pid, interface_name, node_name))
        link_information_tuple = list(link_information_tuple)
        target_pid_0 = link_information_tuple[0][0]
        target_pid_1 = link_information_tuple[1][0]

        target_interface_0 = link_information_tuple[0][1]
        target_interface_1 = link_information_tuple[1][1]

        target_nodename_0 = link_information_tuple[0][2]
        target_nodename_1 = link_information_tuple[1][2]

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

    async def listen_for_pipe_messages(self):
        log.debug("FaultController listening for messages on pipe\n")

        while True:
            while not self.recv_pipe_mininet_to_faults.poll():
                await asyncio.sleep(0) # If this is missing this piece of code will block other tasks from running
                # Don't ask me how long it took me to find that out
                continue
            message_in_pipe = self.recv_pipe_mininet_to_faults.recv_bytes()

            if message_in_pipe == MESSAGE_SHUTDOWN.encode():
                log.debug("FaultController received message for shutdown\n")
                # This is a terminating message - after this we need to return for the controller to shut down,
                # and no other messages will be received
                if self.fault_logger is not None:
                    self.fault_logger.stop()
                return
            elif message_in_pipe == MESSAGE_START_NEXT_RUN.encode():
                log.debug("FaultController received message for next run\n")
                self.do_next_run = True
            else:
                log.error("Received unexpected message while waiting for log-to-file message\n")


    def _config_logger(self, config):
        log_config = config.get("log", None)
        if log_config is None:
            self.fault_logger = None
            return
        interval = int(log_config.get("interval", 0))
        if interval == 0:
            interval = None
        path = log_config.get("path", None)
        commands = log_config.get('commands', [])

        fault_logger = FaultLogger(interval=interval, log_filepath=path, commands=commands)
        self.fault_logger = fault_logger


    def _configByFile(self, config):
        """Reconfigures this controller according to the given file """

        self.start_number_of_links = int(config.get("start_links", 1))
        self.end_number_of_links = int(config.get("end_links",  sys.maxsize)) # defaults to "as many links as we have" in go()
        self.target_links_list = config.get("links", None)

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

        self.target_protocol, self.src_port, self.dst_port = self._get_target_arguments_from_fault_dict(config)
        self.src_port = int(config.get("src_port", 0))
        self.dst_port = int(config.get("dst_port", 0))
        if self.src_port == 0:
            self.src_port = None
        if self.dst_port == 0:
            self.dst_port = None


    def _get_target_arguments_from_fault_dict(self, fault_dict):
        if 'target_traffic' in fault_dict:
            traffic_object = fault_dict.get('target_traffic')

            fault_target_protocol = traffic_object.get('protocol', 'any')
            if fault_target_protocol not in ['ICMP', 'IGMP', 'IP', 'TCP', 'UDP', 'IPv6', 'IPv6-ICMP', 'any']:
                log.error(f"Fault target protocol {fault_target_protocol} is unknown, injecting any instead\n")
                fault_target_protocol = 'any'

            src_port = traffic_object.get('src_port', 0)
            dst_port = traffic_object.get('dst_port', 0)
            if src_port == 0:
                src_port = None
            if dst_port == 0:
                dst_port = None
        else:
            fault_target_protocol = 'any'
            src_port = None
            dst_port = None

        return fault_target_protocol, src_port, dst_port


def entrypoint_for_fault_controller(controller_config: dict, recv_pipe_mininet_to_faults,
                                    send_pipe_mininet_to_faults, recv_pipe_faults_to_mininet,
                                    send_pipe_faults_to_mininet):
    main_injector = RandomLinkFaultController(controller_config, recv_pipe_mininet_to_faults,
                                              send_pipe_mininet_to_faults, recv_pipe_faults_to_mininet,
                                              send_pipe_faults_to_mininet)
    main_injector.wait_until_go()


def notify_controller_of_shutdown(pipe):
    pipe.send_bytes(MESSAGE_SHUTDOWN.encode())
