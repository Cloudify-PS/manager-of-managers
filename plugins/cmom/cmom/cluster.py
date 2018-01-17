#!/usr/bin/env python

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs

from .common import execute_and_log, download_certificate


def _use_profile(config, cert):
    manager = config['manager']
    security = manager['security']

    execute_and_log([
        'cfy', 'profiles', 'use', manager['public_ip'],
        '-u', security['admin_username'],
        '-p', security['admin_password'],
        '-t', 'default_tenant',
        '-c', cert, '--ssl'
    ])


def _start_cluster(master_config, cert):
    ctx.logger.info('Master {0} starting cluster'.format(master_config))

    _use_profile(master_config, cert)

    execute_and_log([
        'cfy', 'cluster', 'start',
        '--cluster-host-ip', master_config['manager']['private_ip'],
        '--cluster-node-name', master_config['manager']['public_ip']
    ], clean_env=True)


def _join_cluster(master_config, slave_config, cert):
    ctx.logger.info('Slave {0} joining the cluster'.format(slave_config))

    _use_profile(slave_config, cert)

    execute_and_log([
        'cfy', 'cluster', 'join',
        '--cluster-host-ip', slave_config['manager']['private_ip'],
        '--cluster-node-name', slave_config['manager']['public_ip'],
        master_config['manager']['public_ip']
    ], clean_env=True)


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
    ca_cert = download_certificate(inputs['ca_cert'])
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


def _add_tenant_and_visibility(cmd, resource):
    tenant = resource.get('tenant')
    if tenant:
        cmd += ['-t', tenant]

    visibility = resource.get('visibility')
    if visibility:
        cmd += ['-l', visibility]
    return cmd


def _upload_plugins(plugins):
    for plugin in plugins:
        if 'wagon' not in plugin or 'yaml' not in plugin:
            ctx.logger.error("""
Provided plugin input is incorrect: {0}
Expected format is:
  plugins:
    - wagon: <WAGON_1>
      yaml: <YAML_1>
      tenant: <TENANT_1>
    - wagon: <WAGON_2>
      yaml: <YAML_2>
      visibility: <VIS_2>
Both wagon and yaml are required fields
""".format(plugin))
            continue

        cmd = ['cfy', 'plugins', 'upload',
               plugin['wagon'], '-y', plugin['yaml']]

        cmd = _add_tenant_and_visibility(cmd, plugin)
        execute_and_log(cmd, clean_env=True)


def _create_secrets(secrets):
    for secret in secrets:
        if ('key' not in secret) or \
                ('string' not in secret and
                 'file' not in secret) or \
                ('string' in secret and 'file' in secret):
            ctx.logger.error("""
Provided secret input is incorrect: {0}
Expected format is:
  secrets:
    - key: <KEY_1>
      string: <STRING_1>
    - key: <KEY_2>
      file: <FILE_2>
      tenant: <TENANT>
key is required, as is one (and only one) of string/file
""".format(secret))
            continue

        # Create basic command
        cmd = ['cfy', 'secrets', 'create', secret['key']]

        # Add string or file as the value of the secret
        string = secret.get('string')
        if string:
            cmd += ['-s', string]
        else:
            cmd += ['-f', secret['file']]

        cmd = _add_tenant_and_visibility(cmd, secret)
        execute_and_log(cmd, clean_env=True)


@operation
def add_additional_resources(**_):
    """ Upload/create additional resources on the managers of the cluster """

    master_profile = ctx.instance.runtime_properties['master']
    execute_and_log(['cfy', 'profiles', 'use', master_profile])
    _upload_plugins(inputs['plugins'])
    _create_secrets(inputs['secrets'])
