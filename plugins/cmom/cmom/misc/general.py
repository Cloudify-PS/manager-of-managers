import os
import shutil

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs

from ..common import CA_KEY, CA_CERT, INSTALL_RPM, execute_and_log

FILE_SERVER_BASE = '/opt/manager/resources'


def _copy_install_rpm():
    """
    Copy the installation RPM over to the fileserver, so that the
    Tier 1 managers will be able to use `ctx` to download it
    """
    ctx.logger.info('Copying the installation RPM to the fileserver...')
    install_rpm_path = os.path.join(FILE_SERVER_BASE, INSTALL_RPM)
    shutil.copy(inputs['install_rpm_path'], install_rpm_path)
    _add_paths_to_remove([install_rpm_path])


def _copy_ca_cert_and_key():
    ctx.logger.info('Copying the CA cert/key to the fileserver...')
    ca_cert_path = os.path.join(FILE_SERVER_BASE, CA_CERT)
    ca_key_path = os.path.join(FILE_SERVER_BASE, CA_KEY)
    shutil.copy(inputs['ca_cert'], ca_cert_path)
    shutil.copy(inputs['ca_key'], ca_key_path)
    _add_paths_to_remove([ca_cert_path, ca_key_path])


def _copy_scripts():
    ctx.logger.info('Copying scripts to the fileserver...')
    scripts_to_remove = []
    for script in inputs['scripts']:
        script_name = os.path.basename(script)
        script_path = os.path.join(FILE_SERVER_BASE, script_name)
        shutil.copy(script, script_path)
        scripts_to_remove.append(script_path)
    _add_paths_to_remove(scripts_to_remove)


def _add_paths_to_remove(paths):
    runtime_props = ctx.instance.runtime_properties
    paths_to_remove = runtime_props.setdefault('paths_to_remove', [])
    paths_to_remove += paths
    runtime_props['paths_to_remove'] = paths_to_remove


@operation
def setup_fileserver(**_):
    """
    Copy install RPM and CA cert/key to the fileserver
    """
    _copy_install_rpm()
    _copy_ca_cert_and_key()
    _copy_scripts()
    ctx.instance.update()


@operation
def cleanup_fileserver(**_):
    """
    Delete the install RPM and CA cert/key from the fileserver
    """
    ctx.logger.info('Cleaning up fileserver...')

    paths_to_remove = ctx.instance.runtime_properties['paths_to_remove']
    execute_and_log(['rm', '-rf'] + paths_to_remove, ignore_errors=True)
