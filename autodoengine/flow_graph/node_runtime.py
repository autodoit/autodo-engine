"""节点运行时（Node Runtime）。

本模块提供基于节点内容分发的执行入口，用于 S2 阶段并行运行新链路。
- 调度层负责执行顺序（`flow`/`flow_groups`）；
- Node Runtime 负责单节点执行、trace 记录、错误分层；
- 内容处理由 `content_handlers` 分发到 `affair/subgraph` 处理器。
"""

from __future__ import annotations

import datetime as _dt
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping

from autodoengine.utils.node_execution import NodeExecutionResult
from autodoengine.utils.time_utils import now_compact, now_iso
from autodoengine.utils.governance import (
    GovernanceRoleConfig,
    build_governance_role_config,
    run_governance_check,
)

from .content_handlers import dispatch_content_handler


AffairExecutor = Callable[[str], NodeExecutionResult]
SubgraphExecutor = Callable[[Path], NodeExecutionResult]


@dataclass(slots=True)
class NodeRuntimeTraceEvent:
    """节点运行时 trace 事件。

    Args:
        event: 事件类型。
        node_uid: 节点 uid。
        payload: 事件载荷。
    """

    event: str
    node_uid: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典。

        Returns:
            结构化事件字典。
        """

        return {
            "timestamp": now_iso(timespec="seconds"),
            "event": self.event,
            "node_uid": self.node_uid,
            "payload": dict(self.payload or {}),
        }


@dataclass(slots=True)
class NodeRuntimeSummary:
    """节点运行时汇总信息。

    Args:
        run_id: 运行标识。
        visited: 已访问节点列表。
        failed: 失败节点消息列表。
        trace_events: trace 事件列表。
    """

    run_id: str
    visited: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    trace_events: List[NodeRuntimeTraceEvent] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class NodeRuntimeRetryConfig:
    """Node Runtime 重试配置。

    Args:
        enabled: 是否启用重试。
        max_attempts: 最大尝试次数（含首次执行）。
        backoff_seconds: 重试间隔秒数。
        retryable_only: 是否仅对 retryable 错误重试。
    """

    enabled: bool = False
    max_attempts: int = 1
    backoff_seconds: float = 0.0
    retryable_only: bool = True


def _classify_error(exc: Exception) -> str:
    """错误分层分类。

    Args:
        exc: 捕获到的异常。

    Returns:
        错误类型标签：`retryable` 或 `non_retryable`。
    """

    retryable_types = (TimeoutError, ConnectionError)
    if isinstance(exc, retryable_types):
        return "retryable"
    return "non_retryable"


def _run_governance(
    *,
    profile: GovernanceRoleConfig,
    check: str,
    context: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    """运行治理检查并返回通过状态与审计数据。

    Args:
        profile: 治理角色配置。
        check: 检查项。
        context: 上下文字典。

    Returns:
        tuple[bool, Dict[str, Any]]: (是否通过, 决策摘要)。
    """

    decision = run_governance_check(profile=profile, check=check, context=context)
    return decision.passed, {
        "role": decision.role,
        "check": decision.check,
        "passed": decision.passed,
        "reason": decision.reason,
        "error_code": decision.error_code,
        "source": decision.source,
        "fail_mode": decision.fail_mode,
    }


def _resolve_flow_order(workflow: Mapping[str, Any]) -> List[str]:
    """解析节点执行顺序。

    优先读取 `flow_groups`，否则回退到 `flow`。

    Args:
        workflow: 工作流配置。

    Returns:
        节点 uid 扁平顺序列表。
    """

    flow_groups = workflow.get("flow_groups")
    if isinstance(flow_groups, list):
        flattened: List[str] = []
        for group in flow_groups:
            if not isinstance(group, list):
                continue
            for item in group:
                if isinstance(item, str) and item.strip():
                    flattened.append(item.strip())
        if flattened:
            return flattened

    flow = workflow.get("flow")
    if isinstance(flow, list):
        return [str(item).strip() for item in flow if isinstance(item, str) and str(item).strip()]
    return []


def _build_runtime_metrics(
    *,
    events: List[NodeRuntimeTraceEvent],
    visited: List[str],
    failed: List[str],
) -> Dict[str, Any]:
    """构建 Node Runtime 指标摘要。

    Args:
        events: trace 事件列表。
        visited: 成功节点列表。
        failed: 失败信息列表。

    Returns:
        Dict[str, Any]: 指标字典。
    """

    event_counts: Dict[str, int] = {}
    for item in events:
        event_counts[item.event] = event_counts.get(item.event, 0) + 1

    governance_decisions = 0
    governance_failures = 0
    for item in events:
        if item.event != "governance_decision":
            continue
        governance_decisions += 1
        decision = item.payload.get("decision")
        if isinstance(decision, dict) and not bool(decision.get("passed", True)):
            governance_failures += 1

    return {
        "event_counts": event_counts,
        "node_retry_count": event_counts.get("node_retry", 0),
        "governance_warning_count": event_counts.get("governance_warning", 0),
        "governance_decision_count": governance_decisions,
        "governance_failure_count": governance_failures,
        "nodes_succeeded": len(visited),
        "fail_messages": len(failed),
    }


def _read_retry_config(workflow: Mapping[str, Any]) -> NodeRuntimeRetryConfig:
    """读取 Node Runtime 重试配置。

    Args:
        workflow: 工作流配置。

    Returns:
        NodeRuntimeRetryConfig: 重试配置。
    """

    runtime_cfg = workflow.get("node_runtime") if isinstance(workflow.get("node_runtime"), Mapping) else {}
    retry_cfg = runtime_cfg.get("retry") if isinstance(runtime_cfg.get("retry"), Mapping) else {}

    enabled = bool(retry_cfg.get("enabled", False))
    max_attempts = max(1, int(retry_cfg.get("max_attempts") or 1))
    backoff_seconds = max(0.0, float(retry_cfg.get("backoff_seconds") or 0.0))
    retryable_only = bool(retry_cfg.get("retryable_only", True))
    return NodeRuntimeRetryConfig(
        enabled=enabled,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
        retryable_only=retryable_only,
    )


def _should_retry(
    *,
    error_type: str,
    attempt: int,
    retry_config: NodeRuntimeRetryConfig,
) -> bool:
    """判断是否继续重试。

    Args:
        error_type: 错误类型。
        attempt: 当前尝试次数（从 1 开始）。
        retry_config: 重试配置。

    Returns:
        bool: 是否应重试。
    """

    if not retry_config.enabled:
        return False
    if attempt >= retry_config.max_attempts:
        return False
    if retry_config.retryable_only:
        return str(error_type or "").strip().lower() == "retryable"
    return True


def run_node_runtime_workflow(
    *,
    workflow: Mapping[str, Any],
    workflow_path: Path,
    workspace_root: Path,
    strict: bool,
    dry_run: bool,
    execute_affair: AffairExecutor,
    execute_subgraph: SubgraphExecutor,
) -> NodeRuntimeSummary:
    """运行 Node Runtime 链路。

    Args:
        workflow: 工作流配置。
        workflow_path: workflow 文件路径。
        workspace_root: 工作区根目录。
        strict: 严格模式（失败即中断）。
        dry_run: 是否 dry-run。
        execute_affair: 事务执行函数。
        execute_subgraph: 子流程图执行函数。

    Returns:
        NodeRuntimeSummary：运行摘要。

    Raises:
        RuntimeError: 严格模式下遇到失败时抛出。
    """

    run_id = uuid.uuid4().hex
    summary = NodeRuntimeSummary(run_id=run_id)
    retry_config = _read_retry_config(workflow)

    governance_cfg = workflow.get("governance") if isinstance(workflow.get("governance"), Mapping) else {}
    process_officer_raw = governance_cfg.get("process_officer") if isinstance(governance_cfg.get("process_officer"), Mapping) else {}
    node_officer_raw = governance_cfg.get("node_officer") if isinstance(governance_cfg.get("node_officer"), Mapping) else {}
    process_officer = build_governance_role_config(dict(process_officer_raw), role="process_officer")
    node_officer = build_governance_role_config(dict(node_officer_raw), role="node_officer")

    control_flow = workflow.get("control_flow")
    control_nodes = control_flow.get("nodes") if isinstance(control_flow, Mapping) else {}
    if not isinstance(control_nodes, Mapping):
        control_nodes = {}

    resolved_flow = _resolve_flow_order(workflow)
    if not resolved_flow:
        raise RuntimeError(f"Node Runtime 无可执行节点：{workflow_path}")

    def _append_trace(event: str, node_uid: str, **payload: Any) -> None:
        """追加 trace 事件。"""

        summary.trace_events.append(NodeRuntimeTraceEvent(event=event, node_uid=node_uid, payload=dict(payload)))

    runtime_cfg = workflow.get("node_runtime") if isinstance(workflow.get("node_runtime"), Mapping) else {}
    governance_retry_attempts = max(1, int(runtime_cfg.get("governance_retry_attempts") or 1))

    def _handle_governance(
        *,
        profile: GovernanceRoleConfig,
        check: str,
        context: Dict[str, Any],
        trace_node_uid: str,
        stage: str,
    ) -> bool:
        """按 fail_mode 执行治理判定。

        Args:
            profile: 治理配置。
            check: 检查项。
            context: 判定上下文。
            trace_node_uid: trace 记录节点 uid。
            stage: 事件阶段名。

        Returns:
            bool: 是否继续执行。
        """

        attempts = governance_retry_attempts if profile.fail_mode == "retry" else 1
        for attempt in range(1, attempts + 1):
            passed, decision = _run_governance(profile=profile, check=check, context=context)
            _append_trace(
                "governance_decision",
                trace_node_uid,
                stage=stage,
                attempt=attempt,
                max_attempts=attempts,
                decision=decision,
            )
            if passed:
                return True
            if profile.fail_mode == "retry" and attempt < attempts:
                continue

            message = (
                f"治理检查未通过：role={profile.role}, check={check}, stage={stage}, "
                f"reason={decision.get('reason')}"
            )
            if profile.fail_mode == "warn":
                _append_trace("governance_warning", trace_node_uid, stage=stage, message=message)
                return True

            summary.failed.append(message)
            if strict:
                raise RuntimeError(message)
            return False

        return True

    workflow_start_ok = _handle_governance(
        profile=process_officer,
        check="can_start",
        context={"allow_start": True, "workflow_id": workflow.get("workflow_id"), "workflow_name": workflow.get("workflow_name")},
        trace_node_uid="__workflow__",
        stage="workflow_can_start",
    )
    if not workflow_start_ok:
        return summary

    for node_uid in resolved_flow:
        node_meta = control_nodes.get(node_uid) if isinstance(control_nodes, Mapping) else {}
        if not isinstance(node_meta, Mapping):
            node_meta = {}

        node_type = str(node_meta.get("node_type") or "").strip().lower()
        whitelist = set(node_officer.node_type_whitelist)
        node_officer_enabled = node_officer.enabled and (not whitelist or node_type in whitelist)

        if node_officer_enabled:
            node_start_ok = _handle_governance(
                profile=node_officer,
                check="can_start",
                context={"allow_start": True, "node_uid": node_uid, "node_type": node_type},
                trace_node_uid=node_uid,
                stage="node_can_start",
            )
            if not node_start_ok:
                continue

        content_meta = node_meta.get("content") if isinstance(node_meta.get("content"), Mapping) else {}
        if not isinstance(content_meta, Mapping):
            content_meta = {}

        content_kind = str(content_meta.get("content_kind") or "affair").strip() or "affair"
        content_ref = str(content_meta.get("content_ref") or node_uid).strip() or node_uid
        content_payload = content_meta.get("content_payload") if isinstance(content_meta.get("content_payload"), Mapping) else {}
        if not isinstance(content_payload, Mapping):
            content_payload = {}

        attempt = 0
        last_result: NodeExecutionResult | None = None
        while True:
            attempt += 1
            started_at = _dt.datetime.now()
            _append_trace(
                "node_started",
                node_uid,
                attempt=attempt,
                max_attempts=retry_config.max_attempts,
                content_kind=content_kind,
                content_ref=content_ref,
            )

            try:
                result = dispatch_content_handler(
                    node_uid=node_uid,
                    content_kind=content_kind,
                    content_ref=content_ref,
                    content_payload=content_payload,
                    workflow=workflow,
                    workflow_dir=workflow_path.parent,
                    workspace_root=workspace_root,
                    dry_run=dry_run,
                    execute_affair=execute_affair,
                    execute_subgraph=execute_subgraph,
                )
                last_result = result
                duration_ms = int((_dt.datetime.now() - started_at).total_seconds() * 1000)
                for message in result.messages:
                    print(message)

                if result.success:
                    summary.visited.append(node_uid)
                    _append_trace(
                        "node_succeeded",
                        node_uid,
                        attempt=attempt,
                        duration_ms=duration_ms,
                        output=result.output,
                    )
                    break

                error_type = str(result.error_type or "non_retryable").strip().lower()
                if _should_retry(error_type=error_type, attempt=attempt, retry_config=retry_config):
                    _append_trace(
                        "node_retry",
                        node_uid,
                        attempt=attempt,
                        next_attempt=attempt + 1,
                        error_type=error_type,
                        reason=result.error_message or "handler_failed",
                    )
                    if retry_config.backoff_seconds > 0:
                        time.sleep(retry_config.backoff_seconds)
                    continue

                _append_trace(
                    "node_failed",
                    node_uid,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_type=error_type,
                    output=result.output,
                    messages=result.messages,
                    error_message=result.error_message,
                )
                break
            except Exception as exc:
                duration_ms = int((_dt.datetime.now() - started_at).total_seconds() * 1000)
                error_type = _classify_error(exc)
                if _should_retry(error_type=error_type, attempt=attempt, retry_config=retry_config):
                    _append_trace(
                        "node_retry",
                        node_uid,
                        attempt=attempt,
                        next_attempt=attempt + 1,
                        error_type=error_type,
                        reason=str(exc),
                    )
                    if retry_config.backoff_seconds > 0:
                        time.sleep(retry_config.backoff_seconds)
                    continue

                last_result = NodeExecutionResult.failed(
                    node_uid=node_uid,
                    messages=[f"节点执行异常：{node_uid}：{exc}"],
                    error_type=error_type,
                    error_message=str(exc),
                )
                _append_trace(
                    "node_failed",
                    node_uid,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_type=error_type,
                    error_message=str(exc),
                )
                break

        if last_result is None:
            last_result = NodeExecutionResult.failed(
                node_uid=node_uid,
                messages=[f"节点执行失败：{node_uid}"],
                error_type="non_retryable",
            )

        if node_officer_enabled:
            completed_ok = _handle_governance(
                profile=node_officer,
                check="completed",
                context={"success": last_result.success, "node_uid": node_uid, "node_type": node_type},
                trace_node_uid=node_uid,
                stage="node_completed",
            )
            healthy_ok = _handle_governance(
                profile=node_officer,
                check="healthy",
                context={"has_error": not last_result.success, "node_uid": node_uid, "node_type": node_type},
                trace_node_uid=node_uid,
                stage="node_healthy",
            )
            if not (completed_ok and healthy_ok):
                continue

        if not last_result.success:
            failed_msg = f"节点执行失败：{node_uid}"
            summary.failed.append(failed_msg)
            if strict:
                raise RuntimeError(failed_msg)

    workflow_completed_ok = _handle_governance(
        profile=process_officer,
        check="completed",
        context={"success": not bool(summary.failed)},
        trace_node_uid="__workflow__",
        stage="workflow_completed",
    )
    workflow_healthy_ok = _handle_governance(
        profile=process_officer,
        check="healthy",
        context={"has_error": bool(summary.failed)},
        trace_node_uid="__workflow__",
        stage="workflow_healthy",
    )
    if not (workflow_completed_ok and workflow_healthy_ok):
        _append_trace("workflow_warning", "__workflow__", message="流程治理检查存在未通过项")

    trace_cfg = workflow.get("node_runtime") if isinstance(workflow.get("node_runtime"), Mapping) else {}
    summary.metrics = _build_runtime_metrics(
        events=summary.trace_events,
        visited=summary.visited,
        failed=summary.failed,
    )
    if trace_cfg.get("trace_enabled", True) is not False:
        raw_output_dir = str(trace_cfg.get("trace_output_dir") or "").strip()
        output_dir = Path(raw_output_dir) if raw_output_dir else (workflow_path.parent / "output" / "node_runtime_traces")
        if not output_dir.is_absolute():
            output_dir = (workspace_root / output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        trace_file = output_dir / f"node_runtime_trace_{workflow_path.stem}_{now_compact(fmt='%Y%m%d_%H%M%S')}_{run_id[:8]}.json"
        payload = {
            "run_id": run_id,
            "workflow_path": str(workflow_path),
            "visited": list(summary.visited),
            "failed": list(summary.failed),
            "metrics": dict(summary.metrics or {}),
            "events": [event.to_dict() for event in summary.trace_events],
        }
        trace_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if summary.failed and strict:
        raise RuntimeError("Node Runtime 存在失败节点：\n" + "\n".join(summary.failed))

    return summary


