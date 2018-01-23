import os
from datetime import datetime

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs
from cloudify.exceptions import NonRecoverableError

from ..common import workdir
from .utils import use_master_profile, execute_and_log

SNAPSHOTS_FOLDER = 'snapshots'


def _snapshots_dir():
    _workdir = workdir()
    snapshots_dir = os.path.join(_workdir, SNAPSHOTS_FOLDER)
    if not os.path.isdir(snapshots_dir):
        os.mkdir(snapshots_dir)
    return snapshots_dir


def _is_snapshot_created(snapshot_id):
    output = execute_and_log(['cfy', 'snapshots', 'list'], no_log=True)
    for line in output.split('\n'):
        if snapshot_id not in line:
            continue
        if 'created' in line:
            return True
    return False


def _create_snapshot(snapshot_id):
    execute_and_log(['cfy', 'snapshots', 'create', snapshot_id])
    ctx.logger.info('Waiting for the snapshot to be created...')
    snapshot_created = False
    for retry in range(10):
        ctx.logger.debug(
            'Waiting for the snapshot to be created [retry {0}/10]'.format(
                retry
            )
        )

        snapshot_created = _is_snapshot_created(snapshot_id)
        if snapshot_created:
            ctx.logger.info(
                'Snapshot {0} created successfully'.format(snapshot_id)
            )
            break
    if not snapshot_created:
        raise NonRecoverableError(
            'Could not create snapshot {0}'.format(snapshot_id)
        )


@operation
def backup(**_):
    """
    Create a snapshot on the Tier 1 cluster, and download it to a dedicated
    folder on the Tier 2 manager
    """
    snapshot_id = inputs.get('snapshot_id')
    if not snapshot_id:
        now = datetime.now()
        snapshot_id = now.strftime('%Y-%m-%d-%H:%M:%S')

    output_path = os.path.join(_snapshots_dir(), '{0}.zip'.format(snapshot_id))
    if os.path.exists(output_path):
        raise NonRecoverableError(
            'Snapshot with ID {0} already exists. Try a different name, '
            'or leave the `snapshot_id` parameter empty in order to create '
            'a snapshot ID based on the current date and time'
        )

    use_master_profile()
    _create_snapshot(snapshot_id)
    execute_and_log([
        'cfy', 'snapshots',
        'download', snapshot_id,
        '-o', output_path
    ])


@operation
def restore(**_):
    """

    :param _:
    :return:
    """