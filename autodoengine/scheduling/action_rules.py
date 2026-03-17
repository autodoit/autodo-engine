"""候选动作规则集。"""

from __future__ import annotations

from autodoengine.core.enums import ResultCode, TaskStatus
from autodoengine.core.types import NodeContext, ResultReceipt, RetryBudget, TaskContext


def should_retry(*, receipt: ResultReceipt, retry_budget: RetryBudget) -> bool:
    """判断是否应继续重试。"""

    return (
        receipt.result_code == ResultCode.RETRY
        and receipt.retryable
        and retry_budget.current_retry < retry_budget.max_retry
    )


def should_backtrack(*, receipt: ResultReceipt, retry_budget: RetryBudget) -> bool:
    """判断是否应回退。"""

    return receipt.result_code == ResultCode.BACKTRACK or (
        receipt.result_code == ResultCode.RETRY and retry_budget.current_retry >= retry_budget.max_retry
    )


def should_split(
    *,
    receipt: ResultReceipt,
    node_context: NodeContext,
    history_summary: dict[str, object],
) -> bool:
    """判断是否应分裂任务。"""

    split_hint = bool(history_summary.get("split_hint", False))
    return receipt.result_code == ResultCode.BLOCKED and split_hint and node_context.risk_level != "high"


def should_suspend(*, receipt: ResultReceipt) -> bool:
    """判断是否应挂起。"""

    return receipt.result_code in {ResultCode.RETRY, ResultCode.BLOCKED}


def should_request_human_gate(*, receipt: ResultReceipt, node_context: NodeContext) -> bool:
    """判断是否命中人工闸门。"""

    if receipt.requires_human:
        return True
    return bool(node_context.policies.get("require_human_gate", False))


def should_complete(*, receipt: ResultReceipt, task_context: TaskContext) -> bool:
    """判断任务是否可以完成。"""

    return receipt.result_code == ResultCode.PASS and task_context.metadata.get("goal_satisfied", False)


def should_fail(*, receipt: ResultReceipt, task_context: TaskContext) -> bool:
    """判断任务是否应失败终止。"""

    _ = task_context
    return receipt.result_code == ResultCode.BLOCKED and not receipt.retryable and not receipt.requires_human


def should_continue(*, receipt: ResultReceipt) -> bool:
    """判断是否可继续前进。"""

    return receipt.result_code == ResultCode.PASS


def target_status_for_action(action: str, before_status: TaskStatus) -> TaskStatus:
    """根据动作计算目标任务状态。"""

    mapping = {
        "continue": TaskStatus.RUNNING,
        "retry": TaskStatus.RUNNING,
        "backtrack": TaskStatus.RUNNING,
        "split": TaskStatus.SUSPENDED,
        "suspend": TaskStatus.SUSPENDED,
        "human_gate": TaskStatus.BLOCKED,
        "complete": TaskStatus.COMPLETED,
        "fail": TaskStatus.FAILED,
        "cancel": TaskStatus.CANCELLED,
    }
    return mapping.get(action, before_status)

