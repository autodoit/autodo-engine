"""运行时管理原子工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from autodoengine.taskdb import bootstrap_runtime_storage


def bootstrap_runtime_tool(base_dir: str | Path) -> Dict[str, str]:
    """初始化运行时并返回根目录。

    Args:
        base_dir: 运行时根目录。

    Returns:
        初始化结果摘要。
    """

    bootstrap_runtime_storage(str(base_dir))
    return {"runtime_base_dir": str(Path(base_dir).resolve()), "status": "initialized"}
