"""事务配置预处理工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from autodoengine.utils.path_tools import resolve_paths_to_absolute


def prepare_affair_config_tool(config: Dict[str, Any], workspace_root: str | Path) -> Dict[str, Any]:
    """预处理事务配置中的路径字段。

    Args:
        config: 原始配置字典。
        workspace_root: 工作区根目录。

    Returns:
        路径已绝对化后的配置。
    """

    workspace = Path(workspace_root).resolve()
    normalized = dict(config or {})
    normalized.setdefault("_workspace_root", str(workspace))
    return resolve_paths_to_absolute(normalized, workspace_root=workspace)
