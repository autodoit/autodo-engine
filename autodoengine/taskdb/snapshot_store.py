"""任务快照存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files


def _get_db_path() -> str:
    return str(get_runtime_store_files()["tasks_db"])

def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path())
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS aoe_task_snapshots (
            snapshot_uid TEXT PRIMARY KEY,
            task_uid TEXT NOT NULL,
            snapshot_type TEXT NOT NULL,
            snapshot_payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _load() -> list[dict[str, object]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM aoe_task_snapshots ORDER BY created_at").fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        payload_text = str(row["snapshot_payload"] or "{}")
        try:
            snapshot_payload = json.loads(payload_text)
        except Exception:
            snapshot_payload = {}
        result.append(
            {
                "snapshot_uid": str(row["snapshot_uid"]),
                "task_uid": str(row["task_uid"]),
                "snapshot_type": str(row["snapshot_type"]),
                "snapshot_payload": snapshot_payload,
                "created_at": str(row["created_at"]),
            }
        )
    return result


def create_snapshot(task_uid: str, snapshot_type: str, snapshot_payload: dict[str, object]) -> str:
    """创建任务快照。"""

    snapshot_uid = f"snapshot-{uuid4().hex[:12]}"
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO aoe_task_snapshots (
                snapshot_uid, task_uid, snapshot_type, snapshot_payload, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                snapshot_uid,
                task_uid,
                snapshot_type,
                json.dumps(snapshot_payload, ensure_ascii=False),
                now_iso(),
            ),
        )
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
