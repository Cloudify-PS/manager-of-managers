import os
import shutil

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs

from ..common import CA_KEY, CA_CERT, INSTALL_RPM

FILE_SERVER_BASE = '/opt/manager/resources'


def _copy_install_rpm():
    """
    Copy the installation RPM over to the fileserver, so that the
    Tier 1 managers will be able to use `ctx` to download it
    """
    ctx.logger.info('Copying the installation RPM to the fileserver...')
    shutil.copy(
        inputs['install_rpm_path'],
        os.path.join(FILE_SERVER_BASE, INSTALL_RPM)
    )


def _copy_ca_cert_and_key():
    ctx.logger.info('Copying the CA cert/key to the fileserver...')
    shutil.copy(
        inputs['ca_cert'],
        os.path.join(FILE_SERVER_BASE, CA_CERT)
    )
    shutil.copy(
        inputs['ca_key'],
        os.path.join(FILE_SERVER_BASE, CA_KEY)
    )


@operation
def setup_fileserver(**_):
    """
    Copy install RPM and CA cert/key to the fileserver
    """
    _copy_install_rpm()
    _copy_ca_cert_and_key()


@operation
def cleanup_fileserver(**_):
    """
    Delete the install RPM and CA cert/key from the fileserver
    """
    ctx.logger.info('Cleaning up fileserver...')
    shutil.rmtree(os.path.join(FILE_SERVER_BASE, CA_CERT))
    shutil.rmtree(os.path.join(FILE_SERVER_BASE, CA_KEY))
    shutil.rmtree(os.path.join(FILE_SERVER_BASE, INSTALL_RPM))
