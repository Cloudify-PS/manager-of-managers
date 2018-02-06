# Cloudify Manager of Managers

The blueprint in this repo allows managing Cloudify Manager instances
(Tier 1 managers) using a master Cloudify Manager (Tier 2 manager).

## Using the blueprint

In order to use the blueprint the following prerequisites are
necessary:

1. A working 4.3 (RC or GA) Cloudify Manager (this will be the Tier 2
manager). You need to be connected to this manager (`cfy profiles use`).
1. An SSH key linked to a cloud keypair (this will be used to SSH
into the Tier 1 VMs).
1. A clone of this repo.

Optional:
1. A `pip` virtualenv with `wagon` installed in it. This is only
necessary if you're planning on building the CMoM plugin yourself
(more on the plugin below).

### Uploading plugins

Two plugins are required to use the blueprint - an IaaS plugin
(currently only OpenStack is supported) and the Cloudify Manager of
Managers (or CMoM for short) plugin (which is a part of this repo).

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


### Tier 2 manager files

a few files need to be present on the Tier 2 manager.
These are:

1. The private SSH key connected to the cloud keypair. Its input is
is `ssh_private_key_path`. This file needs to be accessible by
Cloudify's user (`cfyuser`), so it is advised to place this file
under `/etc/cloudify`. This is not mandatory, and any location will do,
as long as it is accessible by `cfyuser`.

1. The install RPM (its world-accessible URL will be provided
separately). Its input is `install_rpm_path` (it's also possible to
set this path in a secret of the same name - `install_rpm_path`).
This file needs to reside inside the Tier 2 manager's fileserver
directory - `/opt/manager/resources`, and the input fill be its path
relative to this base dir. So if e.g. the full path is:

```
/opt/manager/resources/extras/cloudify-manager-install-4.3.rpm
```

the `install_rpm_path` input's value will be
`extras/cloudify-manager-install-4.3.rpm`.


### Extra files in the blueprint folder

In order to be used both by the Tier 1 and Tier 2 managers, the CA
certificate and key need to be located in the blueprint folder before
the blueprint is uploaded to the Tier 2 manager. This is in order to
utilize the built-in `ctx.download_resource` functionality.
The respective inputs for the cert and the key are
`ca_cert` and `ca_key` (both could be set with secrets with the same
names). So if inside the `manager-of-managers` folder, create a new
folder `ssl` and put the CA cert and key inside it, and then set,
either via secrets or inputs this relative path. e.g.

```
inputs:
  ca_cert: ssl/ca_certificate.pem
  ca_key: ssl/ca_key.pem
```


### Installing the blueprint

Now all that is left is to edit the inputs file (you can copy the
[`sample_inputs`](sample_inputs.yaml) file and edit it - see the
inputs section below for a full explanation), and run:

```
cfy install blueprint.yaml -b <BLUEPRINT_NAME> -d <DEPLOYMENT_ID> -i <INPUTS_FILE>
```

### Getting the outputs

To get the outputs of the installation (currently the IPs of the master
and slaves Cloudify Managers) run:

```
cfy deployments outputs <DEPLOYMENT_ID>
```


## Blueprint inputs and secrets

Below is a list with explanations for all the inputs/secrets necessary
for the blueprint to function. Much of this is mirrored in the
[`sample_inputs`](sample_inputs.yaml) file.

### Secrets

Several global values can be set via the secrets mechanism.
If those are set with `global` availability, they could be used by
any number of deployments. All of those secrets have parallel
input values, and can be used as regular inputs as well.

These are:

1. The above mentioned `install_rpm_path`.

1. The also above mentioned `ca_cert` and `ca_key`.

1. The admin password to be used by the Tier 1 managers -
`manager_admin_password`.

### OpenStack inputs

Currently only Openstack is supported as the platform for this
blueprint. Implementations for other IaaSes will follow.

#### Common OS inputs

* `os_image` - OpenStack image name or ID to use for the new server
* `os_flavor` - OpenStack flavor name or ID to use for the new server
* `os_network` - OpenStack network name or ID the new server will be connected to
* `os_keypair` - OpenStack key pair name or ID of the key to associate with the new server
* `os_security_group` - The name or ID of the OpenStack security group the new server will connect to
* `os_server_group_policy` - The policy to use for the server group
* `os_username` - Username to authenticate to OpenStack with
* `os_password` - OpenStack password
* `os_tenant` - Name of OpenStack tenant to operate on
* `os_auth_url` - Authentication URL for KeyStone

#### Defining the manager's public IP

There are currently 2 supported ways to assign the manager's public IP.
To toggle between the different modes you'll need to comment out one of
the lines in [`openstack_infra`](include/openstack/infra.yaml) -
only one of [`openstack_private_ip.yaml`](include/openstack/private_ip.yaml)
or [`openstack_floating_ip.yaml`](include/openstack/floating_ip.yaml)
needs to be imported.

The two modes are:
1. Using the FloatingIP mechanism. This requires providing a special
input:
* `os_floating_network` - The name or ID of the OpenStack network to use
for allocating floating IPs

2. Using only an internal network, without a floating IP. This requires
creating a new port, which is assumed to be connected to an existing
subnet; thus a special input is needed:
* `os_subnet` - OpenStack name or ID of the subnet that's
connected to the network that is to be used by the manager

#### KeyStone v3 inputs

The following inputs are only relevant in KeyStone v3 environments:
* `os_region` - OpenStack region to use
* `os_project` - Name of OpenStack project (tenant) to operate on
* `os_project_domain` - The name of the OpenStack project domain to use
* `os_user_domain` - The name of the OpenStack user domain to use

#### Block storage devices

When working with block storage devices (e.g. Cinder volumes) there
is a special input that needs to be provided:
* `os_device_mapping` - this is a list of volumes as defined by the API
[here](https://docs.openstack.org/nova/pike/user/block-device-mapping.html).
An example input would look like this:
```
os_device_mapping:
  - boot_index: "0"
    uuid: "41a1f177-1fb0-4708-a5f1-64f4c88dfec5"
    volume_size: 30
    source_type: image
    destination_type: volume
    delete_on_termination: true
```
Where `uuid` is the UUID of the OS image that should be used when
creating the volume.

> Note: When using the `os_device_mapping` input, the `os_image` input
> should be left empty.

Other potential inputs (for example, with subnet names, CIDRs etc.)
might be added later.

### General inputs

These are general inputs necessary for the blueprint:

* `install_rpm_path` - as specified above (can be set via a secret)
* `ca_cert` - as specified above (can be set via a secret)
* `ca_key` - as specified above (can be set via a secret)
* `manager_admin_password` - as specified above (can be set via a secret)
* `manager_admin_username` - the admin username for the Tier 1 managers
(default: admin)
* `num_of_instances` - the number of Tier 1 instances to be created
(default: 2). This affects the size of the HA cluster.
* `ssh_user` - User name used when SSH-ing into the Tier 1 manager VMs
* `ssh_private_key_path` - as described above.
* `additional_config` - An arbitrary dictionary which should mirror the
structure of [config.yaml](https://github.com/cloudify-cosmo/cloudify-manager-install/blob/master/config.yaml)
It will be merged (while taking precedence) with the config as described
in the cloudify.nodes.CloudifyTier1Manager type in the plugin.yaml file.
Whenever possible the inputs in the blueprint.yaml file should be used.
For example:

```
inputs:
  additional_config:
    sanity:
      skip_sanity: true
    restservice:
      log:
        level: DEBUG
    mgmtworker:
      log_level: DEBUG
```

### LDAP inputs

Inside [`ldap_inputs.yaml`](include/ldap_inputs.yaml) is a defined
datatype for LDAP inputs. It is useful to utilize it for convenience.

All the following inputs need to reside under `ldap_config` in
the inputs file:

* `server` - The LDAP server address to authenticate against
* `username` - LDAP admin username. This user needs to be able to make requests
          against the LDAP server
* `password` - LDAP admin password
* `domain` - The LDAP domain to be used by the server
* `dn_extra` - Extra LDAP DN options. (separated by the `;` sign. e.g. a=1;b=2).
Useful, for example, when it is necessary to provide an organization ID.
* `is_active_directory` - Specify whether the LDAP server used for authentication is an
          Active Directory server.

 The actual input should look like this:

 ```
 inputs:
   ldap_config:
     server: SERVER
     username: USERNAME
     password: PASSWORD
     ...
 ```


### Additional inputs


> **NOTE**: When mentioning local paths in the context of the inputs
below, the paths in question are paths on the *Tier 2* manager.
So if it is desirable to upload files from a local location, these
files need to be present on the Tier 2 manager in advance.
Otherwise, URLs may be used freely.

It is possible to create/upload certain types of resources on the
Tier 1 cluster after installation. Those are:

1. `tenants` - a list of tenants to create after the cluster is
installed. The format is:
```
inputs:
  tenants:
    - <TENANT_NAME_1>
    - <TENANT_NAME_2>
```

2. `plugins` - a list of plugins to upload after the cluster is
installed. The format is:
```
inputs:
  plugins:
    - wagon: <WAGON_1>
      yaml: <YAML_1>
      tenant: <TENANT_1>
    - wagon: <WAGON_2>
      yaml: <YAML_2>
      visibility: <VIS_2>
```

Where:
* `WAGON` is either a URL of a Cloudify Plugin (e.g.
[openstack.wgn](http://repository.cloudifysource.org/cloudify/wagons/cloudify-openstack-plugin/2.0.1/cloudify_openstack_plugin-2.0.1-py27-none-linux_x86_64-centos-Core.wgn)),
  or a local (i.e. on the Tier 2 manager) path to such wagon (required)
* `YAML` is the plugin's plugin.yaml file - again, either URL or local
  path (required)
* `TENANT` is the tenant to which the plugin will be uploaded (the tenant
  needs to already exist on the manager - use the above `tenants` input
  to create any tenants in advance). (Optional - default is
  default_tenant)
* `VISIBILITY` defines who can see the plugin - must be one of
  \[private, tenant, global\] (Optional - default is tenant).
Both WAGON and YAML are *required* fields

3. `secrets` - a list of secrets to create after the cluster is
installed. The format is:

```
inputs:
  secrets:
    - key: <KEY_1>
      string: <STRING_1>
      file: <FILE_1>
      visibility: <VISIBILITY_1>
```

Where:
* `KEY` is the name of the secret which will then be used by other
  blueprints by the intrinsic `get_secret` function (required)
* `STRING` is the string value of the secret \[mutually exclusive with FILE\]
* `FILE` is a local path to a file which contents should be used as the
  secrets value \[mutually exclusive with VALUE\]
* `VISIBILITY` defines who can see the secret - must be one of
  \[private, tenant, global\] (Optional - default is tenant).
`KEY` is a *required* field, as well as one (and only one) of STRING or FILE.

4. `blueprints` - a list of blueprints to upload after the cluster is
installed. The format is:

```
inputs:
  blueprints:
    - path: <PATH_1>
      id: <ID_1>
      filename: <FILENAME_1>
      tenant: <TENANT_1>
      visibility: <VISIBILITY_1>
```

Where:
* `PATH` can be either a local blueprint yaml file, a blueprint
  archive or a url to a blueprint archive (required)
* `ID` is the unique identifier for the blueprint (if not specified, the
  name of the blueprint folder/archive will be used
* `FILENAME` is the name of an archive's main blueprint file. Only
  relevant when uploading an archive
* `TENANT` is the tenant to which the blueprint will be uploaded (the tenant
  needs to already exist on the manager - use the above `tenants` input
  to create any tenants in advance). (Optional - default is
  default_tenant)
* `VISIBILITY` defines who can see the secret - must be one of
  \[private, tenant, global\] (Optional - default is tenant).

### Upgrade inputs

The following inputs are only relevant when upgrading a previous
deployment. Use them only when installing a new deployment to which
you wish to transfer data/agents from an old deployment.

* `restore` - Should the newly installed Cloudify Manager be restored
from a previous installation. Must be used in conjunction with some of
the other inputs below. See [`plugin.yaml`](plugins/cmom/plugin.yaml)
for more details (default: false)
* `backup` - Only relevant if `restore` is set to true!
Must be used in conjunction with `old_deployment_id` (and optionally
with `snapshot_id`).  If set to true, a snapshot will be created on the old
deployment (based on `old_deployment_id` and, if passed, on
`snapshot_id`), and it will be used in the restore workflow (default: false)
* `snapshot_path` - A local (relative to the Tier 2 manager) path to a snapshot that should be
used. Mutually exclusive with `old_deployment_id` and `snapshot_id`
(default: '')
* `old_deployment_id` - The ID of the previous deployment which was used to control the Tier 1
managers. If the `backup` workflow was used with default values there will
be a special folder with all the snapshots from the Tier 1 managers. If the
`backup` input is set to `false` `snapshot_id` must be provided as well
(default: '')
* `snapshot_id` - The ID of the snapshot to use. This is only relevant if `old_deployment_id`
is provided as well (default: '')
* `transfer_agents` - If set to `true`, an `install_new_agents` command will be executed after
the restore is complete (default: true)