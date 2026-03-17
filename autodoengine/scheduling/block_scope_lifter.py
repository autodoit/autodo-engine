"""阻断上浮规则模块（v4）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autodoengine.core.enums import BlockReasonCode, BlockScope, ResultCode
from autodoengine.core.types import NodeContext, ResultReceipt, TaskContext


@dataclass(slots=True, frozen=True)
class BlockScopeLiftResult:
    """阻断上浮判定结果。

    Args:
        original_scope: 原始阻断作用域。
        lifted_scope: 上浮后的阻断作用域。
        is_lifted: 是否发生上浮。
        reason: 判定原因。

    Returns:
        None.

    Raises:
        None.

    Examples:
        >>> BlockScopeLiftResult(
        ...     original_scope=BlockScope.AFFAIR,
        ...     lifted_scope=BlockScope.TASK,
        ...     is_lifted=True,
        ...     reason="requires_human_true",
        ... )
        BlockScopeLiftResult(original_scope=<BlockScope.AFFAIR: 'affair'>, lifted_scope=<BlockScope.TASK: 'task'>, is_lifted=True, reason='requires_human_true')
    """

    original_scope: BlockScope
    lifted_scope: BlockScope
    is_lifted: bool
    reason: str


def _is_high_risk(node_context: NodeContext) -> bool:
    """判断节点风险是否为高风险。

    Args:
        node_context: 节点上下文。

    Returns:
        bool: 是否高风险。

    Raises:
        None.

    Examples:
        >>> from autodoengine.core.types import NodeContext
        >>> node = NodeContext(node_uid="n1", node_type="process", affair_uid=None, risk_level="high")
        >>> _is_high_risk(node)
        True
    """

    return str(node_context.risk_level or "").strip().lower() in {"high", "critical", "severe"}


def lift_block_scope(
    *,
    receipt: ResultReceipt,
    node_context: NodeContext,
    task_context: TaskContext,
    history_summary: dict[str, Any],
) -> BlockScopeLiftResult:
    """执行阻断上浮判定。

    规则口径：
    1. 非 BLOCKED 不上浮；
    2. 高风险节点或 requires_human=True 直接上浮到 task；
    3. 若近期同任务连续阻断偏多（blocked_count>=2），上浮到 node；
    4. `dependency_unready` / `missing_required_input` 保持 affair 或 node；
    5. 其余 BLOCKED 默认上浮到 node。

    Args:
        receipt: 统一回执对象。
        node_context: 节点上下文。
        task_context: 任务上下文。
        history_summary: 历史摘要。

    Returns:
        BlockScopeLiftResult: 上浮判定结果。

    Raises:
        None.

    Examples:
        >>> # doctest: +SKIP
        >>> result = lift_block_scope(
        ...     receipt=receipt,
        ...     node_context=node_context,
        ...     task_context=task_context,
        ...     history_summary={"blocked_count": 2},
        ... )
    """

    _ = task_context
    original_scope = receipt.block_scope or BlockScope.AFFAIR

    if receipt.result_code != ResultCode.BLOCKED:
        return BlockScopeLiftResult(
            original_scope=original_scope,
            lifted_scope=original_scope,
            is_lifted=False,
            reason="not_blocked",
        )

    if receipt.requires_human:
        return BlockScopeLiftResult(
            original_scope=original_scope,
            lifted_scope=BlockScope.TASK,
            is_lifted=original_scope != BlockScope.TASK,
            reason="requires_human_true",
        )

    if _is_high_risk(node_context):
        return BlockScopeLiftResult(
            original_scope=original_scope,
            lifted_scope=BlockScope.TASK,
            is_lifted=original_scope != BlockScope.TASK,
            reason="high_risk_node",
        )

    blocked_count = int(history_summary.get("blocked_count", 0))
    if blocked_count >= 2:
        return BlockScopeLiftResult(
            original_scope=original_scope,
            lifted_scope=BlockScope.NODE,
            is_lifted=original_scope != BlockScope.NODE,
            reason="blocked_count_threshold",
        )

    if receipt.block_reason_code in {
        BlockReasonCode.DEPENDENCY_UNREADY,
        BlockReasonCode.MISSING_REQUIRED_INPUT,
    }:
        preserved_scope = original_scope if original_scope in {BlockScope.AFFAIR, BlockScope.NODE} else BlockScope.NODE
        return BlockScopeLiftResult(
            original_scope=original_scope,
            lifted_scope=preserved_scope,
            is_lifted=original_scope != preserved_scope,
            reason="dependency_or_input_missing",
        )

    return BlockScopeLiftResult(
        original_scope=original_scope,
        lifted_scope=BlockScope.NODE,
        is_lifted=original_scope != BlockScope.NODE,
        reason="default_blocked_to_node",
    )

