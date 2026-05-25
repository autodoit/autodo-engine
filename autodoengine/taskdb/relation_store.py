"""任务关系存储（SQLite）。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from uuid import uuid4

from autodoengine.core.enums import RelationType
from autodoengine.utils.time_utils import now_iso
from .storage_paths import get_runtime_store_files


def _now_iso() -> str:
    return now_iso()


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
        CREATE TABLE IF NOT EXISTS "任务关系" (
            uid_关系 TEXT PRIMARY KEY,
            "uid_父任务" TEXT NOT NULL,
            "uid_子任务" TEXT NOT NULL,
            "关系类型" TEXT NOT NULL,
            "创建时间" TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _load_relations() -> list[dict[str, str]]:
    with closing(_connect()) as connection, connection:
        rows = connection.execute('SELECT * FROM "任务关系" ORDER BY "创建时间"').fetchall()
    result: list[dict[str, str]] = []
    for row in rows:
        payload = dict(row)
        raw_relation_type = str(payload.get("关系类型") or payload.get("relation_type") or "")
        try:
            relation_type = RelationType.normalize(raw_relation_type)
            relation_code = relation_type.value
            relation_label = relation_type.db_value
        except Exception:
            relation_code = raw_relation_type
            relation_label = raw_relation_type
        result.append(
            {
                "uid_关系": str(payload.get("uid_关系") or payload.get("relation_uid") or ""),
                "relation_uid": str(payload.get("uid_关系") or payload.get("relation_uid") or ""),
                "uid_父任务": str(payload.get("uid_父任务") or payload.get("父任务UID") or payload.get("parent_task_uid") or ""),
                "parent_task_uid": str(payload.get("uid_父任务") or payload.get("父任务UID") or payload.get("parent_task_uid") or ""),
                "uid_子任务": str(payload.get("uid_子任务") or payload.get("子任务UID") or payload.get("child_task_uid") or ""),
                "child_task_uid": str(payload.get("uid_子任务") or payload.get("子任务UID") or payload.get("child_task_uid") or ""),
                "关系类型": relation_label,
                "relation_type": relation_code,
                "created_at": str(payload.get("创建时间") or payload.get("created_at") or ""),
            }
        )
    return result


def create_task_relation(parent_task_uid: str, child_task_uid: str, relation_type: str) -> None:
    """创建父子任务关系。"""

    normalized_relation_type = RelationType.normalize(relation_type)
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO "任务关系" (
                uid_关系, "uid_父任务", "uid_子任务", "关系类型", "创建时间"
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"rel-{uuid4().hex[:12]}",
                parent_task_uid,
                child_task_uid,
                normalized_relation_type.db_value,
                _now_iso(),
            ),
        )


def list_children(parent_task_uid: str) -> list[dict[str, str]]:
    """列出子任务。"""

    return [item for item in _load_relations() if item["uid_父任务"] == parent_task_uid]


def list_parents(child_task_uid: str) -> list[dict[str, str]]:
    """列出父任务。"""

    return [item for item in _load_relations() if item["uid_子任务"] == child_task_uid]


def find_resume_candidates(parent_task_uid: str) -> list[dict[str, str]]:
    """查找可用于恢复父任务的子任务关系。"""

    from autodoengine.taskdb import task_store

    candidates: list[dict[str, str]] = []
    for relation in list_children(parent_task_uid):
        child = task_store.get_task(relation["uid_子任务"])
        if child.get("status") in {"completed", "cancelled"}:
            candidates.append(relation)
    return candidates

