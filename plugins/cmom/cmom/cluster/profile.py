from uuid import uuid4
from contextlib import contextmanager

from cloudify import ctx
from cloudify.exceptions import (
    CommandExecutionException,
    NonRecoverableError,
    RecoverableError
)

from .utils import execute_and_log
from ..common import DEFAULT_TENANT


def get_current_master(instance=None):
    instance = instance or ctx.instance
    runtime_props = instance.runtime_properties
    managers, ca_cert = get_config(runtime_props)

    cluster_profile = _get_cluster_profile(managers, instance)
    with profile(cluster_profile, instance):
        new_master = _get_cluster_master()

    _update_new_master(new_master, instance, managers)
    return new_master


@contextmanager
def profile(manager_ip=None, instance=None):
    manager_ip = manager_ip or get_current_master(instance)
    instance = instance or ctx.instance
    managers, _ = get_config(instance.runtime_properties)
    temp_profile_name = None
    try:
        temp_profile_name = _create_profile(
            manager_ip,
            instance.runtime_properties
        )
        yield temp_profile_name
    finally:
        if temp_profile_name:
            execute_and_log(
                ['cfy', 'profiles', 'delete', temp_profile_name],
                ignore_errors=True,
                no_log=True
            )


def _update_new_master(new_master, instance, managers):
    master = None
    slaves = []
    for manager, manager_config in managers.items():
        if manager == new_master:
            manager_config['is_master'] = True
            master = manager
        else:
            manager_config['is_master'] = False
            slaves.append(manager)

    runtime_props = instance.runtime_properties

    # Only updating when needed, to avoid conflicts during node-instance update
    if runtime_props.dirty or 'outputs' not in runtime_props:
        runtime_props['managers'] = managers

        runtime_props['outputs'] = {
            'Master': master,
            'Slaves': slaves
        }
        instance.update()


def _get_cluster_master():
    """
    Return the IP of the current cluster leader. This is relevant after a
    failover, when the master has changed
    """
    hosts = execute_and_log(['cfy', 'cluster', 'nodes', 'list'], is_json=True)
    for host in hosts:
        if host['state'] == 'leader':
            leader_ip = host['name']
            ctx.logger.info('The current leader is: {0}'.format(leader_ip))
            return leader_ip

    raise RecoverableError(
        'Could not find a cluster leader in the cluster profile. This might '
        'mean that the cluster is in an undefined state (e.g. midway of '
        'HA failover or right after starting the cluster)'
    )


def get_config(runtime_props):
    """
    Return a tuple with the `managers` config and CA cert path.
    Raise an exception if either of those does not appear in the runtime props
    :param runtime_props: The runtime properties dict from which to get the
    values
    """
    managers = runtime_props.get('managers')
    ca_cert = runtime_props.get('ca_cert')
    missing_value = None
    if not managers:
        missing_value = 'managers'
    elif not ca_cert:
        missing_value = 'ca_cert'
    if missing_value:
        raise NonRecoverableError(
            'Could not load `{0}` config from the runtime '
            'properties. This probably means that the blueprint '
            'was not installed correctly.'.format(missing_value))
    return managers, ca_cert


def _create_profile(manager_ip, runtime_props):
    managers, ca_cert = get_config(runtime_props)
    config = managers[manager_ip]
    profile_name = str(uuid4())

    execute_and_log([
        'cfy', 'profiles', 'use', config['public_ip'],
        '-u', config['admin_username'],
        '-p', config['admin_password'],
        '-t', DEFAULT_TENANT,
        '-c', ca_cert,
        '--ssl',
        '--profile-name', profile_name
    ], no_log=True)
    return profile_name


def _get_cluster_profile(managers, instance=None):
    """
    Try to use all of the available profiles, until you find one which has
    the cluster configured on, and return it
    """
    for manager_ip, manager_config in managers.items():
        ctx.logger.info('Trying: {0}'.format(manager_ip))
        try:
            with profile(manager_ip, instance=instance):
                execute_and_log(
                    ['cfy', 'cluster', 'status'],
                    no_log=True
                )
                ctx.logger.info('Found cluster profile: '
                                '{0}'.format(manager_ip))

                return manager_ip
        except CommandExecutionException:
            pass

    raise RecoverableError(
        'Could not find a profile with a cluster configured. This '
        'might mean that the whole network is unreachable.'
    )
