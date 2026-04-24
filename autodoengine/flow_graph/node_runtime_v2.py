"""节点中心运行时 V2。

本模块基于 nodes/edges/containers 进行拓扑执行，不再依赖 flow、flow_groups
或 control_flow 等旧结构。
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping

from autodoengine.scheduling import (
    CandidateBuilder,
    DispatchEventLogger,
    DispatchExecutor,
    EdgeScorer,
    RouteGuard,
    RouteSelector,
    SchedulerService,
)
from autodoengine.scheduling.types import CandidateEdge, SchedulerContext
from autodoengine.utils.dispatch_map import load_dispatch_map
from autodoengine.utils.node_execution import NodeExecutionResult
from autodoengine.utils.time_utils import now_iso

from .content_handlers import dispatch_content_handler
from .workflow_v2 import WorkflowV2

AffairExecutor = Callable[[str], NodeExecutionResult]
SubgraphExecutor = Callable[[Path], NodeExecutionResult]


@dataclass(slots=True)
class NodeRuntimeV2TraceEvent:
    """运行时追踪事件。

    Args:
        event: 事件类型。
        node_uid: 节点 uid。
        container: 容器 id。
        payload: 附加信息。
    """

    event: str
    node_uid: str
    container: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """导出事件字典。

        Returns:
            Dict[str, Any]: 可序列化事件字典。
        """

        return {
            "timestamp": now_iso(timespec="seconds"),
            "event": self.event,
            "node_uid": self.node_uid,
            "container": self.container,
            "payload": dict(self.payload or {}),
        }


@dataclass(slots=True)
class NodeRuntimeV2Summary:
    """运行时执行摘要。

    Args:
        run_id: 本次运行唯一标识。
        visited: 已成功执行节点 uid 列表。
        failed: 失败信息列表。
        trace_events: 追踪事件列表。
    """

    run_id: str
    visited: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    skipped_ignored: List[str] = field(default_factory=list)
    skipped_closed: List[str] = field(default_factory=list)
    trace_events: List[NodeRuntimeV2TraceEvent] = field(default_factory=list)


def _to_bool(value: Any) -> bool:
    """将任意值转换为布尔语义。

    Args:
        value: 原始值。

    Returns:
        bool: 转换后的布尔值。
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enable", "enabled", "y"}:
            return True
        if normalized in {"0", "false", "no", "off", "disable", "disabled", "n", ""}:
            return False
    return bool(value)


def _extract_node_switches(
    *,
    node_uid: str,
    workflow_raw: Mapping[str, Any],
    node_policies: Mapping[str, Any],
) -> Dict[str, bool]:
    """提取节点运行时开关。

    开关来源（按优先级从高到低）：
    1) `affairs.<node_uid>.runtime_switches`
    2) `affairs.<node_uid>.config.runtime_switches`
    3) `nodes[].policies.runtime_switches`

    支持字段别名：
    - 忽略开关：`ignore` / `skip`
    - 关闭开关：`close` / `disable` / `disabled`

    Args:
        node_uid: 节点 uid。
        workflow_raw: 原始 workflow 字典。
        node_policies: 节点 policies。

    Returns:
        Dict[str, bool]: 包含 `ignore` 与 `close` 两个布尔键。
    """

    switches: Dict[str, Any] = {}

    affairs = workflow_raw.get("affairs")
    if isinstance(affairs, Mapping):
        affair_cfg = affairs.get(node_uid)
        if isinstance(affair_cfg, Mapping):
            direct_switches = affair_cfg.get("runtime_switches")
            if isinstance(direct_switches, Mapping):
                switches.update(dict(direct_switches))

            inline_cfg = affair_cfg.get("config")
            if isinstance(inline_cfg, Mapping):
                cfg_switches = inline_cfg.get("runtime_switches")
                if isinstance(cfg_switches, Mapping):
                    # 配置内 runtime_switches 作为默认值，直接层可覆盖。
                    merged = dict(cfg_switches)
                    merged.update(switches)
                    switches = merged

    policy_switches = node_policies.get("runtime_switches") if isinstance(node_policies, Mapping) else None
    if isinstance(policy_switches, Mapping):
        merged = dict(policy_switches)
        merged.update(switches)
        switches = merged

    ignore_raw = switches.get("ignore", switches.get("skip", False))
    close_raw = switches.get("close", switches.get("disable", switches.get("disabled", False)))

    return {"ignore": _to_bool(ignore_raw), "close": _to_bool(close_raw)}


def _build_adjacency(workflow: WorkflowV2) -> tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """构建前向与反向邻接表。

    Args:
        workflow: 节点中心工作流对象。

    Returns:
        tuple[Dict[str, List[str]], Dict[str, List[str]]]:
            `(forward, reverse)`，分别为出边邻接和入边邻接。
    """

    forward: Dict[str, List[str]] = {uid: [] for uid in workflow.nodes.keys()}
    reverse: Dict[str, List[str]] = {uid: [] for uid in workflow.nodes.keys()}
    for edge in workflow.edges:
        forward.setdefault(edge.source_node_uid, []).append(edge.target_node_uid)
        reverse.setdefault(edge.target_node_uid, []).append(edge.source_node_uid)
    return forward, reverse


def _collect_reachable(seed: str, adjacency: Mapping[str, List[str]]) -> set[str]:
    """从种子节点收集可达节点集合。

    Args:
        seed: 起始节点 uid。
        adjacency: 邻接表。

    Returns:
        set[str]: 可达节点集合（含 seed）。
    """

    visited: set[str] = set()
    stack: List[str] = [seed]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, []))
    return visited


def _resolve_closed_scope(
    *,
    workflow: WorkflowV2,
    closed_nodes: set[str],
) -> set[str]:
    """计算关闭开关影响范围。

    规则：关闭某节点后，该节点及其前后链路节点（祖先/后继）均跳过执行。

    Args:
        workflow: 节点中心工作流对象。
        closed_nodes: 显式关闭的节点集合。

    Returns:
        set[str]: 需要按关闭策略跳过的节点集合。
    """

    if not closed_nodes:
        return set()

    forward, reverse = _build_adjacency(workflow)
    blocked: set[str] = set()
    for uid in closed_nodes:
        blocked.update(_collect_reachable(uid, forward))
        blocked.update(_collect_reachable(uid, reverse))
    return blocked


def _topological_sort(workflow: WorkflowV2) -> List[str]:
    """执行拓扑排序。

    Args:
        workflow: 节点中心工作流对象。

    Returns:
        List[str]: 节点 uid 的拓扑顺序。

    Raises:
        RuntimeError: 存在环时抛出。
    """

    indegree: Dict[str, int] = {uid: 0 for uid in workflow.nodes.keys()}
    outgoing: Dict[str, List[str]] = {uid: [] for uid in workflow.nodes.keys()}

    for edge in workflow.edges:
        indegree[edge.target_node_uid] = indegree.get(edge.target_node_uid, 0) + 1
        outgoing.setdefault(edge.source_node_uid, []).append(edge.target_node_uid)

    queue = sorted([uid for uid, degree in indegree.items() if degree == 0])
    ordered: List[str] = []

    while queue:
        uid = queue.pop(0)
        ordered.append(uid)
        for target_uid in outgoing.get(uid, []):
            indegree[target_uid] -= 1
            if indegree[target_uid] == 0:
                queue.append(target_uid)
                queue.sort()

    if len(ordered) != len(workflow.nodes):
        raise RuntimeError("节点中心工作流存在环，无法拓扑执行")

    return ordered


def run_node_runtime_workflow_v2(
    *,
    workflow_v2: WorkflowV2,
    workflow_raw: Mapping[str, Any],
    workflow_path: Path,
    workspace_root: Path,
    strict: bool,
    dry_run: bool,
    execute_affair: AffairExecutor,
    execute_subgraph: SubgraphExecutor,
) -> NodeRuntimeV2Summary:
    """运行节点中心工作流。

    Args:
        workflow_v2: 节点中心工作流对象。
        workflow_raw: 原始 workflow 字典。
        workflow_path: workflow 文件路径。
        workspace_root: 工作区根目录。
        strict: 严格模式。
        dry_run: 是否 dry-run。
        execute_affair: 事务执行回调。
        execute_subgraph: 子图执行回调。

    Returns:
        NodeRuntimeV2Summary: 执行摘要。

    Raises:
        RuntimeError: 严格模式下任一节点失败时抛出。
    """

    _ = workflow_path
    run_id = uuid.uuid4().hex
    summary = NodeRuntimeV2Summary(run_id=run_id)

    ordered_nodes = _topological_sort(workflow_v2)
    topo_rank = {uid: index for index, uid in enumerate(ordered_nodes)}

    # 在 Node Runtime V2 中接入统一调度服务，确保运行链使用同一调度内核。
    dispatch_map = load_dispatch_map(workspace_root=workspace_root)
    scheduler_service = SchedulerService(
        candidate_builder=CandidateBuilder(),
        edge_scorer=EdgeScorer(),
        route_selector=RouteSelector(),
        route_guard=RouteGuard(),
        dispatch_executor=DispatchExecutor(dispatch_map=dispatch_map),
        event_logger=DispatchEventLogger(workspace_root / "logs" / "run" / "aok_scheduler_events.jsonl"),
    )
    previous_node_uid: str | None = None

    switch_map: Dict[str, Dict[str, bool]] = {
        uid: _extract_node_switches(
            node_uid=uid,
            workflow_raw=workflow_raw,
            node_policies=workflow_v2.nodes[uid].policies,
        )
        for uid in ordered_nodes
    }
    explicit_closed_nodes = {uid for uid, switches in switch_map.items() if switches.get("close", False)}
    blocked_by_close = _resolve_closed_scope(workflow=workflow_v2, closed_nodes=explicit_closed_nodes)

    for node_uid in ordered_nodes:
        node = workflow_v2.nodes[node_uid]

        if node.uid in blocked_by_close:
            summary.skipped_closed.append(node.uid)
            summary.trace_events.append(
                NodeRuntimeV2TraceEvent(
                    event="node_skipped_closed",
                    node_uid=node.uid,
                    container=node.container,
                    payload={"reason": "runtime_switches.close", "messages": ["节点被关闭链路策略跳过"]},
                )
            )
            continue

        if switch_map.get(node.uid, {}).get("ignore", False):
            summary.visited.append(node.uid)
            summary.skipped_ignored.append(node.uid)
            summary.trace_events.append(
                NodeRuntimeV2TraceEvent(
                    event="node_skipped_ignored",
                    node_uid=node.uid,
                    container=node.container,
                    payload={"reason": "runtime_switches.ignore", "messages": ["节点被忽略并视为成功"]},
                )
            )
            continue

        summary.trace_events.append(
            NodeRuntimeV2TraceEvent(
                event="node_started",
                node_uid=node.uid,
                container=node.container,
                payload={"node_type": node.node_type},
            )
        )

        schedule_context = SchedulerContext(
            task_uid=run_id,
            goal=str(workflow_v2.workflow_name or workflow_v2.workflow_id or "node_runtime_v2"),
            current_transaction_uid=previous_node_uid,
            runtime_features={"goal_gain": 1.0},
            completed_transactions=frozenset(summary.visited),
            failed_transactions=frozenset(summary.failed),
            retry_counts={},
            state={"workflow_id": workflow_v2.workflow_id, "node_uid": node.uid},
        )
        schedule_event = scheduler_service.dispatch_once(
            context=schedule_context,
            edges=(
                CandidateEdge(
                    edge_uid=f"runtime-edge-{node.uid}",
                    from_transaction_uid=previous_node_uid,
                    to_transaction_uid=node.uid,
                    dispatch_key=node.uid,
                    # 保持与拓扑执行顺序一致，避免接入阶段产生行为漂移。
                    base_tendency_score=float(len(ordered_nodes) - topo_rank.get(node.uid, 0)),
                ),
            ),
            payload={"node_uid": node.uid, "container": node.container},
            strategy="argmax",
            execute=False,
            result_code="PASS",
            audit_result="PASS",
        )
        summary.trace_events.append(
            NodeRuntimeV2TraceEvent(
                event="node_scheduled",
                node_uid=node.uid,
                container=node.container,
                payload={
                    "selected": (
                        schedule_event.selection.selected.edge.to_transaction_uid
                        if schedule_event.selection.selected is not None
                        else None
                    ),
                    "strategy": schedule_event.selection.strategy,
                    "reason": schedule_event.selection.reason,
                },
            )
        )

        result = dispatch_content_handler(
            node_uid=node.uid,
            content_kind=node.content.content_kind,
            content_ref=node.content.content_ref,
            content_payload=node.content.content_payload,
            workflow=workflow_raw,
            workflow_dir=workflow_path.parent,
            workspace_root=workspace_root,
            dry_run=dry_run,
            execute_affair=execute_affair,
            execute_subgraph=execute_subgraph,
        )

        if result.success:
            summary.visited.append(node.uid)
            previous_node_uid = node.uid
            summary.trace_events.append(
                NodeRuntimeV2TraceEvent(
                    event="node_succeeded",
                    node_uid=node.uid,
                    container=node.container,
                    payload={"messages": list(result.messages or [])},
                )
            )
            continue

        message = (
            f"节点[{node.uid}] 执行失败："
            f"error_type={result.error_type or 'non_retryable'}; "
            f"error_message={result.error_message or '; '.join(result.messages)}"
        )
        summary.failed.append(message)
        summary.trace_events.append(
            NodeRuntimeV2TraceEvent(
                event="node_failed",
                node_uid=node.uid,
                container=node.container,
                payload={"messages": list(result.messages or []), "error_type": result.error_type},
            )
        )

        if strict:
            raise RuntimeError(message)

    return summary

