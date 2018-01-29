from cloudify import ctx
from cloudify.decorators import operation


@operation
def set_floating_ip_on_host(**_):
    floating_ip = ctx.target.instance.runtime_properties['floating_ip_address']
    ctx.source.instance.runtime_properties['public_ip'] = floating_ip
    ctx.source.instance.update()

    ctx.logger.info('Setting floating IP {0} for `{1}`'.format(
        floating_ip,
        ctx.source.instance.id
    ))
