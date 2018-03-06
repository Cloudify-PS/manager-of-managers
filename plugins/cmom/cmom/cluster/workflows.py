from cloudify.decorators import workflow
from cloudify.plugins.lifecycle import (
    install_node_instance_subgraph,
    uninstall_node_instance_subgraph
)

from cloudify.state import current_ctx

from .utils import execute_and_log
from .cluster import use_cluster_profile


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


def _get_manager_node_instance(host_instance):
    """
    Return the `cloudify_manager` node instance connected to the current host
    """
    for instance in host_instance.contained_instances:
        if instance.node.id == 'cloudify_manager':
            return instance


def _get_manager_cluster_relationship(ctx, manager_instance):

    cluster_instance = _get_cluster_instance(ctx)
    for relationship in cluster_instance.relationships:
        if relationship.target_id == manager_instance.id:
            return relationship


@workflow
def heal_tier1_manager(ctx, node_instance_id, diagnose_value, **_):
    """ Run the heal workflow, and then join the cluster """

    ctx.logger.info("Starting 'heal' workflow on {0}, Diagnosis: {1}"
                    .format(node_instance_id, diagnose_value))

    ctx.logger.info('Updating CLI profile...')
    with current_ctx.push(ctx):
        use_cluster_profile()
        execute_and_log(['cfy', 'cluster', 'update-profile'])
    ctx.logger.info('CLI profile updated')

    host_instance = ctx.get_node_instance(node_instance_id)
    manager_instance = _get_manager_node_instance(host_instance)
    relationship = _get_manager_cluster_relationship(ctx, manager_instance)

    graph = ctx.graph_mode()
    sequence = graph.sequence()
    sequence.add(
        uninstall_node_instance_subgraph(
            manager_instance, graph, ignore_failure=True
        ),
        uninstall_node_instance_subgraph(
            host_instance, graph, ignore_failure=True
        ),
        install_node_instance_subgraph(host_instance, graph),
        install_node_instance_subgraph(manager_instance, graph),
        relationship.execute_target_operation(
            'cloudify.interfaces.relationship_lifecycle.postconfigure',
            kwargs={'force_join': True}
        )
    )
    graph.execute()
