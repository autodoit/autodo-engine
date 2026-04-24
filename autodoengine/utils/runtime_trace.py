"""流程轨迹日志工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autodoengine.utils.time_utils import now_compact, now_iso


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
    log_dir = root / "logs" / "run"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"opencode-flow-trace-{now_compact(fmt='%Y-%m-%d')}.jsonl"

    record = {
        "timestamp": now_iso(timespec="seconds"),
        **event,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\\n")
    return log_path
