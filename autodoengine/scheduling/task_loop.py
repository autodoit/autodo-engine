"""任务运行主循环（v4 决策部门口径）。"""

from __future__ import annotations

import importlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from autodoengine.core.enums import DecisionType, RelationType, ResultCode, TaskAction, TaskStatus
from autodoengine.core.types import DecisionResult, NodeContext, TaskContext, TaskStepRecord
from autodoengine.flow_graph import resolve_candidate_edges, resolve_next_node_by_edge
from autodoengine.scheduling.block_scope_lifter import lift_block_scope
from autodoengine.scheduling.candidate_actions import build_candidate_actions
from autodoengine.scheduling.decision_rule_framework import (
    resolve_decision_framework,
    should_invoke_decision_department,
)
from autodoengine.scheduling.pa_decision_adapter import request_pa_decision
from autodoengine.scheduling.result_protocol import normalize_receipt
from autodoengine.scheduling.task_dispatcher import (
    prepare_history_summary,
    prepare_node_context,
    prepare_retry_budget,
    prepare_task_context,
)
from autodoengine.taskdb import (
    decision_store,
    log_store,
    relation_store,
    snapshot_store,
    state_machine,
    step_store,
    task_store,
)
from autodoengine.utils.affair_registry import build_registry, resolve_runner
from autodoengine.utils.path_tools import resolve_paths_to_absolute


def _build_transition_decision(
    *,
    task_context: TaskContext,
    selected_action: TaskAction,
    to_status: TaskStatus,
    reason_code: str,
    reason_text: str,
) -> DecisionResult:
    """构造状态迁移型决策结果。"""

    return DecisionResult(
        decision_uid=f"decision-{uuid4().hex[:12]}",
        task_uid=task_context.task_uid,
        node_uid=task_context.current_node_uid,
        decision_type=DecisionType.ROUTE,
        selected_action=selected_action,
        task_status_before=task_context.status,
        task_status_after=to_status,
        next_node_uid=task_context.current_node_uid,
        reason_code=reason_code,
        reason_text=reason_text,
        decision_actor="decision_department",
        decision_members=["pa", "human"],
        decision_mode="JOINT",
        evidence=[],
    )


def _emit_agent_message(
    *,
    run_uid: str,
    task_uid: str,
    node_uid: str,
    from_role: str,
    to_role: str,
    intent: str,
    decision_uid_ref: str | None = None,
) -> None:
    """写入控制面信件事件。"""

    log_store.append_runtime_event(
        "agent_message_sent",
        {
            "run_uid": run_uid,
            "task_uid": task_uid,
            "node_uid": node_uid,
            "actor_role": from_role,
            "message_uid": f"msg-{uuid4().hex[:12]}",
            "from": from_role,
            "to": to_role,
            "intent": intent,
            "decision_uid_ref": decision_uid_ref,
            "created_at": datetime.now(UTC).isoformat(),
        },
    )


def _build_aa_fallback_policy(task_context: TaskContext, node_context: NodeContext) -> dict[str, Any]:
    """合并并返回 AA 兜底策略。"""

    metadata_policy = task_context.metadata.get("aa_fallback")
    task_policy = metadata_policy if isinstance(metadata_policy, dict) else {}
    node_policy_raw = node_context.policies.get("aa_fallback")
    node_policy = node_policy_raw if isinstance(node_policy_raw, dict) else {}

    merged = {**task_policy, **node_policy}
    trigger_on = merged.get("trigger_on")
    trigger_rules = (
        [str(item) for item in trigger_on if str(item).strip()] if isinstance(trigger_on, list) else []
    )
    if not trigger_rules:
        trigger_rules = ["script_exception", "blocked_non_human"]

    return {
        "enabled": bool(merged.get("enabled", True)),
        "max_attempt_per_step": max(0, int(merged.get("max_attempt_per_step", 1) or 0)),
        "trigger_on": trigger_rules,
        "timeout_sec": max(1, int(merged.get("timeout_sec", 30) or 30)),
    }


def _execute_affair_script(node_context: NodeContext, task_context: TaskContext) -> dict[str, Any]:
    """执行脚本预案（AA 快路径）。"""

    simulated = node_context.policies.get("simulate_receipt")
    if isinstance(simulated, dict):
        return dict(simulated)

    if not node_context.affair_uid:
        return {
            "result_code": ResultCode.PASS.value,
            "output_payload": {},
            "message": "无事务绑定，默认 PASS",
            "executor_meta": {"aa_handling_mode": "preset_script"},
        }

    workspace_root_raw = str(task_context.metadata.get("workspace_root") or "").strip()
    workspace_root = Path(workspace_root_raw).resolve() if workspace_root_raw else None

    registry = build_registry(strict=False, workspace_root=workspace_root)
    try:
        runner = resolve_runner(node_context.affair_uid, registry)
    except Exception:
        return {
            "result_code": ResultCode.PASS.value,
            "output_payload": {"affair_uid": node_context.affair_uid},
            "message": "未找到事务 runner，按 PASS 继续",
            "executor_meta": {"aa_handling_mode": "preset_script"},
        }

    try:
        module = importlib.import_module(str(runner["module"]))
        callable_obj = getattr(module, str(runner["callable"]))

        raw_config = dict(node_context.policies.get("affair_config") or {})
        raw_config.setdefault("task_uid", task_context.task_uid)
        raw_config.setdefault("node_uid", node_context.node_uid)

        resolved_workspace_root = workspace_root if workspace_root is not None else Path.cwd().resolve()
        raw_config.setdefault("_workspace_root", str(resolved_workspace_root))
        config = resolve_paths_to_absolute(raw_config, workspace_root=resolved_workspace_root)

        if str(runner["pass_mode"]) == "config_dict":
            result = callable_obj(config, **dict(runner.get("kwargs") or {}))
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
                json.dump(config, fp, ensure_ascii=False, indent=2)
                temp_config_path = fp.name
            result = callable_obj(temp_config_path, **dict(runner.get("kwargs") or {}))

        if isinstance(result, dict) and "result_code" in result:
            return result

        artifacts: list[str]
        if result is None:
            artifacts = []
        elif isinstance(result, (str, Path)):
            artifacts = [str(result)]
        elif isinstance(result, list):
            artifacts = [str(item) for item in result]
        else:
            artifacts = [str(result)]

        return {
            "result_code": ResultCode.PASS.value,
            "output_payload": {
                "artifacts": artifacts,
                "affair_uid": node_context.affair_uid,
            },
            "message": "事务执行完成",
            "executor_meta": {
                "runner_module": runner["module"],
                "aa_handling_mode": "preset_script",
            },
        }
    except Exception as exc:
        return {
            "result_code": ResultCode.BLOCKED.value,
            "block_reason_code": "dependency_unready",
            "block_scope": "affair",
            "retryable": True,
            "requires_human": False,
            "message": f"事务执行异常：{exc}",
            "evidence": [repr(exc)],
            "executor_meta": {
                "aa_handling_mode": "preset_script",
                "script_exception": True,
                "script_exception_repr": repr(exc),
            },
        }


def _execute_llm_fallback(
    *,
    node_context: NodeContext,
    task_context: TaskContext,
    fallback_reason_code: str,
    fallback_attempt: int,
) -> dict[str, Any]:
    """执行 LLM 兜底（AA 慢路径）。"""

    simulated = node_context.policies.get("simulate_llm_fallback_receipt")
    if isinstance(simulated, dict):
        result = dict(simulated)
    else:
        result = {
            "result_code": ResultCode.BLOCKED.value,
            "block_reason_code": "resource_exhausted",
            "block_scope": "node",
            "retryable": False,
            "requires_human": True,
            "message": "LLM 兜底未配置有效执行器，转人工闸门",
            "output_payload": {
                "task_uid": task_context.task_uid,
                "node_uid": node_context.node_uid,
            },
        }

    meta = dict(result.get("executor_meta") or {})
    meta.update(
        {
            "aa_handling_mode": "llm_fallback",
            "fallback_reason_code": fallback_reason_code,
            "fallback_attempt": fallback_attempt,
        }
    )
    result["executor_meta"] = meta
    result["aa_handling_mode"] = "llm_fallback"
    result["fallback_reason_code"] = fallback_reason_code
    result["fallback_attempt"] = fallback_attempt
    return result


def _execute_affair(
    *,
    node_context: NodeContext,
    task_context: TaskContext,
    run_uid: str,
) -> dict[str, Any]:
    """执行 AA 双模链路：脚本预案优先，必要时触发 LLM 兜底。"""

    fallback_policy = _build_aa_fallback_policy(task_context, node_context)
    script_result = _execute_affair_script(node_context, task_context)

    for key, value in {
        "aa_handling_mode": "preset_script",
        "fallback_reason_code": None,
        "fallback_attempt": 0,
    }.items():
        script_result.setdefault(key, value)

    log_store.append_runtime_event(
        "aa_execution_mode_selected",
        {
            "run_uid": run_uid,
            "task_uid": task_context.task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "AA",
            "aa_handling_mode": "preset_script",
            "fallback_reason_code": None,
            "fallback_attempt": 0,
            "decision_uid_ref": None,
            "fallback_enabled": bool(fallback_policy["enabled"]),
            "fallback_max_attempt_per_step": int(fallback_policy["max_attempt_per_step"]),
            "fallback_trigger_on": list(fallback_policy["trigger_on"]),
        },
    )

    if not bool(fallback_policy["enabled"]) or int(fallback_policy["max_attempt_per_step"]) <= 0:
        return script_result

    fallback_reason_code: str | None = None
    script_meta = script_result.get("executor_meta")
    meta = script_meta if isinstance(script_meta, dict) else {}
    trigger_rules = {str(item) for item in fallback_policy["trigger_on"]}
    block_reason_code = str(script_result.get("block_reason_code") or "")
    split_hint_enabled = bool(node_context.policies.get("force_split_hint", False))
    split_intended_block = split_hint_enabled and block_reason_code == "goal_ambiguous"

    if bool(meta.get("script_exception", False)) and "script_exception" in trigger_rules:
        fallback_reason_code = "script_exception"
    elif (
        str(script_result.get("result_code")) == ResultCode.BLOCKED.value
        and not bool(script_result.get("requires_human", False))
        and not split_intended_block
        and "blocked_non_human" in trigger_rules
    ):
        fallback_reason_code = "blocked_non_human"

    if fallback_reason_code is None:
        return script_result

    fallback_attempt = 1
    log_store.append_runtime_event(
        "aa_fallback_triggered",
        {
            "run_uid": run_uid,
            "task_uid": task_context.task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "AA",
            "aa_handling_mode": "llm_fallback",
            "fallback_reason_code": fallback_reason_code,
            "fallback_attempt": fallback_attempt,
            "decision_uid_ref": None,
        },
    )

    fallback_result = _execute_llm_fallback(
        node_context=node_context,
        task_context=task_context,
        fallback_reason_code=fallback_reason_code,
        fallback_attempt=fallback_attempt,
    )

    fallback_event_type = (
        "aa_fallback_failed"
        if str(fallback_result.get("result_code")) == ResultCode.BLOCKED.value
        else "aa_fallback_completed"
    )
    log_store.append_runtime_event(
        fallback_event_type,
        {
            "run_uid": run_uid,
            "task_uid": task_context.task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "AA",
            "aa_handling_mode": "llm_fallback",
            "fallback_reason_code": fallback_reason_code,
            "fallback_attempt": fallback_attempt,
            "decision_uid_ref": None,
            "result_code": fallback_result.get("result_code"),
        },
    )

    return fallback_result


def _maybe_resume_task(task_context: TaskContext) -> DecisionResult | None:
    """处理 suspended/blocked 的恢复逻辑。"""

    if task_context.status == TaskStatus.SUSPENDED:
        child_relations = relation_store.list_children(task_context.task_uid)
        if child_relations:
            child_statuses = [
                TaskStatus(task_store.get_task(item["child_task_uid"])["status"])
                for item in child_relations
            ]
            if state_machine.can_resume_task(task_context.status, child_statuses):
                state_machine.apply_transition(task_context.task_uid, task_context.status, TaskStatus.READY)
                return _build_transition_decision(
                    task_context=task_context,
                    selected_action=TaskAction.CONTINUE,
                    to_status=TaskStatus.READY,
                    reason_code="resume_children_completed",
                    reason_text="子任务已完成，父任务恢复到 ready",
                )

    if task_context.status == TaskStatus.BLOCKED:
        if bool(task_context.metadata.get("human_gate_approved", False)):
            state_machine.apply_transition(task_context.task_uid, task_context.status, TaskStatus.READY)
            task_store.update_task_metadata(
                task_context.task_uid,
                {
                    "human_gate_approved": False,
                    "human_gate_pending": False,
                },
            )
            log_store.append_runtime_event(
                "human_gate_resolved",
                {
                    "task_uid": task_context.task_uid,
                    "node_uid": task_context.current_node_uid,
                    "reason": "human_gate_approved",
                },
            )
            return _build_transition_decision(
                task_context=task_context,
                selected_action=TaskAction.CONTINUE,
                to_status=TaskStatus.READY,
                reason_code="human_gate_approved",
                reason_text="人工闸门已确认，任务恢复到 ready",
            )

    return None


def apply_decision_result(
    *,
    task_uid: str,
    before_status: TaskStatus,
    decision_result: DecisionResult,
) -> None:
    """按最终动作回写任务状态。"""

    if before_status == decision_result.task_status_after:
        task_store.update_task_status(task_uid, decision_result.task_status_after)
        return
    state_machine.apply_transition(task_uid, before_status, decision_result.task_status_after)


def write_task_step_records(
    *,
    step_record: TaskStepRecord,
    decision_result: DecisionResult,
    packet: Any,
) -> TaskStepRecord:
    """写入任务步、决策和运行日志。"""

    step_store.append_task_step(step_record)
    decision_store.append_decision(decision_result, packet)
    log_store.append_runtime_event(
        "action_effect_recorded",
        {
            "run_uid": step_record.run_uid,
            "task_uid": step_record.task_uid,
            "step_uid": step_record.step_uid,
            "node_uid": step_record.node_uid_after,
            "actor_role": "TA",
            "event_type": "action_effect_recorded",
            "observation_packet_ref": getattr(packet, "packet_uid", None),
            "candidate_actions_json": [item.value for item in getattr(packet, "candidate_actions", [])],
            "selected_action": step_record.selected_action.value,
            "decision_uid": decision_result.decision_uid,
            "decision_uid_ref": decision_result.decision_uid,
            "reason_code": decision_result.reason_code,
            "reason_text": decision_result.reason_text,
            "evidence_refs": list(decision_result.evidence),
            "task_status_before": step_record.task_status_before.value,
            "task_status_after": step_record.task_status_after.value,
            "artifact_refs": list(getattr(packet, "artifact_refs", [])),
            "aa_handling_mode": str((getattr(packet, "receipt", {}) or {}).get("aa_handling_mode") or "preset_script"),
            "fallback_reason_code": (getattr(packet, "receipt", {}) or {}).get("fallback_reason_code"),
            "fallback_attempt": int((getattr(packet, "receipt", {}) or {}).get("fallback_attempt") or 0),
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    return step_record


def _handle_split(task_context: TaskContext, node_context: NodeContext, packet: Any) -> list[str]:
    """处理 split 子任务创建。"""

    split_children = ((packet.receipt or {}).get("output_payload") or {}).get("split_children")
    if not isinstance(split_children, list) or not split_children:
        split_children = node_context.policies.get("split_children")

    child_specs: list[dict[str, Any]]
    if isinstance(split_children, list) and split_children:
        child_specs = [item for item in split_children if isinstance(item, dict)]
    else:
        child_specs = [
            {
                "title": f"{task_context.goal_text}-子任务",
                "goal_text": f"拆分自 {task_context.task_uid}",
                "current_node_uid": node_context.node_uid,
            }
        ]

    child_uids: list[str] = []
    for item in child_specs:
        child = task_store.create_task(
            title=str(item.get("title") or f"子任务-{node_context.node_uid}"),
            goal_text=str(item.get("goal_text") or task_context.goal_text),
            current_node_uid=str(item.get("current_node_uid") or node_context.node_uid),
            parent_task_uid=task_context.task_uid,
        )
        child_uids.append(str(child["task_uid"]))
        relation_store.create_task_relation(
            task_context.task_uid,
            str(child["task_uid"]),
            RelationType.SPLIT.value,
        )

    task_store.update_task_metadata(
        task_context.task_uid,
        {
            "split_children": child_uids,
            "awaiting_children": True,
        },
    )
    return child_uids


def _enrich_packet_for_pa_artifact_review(packet: Any, node_context: NodeContext) -> None:
    """按规则触发 PA 直读产物。"""

    if not hasattr(packet, "artifact_refs"):
        return

    missing_evidence = len(getattr(packet, "evidence", []) or []) == 0
    high_risk = str(node_context.risk_level or "").lower() in {"high", "critical", "severe"}
    recommendation_conflict = len({
        str(item.get("recommendation"))
        for item in (getattr(packet, "agent_recommendations", []) or [])
        if isinstance(item, dict)
    }) > 1

    if high_risk or missing_evidence or recommendation_conflict:
        packet.decision_mode = "JOINT"
        packet.observation_missing_fields = list(getattr(packet, "observation_missing_fields", []) or [])
        if missing_evidence and "evidence" not in packet.observation_missing_fields:
            packet.observation_missing_fields.append("evidence")


def _build_pa_artifact_review_reasons(packet: Any, node_context: NodeContext) -> list[str]:
    """返回触发 PA 直读产物的原因列表。"""

    reasons: list[str] = []
    if str(node_context.risk_level or "").lower() in {"high", "critical", "severe"}:
        reasons.append("high_risk_node")
    if len(getattr(packet, "evidence", []) or []) == 0:
        reasons.append("missing_evidence")

    recommendations = {
        str(item.get("recommendation"))
        for item in (getattr(packet, "agent_recommendations", []) or [])
        if isinstance(item, dict)
    }
    if len(recommendations) > 1:
        reasons.append("recommendation_conflict")
    return reasons


def run_task_step(
    *,
    task_uid: str,
    graph: Any,
    run_uid: str,
) -> DecisionResult:
    """执行一个任务步闭环。"""

    task_context = prepare_task_context(task_uid, graph.graph_uid)

    resumed = _maybe_resume_task(task_context)
    if resumed is not None:
        step_record = TaskStepRecord(
            step_uid=f"step-{uuid4().hex[:12]}",
            run_uid=run_uid,
            task_uid=task_uid,
            node_uid_before=task_context.current_node_uid,
            node_uid_after=task_context.current_node_uid,
            selected_action=resumed.selected_action,
            selected_edge_uid=None,
            task_status_before=task_context.status,
            task_status_after=resumed.task_status_after,
            decision_uid=resumed.decision_uid,
        )
        write_task_step_records(step_record=step_record, decision_result=resumed, packet={"resume": True})
        return resumed

    if task_context.status == TaskStatus.READY:
        state_machine.apply_transition(task_uid, TaskStatus.READY, TaskStatus.RUNNING)
        task_context.status = TaskStatus.RUNNING

    node_context = prepare_node_context(graph, task_context)
    if bool(node_context.policies.get("goal_satisfied_at_node", False)):
        task_context.metadata["goal_satisfied"] = True

    retry_budget = prepare_retry_budget(task_context)
    history_summary = prepare_history_summary(step_store, task_uid)
    if bool(node_context.policies.get("force_split_hint", False)):
        history_summary["split_hint"] = True

    _emit_agent_message(
        run_uid=run_uid,
        task_uid=task_uid,
        node_uid=node_context.node_uid,
        from_role="TA",
        to_role="NA",
        intent="dispatch_node_execution",
    )
    _emit_agent_message(
        run_uid=run_uid,
        task_uid=task_uid,
        node_uid=node_context.node_uid,
        from_role="NA",
        to_role="AA",
        intent="execute_affair",
    )

    raw_receipt = _execute_affair(
        node_context=node_context,
        task_context=task_context,
        run_uid=run_uid,
    )

    _emit_agent_message(
        run_uid=run_uid,
        task_uid=task_uid,
        node_uid=node_context.node_uid,
        from_role="AA",
        to_role="NA",
        intent="return_receipt",
    )
    _emit_agent_message(
        run_uid=run_uid,
        task_uid=task_uid,
        node_uid=node_context.node_uid,
        from_role="NA",
        to_role="TA",
        intent="submit_observation",
    )

    receipt = normalize_receipt(raw_receipt, node_context=node_context)

    lift_result = lift_block_scope(
        receipt=receipt,
        node_context=node_context,
        task_context=task_context,
        history_summary=history_summary,
    )
    if receipt.result_code == ResultCode.BLOCKED:
        receipt.block_scope = lift_result.lifted_scope
        if lift_result.is_lifted:
            log_store.append_runtime_event(
                "block_scope_lifted",
                {
                    "task_uid": task_uid,
                    "node_uid": node_context.node_uid,
                    "from_scope": lift_result.original_scope.value,
                    "to_scope": lift_result.lifted_scope.value,
                    "reason": lift_result.reason,
                },
            )

    log_store.append_runtime_event(
        "receipt_normalized",
        {
            "run_uid": run_uid,
            "task_uid": task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "AA",
            "result_code": receipt.result_code.value,
            "block_reason_code": receipt.block_reason_code.value if receipt.block_reason_code else None,
            "block_scope": receipt.block_scope.value if receipt.block_scope else None,
            "requires_human": receipt.requires_human,
            "evidence_refs": list(receipt.evidence),
            "aa_handling_mode": receipt.aa_handling_mode,
            "fallback_reason_code": receipt.fallback_reason_code,
            "fallback_attempt": receipt.fallback_attempt,
            "decision_uid_ref": None,
        },
    )

    packet = build_candidate_actions(
        receipt=receipt,
        task_context=task_context,
        node_context=node_context,
        retry_budget=retry_budget,
        history_summary=history_summary,
    )

    _enrich_packet_for_pa_artifact_review(packet, node_context)
    pa_artifact_review_reasons = _build_pa_artifact_review_reasons(packet, node_context)
    if pa_artifact_review_reasons:
        log_store.append_runtime_event(
            "pa_artifact_review_requested",
            {
                "run_uid": run_uid,
                "task_uid": task_uid,
                "node_uid": node_context.node_uid,
                "actor_role": "PA",
                "packet_uid": packet.packet_uid,
                "reasons": pa_artifact_review_reasons,
                "artifact_refs": list(packet.artifact_refs),
            },
        )

    framework = resolve_decision_framework(
        graph_policies=dict(graph.policies or {}),
        node_context=node_context,
    )
    packet.decision_members = list(framework.get("members") or ["pa", "human"])
    packet.decision_mode = str(framework.get("decision_mode") or packet.decision_mode or "JOINT")

    log_store.append_runtime_event(
        "observation_packet_built",
        {
            "run_uid": run_uid,
            "task_uid": task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "TA",
            "packet_uid": packet.packet_uid,
            "candidate_actions_json": [item.value for item in packet.candidate_actions],
            "observation_packet_ref": packet.packet_uid,
            "artifact_refs": list(packet.artifact_refs),
            "observation_missing_fields": list(packet.observation_missing_fields),
        },
    )
    log_store.append_runtime_event(
        "agent_recommendation_submitted",
        {
            "run_uid": run_uid,
            "task_uid": task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "TA",
            "packet_uid": packet.packet_uid,
            "agent_recommendations": packet.agent_recommendations,
        },
    )

    should_invoke = should_invoke_decision_department(
        result_code=receipt.result_code,
        framework=framework,
    )
    if not should_invoke:
        packet.decision_members = ["pa"]
        packet.decision_mode = "PA-only"

    pa_enabled = not bool(task_context.metadata.get("disable_pa", False))
    decision_call_actor = "TA"
    if decision_call_actor != "TA":
        raise RuntimeError("v4 约束违反：仅 TA 可调用决策部门")

    log_store.append_runtime_event(
        "decision_department_invoked",
        {
            "run_uid": run_uid,
            "task_uid": task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "TA",
            "packet_uid": packet.packet_uid,
            "decision_members": packet.decision_members,
            "decision_mode": packet.decision_mode,
            "observation_packet_ref": packet.packet_uid,
            "decision_entry_actor": decision_call_actor,
        },
    )
    decision_result = request_pa_decision(
        packet,
        task_status_before=task_context.status,
        pa_enabled=pa_enabled,
    )

    if decision_result.decision_actor.lower() in {"ta", "na", "aa"}:
        raise RuntimeError("v4 约束违反：TA/NA/AA 不具备最终裁决权")

    log_store.append_runtime_event(
        "decision_finalized",
        {
            "run_uid": run_uid,
            "task_uid": task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "PA",
            "packet_uid": packet.packet_uid,
            "decision_uid": decision_result.decision_uid,
            "selected_action": decision_result.selected_action.value,
            "reason_code": decision_result.reason_code,
            "reason_text": decision_result.reason_text,
            "decision_members": decision_result.decision_members,
            "decision_mode": decision_result.decision_mode,
            "is_override_recommendation": decision_result.is_override_recommendation,
            "evidence_refs": list(decision_result.evidence),
            "artifact_refs": list(packet.artifact_refs),
            "task_status_before": task_context.status.value,
            "task_status_after": decision_result.task_status_after.value,
            "aa_handling_mode": receipt.aa_handling_mode,
            "fallback_reason_code": receipt.fallback_reason_code,
            "fallback_attempt": receipt.fallback_attempt,
            "decision_uid_ref": decision_result.decision_uid,
        },
    )

    selected_edge_uid: str | None = None
    node_uid_after = node_context.node_uid

    log_store.append_runtime_event(
        "action_dispatched",
        {
            "run_uid": run_uid,
            "task_uid": task_uid,
            "node_uid": node_context.node_uid,
            "actor_role": "TA",
            "decision_uid": decision_result.decision_uid,
            "selected_action": decision_result.selected_action.value,
            "decision_uid_ref": decision_result.decision_uid,
        },
    )

    if decision_result.selected_action in {TaskAction.CONTINUE, TaskAction.BACKTRACK}:
        candidates = resolve_candidate_edges(graph, task_context=task_context, node_context=node_context)
        if candidates:
            selected_edge_uid = candidates[0].edge_uid
            next_node = resolve_next_node_by_edge(graph, selected_edge_uid)
            node_uid_after = next_node.node_uid
            decision_result.next_node_uid = node_uid_after
            task_store.update_task_cursor(
                task_uid,
                current_node_uid=node_uid_after,
                current_affair_uid=next_node.affair_uid,
            )
    elif decision_result.selected_action == TaskAction.RETRY:
        task_store.bump_retry_count(task_uid)
    elif decision_result.selected_action == TaskAction.HUMAN_GATE:
        decision_result.human_gate_request = {
            "task_uid": task_uid,
            "node_uid": node_context.node_uid,
            "reason_code": decision_result.reason_code,
            "reason_text": decision_result.reason_text,
        }
        task_store.update_task_metadata(
            task_uid,
            {
                "human_gate_pending": True,
                "human_gate_approved": False,
                "human_gate_reason": decision_result.reason_code,
            },
        )
        snapshot_store.create_snapshot(
            task_uid,
            "human_gate_request",
            {
                "node_uid": node_context.node_uid,
                "reason_code": decision_result.reason_code,
                "reason_text": decision_result.reason_text,
            },
        )
        log_store.append_blocked_event(
            "human_gate_requested",
            {
                "run_uid": run_uid,
                "task_uid": task_uid,
                "node_uid": node_context.node_uid,
                "reason_code": decision_result.reason_code,
            },
        )
    elif decision_result.selected_action == TaskAction.SPLIT:
        child_uids = _handle_split(task_context, node_context, packet)
        decision_result.split_children = child_uids

    apply_decision_result(
        task_uid=task_uid,
        before_status=task_context.status,
        decision_result=decision_result,
    )

    step_record = TaskStepRecord(
        step_uid=f"step-{uuid4().hex[:12]}",
        run_uid=run_uid,
        task_uid=task_uid,
        node_uid_before=node_context.node_uid,
        node_uid_after=node_uid_after,
        selected_action=decision_result.selected_action,
        selected_edge_uid=selected_edge_uid,
        task_status_before=task_context.status,
        task_status_after=decision_result.task_status_after,
        decision_uid=decision_result.decision_uid,
    )
    write_task_step_records(step_record=step_record, decision_result=decision_result, packet=packet)
    return decision_result


def run_task_until_wait(
    *,
    task_uid: str,
    graph: Any,
    max_steps: int = 100,
) -> list[DecisionResult]:
    """持续执行直到任务进入等待型状态。"""

    run_uid = f"run-{uuid4().hex[:12]}"
    decisions: list[DecisionResult] = []
    for _ in range(max_steps):
        decision = run_task_step(task_uid=task_uid, graph=graph, run_uid=run_uid)
        decisions.append(decision)
        if decision.task_status_after in {TaskStatus.SUSPENDED, TaskStatus.BLOCKED}:
            return decisions
        if decision.task_status_after in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return decisions
    return decisions


def run_task_until_terminal(
    *,
    task_uid: str,
    graph: Any,
    max_steps: int = 100,
) -> list[DecisionResult]:
    """持续执行直到任务进入终止态。"""

    run_uid = f"run-{uuid4().hex[:12]}"
    decisions: list[DecisionResult] = []
    for _ in range(max_steps):
        decision = run_task_step(task_uid=task_uid, graph=graph, run_uid=run_uid)
        decisions.append(decision)
        if decision.task_status_after in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return decisions
    return decisions

