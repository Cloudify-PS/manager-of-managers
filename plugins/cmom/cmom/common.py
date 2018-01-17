import os
import subprocess

from cloudify import ctx


def execute_and_log(cmd, clean_env=False):
    """
    Execute a command and log each line of its output as it is printed to
    stdout
    Taken from here: https://stackoverflow.com/a/4417735/978089
    """
    env = None
    if clean_env:
        # This is here because we're running in the agent worker's env,
        # but during the installation we provide the cert via an input to the
        # CLI, and this creates a conflict. So we remove the envvar from this
        # process
        env = os.environ.copy()
        env.pop('LOCAL_REST_CERT_FILE', None)

    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=env)
    for stdout_line in iter(popen.stdout.readline, ""):
        if stdout_line:
            ctx.logger.info(stdout_line)
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)


def download_certificate(relative_path):
    target_dir = os.path.expanduser('~/certificates')
    if not os.path.isdir(target_dir):
        os.mkdir(target_dir)

    filename = os.path.basename(relative_path)
    target_file = os.path.join(target_dir, filename)
    local_path = ctx.download_resource(relative_path, target_file)
    return local_path
