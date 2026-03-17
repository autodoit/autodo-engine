"""核心枚举定义。"""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    READY = "ready"
    RUNNING = "running"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResultCode(str, Enum):
    """事务结果码枚举。"""

    PASS = "PASS"
    RETRY = "RETRY"
    BACKTRACK = "BACKTRACK"
    BLOCKED = "BLOCKED"


class TaskAction(str, Enum):
    """任务动作枚举。"""

    CONTINUE = "continue"
    RETRY = "retry"
    BACKTRACK = "backtrack"
    SUSPEND = "suspend"
    SPLIT = "split"
    HUMAN_GATE = "human_gate"
    COMPLETE = "complete"
    FAIL = "fail"
    CANCEL = "cancel"


class BlockScope(str, Enum):
    """阻断作用域枚举。"""

    AFFAIR = "affair"
    NODE = "node"
    TASK = "task"


class BlockReasonCode(str, Enum):
    """阻断原因码枚举。"""

    PERMISSION_MISSING = "permission_missing"
    DEPENDENCY_UNREADY = "dependency_unready"
    MISSING_REQUIRED_INPUT = "missing_required_input"
    POLICY_DENIED = "policy_denied"
    GOAL_AMBIGUOUS = "goal_ambiguous"
    HUMAN_CONFIRMATION_REQUIRED = "human_confirmation_required"
    RESOURCE_EXHAUSTED = "resource_exhausted"


class DecisionType(str, Enum):
    """决策类型枚举。"""

    ROUTE = "route"
    STATUS = "status"
    HUMAN_GATE = "human_gate"


class RelationType(str, Enum):
    """任务关系类型枚举。"""

    SPLIT = "split"
    DEPENDS_ON = "depends_on"
    RESUME_FROM = "resume_from"
