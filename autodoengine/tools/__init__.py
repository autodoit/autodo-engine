"""autodo-engine 内置工具集。

该模块同时提供两层能力：

1. atomic 函数导出，用于兼容旧的 import 调用；
2. public capability facade，用于统一 manifest/schema/审计/多入口调用。
"""

from __future__ import annotations

from typing import Any, Dict, List

from autodoengine.tools.atomic.affair import import_user_affair_tool, run_affair_tool
from autodoengine.tools.atomic.config import prepare_affair_config_tool
from autodoengine.tools.atomic.docs import (
    check_affair_conflicts_summary,
    list_runtime_affairs_summary,
    refresh_affair_registry_minimal,
)
from autodoengine.tools.atomic.graph import load_graph_summary
from autodoengine.tools.atomic.path import show_affair_registry_paths, show_runtime_store_paths
from autodoengine.tools.atomic.runtime import bootstrap_runtime_tool
from autodoengine.tools.public.facade import invoke_capability, list_capabilities
from autodoengine.tools.public.registry import get_capability, lint_public_manifest


_COMPAT_EXPORTS: Dict[str, Any] = {
    "show_runtime_store_paths": show_runtime_store_paths,
    "show_affair_registry_paths": show_affair_registry_paths,
    "refresh_affair_registry_minimal": refresh_affair_registry_minimal,
    "list_runtime_affairs_summary": list_runtime_affairs_summary,
    "check_affair_conflicts_summary": check_affair_conflicts_summary,
    "bootstrap_runtime_tool": bootstrap_runtime_tool,
    "load_graph_summary": load_graph_summary,
    "prepare_affair_config_tool": prepare_affair_config_tool,
    "run_affair_tool": run_affair_tool,
    "import_user_affair_tool": import_user_affair_tool,
}


def list_user_tools() -> List[str]:
    """列出用户级工具名称。

    Returns:
        用户级 capability 列表。
    """

    return [str(item["capability_id"]) for item in list_capabilities(include_internal=False)]


def list_developer_tools() -> List[str]:
    """列出开发者级工具名称。

    Returns:
        开发者 capability 列表。
    """

    return [
        str(item["capability_id"])
        for item in list_capabilities(include_internal=True)
        if str(item.get("exposure") or "") != "user"
    ]


def get_tool(tool_name: str, *, scope: str = "user") -> Any:
    """按名称获取工具函数。

    优先返回兼容导出函数；若名称匹配 capability，则返回 facade 包装函数。

    Args:
        tool_name: 工具名或 capability_id。
        scope: 作用域，支持 `user`、`developer`、`all`。

    Returns:
        可调用对象。

    Raises:
        KeyError: 工具不存在时抛出。
    """

    name = str(tool_name or "").strip()
    if not name:
        raise KeyError("tool_name 不能为空")

    if name in _COMPAT_EXPORTS:
        return _COMPAT_EXPORTS[name]

    definition = get_capability(name)
    if scope == "user" and definition.exposure != "user":
        raise KeyError(f"工具不存在：{name}")
    if scope == "developer" and definition.exposure == "user":
        raise KeyError(f"工具不存在：{name}")

    def _wrapped_tool(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        """capability facade 包装调用。

        Args:
            *args: 位置参数，不支持。
            **kwargs: 关键字参数，作为 payload。

        Returns:
            统一协议结果字典。
        """

        if args:
            raise TypeError("capability 工具仅支持关键字参数调用")
        return invoke_capability(
            name,
            payload=dict(kwargs),
            caller_context={"caller_source": "autodoengine.tools.get_tool"},
            allow_internal=(scope in {"developer", "all"}),
            workspace_root=kwargs.get("workspace_root"),
        )

    return _wrapped_tool


__all__ = [
    "show_runtime_store_paths",
    "show_affair_registry_paths",
    "refresh_affair_registry_minimal",
    "list_runtime_affairs_summary",
    "check_affair_conflicts_summary",
    "bootstrap_runtime_tool",
    "load_graph_summary",
    "prepare_affair_config_tool",
    "run_affair_tool",
    "import_user_affair_tool",
    "list_user_tools",
    "list_developer_tools",
    "list_capabilities",
    "invoke_capability",
    "lint_public_manifest",
    "get_tool",
]
