#!/usr/bin/env python

import shutil

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import CommandExecutionException, NonRecoverableError

from ..common import workdir, DEFAULT_TENANT

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


def _join_cluster(master_ip, slave_config):
    ctx.logger.info('Slave joining the cluster [{0}]'.format(slave_config))

    use_profile(slave_config['public_ip'])

    try:
        execute_and_log([
            'cfy', 'cluster', 'join',
            '--cluster-host-ip', slave_config['private_ip'],
            '--cluster-node-name', slave_config['public_ip'],
            master_ip
        ])
    except CommandExecutionException as e:
        # This is a somewhat expected bug when joining a cluster
        if "Node joined the cluster" in e.error and \
                "'NoneType' object has no attribute 'append'" in e.error:
            return
        raise


def _get_small_config(manager_config):
    return {
        'public_ip': manager_config['manager']['public_ip'],
        'private_ip': manager_config['manager']['private_ip']
    }


def _set_cluster_runtime_props():
    """
    Set up the `managers` runtime prop to only contain the IPs of the managers,
    as the rest of the info should already be present in the CLI profiles

    :return A list of dict with public + private IPs of managers
    """
    managers_config = ctx.instance.runtime_properties['managers']
    managers = [_get_small_config(manager) for manager in managers_config]

    ctx.instance.runtime_properties['managers'] = managers
    ctx.instance.update()

    return managers


def _create_cli_profiles():
    managers = ctx.instance.runtime_properties['managers']
    for config in managers:
        public_ip = config['manager']['public_ip']
        security = config['manager']['security']

        execute_and_log([
            'cfy', 'profiles', 'use', public_ip,
            '-u', security['admin_username'],
            '-p', security['admin_password'],
            '-t', DEFAULT_TENANT,
            '-c', inputs['ca_cert'], '--ssl'
        ])


@operation
def start_cluster(**_):
    """
    This operation performs 3 main functions:
    1. Create the CLI profiles for each of the Tier 1 managers
    2. Start the cluster on the master node (the first manager in the list)
    3. Perform upgrade from a previous deployment, if relevant

    This runs in the `start` operation of the default lifecycle of the
    `cloudify_cluster_config` node
    """
    config = UpgradeConfig()
    config.validate()

    _create_cli_profiles()
    managers = _set_cluster_runtime_props()

    # We take the *first* manager to be the master
    _start_cluster(master_config=managers[0])

    if config.backup:
        config.snapshot_path = backup(deployment_id=config.old_deployment_id)

    if config.restore:
        restore(config)


def _get_all_profiles():
    """ Return a list of all the available profiles """

    output = execute_and_log(['cfy', 'profiles', 'list'], no_log=True)
    profiles = []
    for line in output.split('\n'):
        if '443' in line and '22' in line:
            profiles.append(line.split('|')[1].strip().replace('*', ''))
    return profiles


@operation
def update_cluster_profile(**_):
    """
    Try to use all of the available profiles, until you find one which has
    the cluster configured on, and use it
    """
    ctx.logger.info('Looking for a cluster profile...')
    profiles = _get_all_profiles()

    for profile in profiles:
        ctx.logger.info('Trying `{0}`'.format(profile))
        use_profile(profile)
        try:
            execute_and_log(['cfy', 'cluster', 'status'], no_log=True)
            execute_and_log(['cfy', 'cluster', 'update-profile'], no_log=True)
            ctx.logger.info('Found cluster profile: {0}'.format(profile))
            return profile
        except CommandExecutionException:
            pass

    return ctx.operation.retry(
        'Could not find a profile with a cluster configured. This '
        'might mean that the whole network is unreachable.'
    )


def _get_current_leader_ip():
    """
    Return the IP of the current cluster leader. This is relevant after a
    failover, when the master has changed
    """
    update_cluster_profile()
    output = execute_and_log(['cfy', 'cluster', 'nodes', 'list'], no_log=True)
    for line in output.split('\n'):
        if 'leader' in line:
            leader_ip = line.split('|')[2].strip()
            ctx.logger.info('The new leader is: `{0}`'.format(leader_ip))
            return leader_ip


@operation
def join_cluster(force_join=False, **_):
    """
    Join the cluster created in the `start_cluster` if you're a slave.
    If you're the master, do nothing

    This runs in a relationship where CloudifyManager is the target and
    CloudifyCluster the source
    """
    manager_runtime_props = ctx.target.instance.runtime_properties
    if manager_runtime_props['is_master'] and not force_join:
        ctx.logger.info(
            'Current node `{0}` is the cluster master, '
            'nothing to do'.format(ctx.target.instance.id)
        )
    else:
        config = manager_runtime_props['small_config']
        if force_join:
            master_ip = _get_current_leader_ip()
        else:
            master_config = manager_runtime_props['master_config']
            master_ip = master_config['public_ip']

        _join_cluster(master_ip, slave_config=config)

        if force_join:
            # Need to switch to the only proper profile
            use_profile(master_ip)


@operation
def add_manager_config(**_):
    """
    Pass the manager configuration from a `cloudify_manager` instance
    to the runtime properties of `cloudify_cluster_config`.

    This runs in a relationship where CloudifyManager is the target and
    CloudifyCluster the source
    """
    config = ctx.target.instance.runtime_properties['config']
    managers = ctx.source.instance.runtime_properties.get('managers', [])

    # The first manager to connect to the cluster is the master
    if managers:
        master_config = _get_small_config(managers[0])
        is_master = False
    else:
        master_config = {}
        is_master = True

    managers.append(config)
    ctx.source.instance.runtime_properties['managers'] = managers
    ctx.source.instance.update()
    ctx.logger.info(
        'Added a new manager config: {0}\nAll managers:{1}'.format(
            config, managers)
    )

    # Clear the full configuration from the manager's runtime properties,
    # but keep a limited one
    small_config = _get_small_config(config)
    ctx.target.instance.runtime_properties['small_config'] = small_config

    # Those values will be later used to join the cluster, if the current
    # node is a slave
    ctx.target.instance.runtime_properties['is_master'] = is_master
    ctx.target.instance.runtime_properties['master_config'] = master_config
    ctx.target.instance.update()


@operation
def clear_data(**_):
    """
    Remove the current deployment's workdir, as it remaining here can cause
    potential problems down the road if a deployment with the same name
    will be recreated
    """
    ctx.logger.info(
        'Removing cluster data associated with deployment {0}'.format(
            ctx.deployment.id
        )
    )
    shutil.rmtree(workdir(), ignore_errors=True)

    # Clear the configuration from the cluster's runtime properties
    ctx.instance.runtime_properties.pop('managers', None)
    ctx.instance.update()


@operation
def remove_from_cluster(**_):
    config = ctx.instance.runtime_properties.get('small_config')
    if config:
        ctx.logger.info('Removing current node from cluster...')

        # Ignoring the errors, because maybe the node was already removed
        execute_and_log([
            'cfy', 'cluster', 'nodes', 'remove', config['private_ip']
        ], ignore_errors=True)
