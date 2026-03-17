"""项目运行时通用工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autodoengine.utils.config_loader import resolve_config_path as resolve_global_config_path


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    """解析全局配置路径。"""

    return resolve_global_config_path(config_path=config_path)


def load_json_file(file_path: str | Path) -> dict[str, Any]:
    """读取 JSON 文件。"""

    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败：{path}\\n{exc}") from exc


def resolve_workspace_root(config_file: str | Path, config: dict[str, Any]) -> Path:
    """解析工作区根目录。"""

    path = Path(config_file).resolve()
    raw_value = str(config.get("workspace_root") or "").strip()
    if raw_value:
        candidate = Path(raw_value).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (path.parent / candidate).resolve()
    return path.parent.resolve()


def summarize_workflow(workflow_path: str | Path) -> dict[str, Any]:
    """读取并摘要 workflow 配置。"""

    path = Path(workflow_path).resolve()
    workflow = load_json_file(path)
    raw_affairs = workflow.get("affairs")
    raw_flow = workflow.get("flow")
    affairs: dict[str, Any] = raw_affairs if isinstance(raw_affairs, dict) else {}
    flow: list[Any] = raw_flow if isinstance(raw_flow, list) else []
    return {
        "workflow_path": str(path),
        "workflow_id": path.parent.name,
        "affair_count": len(affairs),
        "flow_count": len(flow),
        "affair_keys": list(affairs.keys()),
        "flow": flow,
    }

