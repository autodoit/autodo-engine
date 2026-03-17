"""流程轨迹日志工具。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def append_flow_trace_event(
    workspace_root: str | Path,
    event: dict[str, Any],
) -> Path:
    """追加一条流程轨迹事件。

    Args:
        workspace_root: 工作区根目录。
        event: 事件内容。

    Returns:
        轨迹日志文件路径。

    Examples:
        >>> append_flow_trace_event(".", {"event_type": "demo"})
        PosixPath('logs/run/opencode-flow-trace-YYYY-MM-DD.jsonl')
    """

    root = Path(workspace_root).expanduser().resolve()
    now = datetime.now()
    log_dir = root / "logs" / "run"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"opencode-flow-trace-{now.strftime('%Y-%m-%d')}.jsonl"

    record = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        **event,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\\n")
    return log_path
