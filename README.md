# Cloudify Manager of Managers

The blueprint in this repo allows managing Cloudify Manager instances
(tier 1 managers) using a master Cloudify Manager (tier 2 manager).

## Using the blueprint

In order to use the blueprint the following prerequisites are
necessary:

1. A working 4.3 (RC or GA) Cloudify Manager (this will be the tier 2
manager). You need to be connected to this manager (`cfy profiles use`).
1. An SSH key linked to a cloud keypair (this will be used to SSH
into the tier 2 VMs).
1. A clone of this repo.
1. A `pip` virtualenv with `wagon` installed in it.

### Uploading plugins

Two plugins are required to use the blueprint - an IaaS plugin
(currently only OpenStack is supported) and the Cloudify Manager of
Managers (or CMom for short) plugin (which is a part of this repo).

First, upload the IaaS plugin to the manager. e.g. run:

```
cfy plugins upload <WAGON_URL> -y <YAML_URL>
```

[link_to_wagon](https://github.com/cloudify-cosmo/cloudify-openstack-plugin/releases/download/2.5.2/cloudify_openstack_plugin-2.5.2-py27-none-linux_x86_64-centos-Core.wgn)
[link to yaml](https://github.com/cloudify-cosmo/cloudify-openstack-plugin/releases/download/2.5.2/plugin.yaml)

Second, you'll need to create a Wagon from the CMoM plugin. Run (this
is assuming you're inside the `manager-of-managers` folder):
```
wagon create -f plugins/cmom -o <CMOM_WAGON_OUTPUT>
```

Now upload this plugin as well:

```
cfy plugins upload <CMOM_WAGON_OUTPUT> -y plugins/cmom/plugin.yaml
```


### Installing the blueprint

Now all that is left is to edit the inputs file (you can copy the
[`sample_inputs`](sample_input.yaml) file and edit it), and run:

```
cfy install blueprint.yaml -b <BLUEPRINT_NAME> -d <DEPLOYMENT_ID> -i <INPUTS_FILE>
```

### Getting the outputs

To get the outputs of the installation (currently the IPs of the master
and slaves Cloudify Managers) run:

```
cfy deployments outputs <DEPLOYMENT_ID>
```