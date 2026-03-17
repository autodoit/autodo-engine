"""静态图校验器。"""

from __future__ import annotations

from .models import Graph, GraphContainer, GraphEdge, GraphNode
from autodoengine.core.errors import GraphValidationError


def validate_graph(graph: Graph) -> None:
    """校验静态图整体合法性。

    Args:
        graph: 待校验静态图对象。

    Returns:
        None

    Raises:
        GraphValidationError: 当静态图不合法时抛出。

    Examples:
        >>> graph = Graph(graph_uid="g", graph_name="n", graph_version="v")
        >>> validate_graph(graph)
    """

    if not graph.graph_uid.strip():
        raise GraphValidationError("graph_uid 不能为空")
    validate_nodes(graph.nodes)
    validate_edges(graph.nodes, graph.edges)
    validate_containers(graph.containers)


def validate_nodes(nodes: dict[str, GraphNode]) -> None:
    """校验节点集合。"""

    for uid, node in nodes.items():
        if uid != node.node_uid:
            raise GraphValidationError(f"节点键与 node_uid 不一致：{uid}")
        if not node.node_type.strip():
            raise GraphValidationError(f"节点类型为空：{uid}")


def validate_edges(nodes: dict[str, GraphNode], edges: list[GraphEdge]) -> None:
    """校验边集合。"""

    seen: set[str] = set()
    for edge in edges:
        if edge.edge_uid in seen:
            raise GraphValidationError(f"重复边 uid：{edge.edge_uid}")
        seen.add(edge.edge_uid)
        if edge.from_node_uid not in nodes:
            raise GraphValidationError(f"边起点不存在：{edge.edge_uid}")
        if edge.to_node_uid not in nodes:
            raise GraphValidationError(f"边终点不存在：{edge.edge_uid}")


def validate_containers(containers: dict[str, GraphContainer]) -> None:
    """校验容器集合。"""

    for key, container in containers.items():
        if key != container.container_id:
            raise GraphValidationError(f"容器键与 container_id 不一致：{key}")


def validate_affair_bindings(graph: Graph, registered_affairs: set[str]) -> None:
    """校验节点绑定事务是否已注册。"""

    for node in graph.nodes.values():
        if not node.affair_uid:
            continue
        if node.affair_uid not in registered_affairs:
            raise GraphValidationError(f"节点[{node.node_uid}] 绑定未注册事务：{node.affair_uid}")

