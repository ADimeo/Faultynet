import asyncio
import atexit
import time
import queue
import json
from mininet import log

ACTIVE_FAULTS_DICT = dict()


# This _should_ be fine, since cpython guarantees us that the dict won't
# corrupt - and based on tags each fault should only change itself

class FaultLogger(object):

    def __init__(self, interval=1000,  # in ms
                 log_filepath='faultynet_faultlogfile.json'):
        self.interval = interval / 1000  # asyncio.sleep expects seconds
        self.log_filepath = log_filepath

        self.logged_faults = queue.Queue()
        self.start_time_ms = None
        self.active = False

    async def go(self):
        self.start_time_ms = int(time.time_ns() / 1000000)
        self.active = True
        log_tasks = []
        while self.active:
            log_tasks.append(asyncio.create_task(self.log()))  # Store to prevent mid-task garbage collection
            await asyncio.sleep(self.interval)

    def stop(self):
        self.active = False

    @classmethod
    def set_fault_active(cls, tag, fault_type, command, retcode):
        ACTIVE_FAULTS_DICT[tag] = {'fault_tag': tag,
                                   'fault_type': fault_type,
                                   'command': command,
                                   'retcode': retcode}

    @classmethod
    def set_fault_inactive(cls, tag):
        try:
            del ACTIVE_FAULTS_DICT[tag]
        except KeyError:
            log.warn(f'Could not disable fault {tag}, likely due to race conditions. Logs may be incorrect.\n')

    def get_active_faults(self):
        return list(ACTIVE_FAULTS_DICT.values())

    async def log(self):
        timestamp_ms = int(time.time_ns() / 1000000)
        ms_since_start = timestamp_ms - self.start_time_ms
        active_faults = self.get_active_faults()

        # TODO potentially add last_changed, activated/deactivated since last?
        logging_point_in_time = {
            'time_ms': timestamp_ms,
            'time_since_start_ms': ms_since_start,
            'active_faults': active_faults,
        }
        self.logged_faults.put(logging_point_in_time)

        # TODO think about executing commands here? -> Is that worth the effort? It'd be a cool feature, and useful.
        #  It's how I'm debugging right now, after all.

    def write_log_to_file(self):
        log.error(f"Writing fault logs to {self.log_filepath}\n")
        logs = list(self.logged_faults.queue)
        with open(self.log_filepath, 'w') as json_file:
            json.dump(logs, json_file, indent=4)
