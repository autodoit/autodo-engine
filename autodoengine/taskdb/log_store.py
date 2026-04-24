"""运行日志存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files


def _get_db_path() -> str:
    return str(get_runtime_store_files()["log_db"])


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path())
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS log_events (
            event_uid TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            level TEXT,
            handler_kind TEXT,
            handler_name TEXT,
            model_name TEXT,
            skill_names_json TEXT,
            agent_names_json TEXT,
            read_files_json TEXT,
            script_path TEXT,
            third_party_tool TEXT,
            reasoning_summary TEXT,
            conversation_excerpt TEXT,
            payload_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _append(event_type: str, payload: dict[str, object], level: str) -> None:
    record = {
        "event_uid": f"event-{uuid4().hex[:12]}",
        "event_type": event_type,
        "level": level,
        "payload": payload,
        "created_at": now_iso(),
    }
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO log_events (
                event_uid, event_type, level, handler_kind, handler_name, model_name,
                skill_names_json, agent_names_json, read_files_json, script_path,
                third_party_tool, reasoning_summary, conversation_excerpt, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record["event_uid"]),
                str(record["event_type"]),
                str(record["level"]),
                "",
                "",
                "",
                "[]",
                "[]",
                "[]",
                "",
                "",
                "",
                "",
                json.dumps(payload, ensure_ascii=False),
                str(record["created_at"]),
            ),
        )


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

    with _connect() as connection:
        db_rows = connection.execute(
            "SELECT event_uid, event_type, level, payload_json, created_at FROM log_events ORDER BY created_at"
        ).fetchall()

    rows: list[dict[str, object]] = []
    for db_row in db_rows:
        payload_text = str(db_row["payload_json"] or "{}")
        try:
            payload = json.loads(payload_text)
        except Exception:
            payload = {}
        item: dict[str, object] = {
            "event_uid": str(db_row["event_uid"]),
            "event_type": str(db_row["event_type"]),
            "level": str(db_row["level"] or "info"),
            "payload": payload,
            "created_at": str(db_row["created_at"] or ""),
        }
        if task_uid is None or (isinstance(payload, dict) and payload.get("task_uid") == task_uid):
            rows.append(item)
    return rows
