"""候选边视图构建。"""

from __future__ import annotations

from simpleeval import NameNotDefined, simple_eval

from autodoengine.core.types import NodeContext
from .models import Graph, GraphEdge


def build_candidate_edges(graph: Graph, node_uid: str) -> list[GraphEdge]:
    """构建当前节点的候选边集合。"""

    return [edge for edge in graph.edges if edge.from_node_uid == node_uid]


def filter_enabled_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    """过滤禁用边。"""

    return [edge for edge in edges if edge.enabled]


def filter_edges_by_condition(
    edges: list[GraphEdge],
    *,
    task_context: dict[str, object],
    node_context: NodeContext,
) -> list[GraphEdge]:
    """按边条件表达式过滤可达边。"""

    filtered: list[GraphEdge] = []
    names = {
        "task": task_context,
        "node": {
            "node_uid": node_context.node_uid,
            "node_type": node_context.node_type,
            "risk_level": node_context.risk_level,
            "policies": node_context.policies,
        },
    }
    for edge in edges:
        if not edge.condition_expr:
            filtered.append(edge)
            continue
        try:
            matched = bool(simple_eval(edge.condition_expr, names=names))
        except (NameNotDefined, TypeError, ValueError):
            matched = False
        if matched:
            filtered.append(edge)
    return filtered

