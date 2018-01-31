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


@operation
def setup_ip_pool(**_):
    """
    Use this operation when creating the IP pool

    Will create the initial `next_ip` runtime prop which will be updated
    further by subsequent calls to `set_ip_from_port`
    """

    # `allowed_address_pairs` expects a list of dicts that looks like this:
    # [{"ip_address": "10.3.3.3"}, {"ip_address": "10.3.3.4"}]
    ip_pool = [{'ip_address': ip} for ip in inputs['ip_pool']]
    ctx.instance.runtime_properties['ip_pool'] = ip_pool
    ctx.logger.info('Setting IP pool to: {0}'.format(ip_pool))

    allocation_pools = [{'start': ip, 'end': ip} for ip in inputs['ip_pool']]
    ctx.instance.runtime_properties['allocation_pools'] = allocation_pools
    ctx.logger.info('Setting subnet IP allocation pools to: {0}'.format(
        allocation_pools
    ))
    ctx.instance.update()


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
