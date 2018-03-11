import os
import shutil

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs

from ..common import CA_KEY, CA_CERT, INSTALL_RPM, execute_and_log

FILE_SERVER_BASE = '/opt/manager/resources'
DEP_DIR = None


def _copy_install_rpm():
    """
    Copy the installation RPM over to the fileserver, so that the
    Tier 1 managers will be able to use `ctx` to download it
    """
    ctx.logger.info('Copying the installation RPM to the fileserver...')
    install_rpm_path = os.path.join(_dep_dir(), INSTALL_RPM)
    shutil.copy(inputs['install_rpm_path'], install_rpm_path)


def _copy_ca_cert_and_key():
    ctx.logger.info('Copying the CA cert/key to the fileserver...')
    ca_cert_path = os.path.join(_dep_dir(), CA_CERT)
    ca_key_path = os.path.join(_dep_dir(), CA_KEY)
    shutil.copy(inputs['ca_cert'], ca_cert_path)
    shutil.copy(inputs['ca_key'], ca_key_path)


def _copy_list(paths):
    for src_path in paths:
        file_name = os.path.basename(src_path)
        dst_path = os.path.join(_dep_dir(), file_name)
        shutil.copy(src_path, dst_path)
        execute_and_log(['chmod', '644', dst_path])


def _copy_scripts():
    ctx.logger.info('Copying scripts to the fileserver...')
    _copy_list(inputs['scripts'])


def _copy_files():
    ctx.logger.info('Copying files to the fileserver...')
    # Only getting the Tier 2 paths of the files
    _copy_list([f['src'] for f in inputs['files']])


def _dep_dir():
    global DEP_DIR
    if not DEP_DIR:
        DEP_DIR = os.path.join(FILE_SERVER_BASE, ctx.deployment.id)
    return DEP_DIR


@operation
def setup_fileserver(**_):
    """
    Copy install RPM and CA cert/key to the fileserver
    """
    if not os.path.exists(_dep_dir()):
        os.mkdir(_dep_dir())
    _copy_install_rpm()
    _copy_ca_cert_and_key()
    _copy_scripts()
    _copy_files()


@operation
def cleanup_fileserver(**_):
    """
    Delete the install RPM and CA cert/key from the fileserver
    """
    ctx.logger.info('Cleaning up fileserver...')
    execute_and_log(['rm', '-rf', _dep_dir()], ignore_errors=True)
