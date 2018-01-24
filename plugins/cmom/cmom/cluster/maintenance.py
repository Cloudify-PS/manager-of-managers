import os
from time import sleep
from datetime import datetime

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import NonRecoverableError

from ..common import workdir
from .utils import execute_and_log

SNAPSHOTS_FOLDER = 'snapshots'
RESTORE_SNAP_ID = 'restored_snapshot'


def _snapshots_dir(deployment_id=None):
    snapshots_dir = os.path.join(workdir(deployment_id), SNAPSHOTS_FOLDER)
    if not os.path.isdir(snapshots_dir):
        os.mkdir(snapshots_dir)
    return snapshots_dir


def _is_snapshot_created(snapshot_id, deployment_id):
    output = execute_and_log(
        ['cfy', 'snapshots', 'list'],
        no_log=True,
        deployment_id=deployment_id
    )
    for line in output.split('\n'):
        if snapshot_id not in line:
            continue
        if 'created' in line:
            return True
    return False


def _create_snapshot(snapshot_id, deployment_id):
    execute_and_log(
        ['cfy', 'snapshots', 'create', snapshot_id],
        deployment_id=deployment_id
    )
    ctx.logger.info('Waiting for the snapshot to be created...')
    snapshot_created = False
    for retry in range(10):
        ctx.logger.debug(
            'Waiting for the snapshot to be created [retry {0}/10]'.format(
                retry
            )
        )

        snapshot_created = _is_snapshot_created(snapshot_id, deployment_id)
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
    def __init__(self):
        self.snapshot_id = inputs.get('snapshot_id')
        self.old_deployment_id = inputs.get('old_deployment_id')
        self.snapshot_path = inputs.get('snapshot_path')
        self.restore = inputs.get('restore', False)
        self.backup = inputs.get('backup', False)
        self.transfer_agents = inputs.get('transfer_agents', True)

    def validate(self):
        if self.restore:
            if self.backup:
                if self.snapshot_path:
                    self._raise_error(
                        'then *either* backup may be set to True or '
                        '`snapshot_path` may be provided, but not both'
                    )
                if not self.old_deployment_id:
                    self._raise_error(
                        'and `backup` is set to True, then '
                        '`old_deployment_id` must be provided as well'
                    )
            else:
                wrong_inputs = False
                if self.snapshot_path:
                    if any([self.old_deployment_id, self.snapshot_id]):
                        wrong_inputs = True
                else:
                    if not all([self.old_deployment_id, self.snapshot_id]):
                        wrong_inputs = True
                if wrong_inputs:
                    self._raise_error(
                        'and `backup` is set to False then either '
                        '`snapshot_path` *or* `old_deployment_id` *and* '
                        '`snapshot_id` need to be provided'
                    )
        else:
            values = ['backup', 'old_deployment_id',
                      'snapshot_id', 'snapshot_path']

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


@operation
def backup(deployment_id=None, **_):
    """
    Create a snapshot on a Tier 1 cluster, and download it to a dedicated
    folder on the Tier 2 manager
    """
    snapshot_id = inputs.get('snapshot_id')
    if not snapshot_id:
        now = datetime.now()
        snapshot_id = now.strftime('%Y-%m-%d-%H:%M:%S')

    output_path = os.path.join(
        _snapshots_dir(deployment_id),
        '{0}.zip'.format(snapshot_id)
    )
    if os.path.exists(output_path):
        raise NonRecoverableError(
            'Snapshot with ID {0} already exists. Try a different name, '
            'or leave the `snapshot_id` parameter empty in order to create '
            'a snapshot ID based on the current date and time'
        )

    _create_snapshot(snapshot_id, deployment_id)
    execute_and_log([
        'cfy', 'snapshots',
        'download', snapshot_id,
        '-o', output_path
    ], deployment_id=deployment_id)
    return output_path


def restore(config):
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

    execute_and_log([
        'cfy', 'snapshots',
        'upload', config.snapshot_path,
        '-s', RESTORE_SNAP_ID
    ])
    _restore_snapshot(RESTORE_SNAP_ID)

    if config.transfer_agents:
        execute_and_log(['cfy', 'agents', 'install'])


def _restore_snapshot(snapshot_id):
    execute_and_log(['cfy', 'snapshots', 'restore', snapshot_id])
