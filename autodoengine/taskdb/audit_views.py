"""v4 审计查询视图。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .decision_store import get_decision, list_task_decisions
from .log_store import list_runtime_events
from .step_store import list_task_steps


def build_task_full_chain_view(task_uid: str) -> dict[str, Any]:
    """构建任务全链路视图。

    Args:
        task_uid: 任务 UID。

    Returns:
        dict[str, Any]: 按任务聚合的全链路视图。

    Raises:
        None.

    Examples:
        >>> # doctest: +SKIP
        >>> view = build_task_full_chain_view("task-001")
    """

    steps = list_task_steps(task_uid)
    decisions = list_task_decisions(task_uid)
    events = list_runtime_events(task_uid)
    decision_map = {(item.get("decision") or {}).get("decision_uid"): item for item in decisions}

    chain: list[dict[str, Any]] = []
    for step in steps:
        decision_row = decision_map.get(step.decision_uid) or {}
        decision_payload = decision_row.get("decision") or {}
        packet_payload = decision_row.get("packet") or {}
        chain.append(
            {
                "step_uid": step.step_uid,
                "node_uid_before": step.node_uid_before,
                "node_uid_after": step.node_uid_after,
                "task_status_before": step.task_status_before.value,
                "task_status_after": step.task_status_after.value,
                "candidate_actions_json": [
                    str(item) for item in (packet_payload.get("candidate_actions") or [])
                ],
                "selected_action": decision_payload.get("selected_action", step.selected_action.value),
                "decision_uid": step.decision_uid,
                "observation_packet_ref": packet_payload.get("packet_uid"),
                "evidence_refs": list(packet_payload.get("evidence") or []),
                "artifact_refs": list(packet_payload.get("artifact_refs") or []),
            }
        )

    return {
        "task_uid": task_uid,
        "steps": chain,
        "events": events,
        "step_count": len(chain),
        "event_count": len(events),
    }


def build_decision_department_view(*, task_uid: str | None = None, decision_uid: str | None = None) -> dict[str, Any]:
    """构建决策部门行为视图。

    Args:
        task_uid: 任务 UID，可选。
        decision_uid: 决策 UID，可选。

    Returns:
        dict[str, Any]: 决策部门行为视图。

    Raises:
        ValueError: task_uid 与 decision_uid 都为空时抛出。

    Examples:
        >>> # doctest: +SKIP
        >>> view = build_decision_department_view(task_uid="task-001")
    """

    if not task_uid and not decision_uid:
        raise ValueError("task_uid 与 decision_uid 至少提供一个")

    rows: list[dict[str, Any]] = []
    if decision_uid:
        rows = [get_decision(decision_uid)]
    elif task_uid:
        rows = list_task_decisions(task_uid)

    decisions: list[dict[str, Any]] = []
    for row in rows:
        decision = row.get("decision") or {}
        packet = row.get("packet") or {}
        decisions.append(
            {
                "decision_uid": decision.get("decision_uid"),
                "task_uid": decision.get("task_uid"),
                "selected_action": decision.get("selected_action"),
                "decision_members": list(decision.get("decision_members") or []),
                "decision_mode": decision.get("decision_mode"),
                "is_override_recommendation": bool(decision.get("is_override_recommendation", False)),
                "override_explanation": decision.get("override_explanation", ""),
                "recommended_action": packet.get("recommended_action"),
                "candidate_actions": list(packet.get("candidate_actions") or []),
                "result_status_after": decision.get("task_status_after"),
            }
        )

    return {
        "task_uid": task_uid,
        "decision_uid": decision_uid,
        "decisions": decisions,
        "decision_count": len(decisions),
    }


def build_blocked_governance_view(task_uid: str | None = None) -> dict[str, Any]:
    """构建阻断治理视图。

    Args:
        task_uid: 任务 UID，可选。

    Returns:
        dict[str, Any]: 阻断原因与作用域聚合视图。

    Raises:
        None.

    Examples:
        >>> # doctest: +SKIP
        >>> view = build_blocked_governance_view(task_uid="task-001")
    """

    events = list_runtime_events(task_uid)
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "task_level": 0,
            "node_level": 0,
            "affair_level": 0,
            "human_gate_requested": 0,
            "actions": defaultdict(int),
        }
    )

    for item in events:
        event_type = str(item.get("event_type") or "")
        payload = item.get("payload") or {}

        if event_type == "receipt_normalized" and str(payload.get("result_code") or "") == "BLOCKED":
            reason = str(payload.get("block_reason_code") or "unknown")
            scope = str(payload.get("block_scope") or "unknown")
            bucket = buckets[reason]
            bucket["count"] += 1
            if scope == "task":
                bucket["task_level"] += 1
            elif scope == "node":
                bucket["node_level"] += 1
            elif scope == "affair":
                bucket["affair_level"] += 1

        if event_type == "human_gate_requested":
            reason = str(payload.get("reason_code") or "unknown")
            buckets[reason]["human_gate_requested"] += 1

        if event_type == "decision_finalized":
            reason = str(payload.get("reason_code") or "unknown")
            action = str(payload.get("selected_action") or "unknown")
            buckets[reason]["actions"][action] += 1

    normalized: dict[str, Any] = {}
    for reason, bucket in buckets.items():
        normalized[reason] = {
            "count": bucket["count"],
            "task_level": bucket["task_level"],
            "node_level": bucket["node_level"],
            "affair_level": bucket["affair_level"],
            "human_gate_requested": bucket["human_gate_requested"],
            "actions": dict(bucket["actions"]),
        }

    return {
        "task_uid": task_uid,
        "by_block_reason_code": normalized,
        "event_count": len(events),
    }
