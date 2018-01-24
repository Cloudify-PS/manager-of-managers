from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import CommandExecutionException

from .utils import execute_and_log


def _add_tenant_and_visibility(cmd, resource):
    tenant = resource.get('tenant')
    if tenant:
        cmd += ['-t', tenant]

    visibility = resource.get('visibility')
    if visibility:
        cmd += ['-l', visibility]
    return cmd


def _try_running_command(cmd, warning_msg):
    try:
        execute_and_log(cmd)
    except CommandExecutionException as e:
        ctx.logger.warning(warning_msg)
        ctx.logger.warning('Error: {0}'.format(e.error))


def _create_tenants():
    tenants = inputs.get('tenants', [])
    for tenant in tenants:
        cmd = ['cfy', 'tenants', 'create', tenant]
        _try_running_command(cmd, 'Could not create tenant {0}'.format(tenant))


def _upload_plugins():
    plugins = inputs.get('plugins', [])
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
Both `wagon` and `yaml` are required fields
""".format(plugin))
            continue

        cmd = ['cfy', 'plugins', 'upload',
               plugin['wagon'], '-y', plugin['yaml']]

        cmd = _add_tenant_and_visibility(cmd, plugin)
        _try_running_command(
            cmd,
            'Could not upload plugin {0}'.format(plugin['wagon'])
        )


def _create_secrets():
    secrets = inputs.get('secrets', [])
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
`key` is required, as is one (and only one) of `string`/`file`
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
        _try_running_command(
            cmd,
            'Could not create secret {0}'.format(secret['key'])
        )


def _upload_blueprints():
    blueprints = inputs.get('blueprints', [])
    for blueprint in blueprints:
        if 'path' not in blueprint:
            ctx.logger.error("""
Provided blueprint input is incorrect: {0}
Expected format is:
  blueprints:
      - path: <PATH_1>
        id: <ID_1>
        filename: <FILENAME_1>
        tenant: <TENANT_1>
        visibility: <VISIBILITY_1>
`path` is required
            """.format(blueprint))
            continue

        # Create basic command
        cmd = ['cfy', 'blueprints', 'upload', blueprint['path']]

        # Add optional params
        blueprint_id = blueprint.get('id')
        if blueprint_id:
            cmd += ['-b', blueprint_id]

        blueprint_filename = blueprint.get('filename')
        if blueprint_filename:
            cmd += ['-n', blueprint_filename]

        cmd = _add_tenant_and_visibility(cmd, blueprint)
        _try_running_command(
            cmd,
            'Could not upload blueprint {0}'.format(blueprint['path'])
        )


@operation
def add_additional_resources(**_):
    """ Upload/create additional resources on the managers of the cluster """

    _create_tenants()
    _upload_plugins()
    _create_secrets()
    _upload_blueprints()
