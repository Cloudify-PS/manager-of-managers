#!/usr/bin/env python

import shutil

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs

from cloudify_rest_client.exceptions import CloudifyClientError

from ..common import download_certificate, workdir

from .utils import execute_and_log, use_profile
from .maintenance import restore, backup, UpgradeConfig


def _start_cluster(master_config):
    ctx.logger.info('Master starting cluster [{0}]'.format(master_config))

    use_profile(master_config['public_ip'])

    execute_and_log([
        'cfy', 'cluster', 'start',
        '--cluster-host-ip', master_config['private_ip'],
        '--cluster-node-name', master_config['public_ip']
    ])


def _join_cluster(master_config, slave_config):
    ctx.logger.info('Slave joining the cluster [{0}]'.format(slave_config))

    use_profile(slave_config['public_ip'])

    execute_and_log([
        'cfy', 'cluster', 'join',
        '--cluster-host-ip', slave_config['private_ip'],
        '--cluster-node-name', slave_config['public_ip'],
        master_config['public_ip']
    ])


def _set_cluster_outputs():
    """
    Set up the `managers` runtime prop to only contain the IPs of the managers,
    as the rest of the info should already be present in the CLI profiles

    :return A list of dict with public + private IPs of managers
    """
    managers_config = ctx.instance.runtime_properties['managers']
    managers = []
    for manager in managers_config:
        managers.append({
            'public_ip': manager['manager']['public_ip'],
            'private_ip': manager['manager']['private_ip'],
        })
    ctx.instance.runtime_properties['managers'] = managers
    ctx.instance.update()

    return managers


def _create_cli_profiles():
    managers = ctx.instance.runtime_properties['managers']
    ca_cert = download_certificate(inputs['ca_cert'], deployment_workdir=True)
    for config in managers:
        public_ip = config['manager']['public_ip']
        security = config['manager']['security']

        execute_and_log([
            'cfy', 'profiles', 'use', public_ip,
            '-u', security['admin_username'],
            '-p', security['admin_password'],
            '-t', 'default_tenant',
            '-c', ca_cert, '--ssl'
        ])


@operation
def start_cluster(**_):
    """
    Start the cluster on the master manager profile, and join the cluster
    for each of the slave profiles

    This runs in the `start` operation of the default lifecycle of the
    `cloudify_cluster_config` node
    """
    config = UpgradeConfig()
    config.validate()

    _create_cli_profiles()
    manager_ips = _set_cluster_outputs()

    master, slaves = manager_ips[0], manager_ips[1:]
    _start_cluster(master)

    if config.backup:
        config.snapshot_path = backup(deployment_id=config.old_deployment_id)

    if config.restore:
        restore(config)

    for slave in slaves:
        _join_cluster(master, slave)


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


@operation
def clear_data(**_):
    """
    Remove the current deployment's workdir, as it remaining here can cause
    potential problems down the road if a deployment with the same name
    will be recreated

    This runs in a relationship where CM is the target and CCC the source
    """
    ctx.logger.info(
        'Removing cluster data associated with deployment {0}'.format(
            ctx.deployment.id
        )
    )
    shutil.rmtree(workdir(), ignore_errors=True)
    try:
        # Clear the configuration from the cluster's runtime properties
        ctx.source.instance.runtime_properties.pop('managers', None)
        ctx.source.instance.update()
    except CloudifyClientError as e:
        # Because this node can have several managers attached to it, and
        # because this operation will be called for each one, it is expected
        # that all except one will fail to update the runtime props, but that's
        # normal
        if e.status_code != 409:
            raise
