from cloudify import ctx

from ..common import execute_and_log as _execute_and_log

DEFAULT_TENANT = 'default_tenant'


def execute_and_log(cmd):
    _execute_and_log(cmd, clean_env=True, deployment_workdir=True)


def use_profile(config, cert):
    manager = config['manager']
    security = manager['security']

    execute_and_log([
        'cfy', 'profiles', 'use', manager['public_ip'],
        '-u', security['admin_username'],
        '-p', security['admin_password'],
        '-t', DEFAULT_TENANT,
        '-c', cert, '--ssl'
    ])


def use_master_profile():
    master_profile = ctx.instance.runtime_properties['master']
    execute_and_log(['cfy', 'profiles', 'use', master_profile])
