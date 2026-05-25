"""v4 决策部门适配器。"""

from __future__ import annotations

from uuid import uuid4
from typing import Any

from autodoengine.core.enums import DecisionType, TaskAction, TaskStatus
from autodoengine.core.errors import ReceiptProtocolError
from autodoengine.core.types import DecisionPacket, DecisionResult
from autodoengine.utils.config_contract_utils import normalize_to_legacy_contract


_PA_ACTION_TO_TASK_ACTION = {
    "pass_next": TaskAction.CONTINUE,
    "retry_current": TaskAction.RETRY,
    "pause_current": TaskAction.SUSPEND,
    "fallback_current": TaskAction.BACKTRACK,
    "stop": TaskAction.CANCEL,
}


def _normalize_selected_action(raw_value: Any, default_action: TaskAction) -> TaskAction:
    normalized = normalize_to_legacy_contract({"decision": raw_value or default_action.value})
    if isinstance(normalized, dict):
        text = str(normalized.get("decision") or default_action.value).strip()
    else:
        text = str(raw_value or default_action.value).strip()

    mapped_action = _PA_ACTION_TO_TASK_ACTION.get(text)
    if mapped_action is not None:
        return mapped_action
    return TaskAction.normalize(text)


def _normalize_decision_mode(raw_value: Any, default_mode: str) -> str:
    normalized = normalize_to_legacy_contract({"decision_mode": raw_value or default_mode})
    if isinstance(normalized, dict):
        text = str(normalized.get("decision_mode") or default_mode).strip()
    else:
        text = str(raw_value or default_mode).strip()

    aliases = {
        "joint": "JOINT",
        "pa-only": "PA-only",
        "human-only": "HUMAN-only",
    }
    return aliases.get(text.lower(), default_mode)


def _normalize_decision_members(raw_value: Any, default_members: list[str]) -> list[str]:
    source = list(raw_value or default_members or ["pa", "human"])
    aliases = {
        "人工": "human",
        "仅人工": "human",
        "仅pa": "pa",
    }
    normalized: list[str] = []
    for item in source:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        member = aliases.get(text, aliases.get(lowered, lowered))
        if member not in normalized:
            normalized.append(member)
    return normalized or list(default_members or ["pa", "human"])


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
    selected_from_raw = _normalize_selected_action(raw_result.get("selected_action"), recommended_action)
    decision_members = _normalize_decision_members(raw_result.get("decision_members"), list(packet.decision_members or ["pa", "human"]))
    decision_mode = _normalize_decision_mode(raw_result.get("decision_mode"), str(packet.decision_mode or "JOINT"))

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

