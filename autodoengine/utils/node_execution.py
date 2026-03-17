"""节点执行结果契约。

本模块用于统一 Node Runtime 与调用方之间的执行结果协议，避免散落的
`(ok: bool, messages: list[str])` 结构在各层反复转换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True, frozen=True)
class NodeExecutionResult:
    """节点执行结果。

    Args:
        success: 是否执行成功。
        node_uid: 节点 uid。
        messages: 执行日志消息。
        output: 执行输出摘要。
        error_type: 错误类型（`retryable` / `non_retryable`）。
        error_message: 错误信息。

    Examples:
        >>> NodeExecutionResult.succeeded(node_uid="A")
        NodeExecutionResult(success=True, node_uid='A', messages=[], output={}, error_type='', error_message='')
    """

    success: bool
    node_uid: str
    messages: List[str] = field(default_factory=list)
    output: Dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    error_message: str = ""

    @classmethod
    def succeeded(
        cls,
        *,
        node_uid: str,
        messages: List[str] | None = None,
        output: Dict[str, Any] | None = None,
    ) -> "NodeExecutionResult":
        """构造成功结果。

        Args:
            node_uid: 节点 uid。
            messages: 日志消息。
            output: 输出摘要。

        Returns:
            NodeExecutionResult: 成功结果对象。
        """

        return cls(
            success=True,
            node_uid=node_uid,
            messages=list(messages or []),
            output=dict(output or {}),
        )

    @classmethod
    def failed(
        cls,
        *,
        node_uid: str,
        messages: List[str] | None = None,
        output: Dict[str, Any] | None = None,
        error_type: str = "non_retryable",
        error_message: str = "",
    ) -> "NodeExecutionResult":
        """构造失败结果。

        Args:
            node_uid: 节点 uid。
            messages: 日志消息。
            output: 输出摘要。
            error_type: 错误类型。
            error_message: 错误信息。

        Returns:
            NodeExecutionResult: 失败结果对象。
        """

        return cls(
            success=False,
            node_uid=node_uid,
            messages=list(messages or []),
            output=dict(output or {}),
            error_type=str(error_type or "non_retryable"),
            error_message=str(error_message or ""),
        )
