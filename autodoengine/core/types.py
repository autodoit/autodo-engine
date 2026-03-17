"""核心数据类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import BlockReasonCode, BlockScope, DecisionType, ResultCode, TaskAction, TaskStatus


@dataclass(slots=True)
class RetryBudget:
    """重试预算对象。

    Args:
        max_retry: 最大重试次数。
        current_retry: 当前已重试次数。

    Returns:
        None

    Raises:
        ValueError: 当参数非法时抛出。

    Examples:
        >>> RetryBudget(max_retry=3, current_retry=1)
        RetryBudget(max_retry=3, current_retry=1)
    """

    max_retry: int
    current_retry: int

    def __post_init__(self) -> None:
        if self.max_retry < 0:
            raise ValueError("max_retry 不能小于 0")
        if self.current_retry < 0:
            raise ValueError("current_retry 不能小于 0")


@dataclass(slots=True)
class TaskContext:
    """任务上下文。"""

    task_uid: str
    graph_uid: str
    status: TaskStatus
    current_node_uid: str
    current_affair_uid: str | None
    goal_text: str
    retry_count: int = 0
    max_retry: int = 2
    parent_task_uid: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NodeContext:
    """节点上下文。"""

    node_uid: str
    node_type: str
    affair_uid: str | None
    risk_level: str
    policies: dict[str, Any] = field(default_factory=dict)
    container_id: str | None = None


@dataclass(slots=True)
class TaskSummary:
    """任务摘要。"""

    task_uid: str
    status: TaskStatus
    current_node_uid: str
    retry_count: int
    child_task_uids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HumanGateRequest:
    """人工闸门请求对象。"""

    request_uid: str
    task_uid: str
    node_uid: str
    reason_code: BlockReasonCode
    reason_text: str
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskStepRecord:
    """任务步记录对象。"""

    step_uid: str
    run_uid: str
    task_uid: str
    node_uid_before: str
    node_uid_after: str
    selected_action: TaskAction
    selected_edge_uid: str | None
    task_status_before: TaskStatus
    task_status_after: TaskStatus
    decision_uid: str


@dataclass(slots=True)
class DecisionPacket:
    """提交给决策部门的观测包。"""

    packet_uid: str
    task_uid: str
    node_uid: str
    decision_type: DecisionType
    task_summary: dict[str, Any]
    node_summary: dict[str, Any]
    receipt: dict[str, Any]
    candidate_actions: list[TaskAction]
    recommended_action: TaskAction | None
    rule_hits: list[str]
    agent_recommendations: list[dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    risk_score_hint: float | None = None
    observation_missing_fields: list[str] = field(default_factory=list)
    decision_members: list[str] = field(default_factory=lambda: ["pa", "human"])
    decision_mode: str = "JOINT"
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DecisionResult:
    """决策部门返回的统一决策结果。"""

    decision_uid: str
    task_uid: str
    node_uid: str
    decision_type: DecisionType
    selected_action: TaskAction
    task_status_before: TaskStatus
    task_status_after: TaskStatus
    next_node_uid: str | None
    reason_code: str
    reason_text: str
    decision_actor: str = "decision_department"
    decision_members: list[str] = field(default_factory=lambda: ["pa", "human"])
    decision_mode: str = "JOINT"
    is_override_recommendation: bool = False
    override_explanation: str = ""
    human_gate_request: dict[str, Any] = field(default_factory=dict)
    split_children: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResultReceipt:
    """统一事务回执对象。"""

    result_code: ResultCode
    block_reason_code: BlockReasonCode | None = None
    block_scope: BlockScope | None = None
    retryable: bool = False
    requires_human: bool = False
    output_payload: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    message: str = ""
    executor_meta: dict[str, Any] = field(default_factory=dict)
    aa_handling_mode: str = "preset_script"
    fallback_reason_code: str | None = None
    fallback_attempt: int = 0
