"""决策部门配置存储（SQLite）。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files

默认部门UID = "dept-default"
默认人类成员UID = "member-human-default"
默认LLM成员UID = "member-llm-default"


def _get_db_path() -> str:
    return str(get_runtime_store_files()["decision_db"])


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path())
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "决策部门" (
            uid_部门 TEXT PRIMARY KEY,
            "部门名称" TEXT NOT NULL,
            "默认LLM供应商" TEXT NOT NULL,
            "默认LLM模型" TEXT NOT NULL,
            "默认决策模式" TEXT NOT NULL,
            "是否启用" INTEGER NOT NULL DEFAULT 1,
            "元数据JSON" TEXT NOT NULL DEFAULT '{}',
            "创建时间" TEXT NOT NULL,
            "更新时间" TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS "决策成员" (
            uid_成员 TEXT PRIMARY KEY,
            uid_部门 TEXT NOT NULL,
            "成员类型" TEXT NOT NULL,
            "成员名称" TEXT NOT NULL,
            "是否启用" INTEGER NOT NULL DEFAULT 1,
            "配置JSON" TEXT NOT NULL DEFAULT '{}',
            "创建时间" TEXT NOT NULL,
            "更新时间" TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _row_to_department(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    try:
        metadata = json.loads(str(payload.get("元数据JSON") or "{}"))
    except Exception:
        metadata = {}
    return {
        "uid_部门": str(payload.get("uid_部门") or ""),
        "department_uid": str(payload.get("uid_部门") or ""),
        "department_name": str(payload.get("部门名称") or ""),
        "llm_vendor": str(payload.get("默认LLM供应商") or ""),
        "llm_model": str(payload.get("默认LLM模型") or ""),
        "decision_mode": str(payload.get("默认决策模式") or "联合决策"),
        "enabled": bool(int(payload.get("是否启用") or 0)),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": str(payload.get("创建时间") or ""),
        "updated_at": str(payload.get("更新时间") or ""),
    }


def _row_to_member(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    try:
        config = json.loads(str(payload.get("配置JSON") or "{}"))
    except Exception:
        config = {}
    return {
        "uid_成员": str(payload.get("uid_成员") or ""),
        "member_uid": str(payload.get("uid_成员") or ""),
        "uid_部门": str(payload.get("uid_部门") or ""),
        "department_uid": str(payload.get("uid_部门") or ""),
        "member_type": str(payload.get("成员类型") or ""),
        "member_name": str(payload.get("成员名称") or ""),
        "enabled": bool(int(payload.get("是否启用") or 0)),
        "config": config if isinstance(config, dict) else {},
        "created_at": str(payload.get("创建时间") or ""),
        "updated_at": str(payload.get("更新时间") or ""),
    }


def ensure_default_department() -> dict[str, Any]:
    """确保默认决策部门存在。"""

    now = now_iso()
    with closing(_connect()) as connection, connection:
        row = connection.execute('SELECT * FROM "决策部门" WHERE uid_部门=?', (默认部门UID,)).fetchone()
        if row is None:
            connection.execute(
                'INSERT INTO "决策部门" (uid_部门, "部门名称", "默认LLM供应商", "默认LLM模型", "默认决策模式", "是否启用", "元数据JSON", "创建时间", "更新时间") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    默认部门UID,
                    "默认决策部门",
                    "阿里百炼",
                    "qwen-max",
                    "联合决策",
                    1,
                    json.dumps({"default_members": ["LLM", "人类"]}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.execute(
                'INSERT OR REPLACE INTO "决策成员" (uid_成员, uid_部门, "成员类型", "成员名称", "是否启用", "配置JSON", "创建时间", "更新时间") VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    默认人类成员UID,
                    默认部门UID,
                    "人类",
                    "默认人工审批成员",
                    1,
                    json.dumps({"role": "human_gate"}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.execute(
                'INSERT OR REPLACE INTO "决策成员" (uid_成员, uid_部门, "成员类型", "成员名称", "是否启用", "配置JSON", "创建时间", "更新时间") VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    默认LLM成员UID,
                    默认部门UID,
                    "LLM",
                    "默认阿里百炼成员",
                    1,
                    json.dumps({"vendor": "阿里百炼", "model": "qwen-max"}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = connection.execute('SELECT * FROM "决策部门" WHERE uid_部门=?', (默认部门UID,)).fetchone()
        department_payload = dict(row) if row is not None else None
    if department_payload is None:
        raise KeyError("默认决策部门创建失败")
    return _row_to_department(department_payload)


def get_department(department_uid: str = 默认部门UID) -> dict[str, Any]:
    """读取决策部门。"""

    ensure_default_department()
    with closing(_connect()) as connection:
        row = connection.execute('SELECT * FROM "决策部门" WHERE uid_部门=?', (department_uid,)).fetchone()
        department_payload = dict(row) if row is not None else None
    if department_payload is None:
        raise KeyError(f"决策部门不存在：{department_uid}")
    return _row_to_department(department_payload)


def list_departments() -> list[dict[str, Any]]:
    """列出决策部门。"""

    ensure_default_department()
    with closing(_connect()) as connection:
        rows = connection.execute('SELECT * FROM "决策部门" ORDER BY "创建时间"').fetchall()
        payloads = [dict(row) for row in rows]
    return [_row_to_department(row) for row in payloads]


def list_department_members(department_uid: str = 默认部门UID) -> list[dict[str, Any]]:
    """列出决策部门成员。"""

    ensure_default_department()
    with closing(_connect()) as connection:
        rows = connection.execute(
            'SELECT * FROM "决策成员" WHERE uid_部门=? ORDER BY "创建时间"',
            (department_uid,),
        ).fetchall()
        payloads = [dict(row) for row in rows]
    return [_row_to_member(row) for row in payloads]