from cloudify.decorators import workflow


def _get_cluster_instance(ctx):
    cluster_node = ctx.get_node('cloudify_cluster')

    # There's only a single cloudify_cluster instances, so it should be safe
    # to just return the first one
    return list(cluster_node.instances)[0]


def _execute_task(ctx, operation, **kwargs):
    cluster_instance = _get_cluster_instance(ctx)
    cluster_instance.execute_operation(
        operation=operation,
        kwargs=kwargs,
        allow_kwargs_override=True
    ).get()


@workflow
def add_resources(ctx, **kwargs):
    _execute_task(ctx, 'cloudify.interfaces.lifecycle.start', **kwargs)


@workflow
def backup(ctx, **kwargs):
    _execute_task(ctx, 'maintenance_interface.backup', **kwargs)


@workflow
def restore(ctx, **kwargs):
    _execute_task(ctx, 'maintenance_interface.restore', **kwargs)
