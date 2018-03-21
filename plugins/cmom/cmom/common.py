import os
import subprocess

from cloudify import ctx
from cloudify.exceptions import CommandExecutionException

FILE_SERVER_BASE = '/opt/manager/resources'
DEFAULT_TENANT = 'default_tenant'
INSTALL_RPM = 'cloudify-manager-install.rpm'
CA_CERT = 'ca_cert.pem'
CA_KEY = 'ca_key.pem'


def execute_and_log(cmd,
                    clean_env=False,
                    deployment_workdir=None,
                    no_log=False,
                    ignore_errors=False):
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
    :param ignore_errors: Don't raise an exception on errors if True
    """
    env = os.environ.copy()
    if clean_env:
        env.pop('LOCAL_REST_CERT_FILE', None)

    if deployment_workdir:
        env['CFY_WORKDIR'] = deployment_workdir

    try:
        proc = _run_process(cmd, env)
    except OSError as e:
        if ignore_errors:
            ctx.logger.debug(
                'Failed running command `{0}` with error: {1}'.format(
                    cmd, e
                )
            )
            return
        raise

    output = _process_output(proc, not no_log)
    return_code = _return_code(proc)
    if return_code and not ignore_errors:
        raise CommandExecutionException(
            cmd, error=output, output=output, code=return_code
        )
    return output


def workdir(deployment_id=None):
    """Return a workdir based on the current deployment"""

    deployment_id = deployment_id or ctx.deployment.id
    _workdir = os.path.expanduser('~/{0}'.format(deployment_id))
    if not os.path.isdir(_workdir):
        os.mkdir(_workdir)
    return _workdir


def _process_output(proc, should_log):
    output_list = []
    for stdout_line in iter(proc.stdout.readline, ""):
        if stdout_line:
            output_list.append(stdout_line)
            if should_log:
                ctx.logger.info(stdout_line)

    return '\n'.join(output_list)


def _run_process(cmd, env):
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env
    )


def _return_code(proc):
    proc.stdout.close()
    return proc.wait()
