"""任务单步运行的图侧辅助函数。"""

from __future__ import annotations

from uuid import uuid4

from autodoengine.core.types import DecisionResult, NodeContext, TaskContext, TaskStepRecord
from .models import Graph, GraphEdge, GraphNode
from .route_view import build_candidate_edges, filter_edges_by_condition, filter_enabled_edges


def resolve_current_node(graph: Graph, task_context: TaskContext) -> GraphNode:
    """解析任务当前位置对应的静态节点。"""

    node = graph.nodes.get(task_context.current_node_uid)
    if node is None:
        raise KeyError(f"任务当前位置不存在于图中：{task_context.current_node_uid}")
    return node


def resolve_candidate_edges(
    graph: Graph,
    *,
    task_context: TaskContext,
    node_context: NodeContext,
) -> list[GraphEdge]:
    """解析当前任务可达候选边。"""

    candidates = build_candidate_edges(graph, node_context.node_uid)
    candidates = filter_enabled_edges(candidates)
    return filter_edges_by_condition(
        candidates,
        task_context={
            "task_uid": task_context.task_uid,
            "status": task_context.status.value,
            "retry_count": task_context.retry_count,
            "goal_text": task_context.goal_text,
            "metadata": task_context.metadata,
        },
        node_context=node_context,
    )


def resolve_next_node_by_edge(graph: Graph, edge_uid: str) -> GraphNode:
    """根据边解析下一节点。"""

    for edge in graph.edges:
        if edge.edge_uid == edge_uid:
            return graph.nodes[edge.to_node_uid]
    raise KeyError(f"边不存在：{edge_uid}")


def derive_dynamic_step(
    *,
    run_uid: str,
    node_uid_before: str,
    node_uid_after: str,
    selected_edge_uid: str | None,
    decision_result: DecisionResult,
) -> TaskStepRecord:
    """生成动态图任务步记录。"""

    return TaskStepRecord(
        step_uid=f"step-{uuid4().hex[:12]}",
        run_uid=run_uid,
        task_uid=decision_result.task_uid,
        node_uid_before=node_uid_before,
        node_uid_after=node_uid_after,
        selected_action=decision_result.selected_action,
        selected_edge_uid=selected_edge_uid,
        task_status_before=decision_result.task_status_before,
        task_status_after=decision_result.task_status_after,
        decision_uid=decision_result.decision_uid,
    )

