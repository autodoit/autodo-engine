"""静态图加载器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .graph_validator import validate_graph
from .models import Graph, GraphContainer, GraphEdge, GraphNode


def load_graph(graph_data: dict[str, Any]) -> Graph:
    """从字典载入静态图。

    Args:
        graph_data: 静态图字典。

    Returns:
        Graph: 静态图对象。

    Raises:
        ValueError: 当输入结构非法时抛出。

    Examples:
        >>> _ = load_graph({"graph_uid": "g", "graph_name": "n", "graph_version": "v"})
    """

    return load_graph_from_dict(graph_data)


def load_graph_from_file(file_path: str) -> Graph:
    """从 JSON 文件载入静态图。"""

    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("图文件根对象必须是 JSON 对象")
    return load_graph_from_dict(data)


def load_graph_from_dict(data: dict[str, Any]) -> Graph:
    """从 Python 字典对象构建静态图。"""

    nodes_payload = data.get("nodes") or {}
    edges_payload = data.get("edges") or []
    containers_payload = data.get("containers") or {}

    nodes: dict[str, GraphNode] = {}
    if isinstance(nodes_payload, list):
        for item in nodes_payload:
            node = GraphNode(
                node_uid=str(item["node_uid"]),
                node_type=str(item.get("node_type") or "generic"),
                affair_uid=item.get("affair_uid"),
                container_id=item.get("container_id"),
                risk_level=str(item.get("risk_level") or "normal"),
                policies=dict(item.get("policies") or {}),
                enabled=bool(item.get("enabled", True)),
            )
            nodes[node.node_uid] = node
    else:
        for uid, item in dict(nodes_payload).items():
            node = GraphNode(
                node_uid=str(uid),
                node_type=str(item.get("node_type") or "generic"),
                affair_uid=item.get("affair_uid"),
                container_id=item.get("container_id"),
                risk_level=str(item.get("risk_level") or "normal"),
                policies=dict(item.get("policies") or {}),
                enabled=bool(item.get("enabled", True)),
            )
            nodes[node.node_uid] = node

    edges: list[GraphEdge] = []
    for item in edges_payload:
        edge = GraphEdge(
            edge_uid=str(item["edge_uid"]),
            from_node_uid=str(item["from_node_uid"]),
            to_node_uid=str(item["to_node_uid"]),
            base_tendency_score=float(item.get("base_tendency_score", 1.0)),
            condition_expr=item.get("condition_expr"),
            enabled=bool(item.get("enabled", True)),
            version=item.get("version"),
        )
        edges.append(edge)

    containers: dict[str, GraphContainer] = {}
    if isinstance(containers_payload, list):
        for item in containers_payload:
            container = GraphContainer(
                container_id=str(item["container_id"]),
                container_name=str(item.get("container_name") or item["container_id"]),
                metadata=dict(item.get("metadata") or {}),
            )
            containers[container.container_id] = container
    else:
        for cid, item in dict(containers_payload).items():
            container = GraphContainer(
                container_id=str(cid),
                container_name=str(item.get("container_name") or cid),
                metadata=dict(item.get("metadata") or {}),
            )
            containers[container.container_id] = container

    graph = Graph(
        graph_uid=str(data.get("graph_uid") or "graph-default"),
        graph_name=str(data.get("graph_name") or "默认图"),
        graph_version=str(data.get("graph_version") or "0.1.0"),
        nodes=nodes,
        edges=edges,
        containers=containers,
        policies=dict(data.get("policies") or {}),
    )
    validate_graph(graph)
    return graph
