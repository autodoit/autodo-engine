"""任务步上下文准备器。"""

from __future__ import annotations

from typing import Any

from autodoengine.core.enums import TaskStatus
from autodoengine.core.types import NodeContext, RetryBudget, TaskContext
from autodoengine.flow_graph.models import Graph
from autodoengine.taskdb import decision_store, relation_store, step_store as _step_store, task_store


def prepare_task_context(task_uid: str, graph_uid: str) -> TaskContext:
    """准备任务上下文。"""

    task = task_store.get_task(task_uid)
    return TaskContext(
        task_uid=task["task_uid"],
        graph_uid=graph_uid,
        status=TaskStatus(task["status"]),
        current_node_uid=task["current_node_uid"],
        current_affair_uid=task.get("current_affair_uid"),
        goal_text=str(task.get("goal_text") or ""),
        retry_count=int(task.get("retry_count", 0)),
        max_retry=int(task.get("max_retry", 2)),
        parent_task_uid=task.get("parent_task_uid"),
        metadata=dict(task.get("metadata") or {}),
    )


def prepare_node_context(graph: Graph, task_context: TaskContext) -> NodeContext:
    """准备节点上下文。"""

    node = graph.nodes[task_context.current_node_uid]
    return NodeContext(
        node_uid=node.node_uid,
        node_type=node.node_type,
        affair_uid=node.affair_uid,
        risk_level=node.risk_level,
        policies=node.policies,
        container_id=node.container_id,
    )


def prepare_retry_budget(task_context: TaskContext) -> RetryBudget:
    """准备重试预算对象。"""

    return RetryBudget(max_retry=task_context.max_retry, current_retry=task_context.retry_count)


def prepare_history_summary(step_store: Any, task_uid: str) -> dict[str, Any]:
    """准备任务历史摘要。"""

    resolved_step_store = step_store or _step_store
    steps = resolved_step_store.list_task_steps(task_uid)
    decisions = decision_store.list_task_decisions(task_uid)
    children = relation_store.list_children(task_uid)
    latest_actions = [item.selected_action.value for item in steps[-3:]]
    retry_count = int(task_store.get_task(task_uid).get("retry_count", 0))
    blocked_count = sum(
        1
        for row in decisions
        if str((row.get("decision") or {}).get("task_status_after") or "") == TaskStatus.BLOCKED.value
    )

    split_hint = (retry_count >= 2 or blocked_count >= 1) and len(children) == 0

    return {
        "task_uid": task_uid,
        "recent_steps": len(steps),
        "latest_actions": latest_actions,
        "retry_count": retry_count,
        "blocked_count": blocked_count,
        "child_count": len(children),
        "split_hint": split_hint,
    }

