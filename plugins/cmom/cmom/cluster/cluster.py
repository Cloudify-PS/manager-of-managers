#!/usr/bin/env python

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs

from ..common import download_certificate

from .utils import execute_and_log, use_profile


def _start_cluster(master_config, cert):
    ctx.logger.info('Master {0} starting cluster'.format(master_config))

    use_profile(master_config, cert)

    execute_and_log([
        'cfy', 'cluster', 'start',
        '--cluster-host-ip', master_config['manager']['private_ip'],
        '--cluster-node-name', master_config['manager']['public_ip']
    ])


def _join_cluster(master_config, slave_config, cert):
    ctx.logger.info('Slave {0} joining the cluster'.format(slave_config))

    use_profile(slave_config, cert)

    execute_and_log([
        'cfy', 'cluster', 'join',
        '--cluster-host-ip', slave_config['manager']['private_ip'],
        '--cluster-node-name', slave_config['manager']['public_ip'],
        master_config['manager']['public_ip']
    ])


def _set_cluster_outputs(master, slaves):
    """ Set up `master` and `slaves` runtime props to be used in outputs """

    ctx.instance.runtime_properties['master'] = master['manager']['public_ip']
    slave_ips = [slave['manager']['public_ip'] for slave in slaves]
    ctx.instance.runtime_properties['slaves'] = slave_ips


@operation
def start_cluster(**_):
    """
    Start the cluster on the master manager profile, and join the cluster
    for each of the slave profiles

    This runs in the `start` operation of the default lifecycle of the
    `cloudify_cluster_config` node
    """
    managers = ctx.instance.runtime_properties['managers']
    master, slaves = managers[0], managers[1:]
    ca_cert = download_certificate(inputs['ca_cert'], deployment_workdir=True)
    _start_cluster(master, ca_cert)

    for slave in slaves:
        _join_cluster(master, slave, ca_cert)

    _set_cluster_outputs(master, slaves)

    # Clear the runtime properties as they may contain sensitive data
    ctx.instance.runtime_properties.pop('managers')
    ctx.instance.update()


@operation
def preconfigure(**_):
    """
    Pass the manager configuration from a `cloudify_manager` instance
    to the runtime properties of `cloudify_cluster_config`.

    This runs in a relationship where CM is the target and CCC the source
    """
    config = ctx.target.instance.runtime_properties['config']
    managers = ctx.source.instance.runtime_properties.get('managers', [])
    managers.append(config)
    ctx.source.instance.runtime_properties['managers'] = managers
    ctx.source.instance.update()
    ctx.logger.info(
        'Added a new manager config: {0}\nAll managers:{1}'.format(
            config, managers)
    )

    # Clear the configuration from the manager's runtime properties
    ctx.target.instance.runtime_properties.pop('config')
    ctx.target.instance.update()
