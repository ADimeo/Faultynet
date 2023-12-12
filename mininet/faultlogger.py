import asyncio
import atexit
import time
import queue
import json
from mininet import log
from subprocess import run

ACTIVE_FAULTS_DICT = dict()


# This _should_ be fine, since cpython guarantees us that the dict won't
# corrupt - and based on tags each fault should only change itself

class FaultLogger(object):
    """Writes details about faults to a file, based on internal state. Checks state in given time interval.
    Start logging with go(), end it with stop(). Logging happens async. Logs are only written to file when
    calling write_log_to_file. Notably, this doesn't happen automatically, when calling either stop() or go().
    """

    def __init__(self, interval=1000,  # in ms
                 log_filepath='faultynet_faultlogfile.json',
                 commands=[]):
        if interval is None:
            interval = 1000
        if log_filepath is None:
            log_filepath = 'faultynet_faultlogfile.json'

        self.interval = interval / 1000  # asyncio.sleep expects seconds
        self.log_filepath = log_filepath
        self.commands = commands

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
        # Once done, write to file.
        # Others can also call us to write to file, but that's fine: IF they write later we only
        # get additional logs, and nothing is lost
        self.write_log_to_file()

    def stop(self):
        log.debug("Stopping fault logger\n")
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
            log.warn(f'Could not disable fault {tag}, likely due to duplicate tag, or race condition. Logs may be incorrect.\n')

    def get_active_faults(self):
        return list(ACTIVE_FAULTS_DICT.values())

    async def log(self):
        timestamp_ms = int(time.time_ns() / 1000000)
        ms_since_start = timestamp_ms - self.start_time_ms
        active_faults = self.get_active_faults()
        log.debug("Generating fault log entry...\n")

        debugging_command_output = self.run_debug_commands()

        logging_point_in_time = {
            'time_ms': timestamp_ms,
            'time_since_start_ms': ms_since_start,
            'active_faults': active_faults,
            'commands': debugging_command_output
        }
        self.logged_faults.put(logging_point_in_time)

    def run_debug_commands(self):
        command_outputs = []
        if self.commands is None:
            return ""

        for command in self.commands:
            if command['host'] is None:
                full_command = command['command']  # Execute in main namespace
            else:
                full_command = f"nsenter --target {str(command['host'])} --net --pid --all " + command['command']
            completed_process = run(full_command, capture_output=True, text=True, shell=True)
            all_output = completed_process.stdout + completed_process.stderr

            debug_object = {
                'tag': command['tag'],
                'command': command['command'],
                'output': all_output
            }
            command_outputs.append(debug_object)
        return command_outputs

    def write_log_to_file(self):
        log.info(f"Writing fault logs to {self.log_filepath}\n")
        logs = list(self.logged_faults.queue)
        with open(self.log_filepath, 'w') as json_file:
            json.dump(logs, json_file, indent=4)
