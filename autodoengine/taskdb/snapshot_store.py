"""任务快照存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
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
        CREATE TABLE IF NOT EXISTS "任务快照" (
            uid_快照 TEXT PRIMARY KEY,
            uid_任务 TEXT NOT NULL,
            "快照类型" TEXT NOT NULL,
            "快照载荷JSON" TEXT NOT NULL,
            "创建时间" TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _load() -> list[dict[str, object]]:
    with closing(_connect()) as connection, connection:
        rows = connection.execute('SELECT * FROM "任务快照" ORDER BY "创建时间"').fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        payload_text = str(row["快照载荷JSON"] or "{}")
        try:
            snapshot_payload = json.loads(payload_text)
        except Exception:
            snapshot_payload = {}
        result.append(
            {
                "uid_快照": str(row["uid_快照"] if "uid_快照" in row.keys() else row["snapshot_uid"]),
                "snapshot_uid": str(row["uid_快照"] if "uid_快照" in row.keys() else row["snapshot_uid"]),
                "uid_任务": str(row["uid_任务"] if "uid_任务" in row.keys() else row["task_uid"]),
                "task_uid": str(row["uid_任务"] if "uid_任务" in row.keys() else row["task_uid"]),
                "snapshot_type": str(row["快照类型"]),
                "snapshot_payload": snapshot_payload,
                "created_at": str(row["创建时间"]),
            }
        )
    return result


def create_snapshot(task_uid: str, snapshot_type: str, snapshot_payload: dict[str, object]) -> str:
    """创建任务快照。"""

    snapshot_uid = f"snapshot-{uuid4().hex[:12]}"
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO "任务快照" (
                uid_快照, uid_任务, "快照类型", "快照载荷JSON", "创建时间"
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
        if row.get("uid_快照", row.get("snapshot_uid")) == snapshot_uid:
            return row
    raise KeyError(f"快照不存在：{snapshot_uid}")


def list_task_snapshots(task_uid: str) -> list[dict[str, object]]:
    """列出任务快照。"""

    return [row for row in _load() if row["uid_任务"] == task_uid or row["task_uid"] == task_uid]
