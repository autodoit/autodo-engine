"""核心协议接口定义。"""

from __future__ import annotations

from typing import Any, Protocol

from .enums import TaskStatus
from .types import DecisionPacket, DecisionResult, NodeContext, ResultReceipt, RetryBudget, TaskContext


class ReceiptNormalizer(Protocol):
    """回执标准化协议。"""

    def normalize_receipt(self, raw_result: Any, *, node_context: NodeContext) -> ResultReceipt:
        """将原始结果标准化为统一回执。"""


class CandidateActionBuilder(Protocol):
    """候选动作构建协议。"""

    def build_candidate_actions(
        self,
        *,
        receipt: ResultReceipt,
        task_context: TaskContext,
        node_context: NodeContext,
        retry_budget: RetryBudget,
        history_summary: dict[str, Any],
    ) -> DecisionPacket:
        """构建候选动作包。"""


class DecisionMaker(Protocol):
    """决策器协议。"""

    def request_pa_decision(self, packet: DecisionPacket, *, task_status_before: TaskStatus) -> DecisionResult:
        """请求 PA 进行裁决。"""


class TaskStoreProtocol(Protocol):
    """任务存储协议。"""

    def get_task(self, task_uid: str) -> dict[str, Any]:
        """读取任务。"""

    def update_task_status(self, task_uid: str, status: str) -> None:
        """更新任务状态。"""


class DecisionStoreProtocol(Protocol):
    """决策存储协议。"""

    def append_decision(self, result: DecisionResult, packet: DecisionPacket) -> None:
        """写入决策记录。"""


class LogStoreProtocol(Protocol):
    """日志存储协议。"""

    def append_runtime_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """写入运行事件。"""


class GraphRegistryProtocol(Protocol):
    """图注册表协议。"""

    def get_graph(self, graph_uid: str) -> Any:
        """读取图对象。"""
