import os
from time import sleep
from datetime import datetime

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import NonRecoverableError, CommandExecutionException

from .utils import execute_and_log
from .profile import profile, get_current_master

SNAPSHOTS_FOLDER = 'snapshots'
RESTORE_SNAP_ID = 'restored_snapshot'


def _snapshots_dir(deployment_id=None):
    deployment_id = deployment_id or ctx.deployment.id
    base_snapshots_dir = os.path.expanduser('~/{0}'.format(SNAPSHOTS_FOLDER))
    if not os.path.isdir(base_snapshots_dir):
        os.mkdir(base_snapshots_dir)
    dep_snapshots_dir = os.path.join(base_snapshots_dir, deployment_id)
    if not os.path.isdir(dep_snapshots_dir):
        os.mkdir(dep_snapshots_dir)
    return dep_snapshots_dir


def _is_snapshot_created(snapshot_id):
    snapshots = execute_and_log(['cfy', 'snapshots', 'list'], is_json=True)
    for snapshot in snapshots:
        if snapshot['id'] == snapshot_id and snapshot['status'] == 'created':
            return True
    return False


def _create_snapshot(snapshot_id, create_snap_params):
    execute_and_log(
        ['cfy', 'snapshots', 'create', snapshot_id] + create_snap_params,
    )
    ctx.logger.info('Waiting for the snapshot to be created...')
    snapshot_created = False
    for retry in range(1, 101):
        ctx.logger.info(
            'Waiting for the snapshot to be created [retry {0}/100]'.format(
                retry
            )
        )

        snapshot_created = _is_snapshot_created(snapshot_id)
        if snapshot_created:
            ctx.logger.info(
                'Snapshot {0} created successfully'.format(snapshot_id)
            )
            break
        sleep(3)
    if not snapshot_created:
        raise NonRecoverableError(
            'Could not create snapshot {0}'.format(snapshot_id)
        )


class UpgradeConfig(object):
    RESTORE_PARAMS = {
        '--without-deployment-envs',
        '--force',
        '--restore-certificates',
        '--no-reboot'
    }

    def __init__(self):
        self.snapshot_id = inputs.get('snapshot_id')
        self.old_deployment_id = inputs.get('old_deployment_id')
        self.snapshot_path = inputs.get('snapshot_path')
        self.restore = inputs.get('restore', False)
        self.transfer_agents = inputs.get('transfer_agents', True)
        self.restore_params = inputs.get('restore_params', [])

    def validate(self):
        if self.restore:
            if not all(param in self.RESTORE_PARAMS for
                       param in self.restore_params):
                self._raise_error(
                    'the only restore parameters allowed are: {0}, '
                    'but: {1} were provided'.format(
                        list(self.RESTORE_PARAMS), self.restore_params)
                )

            wrong_inputs = False
            if self.snapshot_path:
                if any([self.old_deployment_id, self.snapshot_id]):
                    wrong_inputs = True
            else:
                if not all([self.old_deployment_id, self.snapshot_id]):
                    wrong_inputs = True
            if wrong_inputs:
                self._raise_error(
                    'either `snapshot_path` *or* `old_deployment_id` *and* '
                    '`snapshot_id` need to be provided'
                )
        else:
            values = ['old_deployment_id', 'snapshot_id',
                      'snapshot_path', 'restore_params']

            if any([getattr(self, value) for value in values]):
                self._raise_error(
                    'the following inputs should not be '
                    'provided:\n{0}'.format(values)
                )

    def _raise_error(self, message):
        raise NonRecoverableError(
            'Incorrect inputs passed: if `restore` '
            'is set to {0}, {1}'.format(self.restore, message)
        )


def _upload_snapshot(config):
    execute_and_log([
        'cfy', 'snapshots',
        'upload', config.snapshot_path,
        '-s', RESTORE_SNAP_ID
    ])


def _download_snapshot(snapshot_id, output_path):
    execute_and_log([
        'cfy', 'snapshots',
        'download', snapshot_id,
        '-o', output_path
    ])


def _transfer_agents(config):
    if config.transfer_agents:
        try:
            execute_and_log(['cfy', 'agents', 'install', '--all-tenants'])
        except CommandExecutionException as e:
            # If we try to run `cfy agents install` but there are no
            # deployments, we can just ignore it
            if 'There are no deployments installed' not in e.error:
                raise


def _get_backup_params():
    backup_params = inputs.get('backup_params', [])
    if backup_params:
        allowed_backup_params = {
            '--include-metrics',
            '--exclude-credentials',
            '--exclude-logs',
            '--exclude-events'
        }
        if not all(param in allowed_backup_params for
                   param in backup_params):
            raise NonRecoverableError(
                'The only backup parameters allowed are: {0}, '
                'but: {1} were provided'.format(
                    list(allowed_backup_params),
                    backup_params)
            )
    return backup_params


@operation
def backup(**_):
    """
    Create a snapshot on a Tier 1 cluster, and download it to a dedicated
    folder on the Tier 2 manager
    """
    backup_params = _get_backup_params()
    snapshot_id = inputs.get('snapshot_id')
    if not snapshot_id:
        now = datetime.now()
        snapshot_id = 'snap_{0}'.format(now.strftime('%Y_%m_%d_%H_%M_%S'))

    output_path = os.path.join(
        _snapshots_dir(),
        '{0}.zip'.format(snapshot_id)
    )
    if os.path.exists(output_path):
        raise NonRecoverableError(
            'Snapshot with ID {0} already exists. Try a different name, '
            'or leave the `snapshot_id` parameter empty in order to create '
            'a snapshot ID based on the current date and time'
        )

    with profile(get_current_master()):
        _create_snapshot(snapshot_id, backup_params)
        _download_snapshot(snapshot_id, output_path)
    return output_path


def restore(master_ip, config):
    """
    Restore a snapshot on a Tier 1 cluster, and (optionally) upgrade the agents
    """
    # If the old deployment and snapshot ID were provided, calculate the
    # path of snapshot from those variables
    if not config.snapshot_path:
        config.snapshot_path = os.path.join(
            _snapshots_dir(config.old_deployment_id),
            '{0}.zip'.format(config.snapshot_id)
        )

    with profile(master_ip):
        _upload_snapshot(config)
        _restore_snapshot(RESTORE_SNAP_ID, config.restore_params)
        _transfer_agents(config)


def _is_snapshot_restored(execution_id):
    execution = execute_and_log(
        ['cfy', 'executions', 'get', execution_id],
        is_json=True, ignore_errors=True
    )
    if not execution:
        return False
    if execution['status'] == 'completed':
        return True
    elif execution['status'] == 'failed':
        raise NonRecoverableError(
            'Failed restoring snapshot. Error:\n{0}'.format(execution['error'])
        )
    return False


def _restore_snapshot(snapshot_id, restore_params):
    output = execute_and_log(
        ['cfy', 'snapshots', 'restore', snapshot_id] + restore_params
    )
    execution_id = output.split("The execution's id is")[1].strip().split()[0]

    ctx.logger.info('Waiting for the snapshot to be restored...')
    snapshot_restored = False
    for retry in range(1, 101):
        ctx.logger.info(
            'Waiting for the snapshot to be restored [retry {0}/100]'.format(
                retry
            )
        )

        snapshot_restored = _is_snapshot_restored(execution_id)
        if snapshot_restored:
            ctx.logger.info(
                'Snapshot {0} created successfully'.format(snapshot_id)
            )
            break
        sleep(10)
    if not snapshot_restored:
        raise NonRecoverableError(
            'Could not restore snapshot {0}'.format(snapshot_id)
        )


@operation
def get_status(**_):
    error = ''
    try:
        with profile(get_current_master()):
            cluster_status = execute_and_log(
                ['cfy', 'cluster', 'nodes', 'list'],
                is_json=True
            )
            leader_status = execute_and_log(['cfy', 'status'], is_json=True)

            # This is to fix a quirk in how the statuses are returned
            # (with an alignment of 30 spaces)
            for service in leader_status:
                service['service'] = service['service'].strip()
    except NonRecoverableError as e:
        cluster_status = []
        leader_status = {}
        error = str(e)

    current_status = {
        'cluster_status': cluster_status,
        'leader_status': leader_status,
        'error': error
    }
    ctx.instance.runtime_properties['status'] = current_status
    return current_status
