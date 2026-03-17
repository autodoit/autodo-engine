"""节点内容处理器。

本模块负责在 Node Runtime 中按 `content_kind` 分发节点执行逻辑。
当前支持：
- `affair`：执行事务处理器；
- `subgraph`：执行子流程图处理器。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from autodoengine.utils.node_execution import NodeExecutionResult
from autodoengine.utils.path_tools import resolve_workflow_config_path


class ContentHandlerError(RuntimeError):
    """内容处理器异常。"""


AffairExecutor = Callable[[str], NodeExecutionResult]
SubgraphExecutor = Callable[[Path], NodeExecutionResult]


def handle_affair_content(
    *,
    node_uid: str,
    content_ref: str,
    execute_affair: AffairExecutor,
) -> NodeExecutionResult:
    """处理事务类节点内容。

    Args:
        node_uid: 节点 uid。
        content_ref: 事务引用标识。
        execute_affair: 事务执行函数，参数为事务键。

    Returns:
        NodeExecutionResult: 执行结果。
    """

    affair_key = node_uid
    result = execute_affair(affair_key)
    output = dict(result.output or {})
    output.update({"node_uid": node_uid, "content_ref": content_ref, "affair_key": affair_key})
    if result.success:
        return NodeExecutionResult.succeeded(
            node_uid=node_uid,
            messages=list(result.messages or []),
            output=output,
        )
    return NodeExecutionResult.failed(
        node_uid=node_uid,
        messages=list(result.messages or []),
        output=output,
        error_type=result.error_type or "non_retryable",
        error_message=result.error_message,
    )


def handle_subgraph_content(
    *,
    node_uid: str,
    content_ref: str,
    content_payload: Mapping[str, Any],
    workflow: Mapping[str, Any],
    workflow_dir: Path,
    workspace_root: Path,
    dry_run: bool,
    execute_subgraph: SubgraphExecutor,
) -> NodeExecutionResult:
    """处理子流程图节点内容。

    子流程图映射读取规则：
    - `workflow.subgraphs[content_ref]` 为字符串路径；
    - 或 `workflow.subgraphs[content_ref].workflow_path` 为路径。

    Args:
        node_uid: 节点 uid。
        content_ref: 子流程图引用标识。
        content_payload: 节点 payload。
        workflow: 当前工作流配置。
        workflow_dir: 当前 workflow 文件目录。
        workspace_root: 工作区根目录。
        dry_run: 是否 dry-run。
        execute_subgraph: 子流程图执行函数。

    Returns:
        NodeExecutionResult: 执行结果。
    """

    raw_subgraphs = workflow.get("subgraphs")
    if not isinstance(raw_subgraphs, Mapping):
        return NodeExecutionResult.failed(
            node_uid=node_uid,
            messages=[f"节点[{node_uid}] 为 subgraph 类型，但 workflow 缺少 subgraphs 映射。"],
            output={"node_uid": node_uid, "content_ref": content_ref},
            error_type="non_retryable",
        )

    subgraph_entry = raw_subgraphs.get(content_ref)
    if subgraph_entry is None:
        return NodeExecutionResult.failed(
            node_uid=node_uid,
            messages=[f"节点[{node_uid}] 引用的子流程图不存在：{content_ref}"],
            output={"node_uid": node_uid, "content_ref": content_ref},
            error_type="non_retryable",
        )

    raw_path = ""
    if isinstance(subgraph_entry, str):
        raw_path = subgraph_entry
    elif isinstance(subgraph_entry, Mapping):
        raw_path = str(subgraph_entry.get("workflow_path") or "").strip()

    if not raw_path:
        return NodeExecutionResult.failed(
            node_uid=node_uid,
            messages=[f"节点[{node_uid}] 子流程图映射缺少 workflow_path：{content_ref}"],
            output={"node_uid": node_uid, "content_ref": content_ref},
            error_type="non_retryable",
        )

    candidate = resolve_workflow_config_path(
        raw_path,
        workspace_root=workspace_root,
        config_path=workflow_dir / "workflow.json",
    )

    if dry_run:
        return NodeExecutionResult.succeeded(
            node_uid=node_uid,
            messages=[
                f"DRY RUN: 子流程图节点[{node_uid}] 解析完成：{candidate}",
                f"DRY RUN: 子流程图 payload：{dict(content_payload or {})}",
            ],
            output={"node_uid": node_uid, "content_ref": content_ref, "workflow_path": str(candidate)},
        )

    result = execute_subgraph(candidate)
    output = dict(result.output or {})
    output.update({"node_uid": node_uid, "content_ref": content_ref, "workflow_path": str(candidate)})
    if result.success:
        return NodeExecutionResult.succeeded(
            node_uid=node_uid,
            messages=list(result.messages or []),
            output=output,
        )
    return NodeExecutionResult.failed(
        node_uid=node_uid,
        messages=list(result.messages or []),
        output=output,
        error_type=result.error_type or "non_retryable",
        error_message=result.error_message,
    )


def dispatch_content_handler(
    *,
    node_uid: str,
    content_kind: str,
    content_ref: str,
    content_payload: Mapping[str, Any],
    workflow: Mapping[str, Any],
    workflow_dir: Path,
    workspace_root: Path,
    dry_run: bool,
    execute_affair: AffairExecutor,
    execute_subgraph: SubgraphExecutor,
) -> NodeExecutionResult:
    """统一分发节点内容处理器。

    Args:
        node_uid: 节点 uid。
        content_kind: 内容类型。
        content_ref: 内容引用。
        content_payload: 内容参数。
        workflow: 当前工作流配置。
        workflow_dir: 当前 workflow 文件目录。
        workspace_root: 工作区根目录。
        dry_run: 是否 dry-run。
        execute_affair: 事务执行函数。
        execute_subgraph: 子流程图执行函数。

    Returns:
        NodeExecutionResult: 执行结果。

    Raises:
        ContentHandlerError: 内容类型不支持时抛出。
    """

    normalized_kind = str(content_kind or "").strip().lower()
    if normalized_kind == "affair":
        return handle_affair_content(
            node_uid=node_uid,
            content_ref=content_ref,
            execute_affair=execute_affair,
        )
    if normalized_kind == "subgraph":
        return handle_subgraph_content(
            node_uid=node_uid,
            content_ref=content_ref,
            content_payload=content_payload,
            workflow=workflow,
            workflow_dir=workflow_dir,
            workspace_root=workspace_root,
            dry_run=dry_run,
            execute_subgraph=execute_subgraph,
        )

    raise ContentHandlerError(f"节点[{node_uid}] 内容类型不支持：{content_kind}")

