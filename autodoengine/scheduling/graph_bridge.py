"""图模型 ↔ 调度五件套适配层（P2-4 双轨合一的桥）。

把运行态 `Graph` 的候选边（`GraphEdge`）映射到 `SchedulerService` 的
`CandidateEdge`，让"Filter→Score→Select→Guard→Dispatch"脊柱可以在真实图上跑，
与轨道 A（`route_view` + `runtime.resolve_next_node_by_edge`）对照。

本模块只做映射与选择，不改动轨道 A 的既有行为；切换主链调用点是后续步骤。
"""

from __future__ import annotations

from autodoengine.flow_graph.models import Graph, GraphEdge
from autodoengine.scheduling.service import SchedulerService
from autodoengine.scheduling.types import CandidateEdge, SchedulerContext


def to_candidate_edge(edge: GraphEdge) -> CandidateEdge:
    """把图边映射为调度候选边。

    条件表达式（condition_expr）的过滤已由 `route_view` 在调用前完成，
    故此处 condition 统一置 "always"，只做结构映射与打分字段搬运。

    Args:
        edge: 运行态图边。

    Returns:
        调度五件套可用的候选边。
    """

    metadata: dict[str, object] = {}
    if edge.version:
        metadata["version"] = edge.version
    return CandidateEdge(
        edge_uid=edge.edge_uid,
        from_transaction_uid=edge.from_node_uid,
        to_transaction_uid=edge.to_node_uid,
        condition="always",
        active=edge.enabled,
        base_tendency_score=edge.base_tendency_score,
        dispatch_key=edge.edge_uid,
        metadata=metadata,
    )


def select_next_edge(
    service: SchedulerService,
    *,
    graph: Graph,
    context: SchedulerContext,
    candidate_edges: list[GraphEdge],
):
    """用调度脊柱在候选图边中选出下一跳图边。

    Args:
        service: 已装配的 SchedulerService。
        graph: 当前静态图（用于回查选中边）。
        context: 调度上下文；其 `current_transaction_uid` 应为当前节点 uid。
        candidate_edges: 经 `route_view` 过滤后的候选图边。

    Returns:
        选中的 `GraphEdge`；无可用候选时返回 None。
    """

    edges = tuple(to_candidate_edge(edge) for edge in candidate_edges)
    event = service.dispatch_once(context=context, edges=edges, payload={}, result_code="PASS")
    selected = event.selection.selected
    if selected is None:
        return None
    for edge in candidate_edges:
        if edge.edge_uid == selected.edge.edge_uid:
            return edge
    return None
