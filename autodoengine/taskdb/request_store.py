"""事务请求存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any
from uuid import uuid4

from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files

请求状态_待调度 = "待调度"
请求状态_执行中 = "执行中"
请求状态_已完成 = "已完成"
请求状态_已阻断 = "已阻断"
请求状态_已失败 = "已失败"
请求状态_已取消 = "已取消"


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
        CREATE TABLE IF NOT EXISTS "事务请求" (
            uid_请求 TEXT PRIMARY KEY,
            uid_任务 TEXT,
            "请求类型" TEXT NOT NULL,
            "来源对象类型" TEXT NOT NULL DEFAULT '',
            "来源对象UID" TEXT NOT NULL DEFAULT '',
            "节点编码" TEXT NOT NULL DEFAULT '',
            "uid_目标事务" TEXT NOT NULL,
            "配置路径" TEXT NOT NULL DEFAULT '',
            "请求状态" TEXT NOT NULL,
            "优先得分" REAL NOT NULL DEFAULT 0,
            "来源" TEXT NOT NULL DEFAULT '',
            "请求契约JSON" TEXT NOT NULL DEFAULT '{}',
            "载荷JSON" TEXT NOT NULL DEFAULT '{}',
            "结果JSON" TEXT NOT NULL DEFAULT '{}',
            "元数据JSON" TEXT NOT NULL DEFAULT '{}',
            "创建时间" TEXT NOT NULL,
            "更新时间" TEXT NOT NULL
        )
        """
    )
    _ensure_column(connection, "事务请求", "uid_任务", "TEXT")
    _ensure_column(connection, "事务请求", "请求类型", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "来源对象类型", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "来源对象UID", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "节点编码", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "uid_目标事务", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "配置路径", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "请求状态", "TEXT NOT NULL DEFAULT '待调度'")
    _ensure_column(connection, "事务请求", "优先得分", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "事务请求", "来源", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "请求契约JSON", "TEXT NOT NULL DEFAULT '{}' ")
    _ensure_column(connection, "事务请求", "载荷JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "事务请求", "结果JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "事务请求", "元数据JSON", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(connection, "事务请求", "创建时间", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "事务请求", "更新时间", "TEXT NOT NULL DEFAULT ''")
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    existing = {str(row[1]) for row in rows}
    if column_name in existing:
        return
    connection.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_def}')


def _row_to_request(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    try:
        body = json.loads(str(payload.get("载荷JSON") or "{}"))
    except Exception:
        body = {}
    try:
        result = json.loads(str(payload.get("结果JSON") or "{}"))
    except Exception:
        result = {}
    try:
        metadata = json.loads(str(payload.get("元数据JSON") or "{}"))
    except Exception:
        metadata = {}
    try:
        request_contract = json.loads(str(payload.get("请求契约JSON") or "{}"))
    except Exception:
        request_contract = {}
    return {
        "uid_请求": str(payload.get("uid_请求") or ""),
        "request_uid": str(payload.get("uid_请求") or ""),
        "uid_任务": str(payload.get("uid_任务") or ""),
        "task_uid": str(payload.get("uid_任务") or ""),
        "request_type": str(payload.get("请求类型") or ""),
        "source_object_type": str(payload.get("来源对象类型") or ""),
        "来源对象类型": str(payload.get("来源对象类型") or ""),
        "source_object_uid": str(payload.get("来源对象UID") or ""),
        "来源对象UID": str(payload.get("来源对象UID") or ""),
        "node_code": str(payload.get("节点编码") or ""),
        "节点编码": str(payload.get("节点编码") or ""),
        "target_affair_uid": str(payload.get("uid_目标事务") or ""),
        "config_path": str(payload.get("配置路径") or ""),
        "配置路径": str(payload.get("配置路径") or ""),
        "status": str(payload.get("请求状态") or 请求状态_待调度),
        "请求状态": str(payload.get("请求状态") or 请求状态_待调度),
        "priority_score": float(payload.get("优先得分") or 0),
        "source": str(payload.get("来源") or ""),
        "request_contract": request_contract if isinstance(request_contract, dict) else {},
        "请求契约": request_contract if isinstance(request_contract, dict) else {},
        "payload": body if isinstance(body, dict) else {},
        "result": result if isinstance(result, dict) else {},
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": str(payload.get("创建时间") or ""),
        "updated_at": str(payload.get("更新时间") or ""),
    }


def create_request(
    *,
    request_type: str,
    target_affair_uid: str,
    payload: dict[str, Any] | None = None,
    task_uid: str | None = None,
    source_object_type: str = "",
    source_object_uid: str = "",
    node_code: str = "",
    config_path: str = "",
    priority_score: float = 0.0,
    source: str = "任务系统",
    request_contract: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建事务请求。"""

    request_uid = f"request-{uuid4().hex[:12]}"
    now = now_iso()
    with closing(_connect()) as connection, connection:
        schema_rows = connection.execute('PRAGMA table_info("事务请求")').fetchall()
        column_specs = [
            {
                "name": str(row[1]),
                "type": str(row[2] or ""),
                "notnull": bool(row[3]),
                "default": row[4],
            }
            for row in schema_rows
            if len(row) >= 5
        ]
        column_values: dict[str, Any] = {
            "uid_请求": request_uid,
            "uid_任务": task_uid,
            "请求类型": request_type,
            "来源对象类型": source_object_type,
            "来源对象UID": source_object_uid,
            "节点编码": node_code,
            "uid_目标事务": target_affair_uid,
            "配置路径": config_path,
            "请求状态": 请求状态_待调度,
            "优先得分": float(priority_score),
            "来源": source,
            "请求契约JSON": json.dumps(request_contract or {}, ensure_ascii=False),
            "载荷JSON": json.dumps(payload or {}, ensure_ascii=False),
            "结果JSON": "{}",
            "元数据JSON": json.dumps(metadata or {}, ensure_ascii=False),
            "创建时间": now,
            "更新时间": now,
        }
        if "目标节点" in {item["name"] for item in column_specs}:
            column_values.setdefault("目标节点", node_code or target_affair_uid)

        for spec in column_specs:
            column_name = spec["name"]
            if column_name in column_values:
                continue
            if not spec["notnull"] or spec["default"] is not None:
                continue

            column_type = str(spec["type"] or "").upper()
            if column_name.endswith("JSON"):
                column_values[column_name] = "{}"
            elif "INT" in column_type:
                column_values[column_name] = 0
            elif any(token in column_type for token in ["REAL", "FLOA", "DOUB"]):
                column_values[column_name] = 0.0
            else:
                column_values[column_name] = ""

        ordered_columns = [spec["name"] for spec in column_specs if spec["name"] in column_values]
        placeholders = ", ".join(["?"] * len(ordered_columns))
        quoted_columns = ", ".join([f'"{name}"' for name in ordered_columns])
        connection.execute(
            f'INSERT INTO "事务请求" ({quoted_columns}) VALUES ({placeholders})',
            tuple(column_values[name] for name in ordered_columns),
        )
        row = connection.execute('SELECT * FROM "事务请求" WHERE uid_请求=?', (request_uid,)).fetchone()
        request_payload = dict(row) if row is not None else None
    if request_payload is None:
        raise KeyError(f"事务请求创建失败：{request_uid}")
    return _row_to_request(request_payload)


def get_request(request_uid: str) -> dict[str, Any]:
    """读取事务请求。"""

    with closing(_connect()) as connection, connection:
        row = connection.execute('SELECT * FROM "事务请求" WHERE uid_请求=?', (request_uid,)).fetchone()
        request_payload = dict(row) if row is not None else None
    if request_payload is None:
        raise KeyError(f"事务请求不存在：{request_uid}")
    return _row_to_request(request_payload)


def list_requests(*, status: str | None = None) -> list[dict[str, Any]]:
    """列出事务请求。"""

    with closing(_connect()) as connection, connection:
        if status is None:
            rows = connection.execute('SELECT * FROM "事务请求" ORDER BY "创建时间"').fetchall()
        else:
            rows = connection.execute(
                'SELECT * FROM "事务请求" WHERE "请求状态"=? ORDER BY "创建时间"',
                (status,),
            ).fetchall()
        payloads = [dict(row) for row in rows]
    return [_row_to_request(row) for row in payloads]


def list_task_requests(task_uid: str) -> list[dict[str, Any]]:
    """按任务列出事务请求。"""

    with closing(_connect()) as connection, connection:
        rows = connection.execute(
            'SELECT * FROM "事务请求" WHERE uid_任务=? ORDER BY "创建时间"',
            (task_uid,),
        ).fetchall()
        payloads = [dict(row) for row in rows]
    return [_row_to_request(row) for row in payloads]


def update_request_status(
    request_uid: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    merge_metadata: bool = True,
) -> None:
    """更新事务请求状态。"""

    current = get_request(request_uid)
    next_metadata = dict(metadata or {})
    if merge_metadata:
        merged = dict(current.get("metadata") or {})
        merged.update(next_metadata)
        next_metadata = merged

    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            'UPDATE "事务请求" SET "请求状态"=?, "结果JSON"=?, "元数据JSON"=?, "更新时间"=? WHERE uid_请求=?',
            (
                status,
                json.dumps(result or current.get("result") or {}, ensure_ascii=False),
                json.dumps(next_metadata, ensure_ascii=False),
                now_iso(),
                request_uid,
            ),
        )
        if cursor.rowcount:
            return
    raise KeyError(f"事务请求不存在：{request_uid}")


def mark_request_running(request_uid: str) -> None:
    """标记事务请求为执行中。"""

    update_request_status(request_uid, status=请求状态_执行中)


def mark_request_completed(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已完成。"""

    update_request_status(request_uid, status=请求状态_已完成, result=result)


def mark_request_blocked(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已阻断。"""

    update_request_status(request_uid, status=请求状态_已阻断, result=result)


def mark_request_failed(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已失败。"""

    update_request_status(request_uid, status=请求状态_已失败, result=result)


def mark_request_cancelled(request_uid: str, *, result: dict[str, Any] | None = None) -> None:
    """标记事务请求为已取消。"""

    update_request_status(request_uid, status=请求状态_已取消, result=result)