"""v4 决策部门适配器。"""

from __future__ import annotations

from uuid import uuid4
from typing import Any

from autodoengine.core.enums import DecisionType, TaskAction, TaskStatus
from autodoengine.core.errors import ReceiptProtocolError
from autodoengine.core.types import DecisionPacket, DecisionResult


def request_pa_decision(
    packet: DecisionPacket,
    *,
    task_status_before: TaskStatus,
    pa_enabled: bool = True,
) -> DecisionResult:
    """向决策部门请求最终裁决。"""

    if not pa_enabled:
        raw = {
            "selected_action": (packet.recommended_action or TaskAction.FAIL).value,
            "reason_code": "pa_disabled_use_recommended_action",
            "reason_text": "PA 已关闭，决策部门采用候选动作推荐结果",
            "decision_mode": "HUMAN-only" if "human" in packet.decision_members else "PA-only",
            "decision_members": [item for item in packet.decision_members if item != "pa"] or ["human"],
        }
        result = normalize_decision_result(
            raw_result=raw,
            packet=packet,
            task_status_before=task_status_before,
        )
        validate_decision_result(result, packet)
        return result

    requires_human = bool((packet.receipt or {}).get("requires_human", False))
    force_human_gate = requires_human and TaskAction.HUMAN_GATE in packet.candidate_actions and "human" in packet.decision_members

    raw = {
        "selected_action": TaskAction.HUMAN_GATE.value if force_human_gate else (packet.recommended_action or TaskAction.FAIL).value,
        "reason_code": "requires_human_gate" if force_human_gate else "department_recommended",
        "reason_text": "命中 requires_human，决策部门选择 human_gate" if force_human_gate else "决策部门采用候选动作推荐结果",
        "decision_mode": packet.decision_mode,
        "decision_members": list(packet.decision_members),
    }
    result = normalize_decision_result(
        raw_result=raw,
        packet=packet,
        task_status_before=task_status_before,
    )
    validate_decision_result(result, packet)
    return result


def normalize_decision_result(
    raw_result: Any,
    *,
    packet: DecisionPacket,
    task_status_before: TaskStatus,
) -> DecisionResult:
    """把决策部门原始输出规范化为统一决策结果。"""

    if isinstance(raw_result, DecisionResult):
        return raw_result

    status_after_map = {
        TaskAction.CONTINUE: TaskStatus.RUNNING,
        TaskAction.RETRY: TaskStatus.RUNNING,
        TaskAction.BACKTRACK: TaskStatus.RUNNING,
        TaskAction.SUSPEND: TaskStatus.SUSPENDED,
        TaskAction.SPLIT: TaskStatus.SUSPENDED,
        TaskAction.HUMAN_GATE: TaskStatus.BLOCKED,
        TaskAction.COMPLETE: TaskStatus.COMPLETED,
        TaskAction.FAIL: TaskStatus.FAILED,
        TaskAction.CANCEL: TaskStatus.CANCELLED,
    }

    recommended_action = packet.recommended_action or TaskAction.FAIL
    selected_from_raw = TaskAction(str(raw_result.get("selected_action") or recommended_action.value))
    decision_members = list(raw_result.get("decision_members") or packet.decision_members or ["pa", "human"])
    decision_mode = str(raw_result.get("decision_mode") or packet.decision_mode or "JOINT")

    return DecisionResult(
        decision_uid=f"decision-{uuid4().hex[:12]}",
        task_uid=packet.task_uid,
        node_uid=packet.node_uid,
        decision_type=DecisionType.ROUTE,
        selected_action=selected_from_raw,
        task_status_before=task_status_before,
        task_status_after=status_after_map[selected_from_raw],
        next_node_uid=None,
        reason_code=str(raw_result.get("reason_code") or "na"),
        reason_text=str(raw_result.get("reason_text") or ""),
        decision_actor=str(raw_result.get("decision_actor") or "decision_department"),
        decision_members=decision_members,
        decision_mode=decision_mode,
        is_override_recommendation=selected_from_raw != recommended_action,
        override_explanation=str(raw_result.get("override_explanation") or ""),
        human_gate_request=dict(raw_result.get("human_gate_request") or {}),
        split_children=list(raw_result.get("split_children") or []),
        evidence=list(packet.evidence),
    )


def validate_decision_result(result: DecisionResult, packet: DecisionPacket) -> None:
    """校验最终裁决是否合法。"""

    if result.selected_action not in packet.candidate_actions:
        raise ReceiptProtocolError(
            f"决策部门选择了不在候选集合中的动作：{result.selected_action.value}"
        )

