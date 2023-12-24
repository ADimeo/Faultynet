# FaultControllers README

This document describes in detail the different FaultControllers currently implemented in FaultyNet. 
Each FaultController implements both a FaultController, and a FaultControllerStarter. For details see the [Faultynet Documentation](Documentation.md).

## LogOnlyFaultController
`LogOnlyFaultController` is a minimalist FaultController. It doesn't inject any faults, but does provide easy access
to FaultyNets logging system, which allows for scheduled execution of arbitrary commands on arbitrary hosts.
All other currently implemented FaultControllers also support this logging syntax.
For details about the logs, read the [Faultynet Documentation](Documentation.md)

This is the full reference for the config file:
```yml
---
log:
    interval: 1000 # in ms
    path: "/where/output/file/should/be/stored.json" # string, defaults to faultynet_faultlogfile.json
    commands:
        - tag: "command 1" # optional, for identification - defaults to random uuid
          host: "h1" # on which node to execute. Executes on main OS if missing
          command: "ip a" # str, actual command to run. Supports shell built ins
        - command: "ip a" # this command will execute on the main host, with a random uuid tag
...
```

## ConfigFileFaultController
`ConfigFileFaultController`was designed for repeatable usage in testing pipelines and offers limited interactivity.
This fault controller is automatically started when the corresponding net ist started, and faults are activated 
and deactivated based on a timer. After all faults have terminated `ConfigFileFaultController` shuts itself down.
Usually this means that the controller will run for `max(pre_injection_time + injection_time + post_injection_time)`.

The `ConfigFileFaultController` injects faults based on a .yml configuration file. `ConfigFileFaultController` currently 
does not support nodes or links that were added during runtime.
If the `log` tag is present, Faultynet will write logs to the given file.

This is the full reference for the config file:
```yml
---
faults:
  - link_fault:
      tag: 'string' # optional, for identification - defaults to random uuid
      pre_injection_time: 0 # int in seconds, defaults to 0
      injection_time: 20 # int in seconds, defaults to 20
      post_injection_time: 0 # int in seconds, defaults to 0
      type: "link_fault:loss" # "link_fault:limit", "link_fault:delay", "link_fault:loss", "link_fault:corrupt", "link_fault:duplicate", "link_fault:reorder", "link_fault:rate", "link_fault:slot"; "link_fault:down","link_fault:redirect", "link_fault:bottleneck"
      type_args: ["10", 10, 10] # Arguments for type. Vary depending on "type". See below for details
      identifiers: # Supports the two patterns below
        - "host_name_a->host_name_b" # Inject on host_name_a, on the interface that links it to host_name_b
        - "host_name_a->host_name_b:interface_name" # Inject on host_name_a, on the interface that links it to host_name_b, named interface_name
      pattern: "burst"  # 'burst', 'degradation', 'random', 'persistent'
      pattern_args: [10, '10'] # modifies the pattern, e.g. when/how often the fault applies to a packet
      target_traffic: # if missing defaults to "any",  
      	protocol: "string" # Defaults to 'any', can be ICMP, IGMP, IP, TCP, UDP, IPv6, IPv6-ICMP, any
      	src_port: 80
      	dst_port: 445
  - node_fault:
      tag: 'string' # optional, for identification - defaults to random uuid
      pre_injection_time: 0 # int in seconds, defaults to 0
      injection_time: 20 # int in seconds, defaults to 20
      post_injection_time: 0 # int in seconds, defaults to 0
      type: "node_fault:custom" # "node_fault:custom", "node_fault:stress_cpu"
      type_args: ["enable-the-fault {} 23",disable-the-fault", 21] # Depends on type, for details see table 
      pattern: "persistent" # persistent, burst, degradation
      pattern_args: [10] # modifies the pattern, e.g. when/how often the fault applies to a packet
      identifiers:
      	- "host_name" # Inject on host_name
      	- "host_name" # Inject on host_name
log:
    interval: 1000 # in ms
    path: "/where/output/file/should/be/stored.json" # string, defaults to faultynet_faultlogfile.json
    commands:
        - tag: "command 1" # optional, for identification - defaults to random uuid
          host: "h1" # on which node to execute. Executes on main OS if missing
          command: "ip a" # str, actual command to run. Supports shell built ins
        - command: "ip a" # this command will execute on the main host, with a random uuid tag
...
```


### Types
For additional details about link_fault `type`s before the semicolon use `man tc-netem`.
#### link_fault:delay
`fault_args[0]` indicates how much an affected packet should be delayed, in ms.
#### link_fault:down
Disables the interface when indicated. Only works with burst and persistent pattern. Requires the interface to be managed by ifconfig,
but this is an implementation detail, and could be modified with relatively little effort
#### link_fault:redirect
Redirects traffic that ingresses at the identified interface, and makes it appear as egress in a different interface.
The interface to redirect to is `fault_args[0]`, and can be an interface name of the host,
or an interface as indicated by a `a->b` pattern.
`fault_args[1]` can macht `mirror` (to copy to packets from the source interface) or `redirect`
(to remove the packets from the source interface). Defaults to `redirect`.

Only works for `persistent` and `burst` patterns, so all traffic of a type must be redirected. A probabilistic fault
would require adding a filter for random packets to an interface, which is likely possible with eBPF, but not trivial.

#### link_fault:bottleneck
Makes the link act as a bottleneck. Implemented as a token bucket filter,
with `fault_args[0]` as rate in kbit, (no default), `fault_args[1]` (default:1600) as burst size, and `fault_args[2]` default(3000) as limit on the number of bytes that can be stored while waiting for tokens to become available

#### node_fault:cpu-stress
Adds work to the CPU on which the indicated node is running. Probably only makes sense when using CPULimitedHost, or otherwise limited hosts.
`fault_args[0]` is the percentage of how much cpu workload the command should use. The percentage relates to how much cpu the
node has access to.

#### node_fault:custom
Executes custom commands, as indicated by `fault_args[0]`. An optional disable command at `fault_args[1]`is executed whenever
the injection period ends, e.g. after each burst, or after each degradation step.
When in the degradation pattern, `fault_args[0]` can contain `{}`. This position is then filled by the degradation
pattern.

### Patterns
#### burst
Fault is activated in bursts. Each burst has a length of `pattern_args[0]` (in ms) The burst period is defined in `pattern_args[1]` (in ms)
which means that between each burst there is `pattern_args[1] - pattern_args[0]` ms downtime between each burst.
#### degradation
Fault starts small, but becomes increasingly bigger as time moves on. The initial value is `pattern_args[2]` (default:0),
the step size is `pattern_args[0]` (default:5). Each step takes `pattern_args[1]`ms (default: 1000),
and the maximum value is `pattern_args[3]` (default:100). For link_faults
the maximal maximum value is 100, since these are percentage based. 

These values overwrite values specified in fault_args.
#### random
Applies the fault with a probability of `100-fault_pattern_args[0]` percent
to the indicated traffic.

Only available for link_faults.
#### persistent
Applies the fault to the given link, with a probability of 100%.


## RandomLinkFaultController
`RandomLinkFaultController` was designed for simple chaos-monkey style tests. The Controller starts by injecting faults on
`start_links` links in the first iteration. Each iteration runs for `injection_time` seconds.
Once this iteration is done, it injects faults on  `start_links + 1` links, until it finally injects faults into `end_links` links.
Afterward the controller terminates, unless in `repeating`mode. In `repeating` mode, the controller starts
from the beginning, e.g. injects `start_links` random links with faults.

`RandomLinkFaultController` supports three modes, defined via `mode`: In `"automatic"` mode, an iteration is started immediately
after the previous iteration finishes. In `manual` mode, each iteration is started only after the 
`RandomLinkFaultControllerStarter.start_next_run()` function is called. This includes the first iteration, which is not immediately
started after calling `go()`. `go()` still needs to be called before any calls to `start_next_run()`, to activate the Controller.
The third mode is `repeating`, which behaves exactly as `manual` mode, with the difference that after the iteration with
`end_links` injection targets it begins anew with `start_links` injection targets.
The fault controller can be prematurely shut down by calling `RandomLinkFaultControllerStarter.stop()`. This will shut the
controller down after the current iteration finishes.

The fault to inject is defined comparable to `ConfigFileFaultController`, but only a single fault type can be defined.
All link-based faults are supported. `RandomLinkFaultController` supports the same `log` structure as `ConfigFileFaultController`.

This is the full reference for the config file:
```yml
---
start_links: 1 # Number of links to inject faults into in first iteration
end_links: 9  # Number of links to inject faults into in last iteration
mode: "manual" # "manual", "automatic", or "repeating" whether the next iteration is triggered automatically, whether it should stop by itself
fault_type: "link_fault:corrupt" # See ConfigFileFaultController 
type_args: [] # See ConfigFileFaultController 
nodes_blacklist: ['h1'] # Links which include this node will be ignored by the FaultController.
pattern: "random" # See ConfigFileFaultController 
pattern_args: ["14"] # See ConfigFileFaultController 
injection_time: 8 # How long each iteration takes
target_traffic: # See ConfigFileFaultController 
  protocol: "any" # See ConfigFileFaultController 
  src_port: 0 # See ConfigFileFaultController 
  dst_port: 0 # See ConfigFileFaultController 
log: # Enable logging, without modifying options
...
```

## MostUsedFaultController 
`MostUsedFaultCOntroller` was designed to illustrate the possibilities of injecting faults based on runtime net behavior.
For each iteration, the fault controller checks which link was the most trafficked since the last iteration of the
controller. For the first iteration this is the traffic since creation of the associated interface.
Once this link is identified it is added to the pool of links that should contain a fault during the next iteration,
so in the nth iteration the n most trafficked links will be faulty.

The fault to inject is defined comparable to `RandomLinkFaultController`. `MostUsedFaultController` supports the same `mode`
attributes as `RandomLinkFaultController`, but it does not support the `start_links` attribute.

All link-based faults are supported. `MostUsedFaultController` supports the same `log` structure as `ConfigFileFaultController`.

This is the full reference for the config file:

```yml
---
end_links: 9  # Number of links to inject faults into in last iteration
mode: "manual" # "manual", "automatic", or "repeating" whether the next iteration is triggered automatically, whether it should stop by itself
fault_type: "link_fault:corrupt" # See ConfigFileFaultController 
type_args: [] # See ConfigFileFaultController 
nodes_blacklist: ['h1'] # Links which include this node will be ignored by the FaultController.
pattern: "random" # See ConfigFileFaultController 
pattern_args: ["14"] # See ConfigFileFaultController 
injection_time: 8 # How long each iteration takes
target_traffic: # See ConfigFileFaultController 
  protocol: "any" # See ConfigFileFaultController 
  src_port: 0 # See ConfigFileFaultController 
  dst_port: 0 # See ConfigFileFaultController 
log: # Enable logging, without modifying options
...
```

## Implementing your own FaultController

See [Documentation](Documentation.md)
