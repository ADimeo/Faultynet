"""ConfigFileFaultController implements a fault injector that defines faults from a single ocnfiguration file.
 For details, see FaultControllersREADME.md"""
import asyncio
import re

import uuid

from ast import literal_eval

from mininet import log
from mininet.fault_controllers.BaseFaultController import BaseFaultControllerStarter, BaseFaultController
from mininet.fault_injectors import LinkInjector, NodeInjector



class ConfigFileFaultController(BaseFaultController):

    async def go(self):
        await super().go()

        fault_coroutines = []
        for i in self.faults:
            fault_coroutines.append(i.go())
        log.debug("All faults scheduled.\n")
        await asyncio.gather(*fault_coroutines)
        # All faults have finished injecting, so send the "done" message
        await self.deactivate_and_send_done_message()


    def _configByFile(self, config):
        """Reconfigures this controller according to the given file """

        self.faults = []

        for fault_object in config.get("faults"):
            fault_type = list(fault_object.keys())[0]
            fault_dict = fault_object.get(fault_type)

            # fault_target_protocol, src_port, dst_port
            fault_target_protocol, src_port, dst_port = self.get_target_arguments_from_fault_dict(
                fault_dict)

            # type, pattern, type_arg, pattern_arg
            fault_args = fault_dict.get('type_args', None)
            tag = fault_dict.get('tag', None)
            if tag is None:
                tag = str(uuid.uuid4())


            fault_pattern = fault_dict.get('pattern', 'persistent')
            fault_pattern_args = fault_dict.get('pattern_args', None)

            # pre_injection_time, injection_time, post_injection_time
            pre_injection_time = fault_dict.get('pre_injection_time', None)
            injection_time = fault_dict.get('injection_time', None)
            post_injection_time = fault_dict.get('post_injection_time', None)

            # fault type - this also decides which injector we use
            if (fault_type_value := fault_dict.get('type', None)) is None:
                log.warn("No fault type set\n")
                continue

            link_fault_regex = "^link_fault:(\w*)$"
            node_fault_regex = "^node_fault:(\w*)$"

            if match := re.match(link_fault_regex, fault_type_value):
                fault_type = match.groups()[0]

                # target_nics, target_node
                for identifier_string in fault_dict.get("identifiers"):
                    identifier_tuple = literal_eval(identifier_string)
                    node_process_pid = identifier_tuple[0]
                    corresponding_interface_name = identifier_tuple[1]
                    node_string_reference = identifier_tuple[2]
                    actual_tag = tag + "@" + node_string_reference

                    injector = LinkInjector(target_interface=corresponding_interface_name,
                                            target_namespace_pid=node_process_pid,
                                            tag=actual_tag,

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
            elif match := re.match(node_fault_regex, fault_type_value):
                fault_type = match.groups()[0]
                # target_nics, target_node
                for identifier_string in fault_dict.get("identifiers"):
                    identifier_tuple = literal_eval(identifier_string)
                    node_process_pid = identifier_tuple[0]
                    node_string_reference = identifier_tuple[2]
                    actual_tag = tag + "@" + node_string_reference

                    injector = NodeInjector(
                        target_process_pid=node_process_pid,
                        fault_type=fault_type,
                        tag=actual_tag,
                        pre_injection_time=pre_injection_time,
                        injection_time=injection_time,
                        post_injection_time=post_injection_time,

                        fault_pattern=fault_pattern,
                        fault_args=fault_args,
                        fault_pattern_args=fault_pattern_args)
                    self.faults.append(injector)
            else:
                log.warn(f"Fault type unknown:'{fault_type_value}'\n")




class ConfigFileFaultControllerStarter(BaseFaultControllerStarter):
    controller_class = ConfigFileFaultController

    def make_controller_config(self, net: 'Mininet', yml_config: dict) -> dict:
        for i, fault_object in enumerate(yml_config.get("faults")):
            # We expect a single key here, either link_fault or node_fault
            # Right now we don't care which one it is, so just get the first key
            fault_type = list(fault_object.keys())[0]
            fault_dict = fault_object.get(fault_type)

            new_identifier_strings = []
            for identifier_string in fault_dict.get("identifiers"):
                # Identifiers are in a->b or a->b:interface pattern, or in "a" node pattern
                node_identifying_tuple = ConfigFileFaultControllerStarter._get_mininet_agnostic_identifiers_from_identifier_string(
                    net, identifier_string)
                new_identifier_strings.append((repr(node_identifying_tuple)))
            fault_dict['identifiers'] = new_identifier_strings

            # If it's a 'redirect' fault, we also need to enrich the redirect-to interface, in the fault_type_args
            if fault_dict.get('type') == "link_fault:redirect":
                fault_type_args = fault_dict.get("type_args")
                potential_interface_name = fault_type_args[0]

                # it's either the interface name, or in the node->node (or node->node:interface) pattern
                need_to_extract_interface_name = self._is_string_in_arrow_pattern(net, potential_interface_name)
                if need_to_extract_interface_name:
                    interface_name, _ = self._get_node_and_interface_name_from_identifier_string(net,
                                                                                                 potential_interface_name)
                else:
                    interface_name = potential_interface_name

                yml_config['faults'][i]['link_fault']['type_args'][0] = interface_name
        log_dict = self.get_controller_log_dict(net, yml_config)
        if log_dict is not None:
            yml_config['log'] = log_dict
        return yml_config
