from ..common import workdir
from ..common import execute_and_log as _execute_and_log


def execute_and_log(cmd,
                    deployment_id=None,
                    no_log=False,
                    ignore_errors=False,
                    is_json=False):
    if is_json:
        cmd.append('--json')
        no_log = True

    return _execute_and_log(
        cmd,
        clean_env=True,
        deployment_workdir=workdir(deployment_id),
        no_log=no_log,
        ignore_errors=ignore_errors,
        is_json=is_json
    )
