"""运行日志存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
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
        CREATE TABLE IF NOT EXISTS "运行事件" (
            uid_事件 TEXT PRIMARY KEY,
            "事件类型" TEXT NOT NULL,
            "级别" TEXT,
            "处理器类型" TEXT,
            "处理器名称" TEXT,
            "模型名称" TEXT,
            "技能列表JSON" TEXT,
            "智能体列表JSON" TEXT,
            "读取文件列表JSON" TEXT,
            "脚本路径" TEXT,
            "第三方工具" TEXT,
            "推理摘要" TEXT,
            "对话摘录" TEXT,
            "载荷JSON" TEXT,
            "创建时间" TEXT NOT NULL
        )
        """
    )
    for column_name, column_def in {
        "级别": "TEXT",
        "处理器类型": "TEXT",
        "处理器名称": "TEXT",
        "模型名称": "TEXT",
        "技能列表JSON": "TEXT",
        "智能体列表JSON": "TEXT",
        "读取文件列表JSON": "TEXT",
        "脚本路径": "TEXT",
        "第三方工具": "TEXT",
        "推理摘要": "TEXT",
        "对话摘录": "TEXT",
        "载荷JSON": "TEXT",
        "创建时间": "TEXT NOT NULL DEFAULT ''",
    }.items():
        _ensure_column(connection, "运行事件", column_name, column_def)
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    existing = {str(row[1]) for row in rows if len(row) > 1}
    if column_name in existing:
        return
    connection.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_def}')


def _append(event_type: str, payload: dict[str, object], level: str) -> None:
    record = {
        "uid_事件": f"event-{uuid4().hex[:12]}",
        "event_type": event_type,
        "level": level,
        "payload": payload,
        "created_at": now_iso(),
    }
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO "运行事件" (
                uid_事件, "事件类型", "级别", "处理器类型", "处理器名称", "模型名称",
                "技能列表JSON", "智能体列表JSON", "读取文件列表JSON", "脚本路径",
                "第三方工具", "推理摘要", "对话摘录", "载荷JSON", "创建时间"
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record["uid_事件"]),
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

    with closing(_connect()) as connection, connection:
        db_rows = connection.execute(
            'SELECT uid_事件, "事件类型", "级别", "载荷JSON", "创建时间" FROM "运行事件" ORDER BY "创建时间"'
        ).fetchall()

    rows: list[dict[str, object]] = []
    for db_row in db_rows:
        payload_text = str(db_row["载荷JSON"] or "{}")
        try:
            payload = json.loads(payload_text)
        except Exception:
            payload = {}
        item: dict[str, object] = {
            "uid_事件": str(db_row["uid_事件"]),
            "event_uid": str(db_row["uid_事件"]),
            "event_type": str(db_row["事件类型"]),
            "level": str(db_row["级别"] or "info"),
            "payload": payload,
            "created_at": str(db_row["创建时间"] or ""),
        }
        if task_uid is None or (isinstance(payload, dict) and payload.get("task_uid") == task_uid):
            rows.append(item)
    return rows
