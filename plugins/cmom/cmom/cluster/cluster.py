#!/usr/bin/env python

import shutil
from time import sleep

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import (
    CommandExecutionException,
    NonRecoverableError,
    RecoverableError
)

from ..common import workdir

from .utils import execute_and_log
from .maintenance import restore, UpgradeConfig
from .profile import profile, get_current_master, get_config


def _get_master_config():
    managers, _ = get_config(ctx.instance.runtime_properties)
    for manager_ip, manager_config in managers.items():
        if manager_config.get('is_master'):
            return manager_ip, manager_config

    raise NonRecoverableError(
        "Could not find a node that's configured to be the master. "
        "This means that something went wrong during the installation. "
        "Current config is: {0}".format(managers)
    )


def _start_cluster():
    master_ip, master_config = _get_master_config()

    ctx.logger.info('Starting cluster on master: {0}'.format(master_ip))
    with profile(master_ip):
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


def _remove_node_before_join(slave_ip):
    ctx.logger.debug(
        'Trying to remove the slave from the cluster, in case this '
        'is a healing workflow'
    )
    # Ignoring the errors, because maybe the node was already removed
    execute_and_log([
        'cfy', 'cluster', 'nodes', 'remove', slave_ip
    ], no_log=True, ignore_errors=True)


def _update_cluster_profile():
    ctx.logger.info('Updating cluster profile...')
    execute_and_log(['cfy', 'cluster', 'update-profile'])


def _run_join_command(master_profile, slave_config):
    execute_and_log([
        'cfy', 'cluster', 'join',
        '--cluster-host-ip', slave_config['private_ip'],
        '--cluster-node-name', slave_config['public_ip'],
        master_profile
    ])


def _join_cluster(master_ip, slave_config):
    slave_ip = slave_config['public_ip']
    ctx.logger.info('Slave {0} is joining the cluster'.format(slave_ip))

    with profile(master_ip, ctx.source.instance) as master_profile:
        _remove_node_before_join(slave_ip)
        _update_cluster_profile()

        with profile(slave_ip, ctx.source.instance):
            try:
                _run_join_command(master_profile, slave_config)
            except CommandExecutionException as e:
                # This is a somewhat expected bug when joining a cluster
                if "Node joined the cluster" in e.error and \
                        "'NoneType' object has " \
                        "no attribute 'append'" in e.error:
                    return
                ctx.logger.debug(
                    'Caught the following error during join: {0}'.format(e)
                )
                return ctx.operation.retry(
                    'Could not join the cluster. Often this means that '
                    'the cluster is not yet ready. Retrying...',
                    retry_after=5
                )


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

    while successes < 3:
        retries += 1
        try:
            with profile(master_ip):
                execute_and_log(['cfy', 'status'], no_log=True)
                successes += 1
        except CommandExecutionException as e:
            ctx.logger.debug('cfy status/use failed with: {0}'.format(e))
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
    `cloudify_cluster` node
    """
    config = UpgradeConfig()
    config.validate()

    ctx.instance.runtime_properties['ca_cert'] = inputs['ca_cert']
    ctx.instance.update()

    if config.restore:
        master_ip, _ = _get_master_config()
        restore(master_ip, config)
        _wait_for_manager(master_ip)

    _start_cluster()


@operation
def join_cluster(**_):
    """
    Join the cluster created in the `start_cluster` if you're a slave.
    If you're the master, do nothing

    This runs in a relationship where CloudifyManager is the target and
    CloudifyCluster the source
    """
    manager_runtime_props = ctx.target.instance.runtime_properties
    manager_ip = manager_runtime_props['manager_ip']

    try:
        current_master = get_current_master(ctx.source.instance)
    except RecoverableError as e:
        if 'Could not find a cluster leader in the cluster profile' in str(e):
            ctx.logger.debug(
                'Caught error during get_current_master: {0}'.format(e)
            )
            return ctx.operation.retry(
                'Could not join the cluster. Often this means that '
                'the cluster is not yet ready. Retrying...',
                retry_after=5
            )
        raise

    is_master = current_master == manager_ip

    if is_master:
        ctx.logger.info(
            'Current node {0} is the cluster master, '
            'nothing to do'.format(ctx.target.instance.id)
        )
    else:
        managers, _ = get_config(ctx.source.instance.runtime_properties)
        manager_config = managers[manager_ip]

        return _join_cluster(current_master, manager_config)


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
        ctx.logger.info('{0} is the master node'.format(manager_ip))
    else:
        config['is_master'] = False

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
