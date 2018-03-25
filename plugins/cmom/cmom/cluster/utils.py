import os
import json
from uuid import uuid4
from contextlib import contextmanager

from cloudify import ctx

from ..common import workdir, DEFAULT_TENANT
from ..common import execute_and_log as _execute_and_log


CLUSTER_CONFIG = '.cluster'


def execute_and_log(cmd,
                    deployment_id=None,
                    no_log=False,
                    ignore_errors=False):
    return _execute_and_log(
        cmd,
        clean_env=True,
        deployment_workdir=workdir(deployment_id),
        no_log=no_log,
        ignore_errors=ignore_errors
    )


@contextmanager
def profile(manager_ip, deployment_id=None):
    deployment_id = deployment_id or ctx.deployment.id
    temp_profile_name = None
    try:
        temp_profile_name = _create_profile(manager_ip, deployment_id)
        yield temp_profile_name
    finally:
        if temp_profile_name:
            execute_and_log(
                ['cfy', 'profiles', 'delete', temp_profile_name],
                ignore_errors=True,
                no_log=True
            )


def _create_profile(manager_ip, deployment_id):
    cluster_config = load_cluster_config(deployment_id)
    config = cluster_config['managers'][manager_ip]
    profile_name = str(uuid4())

    execute_and_log([
        'cfy', 'profiles', 'use', config['public_ip'],
        '-u', config['admin_username'],
        '-p', config['admin_password'],
        '-t', DEFAULT_TENANT,
        '-c', cluster_config['ca_cert'],
        '--ssl',
        '--profile-name', profile_name
    ], deployment_id=deployment_id)
    # If working with clusters, make sure the profile is recognized as
    # a cluster profile
    execute_and_log(
        ['cfy', 'cluster', 'update-profile'],
        no_log=True,
        ignore_errors=True,
        deployment_id=deployment_id
    )
    return profile_name


def load_cluster_config(deployment_id=None):
    deployment_id = deployment_id or ctx.deployment.id
    config_path = os.path.join(workdir(deployment_id), CLUSTER_CONFIG)
    if not os.path.isfile(config_path):
        return {}

    with open(config_path, 'r') as f:
        return json.load(f)


def dump_cluster_config(new_config, deployment_id=None):
    deployment_id = deployment_id or ctx.deployment.id
    config_path = os.path.join(workdir(deployment_id), CLUSTER_CONFIG)
    with open(config_path, 'w') as f:
        json.dump(new_config, f)


def get_current_master(deployment_id=None):
    deployment_id = deployment_id or ctx.deployment.id
    managers = load_cluster_config(deployment_id)['managers']
    for manager_ip, manager_config in managers.items():
        if manager_config.get('is_master'):
            return manager_ip
