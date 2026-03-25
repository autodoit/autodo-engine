"""public capability 审计落盘。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any, Dict


def default_audit_dir(workspace_root: str | Path | None = None) -> Path:
    """返回审计目录。

    Args:
        workspace_root: 工作区根目录。

    Returns:
        审计目录绝对路径。
    """

    if workspace_root is None:
        return (Path.cwd() / ".autodoengine" / "tool_audits").resolve()
    return (Path(workspace_root).resolve() / ".autodoengine" / "tool_audits").resolve()


def write_audit_record(record: Dict[str, Any], *, workspace_root: str | Path | None = None) -> Path:
    """写入 capability 审计记录。

    Args:
        record: 审计记录字典。
        workspace_root: 工作区根目录。

    Returns:
        审计文件路径。
    """

    audit_dir = default_audit_dir(workspace_root=workspace_root)
    audit_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit_path = audit_dir / f"capability_audit_{timestamp}_{uuid4().hex[:8]}.json"
    audit_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit_path
