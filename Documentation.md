# Faultynet Documentation

Most Faultynet behavior is Faultcontroller specific. For details on existing Faultcontrollers, see [FaultControllersREADME.md](FaultControllersREADME.md)

When creating a `Mininet()` instance, the constructor accepts two new arguments: 
  - `faultControllerStarter`, which refers to a class, and defaults to `ConfigFileFaultControllerStarter`
  - `faultFilepath`, which refers to a file.

When the `Mininet()` is `start()`ed, the net constructs the `faultControllerStarter` with the information from the file at the `faultFilepath` and starts
it via its `go()` method. 
When the `faultControllerStarter` is constructed it constructs the `faultController`, which runs in a different process.
On the call to `go` the `faultControllerStarter` makes sure that the
Within its `go` method, the `faultControllerStarter` makes sure that the `faultController` `go()` method is also called.
After that, behavior differs based on the specific FaultController (or, more specifically, will differ, since no other  FaultControllers have been implemented yet).

# Implementing new Controllers
Note: The following are guidelines and suggestions, other ways of achieving the same outcomes exist

Implementing new controllers requires `FaultControllerStarter`, as well as the `FaultController`. The responsibilities
of the `FaultControllerStarter` are creating the `FaultController`, communicating with the `FaultController`, and 
preparing data from Mininet for `FaultController` consumption. The `FaultController`is responsible for injecting the faults
and running the `Faultlogger`, potentially listening for further instructions from the `FaultControllerStarter`, and informing
it about the `FaultController`s state.

It is strongly encouraged to run the `FaultController` in a different process from the main Mininet instance. 
The reason for this recommendation is that some aspects of Mininet, specifically the execution of long-running commands 
on a node, are blocking, and would prevent other parts of the system from running at the same time, which can lead to 
faults not being injected when they should, or fault logs being generated incorrectly.


The simplest way of implementing a new `FaultController` is using the existing `BaseFaultController` and `BaseFaultControllerStarter`,
which handles both communication between both classes and a number of additional things.

## Building upon BaseFaultController
In your `Starter`, set the `controller_class` value to your custom `FaultController` class. Override the `make_controller_config`
method to transform the user-provided yml into a configuration that contains all information that the `FaultController`
requires. This commonly means identifying process IDs for nodes, as well as interface names.
`BaseFaultController` contains a number of methods that make this process easier, like `get_controller_log_dict`. For more details
see the source code.

In your custom `FaultController` class, override both the `_configByFile` function and the `go` function.
`_configByFile` is the equivalent to the Starters `get_controller_log_dict` function: It gets the output of `get_controller_log_dict`
as input, and its responsibility is to set all required local variables based on that input. It is called in
`BaseFaultController`s `init` method.

The `go` function contains the actual injection logic. `go` is executed when the `Starter`s `go` method is called.
It is important to call `await super().go()` before running custom code, and to call `await self.deactivate_and_send_done_message()`
once the controller is done with its work. If those function calls are not performed things will break.

## Injecting Faults
To inject a fault, construct a `LinkInjector`, `MultiInjecor` or `NodeInjector`, and launch them with the `go()`.
- Each FaultController injects exactly one fault, on one node or interface. 
  - This means that injecting a fault on one link requires to `LinkInjector`s, one for each interface at the ends of the link
  - One fault can lead to multiple commands being executed on a host, e.g. for a burst, which turns an injection on and off repeatedly
- Fault tags must be globally unique, or logging will be incorrect. This restriction is currently not enforced in code
- The [FaultControllersREADME](FaultControllersREADME.md) contains detailed documentation about fault configuration expressiveness, which also applies to the fault injectors
  - One major difference is that `target_namespace_pid` is the process id of the node to inject on, whereas the `identifiers` in the config carry semantic meaning. Usually, the starter of the fault controller is responsible for translating a user-friendly format to the pids of nodes
  - A second difference is that the config expects fault types with a leading `link_fault:` or `node_fault:`. Fault injectors expect no such thing.


## Fault Logger
Much like faultinjectors, the `FaultLogger` should run in a different process than the main Mininet instance.

The Logger starts on the call to `go()`, and adds one entry to the log, depending on the given time interval. 
Each entry contains which faults were active at that moment, timestamps, as well as the executed commands and their outputs.

The logged faults are based on an internal state representation of the system, and not on the state of the system itself:
Whenever a fault is injected or removed, this internal state is modified.  In theory this means that the internal state
may diverge if timings are off, if injections fail, or if interfaces are modified externally. 

Each log also takes commands. These are completely optional. If defined, these commands are executed once for each log interval.
Both the command and its output are stored in the log. This is a relatively simple way to get information on the
actual system state.

Logs are only written to file on logger shutdown, or if Mininet shuts down.
