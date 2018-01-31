from cloudify import ctx
from cloudify.decorators import operation


@operation
def setup_globals(**_):
    """

    """
    ctx.logger.info('Setting up deployment globals...')
