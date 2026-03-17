"""
调度内核核心类型。

本文件集中定义调度过程中的结构化输入输出，便于后续迁移到
数据库、API 或独立服务时保持接口稳定。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

ResultCode = Literal["PASS", "RETRY", "BACKTRACK", "BLOCKED"]
"""事务执行结果码。"""

AuditResult = Literal["PASS", "WARN", "FAIL", "BLOCKED"]
"""审计结果码。"""

SelectionStrategy = Literal["argmax", "softmax"]
"""路由选择策略。"""

DispatchKind = Literal["python_callable", "python_module", "placeholder"]
"""派发目标类型。"""


@dataclass(slots=True, frozen=True)
class CandidateEdge:
    """表示一条可调度事务边。"""

    edge_uid: str
    from_transaction_uid: str | None
    to_transaction_uid: str
    condition: str = "always"
    active: bool = True
    base_tendency_score: float = 0.0
    dynamic_delta: float = 0.0
    transition_prob: float = 1.0
    goal_gain: float = 0.0
    risk_penalty: float = 0.0
    cost_penalty: float = 0.0
    time_penalty: float = 0.0
    audit_bonus: float = 0.0
    required_permissions: tuple[str, ...] = ()
    blocked_by_audit: bool = False
    dispatch_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SchedulerContext:
    """表示单次调度所需上下文。"""

    task_uid: str
    goal: str
    current_transaction_uid: str | None = None
    runtime_features: dict[str, float] = field(default_factory=dict)
    permission_flags: frozenset[str] = field(default_factory=frozenset)
    completed_transactions: frozenset[str] = field(default_factory=frozenset)
    failed_transactions: frozenset[str] = field(default_factory=frozenset)
    retry_counts: dict[str, int] = field(default_factory=dict)
    audit_flags: frozenset[str] = field(default_factory=frozenset)
    state: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: utc_now_iso())


@dataclass(slots=True, frozen=True)
class CandidateSet:
    """表示候选事务集合。"""

    task_uid: str
    current_transaction_uid: str | None
    candidates: tuple[CandidateEdge, ...]
    blocked_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ScoredCandidate:
    """表示完成评分后的候选边。"""

    edge: CandidateEdge
    score: float
    explain: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SelectionResult:
    """表示路由选择结果。"""

    selected: ScoredCandidate | None
    ranked_candidates: tuple[ScoredCandidate, ...]
    strategy: SelectionStrategy
    reason: str
    alternatives: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class GuardDecision:
    """表示守卫动作决策。"""

    action: Literal["continue", "retry", "backtrack", "block"]
    result_code: ResultCode
    audit_result: AuditResult
    reason: str
    retry_transaction_uid: str | None = None
    backtrack_transaction_uid: str | None = None


@dataclass(slots=True, frozen=True)
class DispatchReceipt:
    """表示派发执行回执。"""

    dispatch_key: str
    dispatch_kind: DispatchKind
    target: str
    payload: dict[str, Any]
    accepted: bool
    message: str
    handle: str | None = None
    emitted_at: str = field(default_factory=lambda: utc_now_iso())


@dataclass(slots=True, frozen=True)
class DispatchEvent:
    """表示单次调度事件日志。"""

    event_uid: str
    task_uid: str
    selection: SelectionResult
    guard_decision: GuardDecision | None
    receipt: DispatchReceipt | None
    created_at: str = field(default_factory=lambda: utc_now_iso())

    def to_dict(self) -> dict[str, Any]:
        """导出为 JSON 友好字典。"""

        return asdict(self)


def utc_now_iso() -> str:
    """生成统一的 UTC 时间戳。"""

    return datetime.now(UTC).replace(microsecond=0).isoformat()
