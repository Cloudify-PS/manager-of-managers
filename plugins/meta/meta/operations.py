from time import sleep

from cloudify import ctx as op_ctx
from cloudify.manager import get_rest_client
from cloudify.decorators import workflow, operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import NonRecoverableError

from cloudify_rest_client.executions import Execution


def _get_deps():
    runtime_props = op_ctx.instance.runtime_properties
    return runtime_props.setdefault('deployments', [])


@operation
def add_deployment(**_):
    deployment_id = inputs['deployment_id']
    deps = _get_deps()
    if deployment_id not in deps:
        deps.append(deployment_id)

    op_ctx.instance.runtime_properties['deployments'] = deps
    op_ctx.instance.update()


def _start_get_status_executions(client):
    started_executions = set()
    for dep in _get_deps():
        op_ctx.logger.info('Getting status for deployment `{0}`'.format(dep))
        execution = client.executions.start(
            deployment_id=dep,
            workflow_id='get_status'
        )
        started_executions.add(execution.id)

    return started_executions


def _wait_for_executions_to_end(client, started_executions):
    max_retries = 10
    retries = 0

    while started_executions and retries < max_retries:
        retries += 1
        op_ctx.logger.info(
            'Waiting for executions to finish... [{0}/{1}]'.format(
                retries, max_retries
            )
        )

        finished_executions = set()
        for execution_id in started_executions:
            op_ctx.logger.debug(
                'Checking execution `{0}`'.format(execution_id)
            )
            execution = client.executions.get(execution_id)
            if execution.status in Execution.END_STATES:
                finished_executions.add(execution_id)

        started_executions = started_executions - finished_executions
        sleep(3)

    if retries >= max_retries:
        raise NonRecoverableError(
            'Not all `get_status` executions have finished. '
            'They still might be running in the background. '
            'The unfinished executions are: {0}'.format(started_executions)
        )


@operation
def get_status(**_):
    client = get_rest_client()
    started_executions = _start_get_status_executions(client)

    _wait_for_executions_to_end(client, started_executions)

    op_ctx.logger.info('Getting status reports from deployment outputs...')
    status = {
        dep: client.deployments.outputs.get(deployment_id=dep)
        for dep in _get_deps()
    }

    op_ctx.instance.runtime_properties['status'] = status
