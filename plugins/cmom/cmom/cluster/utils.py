from ..common import workdir
from ..common import execute_and_log as _execute_and_log


def execute_and_log(cmd, deployment_id=None, no_log=False):
    return _execute_and_log(
        cmd,
        clean_env=True,
        deployment_workdir=workdir(deployment_id),
        no_log=no_log
    )


def use_profile(manager_ip):
    execute_and_log(['cfy', 'profiles', 'use', manager_ip])
