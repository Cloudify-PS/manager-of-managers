#!/usr/bin/env python

import shutil

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import CommandExecutionException

from ..common import workdir

from .maintenance import restore, backup, UpgradeConfig
from .utils import (
    execute_and_log,
    profile,
    dump_cluster_config,
    load_cluster_config,
    get_current_master
)


def _start_cluster(master_ip):
    ctx.logger.info('Master starting cluster [{0}]'.format(master_ip))

    master_config = load_cluster_config()['managers'][master_ip]
    with profile(master_config['public_ip']):
        try:
            execute_and_log([
                'cfy', 'cluster', 'start',
                '--cluster-host-ip', master_config['private_ip'],
                '--cluster-node-name', master_config['public_ip']
            ])
        except CommandExecutionException as e:
            # This should make the start_cluster operation more idempotent
            if "This manager machine is already part of " \
               "a Cloudify Manager cluster" in e.error:
                return
            raise


def _join_cluster(master_ip, slave_ip):
    ctx.logger.info('Slave `{0}` is joining the cluster'.format(slave_ip))

    slave_config = load_cluster_config()['managers'][slave_ip]

    with profile(master_ip) as master_profile:
        with profile(slave_ip):
            try:
                execute_and_log([
                    'cfy', 'cluster', 'join',
                    '--cluster-host-ip', slave_config['private_ip'],
                    '--cluster-node-name', slave_config['public_ip'],
                    master_profile
                ])
            except CommandExecutionException as e:
                # This is a somewhat expected bug when joining a cluster
                if "Node joined the cluster" in e.error and \
                        "'NoneType' object has " \
                        "no attribute 'append'" in e.error:
                    return
                raise


def _get_small_config(manager_config):
    config = manager_config['manager']
    return {
        'public_ip': config['public_ip'],
        'private_ip': config['private_ip'],
        'admin_username': config['security']['admin_username'],
        'admin_password': config['security']['admin_password']
    }


def _wait_for_manager(master_ip):
    """
    We're waiting until 3 successive successful attempt to connect to the
    manager has been made, to make sure that the manager has finished
    rebooting (in a restore-certificates scenario), etc.
    """
    ctx.logger.info('Waiting for the manager to become responsive...')

    successes = 0
    retries = 0
    retry_delay = 1

    with profile(master_ip):
        while successes < 3:
            retries += 1
            try:
                execute_and_log(['cfy', 'status'], no_log=True)
                successes += 1
            except CommandExecutionException as e:
                ctx.logger.debug('cfy status failed with: {0}'.format(e))
                successes = 0
            sleep(retry_delay)

            if retries == 30:
                raise NonRecoverableError(
                    'Manager on IP {0} is not responsive'.format(master_ip)
                )

    ctx.logger.info('Manager is up and running after restore')


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

    dump_cluster_config({
        'managers': ctx.instance.runtime_properties['managers'],
        'ca_cert': inputs['ca_cert']
    })

    if config.backup:
        config.snapshot_path = backup(
            config.old_deployment_id,
            config.backup_params
        )

    if config.restore:
        restore(config)

    _start_cluster(get_current_master())


def _get_cluster_profile(managers):
    """
    Try to use all of the available profiles, until you find one which has
    the cluster configured on, and return it
    """
    for manager_ip, manager_config in managers.items():
        ctx.logger.info('Trying `{0}`'.format(manager_ip))
        try:
            with profile(manager_ip):
                execute_and_log(['cfy', 'cluster', 'status'], no_log=True)
                execute_and_log(
                    ['cfy', 'cluster', 'update-profile'],
                    no_log=True
                )
                ctx.logger.info('Found cluster profile: '
                                '{0}'.format(manager_ip))

                return manager_ip
        except CommandExecutionException:
            pass


@operation
def update_cluster(**_):
    """
    Find a working cluster profile, through it find the new leader IP, and
    update the cluster config accordingly
    """

    ctx.logger.info('Looking for a cluster profile...')
    cluster_config = load_cluster_config()
    managers = cluster_config['managers']
    cluster_profile = _get_cluster_profile(managers)
    if not cluster_profile:
        return ctx.operation.retry(
            'Could not find a profile with a cluster configured. This '
            'might mean that the whole network is unreachable.'
        )

    with profile(cluster_profile):
        new_master = _get_cluster_master()

    for manager_ip, manager_config in managers.items():
        manager_config['is_master'] = manager_ip == new_master

    dump_cluster_config(cluster_config)
    return new_master


def _get_cluster_master():
    """
    Return the IP of the current cluster leader. This is relevant after a
    failover, when the master has changed
    """
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
    current_master = get_current_master()

    master = current_master == manager_runtime_props['manager_ip']

    if master and not force_join:
        ctx.logger.info(
            'Current node `{0}` is the cluster master, '
            'nothing to do'.format(ctx.target.instance.id)
        )
    else:
        if force_join:
            current_master = update_cluster()

        _join_cluster(current_master, manager_runtime_props['manager_ip'])


@operation
def add_manager_config(**_):
    """
    Pass the manager configuration from a `cloudify_manager` instance
    to the runtime properties of `cloudify_cluster_config`.

    This runs in a relationship where CloudifyManager is the target and
    CloudifyCluster the source
    """
    managers = ctx.source.instance.runtime_properties.get('managers', {})

    full_config = ctx.target.instance.runtime_properties['config']
    config = _get_small_config(full_config)
    manager_ip = config['public_ip']

    ctx.logger.info('Adding new manager config: `{0}`'.format(manager_ip))

    # The first manager to connect to the cluster is the master
    if not managers:
        config['is_master'] = True
        ctx.logger.info('`{0}` is the master node'.format(manager_ip))

    managers[manager_ip] = config
    ctx.source.instance.runtime_properties['managers'] = managers
    ctx.source.instance.update()
    ctx.logger.debug('Full list of managers:\n{0}'.format(managers))

    ctx.target.instance.runtime_properties['manager_ip'] = config['public_ip']
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
    # There's no point in removing the node from the cluster if we're
    # uninstalling the whole deployment, as the VM instances themselves
    # will be torn down
    if ctx.workflow_id == 'uninstall':
        return

    manager_ip = ctx.instance.runtime_properties.get('manager_ip')
    if manager_ip:
        ctx.logger.info('Removing current node from cluster...')

        master_ip = get_current_master()
        # Ignoring the errors, because maybe the node was already removed
        with profile(master_ip):
            execute_and_log([
                'cfy', 'cluster', 'nodes', 'remove', manager_ip
            ], ignore_errors=True)
