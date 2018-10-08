from cloudify.decorators import workflow


def _get_node_instance(ctx, instance_name):
    node = ctx.get_node(instance_name)

    # Important! This only works for nodes with a single instance
    return list(node.instances)[0]


def _get_task(ctx, instance_name, operation, **kwargs):
    instance = _get_node_instance(ctx, instance_name)
    return instance.execute_operation(
        operation=operation,
        kwargs=kwargs,
        allow_kwargs_override=True
    )


def _execute_task(ctx, instance_name, operation, **kwargs):
    # Calling `task.get()` is what actually executes the task
    _get_task(ctx, instance_name, operation, **kwargs).get()


@workflow
def add_deployment(ctx, **kwargs):
    _execute_task(ctx, 'meta_node',
                  'runtime_interface.add_deployment', **kwargs)


@workflow
def get_status(ctx, **kwargs):
    _execute_task(ctx, 'meta_node', 'runtime_interface.get_status', **kwargs)
