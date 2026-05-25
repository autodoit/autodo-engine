"""核心枚举定义。"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar, Self


_数据库值映射表: dict[type[Enum], dict[str, str]] = {}


class 中文持久化Mixin:
    """提供“内部英文枚举值 + 数据库中文持久化值”的统一映射。"""

    _数据库值映射: ClassVar[dict[str, str]] = {}

    @classmethod
    def normalize(cls, value: str | Self) -> Self:
        """把英文值或中文持久化值统一解析为内部枚举。"""

        if isinstance(value, cls):
            return value
        text = str(value).strip()
        mappings = _数据库值映射表.get(cls, {})
        for member in cls:
            if text == member.value or text == mappings.get(member.value, ""):
                return member
        raise ValueError(f"无法识别的{cls.__name__}：{value}")

    @property
    def db_value(self) -> str:
        """返回数据库持久化使用的中文值。"""

        mappings = _数据库值映射表[type(self)]
        return mappings[self.value]


class TaskStatus(中文持久化Mixin, str, Enum):
    """任务状态枚举。"""

    READY = "ready"
    RUNNING = "running"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"



class ResultCode(中文持久化Mixin, str, Enum):
    """事务结果码枚举。"""

    PASS = "PASS"
    RETRY = "RETRY"
    BACKTRACK = "BACKTRACK"
    BLOCKED = "BLOCKED"



class TaskAction(中文持久化Mixin, str, Enum):
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



class BlockScope(中文持久化Mixin, str, Enum):
    """阻断作用域枚举。"""

    AFFAIR = "affair"
    NODE = "node"
    TASK = "task"



class BlockReasonCode(中文持久化Mixin, str, Enum):
    """阻断原因码枚举。"""

    PERMISSION_MISSING = "permission_missing"
    DEPENDENCY_UNREADY = "dependency_unready"
    MISSING_REQUIRED_INPUT = "missing_required_input"
    POLICY_DENIED = "policy_denied"
    GOAL_AMBIGUOUS = "goal_ambiguous"
    HUMAN_CONFIRMATION_REQUIRED = "human_confirmation_required"
    RESOURCE_EXHAUSTED = "resource_exhausted"



class DecisionType(中文持久化Mixin, str, Enum):
    """决策类型枚举。"""

    ROUTE = "route"
    STATUS = "status"
    HUMAN_GATE = "human_gate"



class RelationType(中文持久化Mixin, str, Enum):
    """任务关系类型枚举。"""

    SPLIT = "split"
    DEPENDS_ON = "depends_on"
    RESUME_FROM = "resume_from"

_数据库值映射表[TaskStatus] = {
    TaskStatus.READY.value: "就绪",
    TaskStatus.RUNNING.value: "运行中",
    TaskStatus.SUSPENDED.value: "已挂起",
    TaskStatus.BLOCKED.value: "已阻断",
    TaskStatus.COMPLETED.value: "已完成",
    TaskStatus.FAILED.value: "已失败",
    TaskStatus.CANCELLED.value: "已取消",
}

_数据库值映射表[ResultCode] = {
    ResultCode.PASS.value: "通过",
    ResultCode.RETRY.value: "重试",
    ResultCode.BACKTRACK.value: "回退",
    ResultCode.BLOCKED.value: "阻断",
}

_数据库值映射表[TaskAction] = {
    TaskAction.CONTINUE.value: "继续推进",
    TaskAction.RETRY.value: "重试",
    TaskAction.BACKTRACK.value: "回退",
    TaskAction.SUSPEND.value: "挂起",
    TaskAction.SPLIT.value: "拆分",
    TaskAction.HUMAN_GATE.value: "人工闸门",
    TaskAction.COMPLETE.value: "完成",
    TaskAction.FAIL.value: "失败",
    TaskAction.CANCEL.value: "取消",
}

_数据库值映射表[BlockScope] = {
    BlockScope.AFFAIR.value: "事务",
    BlockScope.NODE.value: "节点",
    BlockScope.TASK.value: "任务",
}

_数据库值映射表[BlockReasonCode] = {
    BlockReasonCode.PERMISSION_MISSING.value: "权限缺失",
    BlockReasonCode.DEPENDENCY_UNREADY.value: "依赖未就绪",
    BlockReasonCode.MISSING_REQUIRED_INPUT.value: "缺少必要输入",
    BlockReasonCode.POLICY_DENIED.value: "策略拒绝",
    BlockReasonCode.GOAL_AMBIGUOUS.value: "目标不明确",
    BlockReasonCode.HUMAN_CONFIRMATION_REQUIRED.value: "需要人工确认",
    BlockReasonCode.RESOURCE_EXHAUSTED.value: "资源耗尽",
}

_数据库值映射表[DecisionType] = {
    DecisionType.ROUTE.value: "路由决策",
    DecisionType.STATUS.value: "状态决策",
    DecisionType.HUMAN_GATE.value: "人工闸门",
}

_数据库值映射表[RelationType] = {
    RelationType.SPLIT.value: "拆分",
    RelationType.DEPENDS_ON.value: "依赖",
    RelationType.RESUME_FROM.value: "恢复来源",
}
