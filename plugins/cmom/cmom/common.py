import os
import subprocess

from cloudify import ctx
from cloudify.exceptions import CommandExecutionException


def execute_and_log(cmd,
                    clean_env=False,
                    deployment_workdir=False,
                    no_log=False):
    """
    Execute a command and log each line of its output as it is printed to
    stdout
    Taken from here: https://stackoverflow.com/a/4417735/978089
    :param cmd: The command to execute
    :param clean_env: If set to true we pop LOCAL_REST_CERT_FILE from the
        subprocess' env. This is because we're running in the agent worker's
        env and this env var is set there, but when we're calling a CLI
        command from the subprocess, we're using a CLI profile in which the
        cert is already set, and this creates a conflict.
    :param deployment_workdir: If set to true instead of using the default
        .cloudify folder, we use a folder that depends on the deployment ID
    :param no_log: If set to True the output will not be logged
    """
    env = os.environ.copy()
    if clean_env:
        env.pop('LOCAL_REST_CERT_FILE', None)

    if deployment_workdir:
        env['CFY_WORKDIR'] = workdir()

    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=env)
    for stdout_line in iter(popen.stdout.readline, ""):
        if stdout_line and not no_log:
            ctx.logger.info(stdout_line)
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise CommandExecutionException(
            cmd, popen.stderr, popen.stdout, return_code
        )


def download_certificate(relative_path, deployment_workdir=False):
    base_dir = workdir() if deployment_workdir else os.path.expanduser('~')
    target_dir = os.path.join(base_dir, 'certificates')
    if not os.path.isdir(target_dir):
        os.mkdir(target_dir)

    filename = os.path.basename(relative_path)
    target_file = os.path.join(target_dir, filename)
    local_path = ctx.download_resource(relative_path, target_file)
    return local_path


def workdir():
    """Return a workdir based on the current deployment"""

    _workdir = os.path.expanduser('~/{0}'.format(ctx.deployment.id))
    if not os.path.isdir(_workdir):
        os.mkdir(_workdir)
    return _workdir
