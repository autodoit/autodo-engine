"""候选动作包生成器。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from autodoengine.core.enums import DecisionType, TaskAction
from autodoengine.core.types import DecisionPacket, NodeContext, ResultReceipt, RetryBudget, TaskContext
from autodoengine.utils.time_utils import now_iso
from . import action_rules
from .result_protocol import receipt_to_dict

_ACTION_PRIORITY = [
    TaskAction.HUMAN_GATE,
    TaskAction.SPLIT,
    TaskAction.BACKTRACK,
    TaskAction.RETRY,
    TaskAction.SUSPEND,
    TaskAction.CONTINUE,
    TaskAction.COMPLETE,
    TaskAction.FAIL,
    TaskAction.CANCEL,
]


def _build_artifact_refs(paths: list[str], *, source_action: TaskAction | None) -> list[dict[str, str]]:
    """构建产物引用列表。"""

    refs: list[dict[str, str]] = []
    for item in paths:
        p = Path(item)
        digest = ""
        if p.exists() and p.is_file():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        refs.append(
            {
                "path": item,
                "version": "latest",
                "hash": f"sha256:{digest}" if digest else "",
                "generated_at": now_iso(),
                "source_action": (source_action or TaskAction.CONTINUE).value,
            }
        )
    return refs


def collect_rule_hits(
    *,
    receipt: ResultReceipt,
    task_context: TaskContext,
    node_context: NodeContext,
    retry_budget: RetryBudget,
    history_summary: dict[str, object],
) -> list[str]:
    """收集候选动作生成阶段命中的规则。"""

    hits: list[str] = []
    if action_rules.should_retry(receipt=receipt, retry_budget=retry_budget):
        hits.append("should_retry")
    if action_rules.should_backtrack(receipt=receipt, retry_budget=retry_budget):
        hits.append("should_backtrack")
    if action_rules.should_split(
        receipt=receipt,
        node_context=node_context,
        history_summary=history_summary,
    ):
        hits.append("should_split")
    if action_rules.should_suspend(receipt=receipt):
        hits.append("should_suspend")
    if action_rules.should_request_human_gate(receipt=receipt, node_context=node_context):
        hits.append("should_request_human_gate")
    if action_rules.should_complete(receipt=receipt, task_context=task_context):
        hits.append("should_complete")
    if action_rules.should_fail(receipt=receipt, task_context=task_context):
        hits.append("should_fail")
    if action_rules.should_continue(receipt=receipt):
        hits.append("should_continue")
    return hits


def rank_candidate_actions(actions: list[TaskAction]) -> list[TaskAction]:
    """按固定优先级排序候选动作。"""

    unique_actions = list(dict.fromkeys(actions))
    rank_map = {action: index for index, action in enumerate(_ACTION_PRIORITY)}
    return sorted(unique_actions, key=lambda item: rank_map[item])


def build_decision_packet(
    *,
    task_context: TaskContext,
    node_context: NodeContext,
    receipt: ResultReceipt,
    candidate_actions: list[TaskAction],
    rule_hits: list[str],
) -> DecisionPacket:
    """构造提交给决策部门的观测包。"""

    ranked_actions = rank_candidate_actions(candidate_actions)
    recommended_action = ranked_actions[0] if ranked_actions else None
    artifact_values = (receipt.output_payload or {}).get("artifacts")
    artifacts = [str(item) for item in artifact_values] if isinstance(artifact_values, list) else []
    agent_recommendations: list[dict[str, str]] = [
        {
            "actor": "TA",
            "recommendation": (recommended_action or TaskAction.FAIL).value,
            "reason": "rule_hit_priority",
        }
    ]
    if receipt.requires_human:
        agent_recommendations.append(
            {
                "actor": "NA",
                "recommendation": TaskAction.HUMAN_GATE.value,
                "reason": "requires_human_true",
            }
        )
    if receipt.result_code.value == "BLOCKED":
        agent_recommendations.append(
            {
                "actor": "AA",
                "recommendation": TaskAction.HUMAN_GATE.value if receipt.requires_human else TaskAction.SUSPEND.value,
                "reason": str(receipt.block_reason_code.value if receipt.block_reason_code else "blocked"),
            }
        )

    return DecisionPacket(
        packet_uid=f"packet-{uuid4().hex[:12]}",
        task_uid=task_context.task_uid,
        node_uid=node_context.node_uid,
        decision_type=DecisionType.ROUTE,
        task_summary={
            "task_uid": task_context.task_uid,
            "task_status": task_context.status.value,
            "current_node_uid": task_context.current_node_uid,
            "retry_count": task_context.retry_count,
        },
        node_summary={
            "node_uid": node_context.node_uid,
            "node_type": node_context.node_type,
            "risk_level": node_context.risk_level,
        },
        receipt=receipt_to_dict(receipt),
        candidate_actions=ranked_actions,
        recommended_action=recommended_action,
        rule_hits=rule_hits,
        agent_recommendations=agent_recommendations,
        artifact_refs=_build_artifact_refs(artifacts, source_action=recommended_action),
        risk_score_hint=1.0 if receipt.requires_human else None,
        observation_missing_fields=[],
        decision_members=["pa", "human"],
        decision_mode="JOINT",
        evidence=receipt.evidence,
    )


def build_candidate_actions(
    *,
    receipt: ResultReceipt,
    task_context: TaskContext,
    node_context: NodeContext,
    retry_budget: RetryBudget,
    history_summary: dict[str, object],
) -> DecisionPacket:
    """生成候选动作包。"""

    actions: list[TaskAction] = []
    if action_rules.should_request_human_gate(receipt=receipt, node_context=node_context):
        actions.append(TaskAction.HUMAN_GATE)
    if action_rules.should_split(
        receipt=receipt,
        node_context=node_context,
        history_summary=history_summary,
    ):
        actions.append(TaskAction.SPLIT)
    if action_rules.should_backtrack(receipt=receipt, retry_budget=retry_budget):
        actions.append(TaskAction.BACKTRACK)
    if action_rules.should_retry(receipt=receipt, retry_budget=retry_budget):
        actions.append(TaskAction.RETRY)
    if action_rules.should_suspend(receipt=receipt):
        actions.append(TaskAction.SUSPEND)
    if action_rules.should_complete(receipt=receipt, task_context=task_context):
        actions.append(TaskAction.COMPLETE)
    elif action_rules.should_continue(receipt=receipt):
        actions.append(TaskAction.CONTINUE)
    if action_rules.should_fail(receipt=receipt, task_context=task_context):
        actions.append(TaskAction.FAIL)

    if not actions:
        actions = [TaskAction.FAIL]

    rule_hits = collect_rule_hits(
        receipt=receipt,
        task_context=task_context,
        node_context=node_context,
        retry_budget=retry_budget,
        history_summary=history_summary,
    )
    return build_decision_packet(
        task_context=task_context,
        node_context=node_context,
        receipt=receipt,
        candidate_actions=actions,
        rule_hits=rule_hits,
    )

