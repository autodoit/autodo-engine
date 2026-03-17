"""核心基础设施模块。"""

from __future__ import annotations

from .template_affair import TemplateAffairBase
from .graph_node_common import (
    compute_compare_result,
    compute_simple_expression,
    load_affair_config,
    write_graph_node_report,
)
from .enums import (
    BlockReasonCode,
    BlockScope,
    DecisionType,
    RelationType,
    ResultCode,
    TaskAction,
    TaskStatus,
)
from .errors import (
    DecisionWriteError,
    GraphValidationError,
    ReceiptProtocolError,
    SnapshotWriteError,
    TaskTransitionError,
)
from .types import (
    DecisionPacket,
    DecisionResult,
    HumanGateRequest,
    NodeContext,
    ResultReceipt,
    RetryBudget,
    TaskContext,
    TaskStepRecord,
    TaskSummary,
)

__all__ = [
    "TaskStatus",
    "ResultCode",
    "TaskAction",
    "BlockScope",
    "BlockReasonCode",
    "DecisionType",
    "RelationType",
    "RetryBudget",
    "TaskContext",
    "NodeContext",
    "TaskSummary",
    "HumanGateRequest",
    "TaskStepRecord",
    "DecisionPacket",
    "DecisionResult",
    "ResultReceipt",
    "GraphValidationError",
    "TaskTransitionError",
    "ReceiptProtocolError",
    "DecisionWriteError",
    "SnapshotWriteError",
    "TemplateAffairBase",
    "load_affair_config",
    "write_graph_node_report",
    "compute_compare_result",
    "compute_simple_expression",
]
