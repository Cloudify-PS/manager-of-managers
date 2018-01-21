from cloudify.decorators import workflow


def _get_cluster_instance(ctx):
    cluster_node = ctx.get_node('cloudify_cluster')

    # There's only a single cloudify_cluster instances, so it should be safe
    # to just return the first one
    return list(cluster_node.instances)[0]


@workflow
def add_resources(ctx, **kwargs):
    cluster_instance = _get_cluster_instance(ctx)
    cluster_instance.execute_operation(
        operation='cloudify.interfaces.lifecycle.start',
        kwargs=kwargs,
        allow_kwargs_override=True
    ).get()
