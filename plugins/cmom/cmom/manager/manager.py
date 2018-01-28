#!/usr/bin/env python

import os
import json
from collections import Mapping

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs

from ..common import execute_and_log, download_certificate

INSTALL_RPM_PATH = '/tmp/cloudify-manager-install.rpm'
CONFIG_PATH = '/etc/cloudify/config.yaml'


# TODO: Download from Tier 2 manager via ctx.download_resource_from_manager
def _download_rpm():
    ctx.logger.info('Downloading Cloudify Manager installation RPM...')
    execute_and_log([
        'curl', inputs['install_rpm_url'], '-o', INSTALL_RPM_PATH
    ])
    ctx.logger.info('Install RPM downloaded successfully')


def _install_rpm():
    ctx.logger.info('Installing RPM...')
    execute_and_log(['sudo', 'rpm', '-i', INSTALL_RPM_PATH])

    os.remove(INSTALL_RPM_PATH)
    ctx.logger.info('RPM installed successfully')


def _dict_merge(dct, merge_dct):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    Taken from: https://gist.github.com/angstwad/bf22d1822c38a92ec0a9
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None
    """
    for k, v in merge_dct.iteritems():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], Mapping)):
            _dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]


def _dump_configuration():
    """
    Dump the config from the node properties to /etc/cloudify/config.yaml
    """
    # The config file is expected to be YAML, but it should still be able
    # to read a json file
    ctx.logger.info('Dumping configuration from the inputs...')
    config = ctx.instance.runtime_properties['config']
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f)


def _install_manager():
    ctx.logger.info('Installing Cloudify Manager...')

    execute_and_log(['cfy_manager', 'install'], clean_env=True)
    ctx.logger.info('Cloudify Manager installed successfully')


def _update_runtime_properties():
    """
    Update the information relevant for later clustering needs in the
    runtime properties, so that it would be easily accessible by other nodes
    """
    # Override any values in `config` with values in `additional_config`
    config = inputs['config']
    additional_config = inputs['additional_config']
    _dict_merge(config, additional_config)

    ctx.instance.runtime_properties['config'] = config
    ctx.instance.update()
    ctx.logger.debug('Updated {0}: {1}'.format(ctx.instance.id, config))


def _remove_manager():
    ctx.logger.info('Uninstalling Cloudify Manager...')
    execute_and_log(['cfy_manager', 'remove', '--force'])


def _uninstall_rpm():
    ctx.logger.info('Removing RPM...')
    execute_and_log(['yum', 'remove', '-y', 'cloudify-manager-install'])


def _download_certificates():
    """
    Download certificates from the blueprint folder on the Tier 2 manager
    """
    ctx.logger.info('Downloading certificates to a local path...')
    config = inputs['config']
    ssl_inputs = config.setdefault('ssl_inputs', {})
    for key, value in ssl_inputs.items():
        if not value:
            continue

        ssl_inputs[key] = download_certificate(value)


@operation
def install_rpm(**_):
    """
    Install the Cloudify Manager install RPM and set the runtime properties
    to include the entire manager config
    """
    _download_rpm()
    _install_rpm()
    _download_certificates()
    _update_runtime_properties()


@operation
def install_manager(**_):
    _dump_configuration()
    _install_manager()


@operation
def delete(**_):
    _remove_manager()
    _uninstall_rpm()
