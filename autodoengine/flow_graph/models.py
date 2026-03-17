"""静态图模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GraphPolicy:
    """图策略对象。"""

    values: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphContainer:
    """图容器对象。"""

    container_id: str
    container_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphNode:
    """静态图节点对象。"""

    node_uid: str
    node_type: str
    affair_uid: str | None
    container_id: str | None
    risk_level: str = "normal"
    policies: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(slots=True)
class GraphEdge:
    """静态图边对象。"""

    edge_uid: str
    from_node_uid: str
    to_node_uid: str
    base_tendency_score: float = 1.0
    condition_expr: str | None = None
    enabled: bool = True
    version: str | None = None


@dataclass(slots=True)
class Graph:
    """静态图对象。"""

    graph_uid: str
    graph_name: str
    graph_version: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    containers: dict[str, GraphContainer] = field(default_factory=dict)
    policies: dict[str, Any] = field(default_factory=dict)
