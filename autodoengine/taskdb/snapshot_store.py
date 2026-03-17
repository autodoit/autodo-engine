"""任务快照存储。"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from uuid import uuid4

from .storage_paths import resolve_store_file


def _load() -> list[dict[str, object]]:
    file_path = resolve_store_file(kind="taskdb", name="snapshots.json")
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


def _save(rows: list[dict[str, object]]) -> None:
    file_path = resolve_store_file(kind="taskdb", name="snapshots.json")
    file_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def create_snapshot(task_uid: str, snapshot_type: str, snapshot_payload: dict[str, object]) -> str:
    """创建任务快照。"""

    rows = _load()
    snapshot_uid = f"snapshot-{uuid4().hex[:12]}"
    rows.append(
        {
            "snapshot_uid": snapshot_uid,
            "task_uid": task_uid,
            "snapshot_type": snapshot_type,
            "snapshot_payload": snapshot_payload,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    _save(rows)
    return snapshot_uid


def get_snapshot(snapshot_uid: str) -> dict[str, object]:
    """读取快照。"""

    for row in _load():
        if row["snapshot_uid"] == snapshot_uid:
            return row
    raise KeyError(f"快照不存在：{snapshot_uid}")


def list_task_snapshots(task_uid: str) -> list[dict[str, object]]:
    """列出任务快照。"""

    return [row for row in _load() if row["task_uid"] == task_uid]
