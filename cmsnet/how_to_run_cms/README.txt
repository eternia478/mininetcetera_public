
Put runcms wherever you want.

Edit it to change any variables you want (folder locations).

Call it like an executable. Pass it arguments if you need.

Voila! 

Note: This thing is the same as running "sudo cms", so trying to do something
like "sudo cms --topo linear" would instead be "./runcms --topo linear" on the
command line. This automatically makes a config folder at your location or
wherever you specify it to be.

As an example of what to run, the following below will run CMSnet with a new config, VM distribution limit of 5 for each hypervisor, a remote controller, and a Hub and Spoke topology with 6 hypervisor switches. Implied extra parameters include running normal hosts and OVS switches, random distribution mode, CMS messaging level at "all" state and connecting to controller at 127.0.0.1:7790. For this, you type the following in the commandline (assume you run on $HOME):

mininet@mininet:~$ ./runcms --new_config --vm_dist_limit 5 --controller remote --topo hubandspoke,6




