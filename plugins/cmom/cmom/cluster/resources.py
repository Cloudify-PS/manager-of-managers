import json

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import CommandExecutionException

from ..common import DEFAULT_TENANT
from .utils import execute_and_log
from .profile import profile, get_current_master


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


def _switch_tenant(tenant):
    execute_and_log(['cfy', 'profiles', 'set', '-t', tenant])


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

        # `visibility` and `--update-if-exists` are mutually exclusive
        if not secret.get('visibility'):
            cmd.append('--update-if-exists')

        # Add string or file as the value of the secret
        string = secret.get('string')
        if string:
            cmd += ['-s', string]
        else:
            cmd += ['-f', secret['file']]

        # The secrets' CLI command doesn't have a `-t` flag, so we handle it
        # separately here by actually switching to the tenant
        tenant = secret.pop('tenant', None)
        try:
            if tenant:
                _switch_tenant(tenant)

            cmd = _add_tenant_and_visibility(cmd, secret)
            _try_running_command(
                cmd,
                'Could not create secret {0}'.format(secret['key'])
            )
        finally:
            if tenant:
                _switch_tenant(DEFAULT_TENANT)


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


def _create_deployments():
    deployments = inputs.get('deployments', [])
    for deployment in deployments:
        if ('blueprint_id' not in deployment) or \
                ('inputs' in deployment and
                 not isinstance(deployment['inputs'], (dict, basestring))):
            ctx.logger.error("""
Provided deployment input is incorrect: {0}
Expected format is:
  deployments:
      - deployment_id: <DEP_ID_1>
        blueprint_id: <BLU_ID_1>
        inputs: <INPUTS_1>
        tenant: <TENANT_1>
        visibility: <VISIBILITY_1>
`blueprint_id` is required, and inputs can only be dict or string
                """.format(deployment))
            continue

        # Create basic command
        blueprint_id = deployment['blueprint_id']
        cmd = ['cfy', 'deployments', 'create', '-b', blueprint_id]

        # Add optional params
        deployment_id = deployment.get('deployment_id', blueprint_id)
        cmd += [deployment_id]

        dep_inputs = deployment.get('inputs')
        if dep_inputs:
            # If we have a dict, we'll pass it as a JSON string to the command.
            # Otherwise, it's a string with the value of a YAML file path
            if isinstance(dep_inputs, dict):
                dep_inputs = json.dumps(dep_inputs)
            cmd += ['-i', dep_inputs]

        cmd = _add_tenant_and_visibility(cmd, deployment)
        _try_running_command(
            cmd,
            'Could not create deployment {0} from '
            'blueprint {1}'.format(deployment_id, blueprint_id)
        )


def _execute_workflow():
    cmd = ['cfy', 'executions', 'start', '-d', inputs['deployment_id'],
           inputs['workflow_id'], '--timeout', str(inputs['timeout'])]

    if inputs['allow_custom_parameters']:
        cmd += ['--allow-custom-parameters']

    if inputs['tenant_name']:
        cmd += ['-t', inputs['tenant_name']]

    params = inputs['parameters']
    if params:
        if isinstance(params, dict):
            params = json.dumps(params)
        cmd += ['-p', params]

    if inputs['queue']:
        cmd += ['--queue']

    if inputs['force']:
        cmd += ['--force']

    _try_running_command(
        cmd,
        'Could not execute workflow {0} on deployment {1} '
        'with params: {2}'.format(
            inputs['workflow_id'],
            inputs['deployment_id'],
            params
        )
    )


@operation
def add_additional_resources(**_):
    """ Upload/create additional resources on the managers of the cluster """

    with profile(get_current_master()):
        _create_tenants()
        _upload_plugins()
        _create_secrets()
        _upload_blueprints()
        _create_deployments()


@operation
def upload_blueprints(**_):
    with profile(get_current_master()):
        _upload_blueprints()


@operation
def upload_plugins(**_):
    with profile(get_current_master()):
        _upload_plugins()


@operation
def create_tenants(**_):
    with profile(get_current_master()):
        _create_tenants()


@operation
def create_secrets(**_):
    with profile(get_current_master()):
        _create_secrets()


@operation
def create_deployments(**_):
    with profile(get_current_master()):
        _create_deployments()


@operation
def execute_workflow(**_):
    with profile(get_current_master()):
        _execute_workflow()
