"""LogOnlyFaultController implements a fault injector that doesn't inject any faults, but can be used to use
faultloggers. For details, see FaultControllersREADME.md"""
import asyncio


from mininet import log
from mininet.fault_controllers.BaseFaultController import BaseFaultControllerStarter, BaseFaultController

class LogOnlyFaultController(BaseFaultController):
    async def go(self):
        await super().go()
        log.debug("Initiating Logger\n")
        while True:
            if not self.is_active:
                break
            await asyncio.sleep(0)

        # All faults have finished injecting, so send the "done" message
        await self.deactivate_and_send_done_message()


    def _configByFile(self, config):
        """No config necessary - log config is taken care of by BaseFaultController"""
        return

class LogOnlyFaultControllerStarter(BaseFaultControllerStarter):
    controller_class = LogOnlyFaultController

    def make_controller_config(self, net: 'Mininet', yml_config: dict) -> dict:
        log_dict = self.get_controller_log_dict(net, yml_config)
        if log_dict is not None:
            yml_config['log'] = log_dict
        return yml_config
