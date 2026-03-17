"""纯 Python 派发执行器。"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable

from autodoengine.scheduling.types import DispatchKind, DispatchReceipt, SelectionResult

PythonHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(slots=True)
class DispatchExecutor:
    """派发执行器。"""

    dispatch_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    handler_registry: dict[str, PythonHandler] = field(default_factory=dict)

    def dispatch(
        self,
        selection: SelectionResult,
        payload: dict[str, Any],
        execute: bool = False,
    ) -> DispatchReceipt:
        """派发已选事务。"""

        if selection.selected is None:
            return DispatchReceipt(
                dispatch_key="",
                dispatch_kind="placeholder",
                target="",
                payload=payload,
                accepted=False,
                message="无可派发候选",
            )

        edge = selection.selected.edge
        receipt, _ = self.dispatch_by_key(
            dispatch_key=edge.dispatch_key,
            payload=payload,
            execute=execute,
            transaction_uid=edge.to_transaction_uid,
        )
        return receipt

    def dispatch_by_key(
        self,
        dispatch_key: str,
        payload: dict[str, Any],
        execute: bool = False,
        transaction_uid: str | None = None,
    ) -> tuple[DispatchReceipt, dict[str, Any] | None]:
        """按派发键直接派发。"""

        mapping: dict[str, Any] = self.dispatch_map.get(dispatch_key, {})
        dispatch_kind: DispatchKind = mapping.get("kind", "placeholder")
        target: str = str(mapping.get("target") or dispatch_key)

        output: dict[str, Any] | None = None
        if execute and dispatch_kind == "python_callable":
            output = self._run_callable(target=target, payload=payload)
        if execute and dispatch_kind == "python_module":
            output = self._run_module(target=target, payload=payload)

        accepted: bool = bool(target) and dispatch_kind != "placeholder"
        message: str = "已生成纯 Python 派发回执"
        if not execute:
            message = f"已生成派发回执，当前为非执行模式，目标={target}"
        if dispatch_kind == "placeholder":
            message = f"未找到可执行处理器，当前目标为占位映射：{target}"

        handle_suffix = transaction_uid or dispatch_key
        receipt = DispatchReceipt(
            dispatch_key=dispatch_key,
            dispatch_kind=dispatch_kind,
            target=target,
            payload=payload,
            accepted=accepted,
            message=message,
            handle=f"dispatch::{dispatch_key}::{handle_suffix}",
        )
        return receipt, output

    def _run_callable(self, target: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """执行注册表中的可调用对象。"""

        handler = self.handler_registry.get(target)
        if handler is None:
            raise KeyError(f"未找到已注册处理器：{target}")
        return handler(payload)

    def _run_module(self, target: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """执行点路径模块函数。"""

        module_name, function_name = target.split(":", 1)
        module = importlib.import_module(module_name)
        handler = getattr(module, function_name)
        return handler(payload)

