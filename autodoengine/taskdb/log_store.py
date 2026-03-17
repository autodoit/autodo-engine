"""运行日志存储。"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from uuid import uuid4

from .storage_paths import resolve_store_file


def _append(event_type: str, payload: dict[str, object], level: str) -> None:
    file_path = resolve_store_file(kind="logdb", name="runtime_events.jsonl")
    record = {
        "event_uid": f"event-{uuid4().hex[:12]}",
        "event_type": event_type,
        "level": level,
        "payload": payload,
        "created_at": datetime.now(UTC).isoformat(),
    }
    with file_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_runtime_event(event_type: str, payload: dict[str, object]) -> None:
    """写入运行事件。"""

    _append(event_type, payload, "info")


def append_error_event(event_type: str, payload: dict[str, object]) -> None:
    """写入错误事件。"""

    _append(event_type, payload, "error")


def append_blocked_event(event_type: str, payload: dict[str, object]) -> None:
    """写入阻断事件。"""

    _append(event_type, payload, "blocked")


def list_runtime_events(task_uid: str | None = None) -> list[dict[str, object]]:
    """读取运行事件。"""

    file_path = resolve_store_file(kind="logdb", name="runtime_events.jsonl")
    if not file_path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if task_uid is None:
            rows.append(item)
            continue
        payload = item.get("payload") or {}
        if payload.get("task_uid") == task_uid:
            rows.append(item)
    return rows
