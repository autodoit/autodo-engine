"""核心异常定义。"""

from __future__ import annotations


class GraphValidationError(ValueError):
    """静态图校验异常。"""


class TaskTransitionError(ValueError):
    """任务状态迁移异常。"""


class ReceiptProtocolError(ValueError):
    """事务回执协议异常。"""


class DecisionWriteError(RuntimeError):
    """决策写入异常。"""


class SnapshotWriteError(RuntimeError):
    """快照写入异常。"""
