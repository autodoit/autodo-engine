"""任务主表读写（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4
from typing import Any

from autodoengine.core.enums import TaskStatus
from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files


def _now_iso() -> str:
    return now_iso()


def _get_db_path() -> str:
    return str(get_runtime_store_files()["tasks_db"])

def _connect() -> sqlite3.Connection:
    db_path = _get_db_path()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS task_runs (
            task_uid TEXT PRIMARY KEY,
            workflow_uid TEXT NOT NULL DEFAULT '',
            node_code TEXT NOT NULL DEFAULT '',
            gate_code TEXT NOT NULL DEFAULT '',
            decision TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            workspace_root TEXT NOT NULL DEFAULT '',
            input_summary_json TEXT NOT NULL DEFAULT '{}',
            output_summary_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL DEFAULT '',
            ended_at TEXT NOT NULL DEFAULT '',
            operator_name TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            goal_text TEXT NOT NULL DEFAULT '',
            current_node_uid TEXT NOT NULL DEFAULT '',
            current_affair_uid TEXT,
            parent_task_uid TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retry INTEGER NOT NULL DEFAULT 2,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    for column_name, column_def in {
        "task_status": "TEXT NOT NULL DEFAULT ''",
        "title": "TEXT NOT NULL DEFAULT ''",
        "goal_text": "TEXT NOT NULL DEFAULT ''",
        "current_node_uid": "TEXT NOT NULL DEFAULT ''",
        "current_affair_uid": "TEXT",
        "parent_task_uid": "TEXT",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "max_retry": "INTEGER NOT NULL DEFAULT 2",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    }.items():
        _ensure_column(connection, "task_runs", column_name, column_def)
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {str(row[1]) for row in rows if len(row) > 1}
    if column_name in existing:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    raw_metadata = payload.get("metadata_json") or "{}"
    try:
        metadata = json.loads(raw_metadata)
    except Exception:
        metadata = {}
    return {
        "task_uid": str(payload.get("task_uid") or ""),
        "title": str(payload.get("title") or ""),
        "goal_text": str(payload.get("goal_text") or ""),
        "status": str(payload.get("status") or TaskStatus.READY.value),
        "current_node_uid": str(payload.get("current_node_uid") or payload.get("node_code") or ""),
        "current_affair_uid": payload.get("current_affair_uid"),
        "parent_task_uid": payload.get("parent_task_uid"),
        "retry_count": int(payload.get("retry_count") or 0),
        "max_retry": int(payload.get("max_retry") or 2),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": str(payload.get("created_at") or payload.get("started_at") or ""),
        "updated_at": str(payload.get("updated_at") or payload.get("ended_at") or ""),
    }


def create_task(*, title: str, goal_text: str, current_node_uid: str, parent_task_uid: str | None = None) -> dict[str, Any]:
    """创建任务。"""

    task_uid = f"task-{uuid4().hex[:12]}"
    now = _now_iso()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO task_runs (
                task_uid, workflow_uid, node_code, gate_code, decision, status, workspace_root,
                input_summary_json, output_summary_json, started_at, ended_at, operator_name, note,
                title, goal_text, current_node_uid, current_affair_uid, parent_task_uid,
                retry_count, max_retry, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_uid,
                f"wf-{task_uid}",
                current_node_uid,
                "",
                "",
                TaskStatus.READY.value,
                "",
                "{}",
                "{}",
                now,
                now,
                "",
                "",
                title,
                goal_text,
                current_node_uid,
                None,
                parent_task_uid,
                0,
                2,
                "{}",
                now,
                now,
            ),
        )
        row = connection.execute("SELECT * FROM task_runs WHERE task_uid=?", (task_uid,)).fetchone()
    if row is None:
        raise KeyError(f"任务创建失败：{task_uid}")
    return _row_to_task(row)


def get_task(task_uid: str) -> dict[str, Any]:
    """读取单个任务。"""

    with _connect() as connection:
        row = connection.execute("SELECT * FROM task_runs WHERE task_uid=?", (task_uid,)).fetchone()
    if row is not None:
        return _row_to_task(row)
    raise KeyError(f"任务不存在：{task_uid}")


def list_tasks(*, status: TaskStatus | None = None) -> list[dict[str, Any]]:
    """按状态列出任务。"""

    with _connect() as connection:
        if status is None:
            rows = connection.execute("SELECT * FROM task_runs ORDER BY created_at").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM task_runs WHERE status=? ORDER BY created_at", (status.value,)
            ).fetchall()
    return [_row_to_task(row) for row in rows]


def update_task_status(task_uid: str, status: TaskStatus) -> None:
    """更新任务状态。"""

    now = _now_iso()
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE task_runs SET status=?, updated_at=?, task_status=?, ended_at=? WHERE task_uid=?",
            (status.value, now, status.value, now, task_uid),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"任务不存在：{task_uid}")


def update_task_cursor(task_uid: str, *, current_node_uid: str, current_affair_uid: str | None) -> None:
    """更新任务当前位置。"""

    now = _now_iso()
    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE task_runs
            SET current_node_uid=?, current_affair_uid=?, node_code=?, updated_at=?
            WHERE task_uid=?
            """,
            (current_node_uid, current_affair_uid, current_node_uid, now, task_uid),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"任务不存在：{task_uid}")


def mark_task_completed(task_uid: str) -> None:
    """将任务标记为已完成。"""

    update_task_status(task_uid, TaskStatus.COMPLETED)


def mark_task_failed(task_uid: str) -> None:
    """将任务标记为失败。"""

    update_task_status(task_uid, TaskStatus.FAILED)


def mark_task_cancelled(task_uid: str) -> None:
    """将任务标记为已取消。"""

    update_task_status(task_uid, TaskStatus.CANCELLED)


def bump_retry_count(task_uid: str) -> None:
    """递增任务重试计数。"""

    now = _now_iso()
    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE task_runs
            SET retry_count = COALESCE(retry_count, 0) + 1, updated_at=?
            WHERE task_uid=?
            """,
            (now, task_uid),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"任务不存在：{task_uid}")


def update_task_metadata(task_uid: str, metadata: dict[str, Any], *, merge: bool = True) -> None:
    """更新任务元数据。"""

    with _connect() as connection:
        row = connection.execute("SELECT metadata_json FROM task_runs WHERE task_uid=?", (task_uid,)).fetchone()
        if row is None:
            raise KeyError(f"任务不存在：{task_uid}")
        current: dict[str, Any] = {}
        raw_metadata = row[0] if len(row) > 0 else "{}"
        try:
            parsed = json.loads(raw_metadata or "{}")
            if isinstance(parsed, dict):
                current = parsed
        except Exception:
            current = {}

        next_metadata = dict(metadata)
        if merge:
            current.update(next_metadata)
            next_metadata = current

        connection.execute(
            "UPDATE task_runs SET metadata_json=?, updated_at=? WHERE task_uid=?",
            (json.dumps(next_metadata, ensure_ascii=False), _now_iso(), task_uid),
        )
        return


def list_tasks_by_parent(parent_task_uid: str) -> list[dict[str, Any]]:
    """按父任务 UID 列出子任务。"""

    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM task_runs WHERE parent_task_uid=? ORDER BY created_at",
            (parent_task_uid,),
        ).fetchall()
    return [_row_to_task(row) for row in rows]

