"""
Yeah there'll defs be documentation here, but right now that's TODO
"""
import asyncio
import re

from mininet import log
import yaml

from mininet.net import Mininet
from mininet.thorfi_injector.injector_agent import Injector

"""
# TODO
    - Note: Log saving?
    - Note: What happens after _inject_? How about _recovery_?
        - Specifically, supporting TcNodes is non-trivial
"""

class FaultController(object):

    def __init__(self, net_reference: Mininet, filepath_to_config_file=None):
        self.net_reference = net_reference
        self.faults = []
        self.total_runtime = 0

        if filepath_to_config_file is not None:
            self._configByFile(filepath_to_config_file)

    async def go(self):
        log.debug("Initiating faults\n")

        fault_coroutines = []
        for i in self.faults:
            fault_coroutines.append(i.go())
        log.debug("All faults scheduled.\n")

        await asyncio.gather(*fault_coroutines)
        # await asyncio.sleep(self.total_runtime)

    def _get_target_arguments_from_fault_dict(self, fault_dict):
        if 'target_traffic' in fault_dict:
            # TODO check against actually accepted values
            traffic_object = fault_dict.get('target_traffic')

            fault_target_traffic = traffic_object.get('protocol', 'any')
            fault_target_protocol = traffic_object.get('protocol', 'any')
            src_port = traffic_object.get('src_port', None)
            dst_port = traffic_object.get('dst_port', None)
        else:
            fault_target_traffic = 'any'
            fault_target_protocol = None
            src_port = None
            dst_port = None

        return fault_target_traffic, fault_target_protocol, src_port, dst_port

    def _configByFile(self, filepath):
        """Reconfigures this controller according to the given file """

        with open(filepath, 'r') as file:
            config = yaml.safe_load(file)  # TODO handle doesn't exist

        self.faults = []

        for fault_object in config.get("faults"):
            fault_dict = fault_object.get("link_fault")
            # fault_target_protocol, fault_target_traffic, src_port, dst_port
            fault_target_traffic, fault_target_protocol, src_port, dst_port = self._get_target_arguments_from_fault_dict(
                fault_dict)

            # type, pattern, type_arg, pattern_arg
            fault_args = fault_dict.get('type_arg', None)  # TODO handle absence gracefully

            fault_pattern = fault_dict.get('pattern', 'persistent')
            fault_pattern_args = fault_dict.get('pattern_arg', None)  # TODO handle absence gracefully

            # pre_injection_time, injection_time, post_injection_time
            pre_injection_time = fault_dict.get('pre_injection_time', 0)
            injection_time = fault_dict.get('injection_time', 0)
            post_injection_time = fault_dict.get('post_injection_time', 0)
            self.total_runtime = max(self.total_runtime, pre_injection_time + injection_time + post_injection_time)

            # fault type - this also decides which injector we use
            if (fault_type_value := fault_dict.get('type', None)) is None:
                log.warn("No fault type set\n")
                continue
            else:
                link_fault_regex = "^link_fault:(\w*)$"
                if (match := re.match(link_fault_regex, fault_type_value)):
                    fault_type = match.groups()[0]

                    # target_nics, target_node
                    for identifier_string in fault_dict.get("identifiers"):
                        corresponding_interface_name, corresponding_host = self._get_target_identifier_arguments_from_identifier_string(
                            identifier_string)
                        corresponding_interface_name = [corresponding_interface_name]
                        if corresponding_host is None:
                            continue
                        injector = Injector(target_nics=corresponding_interface_name,
                                            target_node=corresponding_host,

                                            fault_target_traffic=fault_target_traffic,
                                            fault_target_protocol=fault_target_protocol,
                                            fault_target_dst_ports=dst_port,
                                            fault_target_src_ports=src_port,

                                            fault_type=fault_type,
                                            fault_pattern=fault_pattern,
                                            fault_args=fault_args,
                                            fault_pattern_args=fault_pattern_args,

                                            pre_injection_time=pre_injection_time,
                                            injection_time=injection_time,
                                            post_injection_time=post_injection_time)
                        self.faults.append(injector)
                    # TODO document our yml fault format
                else:
                    log.warn(f"Fault type unknown:'{fault_type_value}'\n")

    def _get_target_identifier_arguments_from_identifier_string(self, identifier_string):
        implicit_regex = "^(\w*)->(\w*)$"  # matches "host_name->host_name"
        explicit_regex = "^(\w*)->(\w*):(\w*)$"  # matches "host_name->host_name:interface_name", useful if more than one link exists

        if (match := re.match(implicit_regex, identifier_string)):
            nodename_a = match.groups()[0]
            nodename_b = match.groups()[1]
            explicit_name = None
        elif (match := re.match(explicit_regex, identifier_string)):
            nodename_a = match.groups()[0]
            nodename_b = match.groups()[1]
            explicit_name = match.groups()[2]
        else:
            log.warn(f"Argument '{identifier_string}' doesn't conform to any known format\n")
            return None, None

        # TODO create a lookup dict and update it when appropriate if this is a performance bottleneck
        corresponding_interface_name = None
        corresponding_host = None

        # We currently the mininet reference to
        # - Get reference to node
        # - get interface names (by node names)


        # So the new workflow is:
    #    - Call faultcontroller, with net reference
    #    - from config, get all interface names, namespace references, pgroup numbers in tuples
    #    - so that it's a (pgid, net_namespace_identifier, interface_name)' tuple
    #    - start a new python instance, with a communicator (named pipe/socket?)
    #
    #    - in the new python instance:
    #        - read our command line arguments. Within those there's the same .yml config file'
    #        - but _identifiers_ has been rewritten to (pgid, net_namespace_identifier, [cgroup identiifer?], interface_name)
    #        - so out of those we generate a shell (in pgid, net_namespace_identifier)
    #             - which we then pass into a new fault object we're generating'
    #                - interface_name for net faults
    #                - command for node faults? (yeah, I think that should work)
    #        - once done, we tell "rdy" to our host process (via that socket), and wait for the go command to be passed
    #    - once that comes in we just go, as previously


        for link in self.net_reference.links:
            if link.intf1.node.name == nodename_a and link.intf2.node.name == nodename_b:
                corresponding_interface_name = link.intf1.name
                corresponding_host = link.intf1.node
                # If we're looking for a specific interface stop searching only if interface names match
                if explicit_name:
                    if explicit_name == corresponding_interface_name:
                        break
                    else:
                        corresponding_interface_name = None
                        corresponding_host = None
            elif link.intf1.node.name == nodename_b and link.intf2.node.name == nodename_a:
                corresponding_interface_name = link.intf2.name
                corresponding_host = link.intf2.node
                # If we're looking for a specific interface stop searching only if interface names match
                if explicit_name:
                    if explicit_name == corresponding_interface_name:
                        break
                    else:
                        corresponding_interface_name = None
                        corresponding_host = None

        if corresponding_interface_name is None:
            if explicit_name:
                log.warn(
                    f"Couldn't find interface {explicit_name} between hosts {nodename_a} and {nodename_b}. Skipping fault...\n")
            else:
                log.warn(
                    f"Couldn't find fitting interface between hosts {nodename_a} and {nodename_b}. Skipping fault...\n")
            return None, None

        return corresponding_interface_name, corresponding_host
