"""任务关系存储（SQLite）。"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

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
        CREATE TABLE IF NOT EXISTS aoe_task_relations (
            relation_uid TEXT PRIMARY KEY,
            parent_task_uid TEXT NOT NULL,
            child_task_uid TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _load_relations() -> list[dict[str, str]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM aoe_task_relations ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def create_task_relation(parent_task_uid: str, child_task_uid: str, relation_type: str) -> None:
    """创建父子任务关系。"""

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO aoe_task_relations (
                relation_uid, parent_task_uid, child_task_uid, relation_type, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"rel-{uuid4().hex[:12]}",
                parent_task_uid,
                child_task_uid,
                relation_type,
                _now_iso(),
            ),
        )


def list_children(parent_task_uid: str) -> list[dict[str, str]]:
    """列出子任务。"""

    return [item for item in _load_relations() if item["parent_task_uid"] == parent_task_uid]


def list_parents(child_task_uid: str) -> list[dict[str, str]]:
    """列出父任务。"""

    return [item for item in _load_relations() if item["child_task_uid"] == child_task_uid]


def find_resume_candidates(parent_task_uid: str) -> list[dict[str, str]]:
    """查找可用于恢复父任务的子任务关系。"""

    from autodoengine.taskdb import task_store

    candidates: list[dict[str, str]] = []
    for relation in list_children(parent_task_uid):
        child = task_store.get_task(relation["child_task_uid"])
        if child.get("status") in {"completed", "cancelled"}:
            candidates.append(relation)
    return candidates

