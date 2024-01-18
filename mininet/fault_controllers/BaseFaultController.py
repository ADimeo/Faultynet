"""Implements methods that are common to all or most FaultControllers."""
import asyncio
import re
import atexit
import uuid

from ast import literal_eval
from multiprocessing import Pipe, Process

import yaml

from mininet import log
from mininet.faultlogger import FaultLogger
from mininet.node import Node
from mininet.fault_injectors import LinkInjector, NodeInjector

MESSAGE_SETUP_DONE = "m_faultinjector_ready"
MESSAGE_SETUP_ERROR = "m_faultinjector_setuperror"
MESSAGE_START_INJECTING = "m_faultinjector_go"
MESSAGE_INJECTION_DONE = "m_faultinjector_done"
MESSAGE_SHUTDOWN = "m_write_logs"
MESSAGE_START_NEXT_RUN = "m_faultinjector_next"

class BaseFaultControllerStarter:

    controller_class = None
    def __init__(self, net_reference: 'Mininet', filepath_to_config_file=None):
        """Init function takes care of
        - creating pipes for communication with Controller
        - reading config from file, and calling make_controller_config method
        - starting controller, and waiting until it is fully initialized
        - setting active/logger active flags"""
        self.net_reference = net_reference
        self.faults_are_active = False

        self._prepare_communication_pipes()

        starter_config = self._get_base_config_dict(filepath_to_config_file)
        controller_config = self.make_controller_config(self.net_reference, starter_config)

        # "Mode" is nothing the starter needs to keep track of - calling start_next_run() will just not do anything
        # if the mode is automatic, or if no mode is supported
        if 'log' in controller_config:
            log.debug("Config has enabled logging\n")
            self.logger_active = True
        else:
            log.debug("Config has disabled logging\n")
            self.logger_active = False


        fault_process = Process(target=entrypoint_for_fault_controller, args=(
            self.controller_class,
            controller_config, self.recv_pipe_mininet_to_faults,
            self.send_pipe_mininet_to_faults, self.recv_pipe_faults_to_mininet,
            self.send_pipe_faults_to_mininet))

        fault_process.start()


        log.debug("Fault process started\n")
        response = self.recv_pipe_faults_to_mininet.recv_bytes()
        log.debug("Received message from FI\n")
        # We need the second pipe, otherwise we're getting interference from ourselves

        if response == MESSAGE_SETUP_DONE.encode():
            log.debug("FaultController has signalled that it's ready\n")
            return
        log.debug(f"FaultController has sent weird message: {response.decode()}\n")
        return

    def make_controller_config(self, net: 'Mininet', yml_config: dict) -> dict:
        """Each Controller needs to implement this method. It gets the yml_config, read straight from the disk,
        and should return a dict that the _configByFile method from the corresponding controller can read."""
        raise NotImplementedError

    def _prepare_communication_pipes(self):
        """ Creates pipes for communication with Controller"""
        recv_pipe_mininet_to_faults, send_pipe_mininet_to_faults = Pipe()
        recv_pipe_faults_to_mininet, send_pipe_faults_to_mininet = Pipe()

        self.send_pipe_mininet_to_faults = send_pipe_mininet_to_faults
        self.recv_pipe_mininet_to_faults = recv_pipe_mininet_to_faults
        self.send_pipe_faults_to_mininet = send_pipe_faults_to_mininet
        self.recv_pipe_faults_to_mininet = recv_pipe_faults_to_mininet

    def go(self):
        """Tells the created controller to start the fault injection. Not to be confused with start_next_run, which
        starts the next iteration of an already started controller."""
        log.info("Initiating faults\n")
        self.faults_are_active = True
        self.send_pipe_mininet_to_faults.send_bytes(MESSAGE_START_INJECTING.encode())
        atexit.register(notify_controller_of_shutdown, self.send_pipe_mininet_to_faults)

    def stop(self):
        """Tells the FaultController to shut down now, or after the current iteration"""
        self.send_pipe_mininet_to_faults.send_bytes(MESSAGE_SHUTDOWN.encode())

    def start_next_run(self):
        """Tells the FaultController to start the next iteration"""
        self.send_pipe_mininet_to_faults.send_bytes(MESSAGE_START_NEXT_RUN.encode())

    def is_active(self):
        """Returns true if the controller that was started by this starter is still active, otehrwise False"""
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

    def _get_base_config_dict(self, filepath_to_config_file):
        """Reads a yml file from disk, and reutns it"""
        if filepath_to_config_file is None:
            log.error("Filepath to config file is missing\n")
            return None
        with open(filepath_to_config_file, 'r') as file:
            config = yaml.safe_load(file)
        return config


    def get_controller_log_dict(self, net: 'Mininet', yml_config: dict) -> dict:
        """Returns a controller-compatible dict of the log: object from the user-provided yml-config.
        The output of this method should be saved under 'log' if not None.

        This helper method is usually called from your implementation of make_controller_config"""
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


    @staticmethod
    def _get_mininet_agnostic_identifiers_from_identifier_string(net: 'Mininet', identifier_string: str) -> (
            int, str, str):
        """Takes a string in our node presentation, which can either be a node name (h1), arrow notation (h1->s1),
        or arrow notation with interfaces (h1->s1:eth0). Returns (process_group_id, interface_name, identifier_string)
        process_group_id is the pid of the process of the node that is indicated by the string, h1 for all of the cases listed above.
        interface_name is the name of an interface that checks the given condition (None in the first case, an interface that links h1
        with s1 in the second case, and eth0 in the third case, if such an interface should exist).
        identifier_string is the inputted string.
        """
        corresponding_interface_name, corresponding_host = BaseFaultControllerStarter._get_node_and_interface_name_from_identifier_string(
            net, identifier_string)
        process_group_id, interface_name = BaseFaultControllerStarter._get_passable_identifiers_from_node_and_interface_name(
            corresponding_interface_name, corresponding_host)
        return process_group_id, interface_name, identifier_string

    @staticmethod
    def _is_string_in_arrow_pattern(net: 'Mininet', identifier_string) -> bool:
        """Returns true if the string is in the h1->s1:eth0 or h1->s1 pattern"""
        implicit_link_regex = "^(\w*)->(\w*)$"  # matches "host_name->host_name"
        explicit_link_regex = "^(\w*)->(\w*):(\w*)$"  # matches "host_name->host_name:interface_name", useful if more than one link exists
        if match := re.match(implicit_link_regex, identifier_string):
            return True
        if match := re.match(explicit_link_regex, identifier_string):
            return True
        return False

    @staticmethod
    def _get_node_and_interface_name_from_identifier_string(net: 'Mininet', identifier_string) -> (str, Node):
        """Takes a string in our node presentation, which can either be a node name (h1), arrow notation (h1->s1),
        or arrow notation with interfaces (h1->s1:eth0). Returns a fitting interface name (or None if no such interface exists),
        and the Node on which that interface can be found.

        An interface is considered fitting if
        - for h1->s1 it is situated on h1, and links it to s1
        - for h1->s1:eth0 same as above, but it needs to have the name eth0
        - for h1, never. Only the indicated node will be returned."""
        # These patterns are expected for link_fault s
        implicit_link_regex = "^(\w*)->(\w*)$"  # matches "host_name->host_name"
        explicit_link_regex = "^(\w*)->(\w*):([\w|-]*)$"  # matches "host_name->host_name:interface_name", useful if more than one link exists
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
        """Returns a tuple of (pgid, interface_name) for the given interface and node."""
        if corresponding_node is None:
            return None, None
        process_group_id = corresponding_node.pid  # If nodes assume this we can also assume it
        interface_name = corresponding_interface_name
        return process_group_id, interface_name


class BaseFaultController:
    def __init__(self, controller_config, recv_pipe_mininet_to_faults, send_pipe_mininet_to_faults,
                 recv_pipe_faults_to_mininet, send_pipe_faults_to_mininet):
        self.config = controller_config
        self.fault_logger = None  # set in config_logger
        self.is_active = False

        self.recv_pipe_mininet_to_faults = recv_pipe_mininet_to_faults
        self.send_pipe_mininet_to_faults = send_pipe_mininet_to_faults

        self.recv_pipe_faults_to_mininet = recv_pipe_faults_to_mininet
        self.send_pipe_faults_to_mininet = send_pipe_faults_to_mininet

        self._configByFile(self.config)
        self._config_logger(self.config)

        log.debug("FI: Sending setup finished command\n")
        self.send_pipe_faults_to_mininet.send_bytes(MESSAGE_SETUP_DONE.encode())


    def wait_until_go(self):
        """Busy loops. Listens on pipe, and calls go once starter indicates that the
        controller should start running"""
        log.info("FaultController is waiting for go command\n")
        potential_go_message = self.recv_pipe_mininet_to_faults.recv_bytes()
        if potential_go_message == MESSAGE_START_INJECTING.encode():
            asyncio.run(self.go())

    async def go(self):
        """Called when the controller should start running.
        Usually overridden, to make it do more stuff than just starting the logger."""
        log.debug("Initiating faults\n")
        self.is_active = True
        if self.fault_logger is not None:
            self.log_task = asyncio.create_task(self.fault_logger.go())
        self.pipe_listener_task = asyncio.create_task(self.listen_for_pipe_messages())


    async def deactivate_and_send_done_message(self):
        """Tells the Starter that this Controller is finished, and shuts down things, including the logger.

        Needs to be called manually when implementing go(), after all other work has concluded."""
        log.debug("FaultController is initiating deactivation\n")
        self.is_active = False
        # We send a done message to our starter, so that the rest of mininet knows that we are done
        self.send_pipe_faults_to_mininet.send_bytes(MESSAGE_INJECTION_DONE.encode())
        # We also send a done message to ourselves, to stop the listener on our pipe - if we're done here
        # we don't expect any more messages
        self.send_pipe_mininet_to_faults.send_bytes(MESSAGE_SHUTDOWN.encode())

        if self.fault_logger is not None:
            self.fault_logger.stop()
            await self.log_task
            # All faults have finished injecting, so send the "done" message

        await asyncio.gather(self.pipe_listener_task)

    async def listen_for_pipe_messages(self):
        """ Receives and processes messages the Starter sends to the Controller, specifically
        - Shutdown
        - Next Run"""
        log.debug("FaultController listening for messages on pipe\n")

        while True:
            while not self.recv_pipe_mininet_to_faults.poll():
                await asyncio.sleep(0) # If this is missing this piece of code will block other tasks from running
                # Don't ask me how long it took me to find that out
                continue
            message_in_pipe = self.recv_pipe_mininet_to_faults.recv_bytes()

            if message_in_pipe == MESSAGE_SHUTDOWN.encode():
                log.info("FaultController received message for shutdown\n")
                # This is a terminating message - after this we need to return for the controller to shut down,
                # and no other messages will be received
                self.is_active = False
                if self.fault_logger is not None:
                    self.fault_logger.stop()
                return
            elif message_in_pipe == MESSAGE_START_NEXT_RUN.encode():
                log.debug("FaultController received message for next run\n")
                self.do_next_run = True
            else:
                log.error("Received unexpected message while waiting for log-to-file message\n")

    def _config_logger(self, config):
        """Configures the logger, based on the values under the 'log' key"""
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
        """Configures this controller according to the given. Needs to be implemented by each FaultController, and be
        compatible with the  make_controller_config method from the corresponding Starter. """
        raise NotImplementedError

    def get_target_arguments_from_fault_dict(self, fault_dict):
        """Returns fault_target_procotol, src_port, dst_port, from the target_traffic: key"""
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



def entrypoint_for_fault_controller(controller_class, mininet_agnostic_faultconfig: dict, recv_pipe_mininet_to_faults,
                                    send_pipe_mininet_to_faults, recv_pipe_faults_to_mininet,
                                    send_pipe_faults_to_mininet):
    """Entry into the Controllerprocess. Starts the controller, and makes it listen on the communication pipe"""
    if not isinstance(controller_class, type):
        log.error("controller_class of starter is not a controller. Controller not started.\n")
        return

    main_injector = controller_class(mininet_agnostic_faultconfig, recv_pipe_mininet_to_faults,
                                              send_pipe_mininet_to_faults, recv_pipe_faults_to_mininet,
                                              send_pipe_faults_to_mininet)
    main_injector.wait_until_go()


def notify_controller_of_shutdown(pipe):
    """Sends shutdown message to controller"""
    pipe.send_bytes(MESSAGE_SHUTDOWN.encode())
