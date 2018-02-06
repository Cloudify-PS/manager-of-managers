from cloudify import ctx
from cloudify.decorators import operation
from cloudify.state import ctx_parameters as inputs


@operation
def set_floating_ip_on_host(**_):
    """
    Use this operation when connecting a host to a floating IP. This operation
    will set the `public_ip` runtime property on the host instance
    """
    floating_ip = ctx.target.instance.runtime_properties['floating_ip_address']
    ctx.source.instance.runtime_properties['public_ip'] = floating_ip
    ctx.source.instance.update()

    ctx.logger.info('Setting floating IP {0} for `{1}`'.format(
        floating_ip,
        ctx.source.instance.id
    ))


def _get_ip_address_and_hostname():
    """
    Get IP address and hostname from their respective resource pools and
    update the resource_pool object's runtime properties
    :return: A tuple (ip_address, hostname)
    """
    resource_pool = ctx.target.instance.runtime_properties['resource_pool']
    resource = resource_pool.pop(0)
    ctx.target.instance.runtime_properties['resource_pool'] = resource_pool
    ctx.target.instance.update()
    return resource['ip_address'], resource['hostname']


@operation
def get_resources_from_resource_pool(**_):
    """
    Get one of each IP address and hostname from the resource pool and keep
    them in the `resource` object's runtime props

    This operation runs in a relationship where `resource` is the source
    and `resource_pool` is the target
    """
    ip_address, fixed_hostname = _get_ip_address_and_hostname()

    ctx.logger.info('Setting IP `{0}` for instance `{1}`'.format(
        ip_address, ctx.source.instance.id
    ))
    ctx.logger.info('Setting hostname `{0}` for instance `{1}`'.format(
        fixed_hostname, ctx.source.instance.id
    ))

    # The neutron plugin expects a list of dicts with a `ip_address` key
    fixed_ip = [{'ip_address': ip_address}]
    ctx.source.instance.runtime_properties['fixed_ip'] = fixed_ip
    ctx.source.instance.runtime_properties['fixed_hostname'] = fixed_hostname
    ctx.source.instance.update()


@operation
def setup_resource_pool(**_):
    """ Create the resource pool from the user's inputs """

    ctx.instance.runtime_properties['resource_pool'] = inputs['resource_pool']
    ctx.instance.update()

    ctx.logger.info(
        'Setting resource pool: {0}'.format(inputs['resource_pool'])
    )


@operation
def set_ip_from_port(**_):
    """
    Use this operation to pass an IP from a port object to the host. This
    operation will set the `public_ip` runtime property on the host instance
    """

    ip_address = ctx.target.instance.runtime_properties['fixed_ip_address']
    ctx.source.instance.runtime_properties['public_ip'] = ip_address
    ctx.source.instance.update()

    ctx.logger.info('Setting IP {0} from port for `{1}`'.format(
        ip_address,
        ctx.source.instance.id
    ))
