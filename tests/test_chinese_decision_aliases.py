from __future__ import annotations

from autodoengine.core.enums import DecisionType, TaskAction, TaskStatus
from autodoengine.core.types import DecisionPacket, NodeContext
from autodoengine.scheduling.decision_rule_framework import resolve_decision_framework
from autodoengine.scheduling.pa_decision_adapter import normalize_decision_result


def test_resolve_decision_framework_should_accept_chinese_route_and_mode() -> None:
    node = NodeContext(
        node_uid="node-1",
        node_type="process",
        affair_uid="affair-1",
        risk_level="normal",
        policies={
            "route_mode": "决策",
            "decision_department": {
                "intervention_condition": "总是",
                "members": ["人工"],
                "decision_mode": "仅人工",
            },
        },
    )

    framework = resolve_decision_framework(graph_policies={}, node_context=node)

    assert framework["route_mode"] == "decision"
    assert framework["intervention_condition"] == "always"
    assert framework["members"] == ["human"]
    assert framework["decision_mode"] == "HUMAN-only"


def test_normalize_decision_result_should_accept_chinese_pa_action_aliases() -> None:
    packet = DecisionPacket(
        packet_uid="packet-1",
        task_uid="task-1",
        node_uid="node-1",
        decision_type=DecisionType.ROUTE,
        task_summary={},
        node_summary={},
        receipt={},
        candidate_actions=[TaskAction.CONTINUE, TaskAction.BACKTRACK, TaskAction.SUSPEND],
        recommended_action=TaskAction.CONTINUE,
        rule_hits=[],
        decision_members=["pa", "human"],
        decision_mode="JOINT",
        evidence=[],
    )

    result = normalize_decision_result(
        raw_result={
            "selected_action": "回退当前",
            "decision_mode": "仅人工",
            "decision_members": ["人工"],
        },
        packet=packet,
        task_status_before=TaskStatus.RUNNING,
    )

    assert result.selected_action == TaskAction.BACKTRACK
    assert result.task_status_after == TaskStatus.RUNNING
    assert result.decision_mode == "HUMAN-only"
    assert result.decision_members == ["human"]