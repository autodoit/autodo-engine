"""流程图派发表读取工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autodoengine.utils.project_runtime import load_json_file


def load_dispatch_map(workspace_root: str | Path) -> dict[str, dict[str, Any]]:
    """读取派发映射表。"""

    root = Path(workspace_root).resolve()
    dispatch_map_path = root / "config" / "scheduler" / "dispatch_map.json"
    if not dispatch_map_path.exists():
        return {}
    return load_json_file(dispatch_map_path)

